//! Analysis-facing file products for Pineland Native.

pub mod checkpoint;
pub mod config;
pub mod manifest;
pub mod parquet;

use pineland_core::checkpoint::CheckpointStore;
use pineland_core::json::JsonValue;
use pineland_core::provenance::ProvenanceManifest;
use pineland_core::sha256;
use pineland_model::SimulationEngine;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Clone, Debug, PartialEq)]
pub struct RunArtifacts {
    pub output: PathBuf,
    pub summary: PathBuf,
    pub metadata: PathBuf,
    pub checkpoint: PathBuf,
}

pub fn write_json(path: impl AsRef<Path>, value: &JsonValue) -> io::Result<()> {
    let path = path.as_ref();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let temp = path.with_extension(format!("tmp-{nonce}"));
    fs::write(&temp, value.to_pretty())?;
    replace_file(&temp, path)
}

pub fn write_jsonl(path: impl AsRef<Path>, rows: &[JsonValue]) -> io::Result<()> {
    let mut text = String::new();
    for row in rows {
        text.push_str(&row.to_compact());
        text.push('\n');
    }
    let path = path.as_ref();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?
    }
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let temp = path.with_extension(format!("tmp-{nonce}"));
    fs::write(&temp, text)?;
    replace_file(&temp, path)
}

pub fn write_run(
    output: impl AsRef<Path>,
    engine: &SimulationEngine,
    mut provenance: ProvenanceManifest,
) -> io::Result<RunArtifacts> {
    let output = output.as_ref();
    fs::create_dir_all(output)?;
    let summary_path = output.join("summary.json");
    write_json(&summary_path, &engine.summary())?;
    let config_path = output.join("config.json");
    write_json(&config_path, &engine.config.to_json())?;
    let events = engine
        .particle
        .event_log
        .iter()
        .map(|event| {
            let mut row = JsonValue::object();
            row.insert("time", JsonValue::number(event.time));
            row.insert("sequence", JsonValue::integer(event.sequence));
            row.insert("kind", JsonValue::string(&event.kind));
            row.insert("locality", JsonValue::integer(event.locality));
            row.insert("value", JsonValue::number(event.value));
            row
        })
        .collect::<Vec<_>>();
    write_jsonl(output.join("events.jsonl"), &events)?;
    let observations = engine
        .particle
        .observations
        .iter()
        .map(|item| {
            let mut row = JsonValue::object();
            row.insert("time", JsonValue::number(item.time));
            row.insert("kind", JsonValue::integer(item.kind));
            row.insert("locality", JsonValue::integer(item.locality));
            row.insert("actor", JsonValue::integer(item.actor));
            row.insert("value", JsonValue::number(item.value));
            row.insert("confidence", JsonValue::number(item.confidence));
            row
        })
        .collect::<Vec<_>>();
    write_jsonl(output.join("observations.jsonl"), &observations)?;
    let checkpoint_dir = output.join(format!("checkpoint_{:04}", engine.particle.filter_boundary));
    let _ = CheckpointStore::write_directory(
        &checkpoint_dir,
        std::slice::from_ref(&engine.particle),
        engine.config.canonical_hash(),
        engine.model_hash.clone(),
        binary_hash().unwrap_or_else(|_| "unknown".to_string()),
        0,
        1,
    )
    .map_err(|e| io::Error::other(e.to_string()))?;
    provenance.finish();
    let mut metadata = JsonValue::object();
    metadata.insert("schema", JsonValue::string("pineland-native-v1"));
    metadata.insert("engine", JsonValue::string("pineland-cli"));
    metadata.insert(
        "configuration_hash",
        JsonValue::string(engine.config.canonical_hash()),
    );
    metadata.insert("model_hash", JsonValue::string(&engine.model_hash));
    metadata.insert("provenance_hash", JsonValue::string(provenance.hash()));
    metadata.insert("provenance", provenance.to_json());
    metadata.insert("summary_file", JsonValue::string("summary.json"));
    write_json(output.join("run_metadata.json"), &metadata)?;
    Ok(RunArtifacts {
        output: output.to_path_buf(),
        summary: summary_path,
        metadata: output.join("run_metadata.json"),
        checkpoint: checkpoint_dir,
    })
}

pub fn binary_hash() -> io::Result<String> {
    let exe = std::env::current_exe()?;
    Ok(sha256::digest_hex(&fs::read(exe)?))
}

fn replace_file(temp: &Path, destination: &Path) -> io::Result<()> {
    #[cfg(windows)]
    if destination.exists() {
        fs::remove_file(destination)?;
    }
    fs::rename(temp, destination)
}
