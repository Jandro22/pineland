//! Live rsmpi execution for the canonical distributed particle filter.
//!
//! The module is feature-gated because an MPI implementation is a system
//! dependency.  It is intended for the Linux/SLURM build; ordinary Windows
//! and CI builds use [`crate::DistributedParticleFilter`] and do not need an
//! MPI library installed.

use crate::distribution::DeterministicPartition;
use crate::migration::{
    decode_parent_frame, encode_parent_frame, materialize_children_for_range,
    pack_local_parent_states,
};
use crate::mpi::canonical_boundary;
use mpi::datatype::{Partition, PartitionMut};
use mpi::traits::*;
use mpi::Count;
use pineland_core::checkpoint::CheckpointStore;
use pineland_core::config::SimulationConfig;
use pineland_core::json;
use pineland_core::rng::{seed_from_namespace, PyRandomCompat};
use pineland_core::sha256;
use pineland_inference::parallel::for_each_mut;
use pineland_inference::{
    observation_log_likelihood, FilterError, FilterUpdate, McseMonitor, NativeParticleFilter,
    Observation,
};
use pineland_model::SimulationEngine;
use std::fs;
use std::path::{Path, PathBuf};

/// The rank-local result returned after every rank has published its final
/// checkpoint shard.  `log_weights` is in global logical order on rank zero;
/// other ranks retain their local interval.
#[derive(Clone, Debug, PartialEq)]
pub struct MpiFilterResult {
    pub rank: usize,
    pub world_size: usize,
    pub particle_start: usize,
    pub particle_end: usize,
    pub particles: Vec<SimulationEngine>,
    pub log_weights: Vec<f64>,
    pub filter_rng: PyRandomCompat,
    pub boundary: u64,
    pub mcse: McseMonitor,
    pub updates: Vec<FilterUpdate>,
    pub checkpoint: PathBuf,
}

struct InitialFilterState {
    particles: Vec<SimulationEngine>,
    log_weights: Vec<f64>,
    filter_rng: PyRandomCompat,
    boundary: u64,
    ess_fraction: f64,
    mcse: McseMonitor,
}

/// Run a distributed filter under `MPI_COMM_WORLD` and publish one checkpoint
/// shard per rank.  All scientific decisions are made from buffers gathered
/// in canonical logical-particle order; MPI rank and message arrival order are
/// never used as a seed or a resampling tie-breaker.
pub fn run_filter_to_directory(
    config: SimulationConfig,
    particle_count: usize,
    threads: usize,
    boundaries: &[(f64, Option<Observation>)],
    output: impl AsRef<Path>,
    binary_hash: impl Into<String>,
) -> Result<MpiFilterResult, String> {
    if particle_count == 0 {
        return Err("MPI filter particle count must be positive".to_string());
    }
    config.validate().map_err(|error| error.to_string())?;
    let Some((universe, _provided)) = mpi::initialize_with_threading(mpi::Threading::Funneled)
    else {
        return Err("MPI is already initialized or unavailable".to_string());
    };
    let world = universe.world();
    let configuration_hash = config.canonical_hash();
    let result = run_on_world(&world, config, particle_count, threads, boundaries, None)?;
    let checkpoint = publish_checkpoint(
        &world,
        output.as_ref(),
        result.boundary,
        &result.particles,
        configuration_hash,
        binary_hash.into(),
    )?;
    world.barrier();
    Ok(MpiFilterResult {
        checkpoint,
        ..result
    })
}

