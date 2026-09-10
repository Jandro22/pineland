//! Pineland Native's dependency-light deterministic core.
//!
//! The core deliberately contains no model-specific equations.  It provides
//! the stable numeric representation, exact event ordering, CPython-compatible
//! random streams, versioned state/checkpoint primitives, and provenance
//! utilities used by the model, inference, and command-line crates.

pub mod checkpoint;
pub mod config;
pub mod ids;
pub mod json;
pub mod provenance;
pub mod rng;
pub mod scheduler;
pub mod sha256;
pub mod state;
pub mod topology;

/// Cache parity/debug environment flags at their call site.
///
/// Trace configuration is a launch-time concern. Re-querying the Windows
/// process environment from inner loops adds shared runtime overhead when many
/// particles execute concurrently, so each literal flag is resolved once.
#[macro_export]
macro_rules! trace_env {
    ($name:literal) => {{
        static ENABLED: std::sync::OnceLock<bool> = std::sync::OnceLock::new();
        *ENABLED.get_or_init(|| std::env::var_os($name).is_some())
    }};
}

pub use checkpoint::{CheckpointError, CheckpointManifest, CheckpointStore};
pub use config::{ConfigError, SimulationConfig};
pub use ids::*;
pub use json::JsonValue;
pub use provenance::ProvenanceManifest;
pub use rng::{seed_from_namespace, PyRandomCompat, RngState, RngStreams};
pub use scheduler::{EventPayload, ScheduledEvent, Scheduler, SchedulerError};
pub use state::{
    BeliefState, FootholdState, FormationState, LocalityState, OrganizationState, ParticleState,
    PatrolState, PersonState, PresenceKey, PresenceState, SecurityPostState, StateError, ZoneState,
    CONTROL_DIMENSIONS,
};
pub use topology::{CsrGraph, StaticTopology};
