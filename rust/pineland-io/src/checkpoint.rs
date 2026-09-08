//! Public checkpoint directory helpers.
use pineland_core::checkpoint::{CheckpointError, CheckpointManifest, CheckpointStore};
use pineland_core::state::ParticleState;
use std::path::Path;
pub fn write(
    path: impl AsRef<Path>,
    particles: &[ParticleState],
    configuration_hash: &str,
    model_hash: &str,
    binary_hash: &str,
) -> Result<CheckpointManifest, CheckpointError> {
    CheckpointStore::write_directory(
        path,
        particles,
        configuration_hash,
        model_hash,
        binary_hash,
        0,
        1,
    )
}
pub fn read(
    path: impl AsRef<Path>,
) -> Result<(CheckpointManifest, Vec<ParticleState>), CheckpointError> {
    CheckpointStore::read_directory(path)
}