/// Resume a distributed filter from a completed checkpoint directory.  The
/// checkpoint is read and validated on every rank, then each rank keeps only
/// its new canonical interval.  Reading the complete state here is deliberate:
/// it permits a restart with a different MPI world size while retaining the
/// same logical particle order and scientific filter state.
pub fn resume_filter_to_directory(
    config: SimulationConfig,
    checkpoint: impl AsRef<Path>,
    threads: usize,
    boundaries: &[(f64, Option<Observation>)],
    output: impl AsRef<Path>,
    binary_hash: impl Into<String>,
) -> Result<MpiFilterResult, String> {
    let checkpoint = checkpoint.as_ref().to_path_buf();
    let particle_count = CheckpointStore::read_directory(&checkpoint)
        .map_err(|error| error.to_string())?
        .1
        .len();
    if particle_count == 0 {
        return Err("MPI filter checkpoint contains no particles".to_string());
    }
    config.validate().map_err(|error| error.to_string())?;
    let Some((universe, _provided)) = mpi::initialize_with_threading(mpi::Threading::Funneled)
    else {
        return Err("MPI is already initialized or unavailable".to_string());
    };
    let world = universe.world();
    let (manifest, states) =
        CheckpointStore::read_directory(&checkpoint).map_err(|error| error.to_string())?;
    if manifest.configuration_hash != config.canonical_hash() {
        return Err(format!(
            "checkpoint configuration hash {} does not match supplied configuration {}",
            manifest.configuration_hash,
            config.canonical_hash()
        ));
    }
    let expected_count = states.len();
    if states
        .iter()
        .enumerate()
        .any(|(index, state)| state.logical_id != index as u64)
    {
        return Err(
            "MPI filter checkpoint particles are not in canonical logical order".to_string(),
        );
    }
    let topology = states
        .first()
        .map(|state| topology_for_particle(state, &config))
        .ok_or_else(|| "MPI filter checkpoint contains no particles".to_string())?;
    let engines = states
        .into_iter()
        .map(|state| {
            SimulationEngine::from_particle(config.clone(), topology.clone(), state)
                .map_err(|error| error.to_string())
        })
        .collect::<Result<Vec<_>, _>>()?;
    let continuation_path = checkpoint
        .parent()
        .ok_or_else(|| "MPI filter checkpoint has no parent directory".to_string())?
        .join("filter_state.json");
    let continuation_text = fs::read_to_string(&continuation_path).map_err(|error| {
        format!(
            "cannot read MPI filter continuation {}: {error}",
            continuation_path.display()
        )
    })?;
    let continuation = json::parse(&continuation_text).map_err(|error| error.to_string())?;
    let filter = NativeParticleFilter::from_continuation(config.clone(), engines, &continuation)
        .map_err(|error| error.to_string())?;
    if filter.particles.len() != expected_count || filter.particles.len() != particle_count {
        return Err("MPI filter continuation/checkpoint particle count mismatch".to_string());
    }
    if filter.guided.is_some() {
        return Err(
            "MPI filter restart does not support guided proposals in this release".to_string(),
        );
    }
    let world_size = usize::try_from(world.size())
        .map_err(|_| "MPI world size does not fit usize".to_string())?;
    let rank =
        usize::try_from(world.rank()).map_err(|_| "MPI rank does not fit usize".to_string())?;
    let partition = DeterministicPartition::new(particle_count, world_size);
    let range = partition.rank_particles(rank);
    let initial = InitialFilterState {
        particles: filter.particles[range.clone()].to_vec(),
        log_weights: filter.log_weights[range].to_vec(),
        filter_rng: filter.rng,
        boundary: filter.boundary,
        ess_fraction: filter.ess_fraction,
        mcse: filter.mcse,
    };
    let configuration_hash = config.canonical_hash();
    let result = run_on_world(
        &world,
        config,
        particle_count,
        threads,
        boundaries,
        Some(initial),
    )?;
    let checkpoint = publish_checkpoint(
        &world,
        output.as_ref(),
        result.boundary,
        &result.particles,
        configuration_hash,
        binary_hash.into(),
    )?;
    world.barrier();
    Ok(MpiFilterResult {
        checkpoint,
        ..result
    })
}

