//! `pineland` — the authoritative standalone Pineland Native runtime.
//!
//! The command line is intentionally dependency-light and keeps all hot
//! simulation work inside the Rust workspace.  Python remains an optional
//! analysis client, never a requirement for these commands.

use pineland_core::checkpoint::CheckpointStore;
use pineland_core::config::SimulationConfig;
use pineland_core::json::{self, JsonValue};
use pineland_core::sha256;
use pineland_core::topology::StaticTopology;
use pineland_inference::{forecast::run_branches, FilterUpdate, NativeParticleFilter, Observation};
use pineland_io::{binary_hash, manifest::for_engine, write_json, write_run};
use pineland_model::SimulationEngine;
use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Instant;

const VERSION: &str = "1.0.0";

fn main() {
    if let Err(error) = dispatch() {
        eprintln!("pineland: {error}");
        std::process::exit(1);
    }
}

fn dispatch() -> Result<(), String> {
    let mut tokens = env::args().skip(1).collect::<Vec<_>>();
    if tokens.is_empty()
        || matches!(
            tokens.first().map(String::as_str),
            Some("help" | "--help" | "-h")
        )
    {
        print_help();
        return Ok(());
    }
    let command = tokens.remove(0);
    let arguments = Arguments::parse(tokens)?;
    match command.as_str() {
        "version" | "--version" => {
            println!("pineland {VERSION}");
            Ok(())
        }
        "validate-config" => validate_config(&arguments),
        "generate" => generate(&arguments),
        "run" => run(&arguments),
        "resume" => resume(&arguments),
        "filter" => filter(&arguments),
        "forecast" => forecast(&arguments),
        "inspect-checkpoint" => inspect_checkpoint(&arguments),
        "hash-state" => hash_state(&arguments),
        "benchmark" => benchmark(&arguments),
        other => Err(format!(
            "unknown command '{other}'. Run `pineland help` for usage."
        )),
    }
}

#[derive(Clone, Debug, Default)]
struct Arguments {
    options: BTreeMap<String, String>,
    flags: Vec<String>,
    positional: Vec<String>,
}

impl Arguments {
    fn parse(tokens: Vec<String>) -> Result<Self, String> {
        let mut result = Self::default();
        let mut index = 0;
        while index < tokens.len() {
            let token = &tokens[index];
            if let Some(stripped) = token.strip_prefix("--") {
                if let Some((key, value)) = stripped.split_once('=') {
                    result.options.insert(key.to_string(), value.to_string());
                } else if index + 1 < tokens.len() && !tokens[index + 1].starts_with('-') {
                    result
                        .options
                        .insert(stripped.to_string(), tokens[index + 1].clone());
                    index += 1;
                } else {
                    result.flags.push(stripped.to_string());
                }
            } else if token.starts_with('-') {
                return Err(format!("unsupported option {token}"));
            } else {
                result.positional.push(token.clone());
            }
            index += 1;
        }
        Ok(result)
    }

    fn value(&self, key: &str) -> Option<&str> {
        self.options.get(key).map(String::as_str)
    }
    fn string(&self, key: &str, default: &str) -> String {
        self.value(key).unwrap_or(default).to_string()
    }
    fn usize(&self, key: &str, default: usize) -> Result<usize, String> {
        self.value(key)
            .map(|value| {
                value
                    .parse::<usize>()
                    .map_err(|_| format!("--{key} must be an integer"))
            })
            .unwrap_or(Ok(default))
    }
    fn f64(&self, key: &str, default: f64) -> Result<f64, String> {
        self.value(key)
            .map(|value| {
                value
                    .parse::<f64>()
                    .map_err(|_| format!("--{key} must be a number"))
            })
            .unwrap_or(Ok(default))
    }
}

fn load_config(
    arguments: &Arguments,
    allow_positional_config: bool,
) -> Result<SimulationConfig, String> {
    load_config_inner(arguments, allow_positional_config, true)
}

fn load_config_without_days(
    arguments: &Arguments,
    allow_positional_config: bool,
) -> Result<SimulationConfig, String> {
    load_config_inner(arguments, allow_positional_config, false)
}

fn load_config_inner(
    arguments: &Arguments,
    allow_positional_config: bool,
    apply_days: bool,
) -> Result<SimulationConfig, String> {
    let path = arguments.value("config").map(PathBuf::from).or_else(|| {
        allow_positional_config
            .then(|| arguments.positional.first())
            .flatten()
            .map(PathBuf::from)
    });
    let mut config = if let Some(path) = path {
        SimulationConfig::load(path).map_err(|error| error.to_string())?
    } else {
        SimulationConfig::default()
    };
    if let Some(seed) = arguments.value("seed") {
        config.seed = seed
            .parse()
            .map_err(|_| "--seed must be an unsigned integer".to_string())?;
    }
    if apply_days {
        if let Some(days) = arguments.value("days") {
            config.horizon_days = days
                .parse()
                .map_err(|_| "--days must be a number".to_string())?;
        }
    }
    if let Some(mode) = arguments.value("output-mode") {
        config.output_mode = mode.to_string();
    }
    config.validate().map_err(|error| error.to_string())?;
    Ok(config)
}

