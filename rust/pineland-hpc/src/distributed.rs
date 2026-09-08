//! Rank-count-independent particle-filter execution.
//!
//! This module contains the deterministic part of the hybrid MPI/Rayon
//! design.  It deliberately keeps transport out of the scientific boundary:
//! logical particles are partitioned into canonical contiguous ranges,
//! propagated independently, and brought back into canonical order before
//! normalization and resampling.  An MPI adapter can use the same boundary
//! and the packed-state helpers in [`crate::migration`] for transport.

use crate::distribution::DeterministicPartition;
use crate::mpi::canonical_boundary;
use pineland_core::config::SimulationConfig;
use pineland_inference::parallel::for_each_mut;
use pineland_inference::{FilterError, FilterUpdate, NativeParticleFilter};
use pineland_model::SimulationEngine;

#[derive(Clone, Debug, PartialEq)]
pub struct DistributedParticleFilter {
    pub filter: NativeParticleFilter,
    pub partition: DeterministicPartition,
}

impl DistributedParticleFilter {
    pub fn new(
        config: SimulationConfig,
        particle_count: usize,
        rank_count: usize,
    ) -> Result<Self, FilterError> {
        if rank_count == 0 {
            return Err(FilterError::Invalid(
                "rank count must be positive".to_string(),
            ));
        }
        let filter = NativeParticleFilter::new(config, particle_count)?;
        let partition = DeterministicPartition::new(particle_count, rank_count);
        Ok(Self { filter, partition })
    }

    pub fn from_filter(
        filter: NativeParticleFilter,
        rank_count: usize,
    ) -> Result<Self, FilterError> {
        if rank_count == 0 {
            return Err(FilterError::Invalid(
                "rank count must be positive".to_string(),
            ));
        }
        let partition = DeterministicPartition::new(filter.particle_count(), rank_count);
        Ok(Self { filter, partition })
    }

    pub fn set_rank_count(&mut self, rank_count: usize) -> Result<(), FilterError> {
        if rank_count == 0 {
            return Err(FilterError::Invalid(
                "rank count must be positive".to_string(),
            ));
        }
        self.partition = DeterministicPartition::new(self.filter.particle_count(), rank_count);
        Ok(())
    }

    pub fn set_threads(&mut self, threads: usize) {
        self.filter.set_threads(threads);
    }

    pub fn particles(&self) -> &[SimulationEngine] {
        &self.filter.particles
    }

    /// Propagate logical ranges in rank order, then perform one canonical
    /// SMC boundary.  Propagation order is intentionally independent of rank
    /// count; each trajectory owns its RNG and no reduction is performed in a
    /// worker.
    pub fn update(
        &mut self,
        time: f64,
        log_likelihood: Option<&[f64]>,
    ) -> Result<FilterUpdate, FilterError> {
        if !time.is_finite() {
            return Err(FilterError::Invalid(
                "filter boundary time must be finite".to_string(),
            ));
        }
        if let Some(values) = log_likelihood {
            if values.len() != self.filter.particle_count() {
                return Err(FilterError::Invalid(
                    "likelihood length does not equal particle count".to_string(),
                ));
            }
            for (weight, likelihood) in self.filter.log_weights.iter_mut().zip(values) {
                if likelihood.is_finite() {
                    *weight += *likelihood;
                } else {
                    *weight = f64::NEG_INFINITY;
                }
            }
        }

        let target_boundary = self.filter.boundary.saturating_add(1);
        for rank in 0..self.partition.rank_count {
            let range = self.partition.rank_particles(rank);
            for_each_mut(
                &mut self.filter.particles[range],
                self.filter.threads,
                |particle| particle.advance_until(time).map_err(FilterError::from),
            )?;
        }

        let boundary = canonical_boundary(
            &self.filter.log_weights,
            self.filter.ess_fraction,
            &mut self.filter.rng,
        )
        .map_err(FilterError::Weight)?;

        let weighted_control = self
            .filter
            .particles
            .iter()
            .zip(boundary.normalized_weights.iter().copied())
            .map(|(particle, weight)| {
                let total = particle
                    .particle
                    .locality
                    .insurgent_control
                    .iter()
                    .sum::<f64>();
                let count = particle.particle.locality.population.len().max(1) as f64;
                weight * total / count
            })
            .sum::<f64>();
        self.filter.mcse.push(weighted_control);

        let threshold = self.filter.particle_count() as f64 * self.filter.ess_fraction;
        let (resampled, parents) = if boundary.ess < threshold {
            let parents = boundary.parent_indices.clone();
            let old = self.filter.particles.clone();
            let mut next = Vec::with_capacity(old.len());
            for (child, parent) in parents.iter().copied().enumerate() {
                let source = old.get(parent).ok_or_else(|| {
                    FilterError::Invalid("canonical parent index is out of bounds".to_string())
                })?;
                let lineage = format!("{}.{}", source.particle.lineage, child);
                let mut engine = source.clone();
                engine.particle = source.particle.clone_for_child(child as u64, lineage);
                engine.particle.rng = source.particle.rng.fork(&format!(
                    "filter-boundary-{target_boundary}:child-{child}:parent-{parent}"
                ));
                engine.particle.weights_log = -(old.len() as f64).ln();
                engine.particle.filter_boundary = target_boundary;
                next.push(engine);
            }
            self.filter.particles = next;
            self.filter.log_weights = vec![0.0; self.filter.particle_count()];
            (true, parents)
        } else {
            for (index, particle) in self.filter.particles.iter_mut().enumerate() {
                particle.particle.filter_boundary = target_boundary;
                particle.particle.weights_log = self.filter.log_weights[index];
            }
            (false, (0..self.filter.particle_count()).collect())
        };
        self.filter.boundary = target_boundary;
        let ancestry = self
            .filter
            .particles
            .iter()
            .map(|particle| particle.particle.lineage.clone())
            .collect();
        Ok(FilterUpdate {
            time,
            log_normalizer: boundary.log_normalizer,
            ess: boundary.ess,
            resampled,
            parent_indices: parents,
            ancestry,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::DistributedParticleFilter;
    use pineland_core::config::SimulationConfig;

    #[test]
    fn rank_count_does_not_change_logical_ensemble() {
        let config = SimulationConfig {
            agent_count: 80,
            locality_count: 4,
            horizon_days: 1.0,
            ..Default::default()
        };
        let mut one = DistributedParticleFilter::new(config.clone(), 8, 1).unwrap();
        let mut four = DistributedParticleFilter::new(config, 8, 4).unwrap();
        one.set_threads(2);
        four.set_threads(2);
        let likelihoods = [0.0, -0.3, -0.7, -1.2, -0.1, -0.8, -0.4, -1.0];
        let first = one.update(1.0, Some(&likelihoods)).unwrap();
        let second = four.update(1.0, Some(&likelihoods)).unwrap();
        assert_eq!(first, second);
        assert_eq!(
            one.particles()
                .iter()
                .map(|particle| particle.state_hash())
                .collect::<Vec<_>>(),
            four.particles()
                .iter()
                .map(|particle| particle.state_hash())
                .collect::<Vec<_>>()
        );
    }
}
