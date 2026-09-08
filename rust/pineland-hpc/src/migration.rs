//! Packed parent-state migration bookkeeping for MPI_Alltoallv.
use crate::distribution::{DeterministicPartition, ParentTransfer};
use pineland_core::checkpoint::CheckpointStore;
use pineland_core::state::ParticleState;

const PARENT_FRAME_MAGIC: &[u8; 9] = b"PLPARENT1";

#[derive(Clone, Debug, PartialEq)]
pub struct PackedParentState {
    pub transfer: ParentTransfer,
    pub payload: Vec<u8>,
}

pub fn alltoallv_buckets(
    partition: &DeterministicPartition,
    parents: &[usize],
) -> Vec<Vec<ParentTransfer>> {
    let mut buckets = vec![Vec::new(); partition.rank_count];
    for transfer in partition.transfer_plan(parents) {
        if let Some(bucket) = buckets.get_mut(transfer.destination_rank) {
            bucket.push(transfer);
        }
    }
    for bucket in &mut buckets {
        bucket.sort_by_key(|item| (item.source_rank, item.child_particle, item.parent_particle));
    }
    buckets
}

/// Pack canonical parent states into one deterministic bucket per destination
/// rank.  The caller can concatenate each bucket and send it with
/// `MPI_Alltoallv`; no Rust object memory or pointer is put on the wire.
pub fn pack_parent_states(
    partition: &DeterministicPartition,
    particles: &[ParticleState],
    parents: &[usize],
) -> Result<Vec<Vec<PackedParentState>>, String> {
    if particles.len() != partition.particle_count || parents.len() != partition.particle_count {
        return Err("particle and parent arrays must equal partition size".to_string());
    }
    if parents
        .iter()
        .any(|parent| *parent >= partition.particle_count)
    {
        return Err("parent index is outside the partition".to_string());
    }
    let transfers = alltoallv_buckets(partition, parents);
    let mut buckets = Vec::with_capacity(partition.rank_count);
    for transfers_for_rank in transfers {
        let mut bucket = Vec::with_capacity(transfers_for_rank.len());
        for transfer in transfers_for_rank {
            let payload = CheckpointStore::encode_particle(&particles[transfer.parent_particle])
                .map_err(|error| error.to_string())?;
            bucket.push(PackedParentState { transfer, payload });
        }
        buckets.push(bucket);
    }
    Ok(buckets)
}

/// Pack only the parent states owned by one rank.  This is the direct input
/// to an MPI_Alltoallv exchange when each rank keeps a contiguous canonical
/// interval instead of a duplicated global particle array.
pub fn pack_local_parent_states(
    partition: &DeterministicPartition,
    local_start: usize,
    source_rank: usize,
    particles: &[ParticleState],
    parents: &[usize],
) -> Result<Vec<Vec<PackedParentState>>, String> {
    let local_end = local_start
        .checked_add(particles.len())
        .ok_or_else(|| "local particle range overflows usize".to_string())?;
    if local_end > partition.particle_count
        || partition.rank_particles(source_rank) != (local_start..local_end)
    {
        return Err("local particle slice does not match its canonical rank range".to_string());
    }
    if parents.len() != partition.particle_count {
        return Err("parent array must equal the global particle count".to_string());
    }
    let mut buckets = vec![Vec::new(); partition.rank_count];
    for (child_particle, parent_particle) in parents.iter().copied().enumerate() {
        if parent_particle >= partition.particle_count {
            return Err("parent index is outside the partition".to_string());
        }
        if partition.owners[parent_particle] != source_rank {
            continue;
        }
        let local_parent = parent_particle - local_start;
        let destination_rank = partition.owners[child_particle];
        let transfer = ParentTransfer {
            source_rank,
            destination_rank,
            child_particle,
            parent_particle,
        };
        let payload = CheckpointStore::encode_particle(&particles[local_parent])
            .map_err(|error| error.to_string())?;
        buckets[destination_rank].push(PackedParentState { transfer, payload });
    }
    for bucket in &mut buckets {
        bucket.sort_by_key(|item| {
            (
                item.transfer.child_particle,
                item.transfer.source_rank,
                item.transfer.parent_particle,
            )
        });
    }
    Ok(buckets)
}