fn config(arguments: &Arguments) -> Result<SimulationConfig, String> {
    load_config(arguments, true)
}

fn thread_count(arguments: &Arguments) -> Result<usize, String> {
    if let Some(value) = arguments.value("threads") {
        return value
            .parse::<usize>()
            .map(|value| value.max(1))
            .map_err(|_| "--threads must be an integer".to_string());
    }
    Ok(env::var("RAYON_NUM_THREADS")
        .or_else(|_| env::var("SLURM_CPUS_PER_TASK"))
        .ok()
        .and_then(|value| value.parse::<usize>().ok())
        .map(|value| value.max(1))
        .unwrap_or(1))
}

fn validate_config(arguments: &Arguments) -> Result<(), String> {
    let config = config(arguments)?;
    let mut output = JsonValue::object();
    output.insert("valid", JsonValue::Bool(true));
    output.insert(
        "configuration_hash",
        JsonValue::string(config.canonical_hash()),
    );
    output.insert("config", config.to_json());
    println!("{}", output.to_pretty());
    Ok(())
}

fn generate(arguments: &Arguments) -> Result<(), String> {
    let config = config(arguments)?;
    let output = PathBuf::from(arguments.string("output", "outputs/native-generated"));
    fs::create_dir_all(&output).map_err(|error| error.to_string())?;
    let engine = SimulationEngine::new(config).map_err(|error| error.to_string())?;
    let provenance = for_engine(&engine);
    let _ = write_run(&output, &engine, provenance).map_err(|error| error.to_string())?;
    println!("{}", engine.summary().to_pretty());
    Ok(())
}

fn run(arguments: &Arguments) -> Result<(), String> {
    let config = config(arguments)?;
    let output = PathBuf::from(arguments.string("output", "outputs/native"));
    let start = Instant::now();
    let mut engine = SimulationEngine::new(config).map_err(|error| error.to_string())?;
    engine.run().map_err(|error| error.to_string())?;
    let provenance = for_engine(&engine);
    let artifacts = write_run(&output, &engine, provenance).map_err(|error| error.to_string())?;
    let mut summary = engine.summary();
    summary.insert(
        "wall_seconds",
        JsonValue::number(start.elapsed().as_secs_f64()),
    );
    summary.insert(
        "output",
        JsonValue::string(artifacts.output.to_string_lossy().to_string()),
    );
    write_json(&artifacts.summary, &summary).map_err(|error| error.to_string())?;
    println!("{}", summary.to_pretty());
    Ok(())
}

fn resume(arguments: &Arguments) -> Result<(), String> {
    let checkpoint = checkpoint_argument(arguments, "resume")?;
    let (manifest, mut particles) =
        CheckpointStore::read_directory(&checkpoint).map_err(|error| error.to_string())?;
    let particle = particles
        .drain(..)
        .next()
        .ok_or_else(|| "checkpoint contains no particles".to_string())?;
    let config = resume_config(arguments, &checkpoint)?;
    if manifest.configuration_hash != config.canonical_hash() {
        return Err(format!(
            "checkpoint configuration hash {} does not match supplied configuration {}; pass --config with the original config",
            manifest.configuration_hash,
            config.canonical_hash()
        ));
    }
    let mut config = config;
    if let Some(until) = arguments.value("until") {
        config.horizon_days = until
            .parse()
            .map_err(|_| "--until must be a number".to_string())?;
    }
    config.validate().map_err(|error| error.to_string())?;
    let output = PathBuf::from(arguments.string("output", "outputs/native-resumed"));
    let topology = topology_for_particle(&particle);
    let mut engine = SimulationEngine::from_particle(config, topology, particle)
        .map_err(|error| error.to_string())?;
    engine
        .advance_until(engine.config.horizon_days)
        .map_err(|error| error.to_string())?;
    let artifacts =
        write_run(&output, &engine, for_engine(&engine)).map_err(|error| error.to_string())?;
    println!("{}", engine.summary().to_pretty());
    println!("checkpoint: {}", artifacts.checkpoint.display());
    Ok(())
}

fn resume_config(arguments: &Arguments, checkpoint: &Path) -> Result<SimulationConfig, String> {
    if arguments.value("config").is_none() {
        if let Some(parent) = checkpoint.parent() {
            let candidate = parent.join("config.json");
            if candidate.is_file() {
                return SimulationConfig::load(candidate).map_err(|error| error.to_string());
            }
        }
    }
    load_config_without_days(arguments, false)
}