fn run_on_world<C: Communicator + CommunicatorCollectives>(
    world: &C,
    config: SimulationConfig,
    particle_count: usize,
    threads: usize,
    boundaries: &[(f64, Option<Observation>)],
    initial: Option<InitialFilterState>,
) -> Result<MpiFilterResult, String> {
    let world_size = usize::try_from(world.size())
        .map_err(|_| "MPI world size does not fit usize".to_string())?;
    let rank =
        usize::try_from(world.rank()).map_err(|_| "MPI rank does not fit usize".to_string())?;
    if world_size == 0 || rank >= world_size {
        return Err("MPI communicator has an invalid rank topology".to_string());
    }
    let partition = DeterministicPartition::new(particle_count, world_size);
    let range = partition.rank_particles(rank);
    let particle_start = range.start;
    let particle_end = range.end;
    let topology = pineland_core::topology::StaticTopology::synthetic(
        config.locality_count,
        config.physical.town_microzones.max(1).min(8),
    );

    let (
        mut particles,
        mut local_weights,
        mut filter_rng,
        mut boundary_index,
        ess_fraction,
        mut mcse,
    ) = if let Some(initial) = initial {
        if initial.particles.len() != particle_end - particle_start
            || initial.log_weights.len() != particle_end - particle_start
        {
            return Err("MPI restart state does not match its canonical rank range".to_string());
        }
        (
            initial.particles,
            initial.log_weights,
            initial.filter_rng,
            initial.boundary,
            initial.ess_fraction,
            initial.mcse,
        )
    } else {
        let mut particles = Vec::with_capacity(particle_end - particle_start);
        for index in particle_start..particle_end {
            let mut particle_config = config.clone();
            particle_config.seed = seed_from_namespace(
                config.seed,
                &config.random_stream_namespace,
                &format!("particle-{index}"),
            );
            let mut engine =
                SimulationEngine::new(particle_config).map_err(|error| error.to_string())?;
            engine.particle.logical_id = index as u64;
            engine.particle.lineage = format!("root.{index}");
            engine.particle.ancestry = vec![index as u64];
            particles.push(engine);
        }
        (
            particles,
            vec![0.0; particle_end - particle_start],
            PyRandomCompat::from_seed(seed_from_namespace(
                config.seed,
                &config.random_stream_namespace,
                "filter",
            )),
            0,
            0.5,
            McseMonitor::new(0.01, 32),
        )
    };
    if !ess_fraction.is_finite() || ess_fraction < 0.0 {
        return Err("MPI filter ESS fraction must be finite and non-negative".to_string());
    }
    let mut updates = Vec::new();

    let current_time = particles
        .first()
        .map(|particle| particle.particle.time)
        .unwrap_or(0.0);
    if particles
        .iter()
        .any(|particle| particle.particle.time.to_bits() != current_time.to_bits())
    {
        return Err("MPI filter particles do not share a common simulation time".to_string());
    }
    let mut previous_time = current_time;
    for (time, observation) in boundaries {
        if !time.is_finite() || *time < previous_time {
            return Err("MPI filter boundaries must be finite and nondecreasing".to_string());
        }
        previous_time = *time;
        for_each_mut(&mut particles, threads.max(1), |particle| {
            particle.advance_until(*time).map_err(FilterError::from)
        })
        .map_err(|error| error.to_string())?;
        if let Some(observation) = observation {
            for (weight, particle) in local_weights.iter_mut().zip(particles.iter()) {
                let likelihood = observation_log_likelihood(particle, observation);
                if likelihood.is_finite() {
                    *weight += likelihood;
                } else {
                    *weight = f64::NEG_INFINITY;
                }
            }
        }

        let global_weights = all_gather_f64(world, &partition, &local_weights)?;
        let is_root = rank == 0;
        let mut canonical = if is_root {
            Some(canonical_boundary(
                &global_weights,
                ess_fraction,
                &mut filter_rng,
            )?)
        } else {
            None
        };
        let mut metadata = [
            canonical
                .as_ref()
                .map(|value| value.log_normalizer)
                .unwrap_or(0.0),
            canonical.as_ref().map(|value| value.ess).unwrap_or(0.0),
        ];
        world.process_at_rank(0).broadcast_into(&mut metadata[..]);
        let mut resampled = [if canonical.as_ref().is_some_and(|value| value.resampled) {
            1
        } else {
            0
        }];
        world.process_at_rank(0).broadcast_into(&mut resampled[..]);
        let mut normalized = vec![0.0; particle_count];
        let mut parents = vec![0; particle_count];
        if let Some(value) = canonical.take() {
            normalized = value.normalized_weights;
            parents = value.parent_indices;
        }
        world.process_at_rank(0).broadcast_into(&mut normalized[..]);
        world.process_at_rank(0).broadcast_into(&mut parents[..]);

        let contributions = particles
            .iter()
            .enumerate()
            .map(|(offset, particle)| {
                let total = particle
                    .particle
                    .locality
                    .insurgent_control
                    .iter()
                    .sum::<f64>();
                let count = particle.particle.locality.population.len().max(1) as f64;
                normalized[particle_start + offset] * total / count
            })
            .collect::<Vec<_>>();
        let global_contributions = all_gather_f64(world, &partition, &contributions)?;
        mcse.push(crate::mpi::canonical_reduce(&global_contributions));

        boundary_index = boundary_index.saturating_add(1);
        let did_resample = resampled[0] != 0;
        let ancestry = if did_resample {
            let buckets = pack_local_parent_states(
                &partition,
                particle_start,
                rank,
                &particles
                    .iter()
                    .map(|engine| engine.particle.clone())
                    .collect::<Vec<_>>(),
                &parents,
            )?;
            let frames = buckets
                .iter()
                .map(|bucket| encode_parent_frame(bucket))
                .collect::<Result<Vec<_>, _>>()?;
            let received = all_to_all_frames(world, &frames)?;
            let mut packets = Vec::new();
            for frame in received {
                packets.extend(decode_parent_frame(&frame)?);
            }
            let child_states = materialize_children_for_range(
                &packets,
                particle_start,
                particle_end,
                particle_count,
                boundary_index,
            )?;
            particles = child_states
                .into_iter()
                .map(|state| {
                    SimulationEngine::from_particle(config.clone(), topology.clone(), state)
                        .map_err(|error| error.to_string())
                })
                .collect::<Result<Vec<_>, _>>()?;
            local_weights.fill(0.0);
            all_gather_lineages(world, &partition, &particles)?
        } else {
            for (offset, particle) in particles.iter_mut().enumerate() {
                particle.particle.filter_boundary = boundary_index;
                particle.particle.weights_log = local_weights[offset];
            }
            all_gather_lineages(world, &partition, &particles)?
        };
        if is_root {
            updates.push(FilterUpdate {
                time: *time,
                log_normalizer: metadata[0],
                ess: metadata[1],
                resampled: did_resample,
                parent_indices: parents.clone(),
                ancestry,
            });
        }
    }

    let global_log_weights = all_gather_f64(world, &partition, &local_weights)?;
    Ok(MpiFilterResult {
        rank,
        world_size,
        particle_start,
        particle_end,
        particles,
        log_weights: if rank == 0 {
            global_log_weights
        } else {
            local_weights
        },
        filter_rng,
        boundary: boundary_index,
        mcse,
        updates,
        checkpoint: PathBuf::new(),
    })
}

