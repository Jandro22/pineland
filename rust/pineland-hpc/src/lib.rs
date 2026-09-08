//! MPI/SLURM distribution contracts.
//!
//! The core partitioning is MPI-library agnostic.  This keeps local Windows
//! builds usable while making canonical particle ownership and all-to-all
//! resampling plans explicit for an rsmpi-enabled Owl build.

pub mod distributed;
pub mod distribution;
pub mod migration;
pub mod mpi;
#[cfg(feature = "mpi")]
pub mod mpi_runtime;

pub use distributed::DistributedParticleFilter;
pub use distribution::{canonical_owner, DeterministicPartition, ParentTransfer};