fn filter(arguments: &Arguments) -> Result<(), String> {
    if arguments.flags.iter().any(|flag| flag == "mpi") {
        #[cfg(feature = "mpi")]
        {
            return filter_mpi(arguments);
        }
        #[cfg(not(feature = "mpi"))]
        {
            return Err(
                "--mpi requires an MPI-enabled build: cargo build --release --features mpi"
                    .to_string(),
            );
        }
    }
    filter_local(arguments)
}

fn filter_local(arguments: &Arguments) -> Result<(), String> {
    let output = PathBuf::from(arguments.string("output", "outputs/native-filter"));
    let observations = load_observations(arguments)?;
    let (mut filter, config, target_time) = if let Some(value) = arguments.value("checkpoint") {
        filter_from_checkpoint(arguments, PathBuf::from(value))?
    } else {
        let config = config(arguments)?;
        let target_time = arguments
            .value("until")
            .or_else(|| arguments.value("days"))
            .map(|value| {
                value
                    .parse::<f64>()
                    .map_err(|_| "filter target time must be a number".to_string())
            })
            .transpose()?
            .unwrap_or(config.horizon_days);
        let particles = arguments.usize("particles", 32)?;
        (
            NativeParticleFilter::new(config.clone(), particles)
                .map_err(|error| error.to_string())?,
            config,
            target_time,
        )
    };
    let target_time = if arguments.value("until").is_none()
        && arguments.value("days").is_none()
        && !observations.is_empty()
    {
        observations
            .last()
            .map(|item| item.time)
            .unwrap_or(target_time)
    } else {
        target_time
    };
    let current_time = filter
        .particles
        .first()
        .map(|particle| particle.particle.time)
        .ok_or_else(|| "filter produced no particles".to_string())?;
    if !target_time.is_finite() {
        return Err("filter target time must be finite".to_string());
    }
    if target_time < current_time {
        return Err(format!(
            "filter target time {target_time} is before the current particle time {current_time}"
        ));
    }
    if observations.iter().any(|item| item.time > target_time) {
        return Err("an observation occurs after the requested filter target time".to_string());
    }
    if observations.iter().any(|item| item.time < current_time) {
        return Err("an observation occurs before the current filter checkpoint time".to_string());
    }
    if arguments.value("threads").is_some() || filter.boundary == 0 {
        filter.set_threads(thread_count(arguments)?);
    }
    let start = Instant::now();
    let mut updates = Vec::new();
    let mut update = None;
    for item in &observations {
        let current = filter
            .update_observation(item.time, &item.observation)
            .map_err(|error| error.to_string())?;
        update = Some(current.clone());
        updates.push(filter_update_json(&current));
    }
    if update.is_none() || target_time > filter.particles[0].particle.time {
        let current = filter
            .update(target_time, None)
            .map_err(|error| error.to_string())?;
        update = Some(current.clone());
        updates.push(filter_update_json(&current));
    }
    let update = update.ok_or_else(|| "filter produced no boundary update".to_string())?;
    fs::create_dir_all(&output).map_err(|error| error.to_string())?;

    let mut result = filter.summary();
    result.insert("time_days", JsonValue::number(target_time));
    result.insert("effective_sample_size", JsonValue::number(update.ess));
    result.insert("resampled", JsonValue::Bool(update.resampled));
    let mut update_rows = JsonValue::Array(Vec::new());
    if let JsonValue::Array(values) = &mut update_rows {
        values.extend(updates);
    }
    result.insert("updates", update_rows);
    result.insert(
        "wall_seconds",
        JsonValue::number(start.elapsed().as_secs_f64()),
    );
    let mut parents = JsonValue::Array(Vec::new());
    if let JsonValue::Array(values) = &mut parents {
        for index in update.parent_indices {
            values.push(JsonValue::integer(index as u64));
        }
    }
    result.insert("parent_indices", parents);

    write_json(output.join("config.json"), &config.to_json()).map_err(|error| error.to_string())?;
    let first = filter
        .particles
        .first()
        .ok_or_else(|| "filter produced no particles".to_string())?;
    let model_hash = first.model_hash.clone();
    let particle_states = filter
        .particles
        .iter()
        .map(|engine| engine.particle.clone())
        .collect::<Vec<_>>();
    let checkpoint = output.join(format!("checkpoint_{:04}", filter.boundary));
    let manifest = CheckpointStore::write_directory(
        &checkpoint,
        &particle_states,
        config.canonical_hash(),
        model_hash,
        binary_hash().unwrap_or_else(|_| "unknown".to_string()),
        0,
        1,
    )
    .map_err(|error| error.to_string())?;
    result.insert(
        "checkpoint",
        JsonValue::string(checkpoint.to_string_lossy().to_string()),
    );
    result.insert(
        "checkpoint_state_hash",
        JsonValue::string(manifest.state_hash),
    );
    write_json(
        output.join("filter_state.json"),
        &filter.continuation_json(),
    )
    .map_err(|error| error.to_string())?;
    result.insert("filter_state", JsonValue::string("filter_state.json"));
    write_json(output.join("filter_summary.json"), &result).map_err(|error| error.to_string())?;

    let mut provenance = for_engine(first);
    provenance.finish();
    let mut metadata = JsonValue::object();
    metadata.insert("schema", JsonValue::string("pineland-native-v1"));
    metadata.insert("engine", JsonValue::string("pineland-cli"));
    metadata.insert("mode", JsonValue::string("filter"));
    metadata.insert(
        "configuration_hash",
        JsonValue::string(config.canonical_hash()),
    );
    metadata.insert("provenance_hash", JsonValue::string(provenance.hash()));
    metadata.insert("provenance", provenance.to_json());
    metadata.insert("summary_file", JsonValue::string("filter_summary.json"));
    metadata.insert(
        "checkpoint",
        JsonValue::string(checkpoint.to_string_lossy().to_string()),
    );
    write_json(output.join("run_metadata.json"), &metadata).map_err(|error| error.to_string())?;
    println!("{}", result.to_pretty());
    Ok(())
}