fn topology_for_particle(
    particle: &pineland_core::state::ParticleState,
    config: &SimulationConfig,
) -> pineland_core::topology::StaticTopology {
    let initialization_seed = config.initialization_seed.unwrap_or(config.seed);
    let topology =
        pineland_core::topology::StaticTopology::pineland(config, initialization_seed).topology;
    if particle.locality.population.len() != topology.locality_count()
        || particle.zones.population_share.len() != topology.microzone_count()
    {
        let locality_count = particle.locality.population.len().max(1);
        let zones_per_locality = (particle.zones.population_share.len() / locality_count).max(1);
        return pineland_core::topology::StaticTopology::synthetic(
            locality_count,
            zones_per_locality,
        );
    }
    topology
}

fn all_gather_f64<C: Communicator + CommunicatorCollectives>(
    world: &C,
    partition: &DeterministicPartition,
    local: &[f64],
) -> Result<Vec<f64>, String> {
    if local.len()
        != partition
            .rank_particles(usize::try_from(world.rank()).unwrap())
            .len()
    {
        return Err("rank-local buffer does not match its canonical range".to_string());
    }
    let (counts, displacements) = mpi_partitions(partition)?;
    let mut global = vec![0.0; partition.particle_count];
    {
        let mut receive = PartitionMut::new(&mut global[..], counts, displacements);
        world.all_gather_varcount_into(local, &mut receive);
    }
    Ok(global)
}