/// Encode one destination bucket as a self-delimiting byte frame.  Frames are
/// deliberately independent of MPI datatype layout and can be validated
/// before any child is installed in the live ensemble.
pub fn encode_parent_frame(bucket: &[PackedParentState]) -> Result<Vec<u8>, String> {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(PARENT_FRAME_MAGIC);
    put_u64(&mut bytes, bucket.len())?;
    for item in bucket {
        put_u64(&mut bytes, item.transfer.source_rank)?;
        put_u64(&mut bytes, item.transfer.destination_rank)?;
        put_u64(&mut bytes, item.transfer.child_particle)?;
        put_u64(&mut bytes, item.transfer.parent_particle)?;
        put_u64(&mut bytes, item.payload.len())?;
        bytes.extend_from_slice(&item.payload);
    }
    Ok(bytes)
}

pub fn decode_parent_frame(bytes: &[u8]) -> Result<Vec<PackedParentState>, String> {
    let mut reader = FrameReader { bytes, position: 0 };
    if reader.take(PARENT_FRAME_MAGIC.len())? != &PARENT_FRAME_MAGIC[..] {
        return Err("invalid parent-state frame magic".to_string());
    }
    let count = reader.count()?;
    let mut result = Vec::with_capacity(count);
    for _ in 0..count {
        let source_rank = reader.usize("source rank")?;
        let destination_rank = reader.usize("destination rank")?;
        let child_particle = reader.usize("child particle")?;
        let parent_particle = reader.usize("parent particle")?;
        let payload_length = reader.count()?;
        let payload = reader.take(payload_length)?.to_vec();
        // Decode here to reject truncated or malformed state before MPI
        // callers attempt to materialize a child.
        CheckpointStore::decode_particle(&payload).map_err(|error| error.to_string())?;
        result.push(PackedParentState {
            transfer: ParentTransfer {
                source_rank,
                destination_rank,
                child_particle,
                parent_particle,
            },
            payload,
        });
    }
    if reader.remaining() != 0 {
        return Err("trailing bytes in parent-state frame".to_string());
    }
    result.sort_by_key(|item| {
        (
            item.transfer.child_particle,
            item.transfer.source_rank,
            item.transfer.parent_particle,
        )
    });
    Ok(result)
}

/// Turn received parent payloads into canonical logical children.  This is
/// the state-side half of cross-rank resampling and uses the same branch
/// identity as the local filter.
pub fn materialize_children(
    packets: &[PackedParentState],
    particle_count: usize,
    boundary: u64,
) -> Result<Vec<ParticleState>, String> {
    materialize_children_for_range(packets, 0, particle_count, particle_count, boundary)
}

/// Materialize only the canonical child interval owned by one MPI rank.
/// `child_start..child_end` remains in global logical-particle coordinates;
/// the returned vector is local and ordered by that global child ID.
pub fn materialize_children_for_range(
    packets: &[PackedParentState],
    child_start: usize,
    child_end: usize,
    particle_count: usize,
    boundary: u64,
) -> Result<Vec<ParticleState>, String> {
    if child_start > child_end || child_end > particle_count {
        return Err("child range is outside the particle population".to_string());
    }
    if packets.len() != child_end - child_start {
        return Err("received child count does not equal particle count".to_string());
    }
    let mut sorted = packets.to_vec();
    sorted.sort_by_key(|item| item.transfer.child_particle);
    let mut children = Vec::with_capacity(child_end - child_start);
    for (offset, packet) in sorted.iter().enumerate() {
        let expected_child = child_start + offset;
        if packet.transfer.child_particle != expected_child {
            return Err("received child IDs are not contiguous and unique".to_string());
        }
        let source =
            CheckpointStore::decode_particle(&packet.payload).map_err(|error| error.to_string())?;
        let lineage = format!("{}.{}", source.lineage, expected_child);
        let mut child = source.clone_for_child(expected_child as u64, lineage);
        let identity = format!(
            "filter-boundary-{boundary}:child-{expected_child}:parent-{}",
            packet.transfer.parent_particle
        );
        child.rng = source.rng.fork(&identity);
        child.weights_log = -(particle_count as f64).ln();
        child.filter_boundary = boundary;
        children.push(child);
    }
    Ok(children)
}