#[cfg(feature = "mpi")]
fn filter_mpi(arguments: &Arguments) -> Result<(), String> {
    let input_checkpoint = arguments.value("checkpoint").map(PathBuf::from);
    let config = if let Some(checkpoint) = &input_checkpoint {
        filter_resume_config(arguments, checkpoint)?
    } else {
        config(arguments)?
    };
    let observations = load_observations(arguments)?;
    let checkpoint_time = if let Some(checkpoint) = &input_checkpoint {
        let (_, states) =
            CheckpointStore::read_directory(checkpoint).map_err(|error| error.to_string())?;
        states
            .first()
            .map(|state| state.time)
            .ok_or_else(|| "MPI filter checkpoint contains no particles".to_string())?
    } else {
        0.0
    };
    let target_time = arguments
        .value("until")
        .or_else(|| arguments.value("days"))
        .map(|value| {
            value
                .parse::<f64>()
                .map_err(|_| "filter target time must be a number".to_string())
        })
        .transpose()?
        .or_else(|| observations.last().map(|item| item.time))
        .unwrap_or(config.horizon_days);
    if !target_time.is_finite() {
        return Err("filter target time must be finite".to_string());
    }
    if target_time < checkpoint_time {
        return Err(format!(
            "MPI filter target time {target_time} is before the current particle time {checkpoint_time}"
        ));
    }
    if observations.iter().any(|item| item.time > target_time) {
        return Err("an observation occurs after the requested filter target time".to_string());
    }
    if observations.iter().any(|item| item.time < checkpoint_time) {
        return Err("an observation occurs before the current filter checkpoint time".to_string());
    }
    let particles = if let Some(checkpoint) = &input_checkpoint {
        CheckpointStore::read_directory(checkpoint)
            .map_err(|error| error.to_string())?
            .1
            .len()
    } else {
        arguments.usize("particles", 4096)?
    };
    let threads = thread_count(arguments)?;
    let mut boundaries = observations
        .iter()
        .map(|item| (item.time, Some(item.observation.clone())))
        .collect::<Vec<_>>();
    if boundaries
        .last()
        .map(|(time, _)| *time < target_time)
        .unwrap_or(true)
    {
        boundaries.push((target_time, None));
    }
    let output = PathBuf::from(arguments.string("output", "outputs/native-mpi-filter"));
    let mpi_run = if let Some(checkpoint) = input_checkpoint {
        pineland_hpc::mpi_runtime::resume_filter_to_directory(
            config.clone(),
            checkpoint,
            threads,
            &boundaries,
            &output,
            binary_hash().unwrap_or_else(|_| "unknown".to_string()),
        )?
    } else {
        pineland_hpc::mpi_runtime::run_filter_to_directory(
            config.clone(),
            particles,
            threads,
            &boundaries,
            &output,
            binary_hash().unwrap_or_else(|_| "unknown".to_string()),
        )?
    };
    if mpi_run.rank != 0 {
        return Ok(());
    }

    let (manifest, states) =
        CheckpointStore::read_directory(&mpi_run.checkpoint).map_err(|error| error.to_string())?;
    let topology = states
        .first()
        .map(topology_for_particle)
        .ok_or_else(|| "MPI checkpoint contains no particles".to_string())?;
    let engines = states
        .into_iter()
        .map(|state| {
            SimulationEngine::from_particle(config.clone(), topology.clone(), state)
                .map_err(|error| error.to_string())
        })
        .collect::<Result<Vec<_>, _>>()?;
    let mut filter = NativeParticleFilter::from_engines(config.clone(), engines)
        .map_err(|error| error.to_string())?;
    filter.log_weights = mpi_run.log_weights;
    filter.rng = mpi_run.filter_rng;
    filter.boundary = mpi_run.boundary;
    filter.threads = threads;
    filter.mcse = mpi_run.mcse;
    let update = mpi_run
        .updates
        .last()
        .ok_or_else(|| "MPI filter produced no boundary update".to_string())?;

    let mut result = filter.summary();
    result.insert("time_days", JsonValue::number(target_time));
    result.insert("effective_sample_size", JsonValue::number(update.ess));
    result.insert("resampled", JsonValue::Bool(update.resampled));
    let mut update_rows = JsonValue::Array(Vec::new());
    if let JsonValue::Array(values) = &mut update_rows {
        values.extend(mpi_run.updates.iter().map(filter_update_json));
    }
    result.insert("updates", update_rows);
    result.insert(
        "mpi_world_size",
        JsonValue::integer(mpi_run.world_size as u64),
    );
    result.insert("mpi_rank", JsonValue::integer(mpi_run.rank as u64));
    result.insert(
        "checkpoint",
        JsonValue::string(mpi_run.checkpoint.to_string_lossy().to_string()),
    );
    result.insert(
        "checkpoint_state_hash",
        JsonValue::string(manifest.state_hash),
    );
    write_json(output.join("config.json"), &config.to_json()).map_err(|error| error.to_string())?;
    write_json(
        output.join("filter_state.json"),
        &filter.continuation_json(),
    )
    .map_err(|error| error.to_string())?;
    result.insert("filter_state", JsonValue::string("filter_state.json"));
    write_json(output.join("filter_summary.json"), &result).map_err(|error| error.to_string())?;

    let first = filter
        .particles
        .first()
        .ok_or_else(|| "MPI filter produced no particles".to_string())?;
    let mut provenance = for_engine(first);
    provenance.finish();
    let mut metadata = JsonValue::object();
    metadata.insert("schema", JsonValue::string("pineland-native-v1"));
    metadata.insert("engine", JsonValue::string("pineland-cli"));
    metadata.insert("mode", JsonValue::string("mpi-filter"));
    metadata.insert(
        "configuration_hash",
        JsonValue::string(config.canonical_hash()),
    );
    metadata.insert("provenance_hash", JsonValue::string(provenance.hash()));
    metadata.insert("provenance", provenance.to_json());
    metadata.insert("summary_file", JsonValue::string("filter_summary.json"));
    metadata.insert(
        "checkpoint",
        JsonValue::string(mpi_run.checkpoint.to_string_lossy().to_string()),
    );
    write_json(output.join("run_metadata.json"), &metadata).map_err(|error| error.to_string())?;
    println!("{}", result.to_pretty());
    Ok(())
}