fn all_gather_lineages<C: Communicator + CommunicatorCollectives>(
    world: &C,
    partition: &DeterministicPartition,
    particles: &[SimulationEngine],
) -> Result<Vec<String>, String> {
    let local = encode_strings(
        &particles
            .iter()
            .map(|particle| particle.particle.lineage.clone())
            .collect::<Vec<_>>(),
    )?;
    // Exchange byte counts first so every rank can receive every rank's
    // encoded list.
    let mut local_count = [
        i32::try_from(local.len()).map_err(|_| "lineage buffer exceeds MPI Count".to_string())?
    ];
    let mut all_counts = vec![0i32; partition.rank_count];
    world.all_gather_into(&local_count[..], &mut all_counts[..]);
    let displacements = displacements_for_counts(&all_counts)?;
    let total = checked_count_sum(&all_counts)?;
    let mut bytes = vec![0u8; total];
    {
        let mut receive = PartitionMut::new(&mut bytes[..], all_counts, displacements.clone());
        world.all_gather_varcount_into(&local[..], &mut receive);
    }
    let mut result = Vec::with_capacity(partition.particle_count);
    for rank in 0..partition.rank_count {
        let start = displacements[rank] as usize;
        let end = start + all_counts[rank] as usize;
        result.extend(decode_strings(&bytes[start..end])?);
    }
    if result.len() != partition.particle_count {
        return Err("gathered lineage count does not equal particle count".to_string());
    }
    Ok(result)
}

fn encode_strings(values: &[String]) -> Result<Vec<u8>, String> {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(
        &u64::try_from(values.len())
            .map_err(|_| "lineage count exceeds u64".to_string())?
            .to_le_bytes(),
    );
    for value in values {
        let value = value.as_bytes();
        bytes.extend_from_slice(
            &u64::try_from(value.len())
                .map_err(|_| "lineage length exceeds u64".to_string())?
                .to_le_bytes(),
        );
        bytes.extend_from_slice(value);
    }
    Ok(bytes)
}

fn decode_strings(bytes: &[u8]) -> Result<Vec<String>, String> {
    let mut reader = ByteCursor { bytes, position: 0 };
    let count = reader.u64()?;
    let count = usize::try_from(count).map_err(|_| "lineage count overflows usize".to_string())?;
    let mut result = Vec::with_capacity(count);
    for _ in 0..count {
        let length = usize::try_from(reader.u64()?)
            .map_err(|_| "lineage length overflows usize".to_string())?;
        let value = reader.take(length)?;
        result.push(
            String::from_utf8(value.to_vec()).map_err(|_| "lineage is not UTF-8".to_string())?,
        );
    }
    if reader.remaining() != 0 {
        return Err("trailing bytes after lineage list".to_string());
    }
    Ok(result)
}

fn all_to_all_frames<C: Communicator + CommunicatorCollectives>(
    world: &C,
    frames: &[Vec<u8>],
) -> Result<Vec<Vec<u8>>, String> {
    let send_counts = frames
        .iter()
        .map(|frame| i32::try_from(frame.len()).map_err(|_| "MPI frame exceeds Count".to_string()))
        .collect::<Result<Vec<_>, _>>()?;
    let size = usize::try_from(world.size()).map_err(|_| "MPI size overflows usize".to_string())?;
    if send_counts.len() != size {
        return Err("all-to-all frame count does not equal MPI world size".to_string());
    }
    let mut receive_counts = vec![0i32; size];
    world.all_to_all_into(&send_counts[..], &mut receive_counts[..]);
    let send_displacements = displacements_for_counts(&send_counts)?;
    let receive_displacements = displacements_for_counts(&receive_counts)?;
    let send_total = checked_count_sum(&send_counts)?;
    let receive_total = checked_count_sum(&receive_counts)?;
    let send_bytes = frames.iter().flatten().copied().collect::<Vec<_>>();
    if send_bytes.len() != send_total {
        return Err("all-to-all send frame lengths are inconsistent".to_string());
    }
    let mut receive_bytes = vec![0u8; receive_total];
    {
        let send = Partition::new(&send_bytes[..], send_counts, send_displacements);
        let mut receive = PartitionMut::new(
            &mut receive_bytes[..],
            receive_counts.clone(),
            receive_displacements.clone(),
        );
        world.all_to_all_varcount_into(&send, &mut receive);
    }
    let mut result = Vec::with_capacity(size);
    for rank in 0..size {
        let start = receive_displacements[rank] as usize;
        let end = start + receive_counts[rank] as usize;
        result.push(receive_bytes[start..end].to_vec());
    }
    Ok(result)
}

