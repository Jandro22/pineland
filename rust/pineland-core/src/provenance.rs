//! Reconstructibility metadata for every production run.

use crate::json::JsonValue;
use crate::sha256;
use std::env;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Clone, Debug, PartialEq)]
pub struct ProvenanceManifest {
    pub schema: String,
    pub git_commit: String,
    pub rust_source_sha256: String,
    pub cargo_lock_sha256: String,
    pub binary_sha256: String,
    pub compiler_version: String,
    pub target_architecture: String,
    pub configuration_sha256: String,
    pub parameter_registry_sha256: String,
    pub case_data_sha256: String,
    pub seed: u64,
    pub initialization_seed: u64,
    pub rng_schema: String,
    pub scheduler_schema: String,
    pub checkpoint_schema: String,
    pub mpi_world_size: u32,
    pub threads_per_rank: u32,
    pub slurm_job_id: String,
    pub slurm_node_list: String,
    pub cpu_model: String,
    pub start_unix_seconds: u64,
    pub end_unix_seconds: Option<u64>,
}

impl ProvenanceManifest {
    pub fn start(
        seed: u64,
        initialization_seed: u64,
        configuration_sha256: impl Into<String>,
    ) -> Self {
        Self {
            schema: "pineland-native-v1".to_string(),
            git_commit: env::var("PINELAND_GIT_COMMIT").unwrap_or_else(|_| "unknown".to_string()),
            rust_source_sha256: env::var("PINELAND_RUST_SOURCE_SHA256")
                .unwrap_or_else(|_| "unknown".to_string()),
            cargo_lock_sha256: env::var("PINELAND_CARGO_LOCK_SHA256")
                .unwrap_or_else(|_| "unknown".to_string()),
            binary_sha256: env::var("PINELAND_BINARY_SHA256")
                .unwrap_or_else(|_| "unknown".to_string()),
            compiler_version: env::var("PINELAND_COMPILER_VERSION")
                .unwrap_or_else(|_| "rustc-unknown".to_string()),
            target_architecture: format!("{}-{}", env::consts::OS, env::consts::ARCH),
            configuration_sha256: configuration_sha256.into(),
            parameter_registry_sha256: env::var("PINELAND_PARAMETER_REGISTRY_SHA256")
                .unwrap_or_else(|_| "not-supplied".to_string()),
            case_data_sha256: env::var("PINELAND_CASE_DATA_SHA256")
                .unwrap_or_else(|_| "not-supplied".to_string()),
            seed,
            initialization_seed,
            rng_schema: "cpython-mt19937-random-v1".to_string(),
            scheduler_schema: "time-priority-sequence-v1".to_string(),
            checkpoint_schema: "PINELAND-v1-little-endian".to_string(),
            mpi_world_size: env::var("OMPI_COMM_WORLD_SIZE")
                .or_else(|_| env::var("PMI_SIZE"))
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(1),
            threads_per_rank: env::var("RAYON_NUM_THREADS")
                .or_else(|_| env::var("SLURM_CPUS_PER_TASK"))
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(1),
            slurm_job_id: env::var("SLURM_JOB_ID").unwrap_or_else(|_| "local".to_string()),
            slurm_node_list: env::var("SLURM_NODELIST").unwrap_or_else(|_| "local".to_string()),
            cpu_model: env::var("PINELAND_CPU_MODEL").unwrap_or_else(|_| detect_cpu_model()),
            start_unix_seconds: now(),
            end_unix_seconds: None,
        }
    }

    pub fn finish(&mut self) {
        self.end_unix_seconds = Some(now());
    }

    pub fn to_json(&self) -> JsonValue {
        let mut value = JsonValue::object();
        for (key, field) in [
            ("schema", &self.schema),
            ("git_commit", &self.git_commit),
            ("rust_source_sha256", &self.rust_source_sha256),
            ("cargo_lock_sha256", &self.cargo_lock_sha256),
            ("binary_sha256", &self.binary_sha256),
            ("compiler_version", &self.compiler_version),
            ("target_architecture", &self.target_architecture),
            ("configuration_sha256", &self.configuration_sha256),
            ("parameter_registry_sha256", &self.parameter_registry_sha256),
            ("case_data_sha256", &self.case_data_sha256),
            ("rng_schema", &self.rng_schema),
            ("scheduler_schema", &self.scheduler_schema),
            ("checkpoint_schema", &self.checkpoint_schema),
            ("slurm_job_id", &self.slurm_job_id),
            ("slurm_node_list", &self.slurm_node_list),
            ("cpu_model", &self.cpu_model),
        ] {
            value.insert(key, JsonValue::string(field));
        }
        value.insert("seed", JsonValue::integer(self.seed));
        value.insert(
            "initialization_seed",
            JsonValue::integer(self.initialization_seed),
        );
        value.insert("mpi_world_size", JsonValue::integer(self.mpi_world_size));
        value.insert(
            "threads_per_rank",
            JsonValue::integer(self.threads_per_rank),
        );
        value.insert(
            "start_unix_seconds",
            JsonValue::integer(self.start_unix_seconds),
        );
        value.insert(
            "end_unix_seconds",
            self.end_unix_seconds
                .map_or(JsonValue::Null, JsonValue::integer),
        );
        value
    }

    pub fn hash(&self) -> String {
        sha256::digest_hex(self.to_json().to_compact().as_bytes())
    }
}

fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

fn detect_cpu_model() -> String {
    if let Ok(value) = env::var("PROCESSOR_IDENTIFIER") {
        if !value.trim().is_empty() {
            return value;
        }
    }
    if let Ok(text) = std::fs::read_to_string("/proc/cpuinfo") {
        if let Some(value) = text.lines().find_map(|line| {
            line.strip_prefix("model name\t: ")
                .or_else(|| line.strip_prefix("Model\t:\t"))
        }) {
            if !value.trim().is_empty() {
                return value.trim().to_string();
            }
        }
    }
    "unknown".to_string()
}