fn filter_from_checkpoint(
    arguments: &Arguments,
    checkpoint: PathBuf,
) -> Result<(NativeParticleFilter, SimulationConfig, f64), String> {
    let (manifest, particles) =
        CheckpointStore::read_directory(&checkpoint).map_err(|error| error.to_string())?;
    let config = filter_resume_config(arguments, &checkpoint)?;
    if manifest.configuration_hash != config.canonical_hash() {
        return Err(format!(
            "checkpoint configuration hash {} does not match filter configuration {}",
            manifest.configuration_hash,
            config.canonical_hash()
        ));
    }
    let topology = particles
        .first()
        .map(topology_for_particle)
        .ok_or_else(|| "checkpoint contains no particles".to_string())?;
    let engines = particles
        .into_iter()
        .map(|particle| {
            SimulationEngine::from_particle(config.clone(), topology.clone(), particle)
                .map_err(|error| error.to_string())
        })
        .collect::<Result<Vec<_>, _>>()?;
    let state_path = arguments
        .value("filter-state")
        .map(PathBuf::from)
        .or_else(|| {
            checkpoint
                .parent()
                .map(|parent| parent.join("filter_state.json"))
        })
        .ok_or_else(|| "filter checkpoint has no parent directory".to_string())?;
    let text = fs::read_to_string(&state_path).map_err(|error| {
        format!(
            "cannot read filter continuation {}: {error}",
            state_path.display()
        )
    })?;
    let state = json::parse(&text).map_err(|error| error.to_string())?;
    let filter = NativeParticleFilter::from_continuation(config.clone(), engines, &state)
        .map_err(|error| error.to_string())?;
    let target = arguments
        .value("until")
        .or_else(|| arguments.value("days"))
        .map(|value| {
            value
                .parse::<f64>()
                .map_err(|_| "filter target time must be a number".to_string())
        })
        .transpose()?
        .unwrap_or(config.horizon_days);
    Ok((filter, config, target))
}