fn mpi_partitions(partition: &DeterministicPartition) -> Result<(Vec<Count>, Vec<Count>), String> {
    let counts = partition
        .ranges
        .iter()
        .map(|(start, end)| {
            i32::try_from(end - start).map_err(|_| "particle range exceeds MPI Count".to_string())
        })
        .collect::<Result<Vec<_>, _>>()?;
    let displacements = displacements_for_counts(&counts)?;
    Ok((counts, displacements))
}

fn displacements_for_counts(counts: &[Count]) -> Result<Vec<Count>, String> {
    let mut displacements = Vec::with_capacity(counts.len());
    let mut total = 0i64;
    for count in counts {
        if *count < 0 {
            return Err("negative MPI count".to_string());
        }
        displacements
            .push(i32::try_from(total).map_err(|_| "MPI displacement exceeds Count".to_string())?);
        total = total
            .checked_add(i64::from(*count))
            .ok_or_else(|| "MPI count sum overflows i64".to_string())?;
    }
    if total > i64::from(i32::MAX) {
        return Err("MPI buffer exceeds the 32-bit Count limit".to_string());
    }
    Ok(displacements)
}

fn checked_count_sum(counts: &[Count]) -> Result<usize, String> {
    counts.iter().try_fold(0usize, |total, count| {
        if *count < 0 {
            return Err("negative MPI count".to_string());
        }
        total
            .checked_add(*count as usize)
            .ok_or_else(|| "MPI count sum overflows usize".to_string())
    })
}

fn publish_checkpoint<C: Communicator + CommunicatorCollectives>(
    world: &C,
    output: &Path,
    boundary: u64,
    particles: &[SimulationEngine],
    configuration_hash: String,
    binary_hash: String,
) -> Result<PathBuf, String> {
    let rank = u32::try_from(world.rank()).map_err(|_| "MPI rank overflows u32".to_string())?;
    let world_size =
        u32::try_from(world.size()).map_err(|_| "MPI world size overflows u32".to_string())?;
    let checkpoint = output.join(format!("checkpoint_{boundary:04}"));
    let local_write = CheckpointStore::write_shard(
        &checkpoint,
        &particles
            .iter()
            .map(|engine| engine.particle.clone())
            .collect::<Vec<_>>(),
        rank,
    );
    let mut local_status = [if local_write.is_ok() { 1 } else { 0 }];
    let mut statuses = vec![0i32; usize::try_from(world.size()).unwrap_or(0)];
    world.all_gather_into(&local_status[..], &mut statuses[..]);
    if statuses.iter().any(|status| *status == 0) {
        world.barrier();
        return Err(local_write
            .err()
            .map(|error| error.to_string())
            .unwrap_or_else(|| {
                "at least one MPI rank failed to write its checkpoint shard".to_string()
            }));
    }
    world.barrier();
    let model_hash = sha256::digest_hex(b"pineland-native-v1-frozen-core");
    let finalized = if rank == 0 {
        CheckpointStore::finalize_directory(
            &checkpoint,
            configuration_hash,
            model_hash,
            binary_hash,
            world_size,
        )
        .map(|_| true)
        .unwrap_or(false)
    } else {
        false
    };
    let mut status = [if finalized { 1 } else { 0 }];
    world.process_at_rank(0).broadcast_into(&mut status[..]);
    world.barrier();
    if status[0] == 0 {
        return Err("MPI checkpoint manifest could not be finalized".to_string());
    }
    Ok(checkpoint)
}

struct ByteCursor<'a> {
    bytes: &'a [u8],
    position: usize,
}

impl<'a> ByteCursor<'a> {
    fn remaining(&self) -> usize {
        self.bytes.len().saturating_sub(self.position)
    }

    fn take(&mut self, length: usize) -> Result<&'a [u8], String> {
        let end = self
            .position
            .checked_add(length)
            .ok_or_else(|| "MPI byte cursor length overflow".to_string())?;
        if end > self.bytes.len() {
            return Err("truncated MPI byte buffer".to_string());
        }
        let value = &self.bytes[self.position..end];
        self.position = end;
        Ok(value)
    }

    fn u64(&mut self) -> Result<u64, String> {
        Ok(u64::from_le_bytes(
            self.take(8)?.try_into().expect("eight-byte MPI field"),
        ))
    }
}