fn put_u64(bytes: &mut Vec<u8>, value: usize) -> Result<(), String> {
    let value = u64::try_from(value).map_err(|_| "frame length overflows u64".to_string())?;
    bytes.extend_from_slice(&value.to_le_bytes());
    Ok(())
}

struct FrameReader<'a> {
    bytes: &'a [u8],
    position: usize,
}

impl<'a> FrameReader<'a> {
    fn remaining(&self) -> usize {
        self.bytes.len().saturating_sub(self.position)
    }

    fn take(&mut self, count: usize) -> Result<&'a [u8], String> {
        let end = self
            .position
            .checked_add(count)
            .ok_or_else(|| "parent frame length overflow".to_string())?;
        if end > self.bytes.len() {
            return Err("truncated parent-state frame".to_string());
        }
        let value = &self.bytes[self.position..end];
        self.position = end;
        Ok(value)
    }

    fn u64(&mut self) -> Result<u64, String> {
        Ok(u64::from_le_bytes(
            self.take(8)?.try_into().expect("eight-byte frame field"),
        ))
    }

    fn count(&mut self) -> Result<usize, String> {
        let value = self.u64()?;
        if value > 100_000_000 {
            return Err("parent frame declares too many records".to_string());
        }
        usize::try_from(value).map_err(|_| "parent frame count overflows usize".to_string())
    }

    fn usize(&mut self, name: &str) -> Result<usize, String> {
        let value = self.u64()?;
        usize::try_from(value).map_err(|_| format!("{name} overflows usize"))
    }
}

pub fn canonical_child_order(parents: &[usize]) -> Vec<usize> {
    (0..parents.len()).collect()
}

#[cfg(test)]
mod tests {
    use super::{
        decode_parent_frame, encode_parent_frame, materialize_children, pack_parent_states,
    };
    use crate::distribution::DeterministicPartition;
    use pineland_core::rng::RngStreams;
    use pineland_core::state::ParticleState;

    #[test]
    fn packed_parent_states_round_trip_into_canonical_children() {
        let partition = DeterministicPartition::new(4, 2);
        let particles = (0..4)
            .map(|index| {
                let mut particle =
                    ParticleState::new(2, 2, 1, 1, 1, RngStreams::new(index as u64, "migration"));
                particle.logical_id = index as u64;
                particle.lineage = format!("root.{index}");
                particle
            })
            .collect::<Vec<_>>();
        let buckets = pack_parent_states(&partition, &particles, &[3, 0, 3, 1]).unwrap();
        let frames = buckets
            .iter()
            .map(|bucket| encode_parent_frame(bucket).unwrap())
            .collect::<Vec<_>>();
        let mut received = Vec::new();
        for frame in frames {
            received.extend(decode_parent_frame(&frame).unwrap());
        }
        let children = materialize_children(&received, 4, 5).unwrap();
        assert_eq!(
            children
                .iter()
                .map(|child| child.logical_id)
                .collect::<Vec<_>>(),
            vec![0, 1, 2, 3]
        );
        assert_eq!(children[0].lineage, "root.3.0");
        assert_eq!(children[1].lineage, "root.0.1");
        assert_ne!(children[0].rng, children[2].rng);
        assert!(children.iter().all(|child| child.filter_boundary == 5));
    }

    #[test]
    fn malformed_parent_frames_are_rejected() {
        assert!(decode_parent_frame(b"PLPARENT1\0").is_err());
    }
}