fn filter_resume_config(
    arguments: &Arguments,
    checkpoint: &Path,
) -> Result<SimulationConfig, String> {
    if let Some(path) = arguments.value("config") {
        return SimulationConfig::load(path).map_err(|error| error.to_string());
    }
    let parent = checkpoint
        .parent()
        .ok_or_else(|| "filter checkpoint has no parent directory".to_string())?;
    SimulationConfig::load(parent.join("config.json")).map_err(|error| error.to_string())
}

#[derive(Clone, Debug)]
struct TimedObservation {
    time: f64,
    observation: Observation,
}

fn load_observations(arguments: &Arguments) -> Result<Vec<TimedObservation>, String> {
    let Some(path) = arguments.value("observations").map(PathBuf::from) else {
        return Ok(Vec::new());
    };
    let text = fs::read_to_string(&path)
        .map_err(|error| format!("cannot read observations {}: {error}", path.display()))?;

    let mut observations = if let Ok(document) = json::parse(&text) {
        let entries =
            match &document {
                JsonValue::Array(values) => values.iter().collect::<Vec<_>>(),
                JsonValue::Object(object) => match object.get("observations") {
                    Some(JsonValue::Array(values)) => values.iter().collect::<Vec<_>>(),
                    Some(_) => return Err("observations.observations must be an array".to_string()),
                    None => vec![&document],
                },
                _ => return Err(
                    "observations must be an array or an object containing an observations array"
                        .to_string(),
                ),
            };
        entries
            .into_iter()
            .enumerate()
            .map(|(index, value)| parse_timed_observation(value, index))
            .collect::<Result<Vec<_>, _>>()?
    } else {
        let mut rows = Vec::new();
        for (line_number, line) in text.lines().enumerate() {
            if line.trim().is_empty() {
                continue;
            }
            let value = json::parse(line).map_err(|error| {
                format!(
                    "cannot parse observations JSON or JSONL (line {}): {error}",
                    line_number + 1
                )
            })?;
            rows.push(parse_timed_observation(&value, line_number + 1)?);
        }
        rows
    };

    observations.sort_by(|left, right| left.time.total_cmp(&right.time));
    Ok(observations)
}

fn parse_timed_observation(value: &JsonValue, index: usize) -> Result<TimedObservation, String> {
    let object = value
        .as_object()
        .ok_or_else(|| format!("observation {index} must be an object"))?;
    let time = observation_f64(object, "time")?;
    let kind = ["type", "kind", "observation_type"]
        .iter()
        .find_map(|key| object.get(*key).and_then(JsonValue::as_str))
        .ok_or_else(|| format!("observation {index} is missing type"))?
        .to_ascii_lowercase();
    let observation = match kind.as_str() {
        "binary" | "binary_activity" | "binary-activity" | "activity" => {
            Observation::BinaryActivity {
                observed: object
                    .get("observed")
                    .and_then(JsonValue::as_bool)
                    .ok_or_else(|| {
                        format!("observation {index} binary activity observed must be boolean")
                    })?,
                hazard: nonnegative_observation_f64(object, "hazard")?,
                opportunities: nonnegative_observation_f64(object, "opportunities")?,
            }
        }
        "control" | "gaussian_control" | "gaussian-control" => Observation::GaussianControl {
            actor: observation_u8(object, "actor")?,
            observed: observation_f64(object, "observed")?,
            sigma: positive_observation_f64(object, "sigma")?,
        },
        "insurgent_personnel"
        | "gaussian_insurgent_personnel"
        | "gaussian-insurgent-personnel"
        | "personnel" => Observation::GaussianInsurgentPersonnel {
            observed: nonnegative_observation_f64(object, "observed")?,
            sigma: positive_observation_f64(object, "sigma")?,
        },
        _ => return Err(format!("observation {index} has unsupported type '{kind}'")),
    };
    Ok(TimedObservation { time, observation })
}

fn observation_f64(object: &BTreeMap<String, JsonValue>, key: &str) -> Result<f64, String> {
    object
        .get(key)
        .and_then(JsonValue::as_f64)
        .filter(|value| value.is_finite())
        .ok_or_else(|| format!("observation field {key} must be a finite number"))
}

fn nonnegative_observation_f64(
    object: &BTreeMap<String, JsonValue>,
    key: &str,
) -> Result<f64, String> {
    let value = observation_f64(object, key)?;
    if value < 0.0 {
        return Err(format!("observation field {key} must be nonnegative"));
    }
    Ok(value)
}

fn positive_observation_f64(
    object: &BTreeMap<String, JsonValue>,
    key: &str,
) -> Result<f64, String> {
    let value = observation_f64(object, key)?;
    if value <= 0.0 {
        return Err(format!("observation field {key} must be positive"));
    }
    Ok(value)
}

fn observation_u8(object: &BTreeMap<String, JsonValue>, key: &str) -> Result<u8, String> {
    object
        .get(key)
        .and_then(JsonValue::as_u64)
        .and_then(|value| u8::try_from(value).ok())
        .ok_or_else(|| format!("observation field {key} must be an integer in 0..=255"))
}

fn filter_update_json(update: &FilterUpdate) -> JsonValue {
    let mut value = JsonValue::object();
    value.insert("time", JsonValue::number(update.time));
    value.insert("log_normalizer", finite_or_null(update.log_normalizer));
    value.insert("effective_sample_size", finite_or_null(update.ess));
    value.insert("resampled", JsonValue::Bool(update.resampled));
    let mut parents = JsonValue::Array(Vec::with_capacity(update.parent_indices.len()));
    if let JsonValue::Array(values) = &mut parents {
        values.extend(
            update
                .parent_indices
                .iter()
                .map(|parent| JsonValue::integer(*parent as u64)),
        );
    }
    value.insert("parent_indices", parents);
    let mut ancestry = JsonValue::Array(Vec::with_capacity(update.ancestry.len()));
    if let JsonValue::Array(values) = &mut ancestry {
        values.extend(
            update
                .ancestry
                .iter()
                .map(|lineage| JsonValue::string(lineage.clone())),
        );
    }
    value.insert("ancestry", ancestry);
    value
}

fn finite_or_null(value: f64) -> JsonValue {
    if value.is_finite() {
        JsonValue::number(value)
    } else {
        JsonValue::Null
    }
}

fn forecast(arguments: &Arguments) -> Result<(), String> {
    let config = config(arguments)?;
    let particles = arguments.usize("particles", 4)?;
    let branches = arguments.usize("branches", 3)?;
    let from = arguments.f64("from", 0.0)?;
    let until = arguments.f64("until", config.horizon_days)?;
    let mut parents = Vec::with_capacity(particles);
    for index in 0..particles {
        let mut parent_config = config.clone();
        parent_config.seed = pineland_core::rng::seed_from_namespace(
            config.seed,
            &config.random_stream_namespace,
            &format!("forecast-parent-{index}"),
        );
        let mut engine = SimulationEngine::new(parent_config).map_err(|error| error.to_string())?;
        engine
            .advance_until(from)
            .map_err(|error| error.to_string())?;
        engine.particle.logical_id = index as u64;
        engine.particle.lineage = format!("root.{index}");
        engine.particle.ancestry = vec![index as u64];
        parents.push(engine);
    }
    let result = run_branches(&parents, until, branches).map_err(|error| error.to_string())?;
    let output = PathBuf::from(arguments.string("output", "outputs/native-forecast"));
    let mut value = JsonValue::object();
    let mut rows = JsonValue::Array(Vec::new());
    if let JsonValue::Array(values) = &mut rows {
        values.extend(result.branches);
    }
    value.insert("branches", rows);
    value.insert("means", result.means);
    write_json(output.join("forecast.json"), &value).map_err(|error| error.to_string())?;
    println!("{}", value.to_pretty());
    Ok(())
}

fn inspect_checkpoint(arguments: &Arguments) -> Result<(), String> {
    let path = checkpoint_argument(arguments, "inspect-checkpoint")?;
    let (manifest, particles) =
        CheckpointStore::read_directory(&path).map_err(|error| error.to_string())?;
    let mut result = manifest.to_json();
    result.insert("particle_count", JsonValue::integer(particles.len() as u64));
    let mut hashes = JsonValue::Array(Vec::new());
    if let JsonValue::Array(values) = &mut hashes {
        for particle in particles {
            values.push(JsonValue::string(particle.state_hash()));
        }
    }
    result.insert("state_hashes", hashes);
    println!("{}", result.to_pretty());
    Ok(())
}

fn hash_state(arguments: &Arguments) -> Result<(), String> {
    let positional_checkpoint = arguments
        .positional
        .first()
        .map(Path::new)
        .is_some_and(|path| path.is_dir() || path.join("manifest.json").is_file());
    if arguments.value("checkpoint").is_some() || positional_checkpoint {
        let path = checkpoint_argument(arguments, "hash-state")?;
        let (_manifest, particles) =
            CheckpointStore::read_directory(path).map_err(|error| error.to_string())?;
        for particle in particles {
            println!("{}", particle.state_hash());
        }
        return Ok(());
    }
    let engine = SimulationEngine::new(config(arguments)?).map_err(|error| error.to_string())?;
    println!("{}", engine.state_hash());
    Ok(())
}

fn benchmark(arguments: &Arguments) -> Result<(), String> {
    let mut config = config(arguments)?;
    let particles = arguments.usize("particles", 768)?;
    let days = arguments.f64("days", 7.0)?;
    config.horizon_days = days;
    let threads = thread_count(arguments)?;
    let start = Instant::now();
    let mut filter =
        NativeParticleFilter::new(config, particles).map_err(|error| error.to_string())?;
    filter.set_threads(threads);
    filter
        .update(days, None)
        .map_err(|error| error.to_string())?;
    let elapsed = start.elapsed().as_secs_f64().max(1e-12);
    let hash_input = filter
        .particles
        .iter()
        .flat_map(|engine| engine.state_hash().into_bytes())
        .collect::<Vec<_>>();
    let mut result = JsonValue::object();
    let workload_pwb = particles as f64 * days / 7.0;
    result.insert("workload_pwb", JsonValue::number(workload_pwb));
    result.insert("wall_seconds", JsonValue::number(elapsed));
    result.insert("pwb_per_second", JsonValue::number(workload_pwb / elapsed));
    result.insert("particles", JsonValue::integer(particles as u64));
    result.insert("days", JsonValue::number(days));
    result.insert("threads", JsonValue::integer(threads as u64));
    result.insert("backend", JsonValue::string("rayon"));
    result.insert(
        "state_hash",
        JsonValue::string(sha256::digest_hex(&hash_input)),
    );
    if let Some(path) = arguments.value("output") {
        write_json(path, &result).map_err(|error| error.to_string())?;
    }
    println!("{}", result.to_pretty());
    Ok(())
}

fn checkpoint_argument(arguments: &Arguments, command: &str) -> Result<PathBuf, String> {
    arguments
        .value("checkpoint")
        .map(PathBuf::from)
        .or_else(|| arguments.positional.first().map(PathBuf::from))
        .ok_or_else(|| format!("{command} requires a checkpoint directory"))
}

fn topology_for_particle(particle: &pineland_core::state::ParticleState) -> StaticTopology {
    let locality_count = particle.locality.population.len().max(1);
    let zones_per_locality = (particle.zones.population_share.len() / locality_count).max(1);
    StaticTopology::synthetic(locality_count, zones_per_locality)
}

fn print_help() {
    println!("pineland {VERSION}");
    println!();
    println!("Commands:");
    println!("  validate-config [config.json]");
    println!("  generate [config.json] --output DIR");
    println!("  run [config.json] --seed N --days N --output DIR");
    println!("  resume CHECKPOINT_DIR --until N --output DIR");
    println!("  filter [config.json] --particles N --days N --observations FILE --output DIR");
    println!("  filter --checkpoint CHECKPOINT_DIR --until N --observations FILE --output DIR");
    println!(
        "  filter [config.json] --mpi --particles N --days N --observations FILE --output DIR"
    );
    println!("  forecast [config.json] --particles N --branches N --until N");
    println!("  inspect-checkpoint CHECKPOINT_DIR");
    println!("  hash-state [config.json|CHECKPOINT_DIR]");
    println!("  benchmark [config.json] --particles N --days N --threads N");
    println!("  version");
    println!();
    println!("Observations accept JSON arrays, {{\"observations\": [...]}} documents, or JSONL.");
    println!("The executable is self-contained and does not require Python.");
}

#[cfg(test)]
mod tests {
    use super::{json, parse_timed_observation, Observation};

    #[test]
    fn observation_document_decodes_all_native_likelihoods() {
        let binary = json::parse(
            r#"{"time":1,"type":"binary_activity","observed":true,"hazard":0.2,"opportunities":1}"#,
        )
        .unwrap();
        let control = json::parse(
            r#"{"time":2,"kind":"gaussian_control","actor":1,"observed":0.6,"sigma":0.2}"#,
        )
        .unwrap();
        let personnel = json::parse(
            r#"{"time":3,"observation_type":"gaussian_insurgent_personnel","observed":12,"sigma":4}"#,
        )
        .unwrap();
        assert!(matches!(
            parse_timed_observation(&binary, 0).unwrap().observation,
            Observation::BinaryActivity { .. }
        ));
        assert!(matches!(
            parse_timed_observation(&control, 1).unwrap().observation,
            Observation::GaussianControl { actor: 1, .. }
        ));
        assert!(matches!(
            parse_timed_observation(&personnel, 2).unwrap().observation,
            Observation::GaussianInsurgentPersonnel { .. }
        ));
    }

    #[test]
    fn observation_document_rejects_invalid_support_parameters() {
        let value = json::parse(
            r#"{"time":1,"type":"gaussian_control","actor":0,"observed":0.6,"sigma":0}"#,
        )
        .unwrap();
        assert!(parse_timed_observation(&value, 0).is_err());
    }
}
