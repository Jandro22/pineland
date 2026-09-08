//! Versioned dense checkpoint files.
//!
//! A checkpoint is a schema-owned binary payload, never a memory image.  The
//! manifest is committed last, after the shard has been written, flushed, and
//! checksummed.  This makes interrupted writes distinguishable from valid
//! restart points on local disks and shared filesystems.

use crate::json::JsonValue;
use crate::rng::{PyRandomCompat, RngState, RngStreams};
use crate::sha256;
use crate::state::{
    decode_event, encode_event, BeliefKey, ByteReader, Counters, EventRecord, ObservationRecord,
    ParticleState, StateError,
};
use std::collections::BTreeMap;
use std::fmt;
use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

pub const CHECKPOINT_MAGIC: &[u8; 8] = b"PINELAND";
pub const CHECKPOINT_VERSION: u32 = 1;

#[derive(Clone, Debug, PartialEq)]
pub struct CheckpointManifest {
    pub schema_version: u32,
    pub model_hash: String,
    pub binary_hash: String,
    pub configuration_hash: String,
    pub shard: String,
    pub shard_sha256: String,
    pub shards: Vec<String>,
    pub shard_sha256s: Vec<String>,
    pub state_hash: String,
    pub simulation_time: f64,
    pub filter_boundary: u64,
    pub rank: u32,
    pub world_size: u32,
    pub complete: bool,
    pub created_unix_seconds: u64,
}

impl CheckpointManifest {
    pub fn to_json(&self) -> JsonValue {
        let mut value = JsonValue::object();
        value.insert("format", JsonValue::string("PINELAND"));
        value.insert("schema_version", JsonValue::integer(self.schema_version));
        value.insert("model_hash", JsonValue::string(&self.model_hash));
        value.insert("binary_hash", JsonValue::string(&self.binary_hash));
        value.insert(
            "configuration_hash",
            JsonValue::string(&self.configuration_hash),
        );
        value.insert("shard", JsonValue::string(&self.shard));
        value.insert("shard_sha256", JsonValue::string(&self.shard_sha256));
        let mut shards = JsonValue::array();
        for shard in &self.shards {
            shards.push(JsonValue::string(shard));
        }
        value.insert("shards", shards);
        let mut checksums = JsonValue::array();
        for checksum in &self.shard_sha256s {
            checksums.push(JsonValue::string(checksum));
        }
        value.insert("shard_sha256s", checksums);
        value.insert("state_hash", JsonValue::string(&self.state_hash));
        value.insert("simulation_time", JsonValue::number(self.simulation_time));
        value.insert("filter_boundary", JsonValue::integer(self.filter_boundary));
        value.insert("rank", JsonValue::integer(self.rank));
        value.insert("world_size", JsonValue::integer(self.world_size));
        value.insert("complete", JsonValue::Bool(self.complete));
        value.insert(
            "created_unix_seconds",
            JsonValue::integer(self.created_unix_seconds),
        );
        value
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum CheckpointError {
    Io(String),
    State(StateError),
    Invalid(String),
}

impl fmt::Display for CheckpointError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(message) => write!(formatter, "checkpoint I/O: {message}"),
            Self::State(error) => error.fmt(formatter),
            Self::Invalid(message) => write!(formatter, "invalid checkpoint: {message}"),
        }
    }
}

impl std::error::Error for CheckpointError {}
impl From<StateError> for CheckpointError {
    fn from(value: StateError) -> Self {
        Self::State(value)
    }
}
impl From<io::Error> for CheckpointError {
    fn from(value: io::Error) -> Self {
        Self::Io(value.to_string())
    }
}

#[derive(Clone, Debug, Default)]
pub struct CheckpointStore;

impl CheckpointStore {
    pub fn encode_particle(particle: &ParticleState) -> Result<Vec<u8>, CheckpointError> {
        particle.validate()?;
        let mut buffer = Vec::new();
        buffer.extend_from_slice(CHECKPOINT_MAGIC);
        buffer.extend_from_slice(&CHECKPOINT_VERSION.to_le_bytes());
        buffer.extend_from_slice(&0x0102_0304u32.to_le_bytes());
        put_string(&mut buffer, &particle.lineage);
        put_u64(&mut buffer, particle.logical_id);
        put_f64(&mut buffer, particle.time);
        put_f64(&mut buffer, particle.weights_log);
        put_u64(&mut buffer, particle.filter_boundary);
        put_u64_vec(&mut buffer, &particle.ancestry);
        encode_locality(&mut buffer, particle);
        encode_people(&mut buffer, particle);
        encode_zones(&mut buffer, particle);
        encode_organizations(&mut buffer, particle);
        encode_formations(&mut buffer, particle);
        encode_patrols(&mut buffer, particle);
        encode_security_posts(&mut buffer, particle);
        encode_footholds(&mut buffer, particle);
        encode_beliefs(&mut buffer, particle);
        encode_logistics(&mut buffer, particle);
        encode_scheduler(&mut buffer, particle);
        encode_rng(&mut buffer, particle);
        encode_counters(&mut buffer, &particle.counters);
        put_u64(&mut buffer, particle.observations.len() as u64);
        for record in &particle.observations {
            put_f64(&mut buffer, record.time);
            buffer.push(record.kind);
            put_u32(&mut buffer, record.locality);
            put_u32(&mut buffer, record.actor);
            put_f64(&mut buffer, record.value);
            put_f64(&mut buffer, record.confidence);
        }
        put_u64(&mut buffer, particle.event_log.len() as u64);
        for record in &particle.event_log {
            put_f64(&mut buffer, record.time);
            put_u64(&mut buffer, record.sequence);
            put_string(&mut buffer, &record.kind);
            put_u32(&mut buffer, record.locality);
            put_f64(&mut buffer, record.value);
        }
        Ok(buffer)
    }

    pub fn decode_particle(bytes: &[u8]) -> Result<ParticleState, CheckpointError> {
        let mut reader = ByteReader::new(bytes);
        if reader.take(8)? != CHECKPOINT_MAGIC {
            return Err(CheckpointError::Invalid("bad magic".to_string()));
        }
        if reader.u32()? != CHECKPOINT_VERSION {
            return Err(CheckpointError::Invalid(
                "unsupported checkpoint version".to_string(),
            ));
        }
        if reader.u32()? != 0x0102_0304 {
            return Err(CheckpointError::Invalid(
                "unsupported endianness".to_string(),
            ));
        }
        let lineage = reader.string()?;
        let logical_id = reader.u64()?;
        let time = reader.f64()?;
        let weights_log = reader.f64()?;
        let filter_boundary = reader.u64()?;
        let ancestry = read_u64_vec(&mut reader)?;
        let mut particle = ParticleState::new(0, 0, 0, 0, 0, RngStreams::new(0, "baseline"));
        particle.lineage = lineage;
        particle.logical_id = logical_id;
        particle.time = time;
        particle.weights_log = weights_log;
        particle.filter_boundary = filter_boundary;
        particle.ancestry = ancestry;
        decode_locality(&mut reader, &mut particle)?;
        decode_people(&mut reader, &mut particle)?;
        decode_zones(&mut reader, &mut particle)?;
        decode_organizations(&mut reader, &mut particle)?;
        decode_formations(&mut reader, &mut particle)?;
        decode_patrols(&mut reader, &mut particle)?;
        decode_security_posts(&mut reader, &mut particle)?;
        decode_footholds(&mut reader, &mut particle)?;
        decode_beliefs(&mut reader, &mut particle)?;
        decode_logistics(&mut reader, &mut particle)?;
        decode_scheduler(&mut reader, &mut particle)?;
        decode_rng(&mut reader, &mut particle)?;
        decode_counters(&mut reader, &mut particle.counters)?;
        let observation_count = bounded_count(reader.u64()?)?;
        particle.observations = Vec::with_capacity(observation_count);
        for _ in 0..observation_count {
            particle.observations.push(ObservationRecord {
                time: reader.f64()?,
                kind: reader.u8()?,
                locality: reader.u32()?,
                actor: reader.u32()?,
                value: reader.f64()?,
                confidence: reader.f64()?,
            });
        }
        let event_count = bounded_count(reader.u64()?)?;
        particle.event_log = Vec::with_capacity(event_count);
        for _ in 0..event_count {
            particle.event_log.push(EventRecord {
                time: reader.f64()?,
                sequence: reader.u64()?,
                kind: reader.string()?,
                locality: reader.u32()?,
                value: reader.f64()?,
            });
        }
        if reader.remaining() != 0 {
            return Err(CheckpointError::Invalid(
                "trailing bytes after particle payload".to_string(),
            ));
        }
        particle.validate()?;
        Ok(particle)
    }

    pub fn write_particle(
        path: impl AsRef<Path>,
        particle: &ParticleState,
    ) -> Result<String, CheckpointError> {
        let bytes = Self::encode_particle(particle)?;
        atomic_write(path.as_ref(), &bytes)?;
        Ok(sha256::digest_hex(&bytes))
    }

    pub fn read_particle(path: impl AsRef<Path>) -> Result<ParticleState, CheckpointError> {
        let bytes = fs::read(path)?;
        Self::decode_particle(&bytes)
    }

    pub fn write_directory(
        directory: impl AsRef<Path>,
        particles: &[ParticleState],
        configuration_hash: impl Into<String>,
        model_hash: impl Into<String>,
        binary_hash: impl Into<String>,
        rank: u32,
        world_size: u32,
    ) -> Result<CheckpointManifest, CheckpointError> {
        let directory = directory.as_ref();
        if world_size == 0 {
            return Err(CheckpointError::Invalid(
                "checkpoint world size must be positive".to_string(),
            ));
        }
        if rank != 0 || world_size != 1 {
            return Err(CheckpointError::Invalid(
                "write_directory is single-rank; write each shard then call finalize_directory"
                    .to_string(),
            ));
        }
        if particles.is_empty() {
            return Err(CheckpointError::Invalid(
                "checkpoint must contain at least one particle".to_string(),
            ));
        }
        fs::create_dir_all(directory)?;
        let shard_name = format!("rank_{rank:04}.pld");
        let shard_path = directory.join(&shard_name);
        let mut bytes = Vec::new();
        bytes.extend_from_slice(b"PLSHARD1");
        put_u64(&mut bytes, particles.len() as u64);
        for particle in particles {
            let encoded = Self::encode_particle(particle)?;
            put_u64(&mut bytes, encoded.len() as u64);
            bytes.extend_from_slice(&encoded);
        }
        atomic_write(&shard_path, &bytes)?;
        let shard_sha256 = sha256::digest_hex(&bytes);
        let state_hash = if particles.len() == 1 {
            particles[0].state_hash()
        } else {
            sha256::digest_hex(
                &particles
                    .iter()
                    .flat_map(|item| item.state_hash().into_bytes())
                    .collect::<Vec<_>>(),
            )
        };
        let simulation_time = aggregate_simulation_time(particles);
        let manifest = CheckpointManifest {
            schema_version: CHECKPOINT_VERSION,
            model_hash: model_hash.into(),
            binary_hash: binary_hash.into(),
            configuration_hash: configuration_hash.into(),
            shard: shard_name.clone(),
            shard_sha256: shard_sha256.clone(),
            shards: vec![shard_name],
            shard_sha256s: vec![shard_sha256],
            state_hash,
            simulation_time,
            filter_boundary: particles
                .iter()
                .map(|p| p.filter_boundary)
                .max()
                .unwrap_or(0),
            rank,
            world_size,
            complete: true,
            created_unix_seconds: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs(),
        };
        let manifest_path = directory.join("manifest.json");
        atomic_write(&manifest_path, manifest.to_json().to_pretty().as_bytes())?;
        Ok(manifest)
    }

    /// Write one rank-owned shard.  This operation is safe for concurrent
    /// ranks because it touches only the caller's deterministic filename.
    pub fn write_shard(
        directory: impl AsRef<Path>,
        particles: &[ParticleState],
        rank: u32,
    ) -> Result<(String, String), CheckpointError> {
        let directory = directory.as_ref();
        fs::create_dir_all(directory)?;
        let shard_name = format!("rank_{rank:04}.pld");
        let bytes = encode_shard(particles)?;
        atomic_write(&directory.join(&shard_name), &bytes)?;
        Ok((shard_name, sha256::digest_hex(&bytes)))
    }

    /// Read and validate one rank shard without materializing the other ranks.
    /// This is useful for distributed restart paths that already have a
    /// validated manifest and want to keep memory proportional to the local
    /// particle interval.
    pub fn read_shard(
        directory: impl AsRef<Path>,
        rank: u32,
    ) -> Result<Vec<ParticleState>, CheckpointError> {
        let shard_name = format!("rank_{rank:04}.pld");
        let bytes = fs::read(directory.as_ref().join(&shard_name))?;
        decode_shard(&bytes)
    }

    /// Validate all rank shards and atomically publish the complete manifest.
    /// A manifest is never written when a rank is missing or a shard cannot be
    /// decoded, which lets a restart distinguish an interrupted job from a
    /// valid checkpoint directory.
    pub fn finalize_directory(
        directory: impl AsRef<Path>,
        configuration_hash: impl Into<String>,
        model_hash: impl Into<String>,
        binary_hash: impl Into<String>,
        world_size: u32,
    ) -> Result<CheckpointManifest, CheckpointError> {
        let directory = directory.as_ref();
        if world_size == 0 {
            return Err(CheckpointError::Invalid(
                "checkpoint world size must be positive".to_string(),
            ));
        }
        let mut shard_names = fs::read_dir(directory)?
            .flatten()
            .filter_map(|entry| {
                let name = entry.file_name().to_string_lossy().to_string();
                (name.starts_with("rank_") && name.ends_with(".pld")).then_some(name)
            })
            .collect::<Vec<_>>();
        shard_names.sort();
        if shard_names.len() != world_size as usize {
            return Err(CheckpointError::Invalid(format!(
                "expected {world_size} rank shards, found {}",
                shard_names.len()
            )));
        }
        let expected_names = (0..world_size)
            .map(|rank| format!("rank_{rank:04}.pld"))
            .collect::<Vec<_>>();
        if shard_names != expected_names {
            return Err(CheckpointError::Invalid(
                "rank shard set is not contiguous from rank_0000".to_string(),
            ));
        }
        let mut particles = Vec::new();
        let mut checksums = Vec::with_capacity(shard_names.len());
        for shard in &shard_names {
            let bytes = fs::read(directory.join(shard))?;
            checksums.push(sha256::digest_hex(&bytes));
            particles.extend(decode_shard(&bytes)?);
        }
        let state_hash = aggregate_state_hash(&particles);
        if particles.is_empty() {
            return Err(CheckpointError::Invalid(
                "checkpoint must contain at least one particle".to_string(),
            ));
        }
        let simulation_time = aggregate_simulation_time(&particles);
        let manifest = CheckpointManifest {
            schema_version: CHECKPOINT_VERSION,
            model_hash: model_hash.into(),
            binary_hash: binary_hash.into(),
            configuration_hash: configuration_hash.into(),
            shard: shard_names.first().cloned().unwrap_or_default(),
            shard_sha256: checksums.first().cloned().unwrap_or_default(),
            shards: shard_names,
            shard_sha256s: checksums,
            state_hash,
            simulation_time,
            filter_boundary: particles
                .iter()
                .map(|particle| particle.filter_boundary)
                .max()
                .unwrap_or(0),
            rank: 0,
            world_size,
            complete: true,
            created_unix_seconds: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs(),
        };
        atomic_write(
            &directory.join("manifest.json"),
            manifest.to_json().to_pretty().as_bytes(),
        )?;
        Ok(manifest)
    }

    pub fn read_directory(
        directory: impl AsRef<Path>,
    ) -> Result<(CheckpointManifest, Vec<ParticleState>), CheckpointError> {
        let directory = directory.as_ref();
        let manifest_text = fs::read_to_string(directory.join("manifest.json"))?;
        let manifest_value = crate::json::parse(&manifest_text)
            .map_err(|e| CheckpointError::Invalid(e.to_string()))?;
        let object = manifest_value
            .as_object()
            .ok_or_else(|| CheckpointError::Invalid("manifest is not an object".to_string()))?;
        if object.get("format").and_then(|v| v.as_str()) != Some("PINELAND") {
            return Err(CheckpointError::Invalid("manifest format".to_string()));
        }
        let shards = match object
            .get("shards")
            .and_then(|value| value.as_array())
            .map(|values| {
                values
                    .iter()
                    .filter_map(|value| value.as_str().map(str::to_string))
                    .collect::<Vec<_>>()
            })
            .filter(|values| !values.is_empty())
        {
            Some(values) => values,
            None => vec![string_field(object, "shard")?],
        };
        let shard_sha256s = match object
            .get("shard_sha256s")
            .and_then(|value| value.as_array())
            .map(|values| {
                values
                    .iter()
                    .filter_map(|value| value.as_str().map(str::to_string))
                    .collect::<Vec<_>>()
            })
            .filter(|values| !values.is_empty())
        {
            Some(values) => values,
            None => vec![string_field(object, "shard_sha256")?],
        };
        if shards.len() != shard_sha256s.len() {
            return Err(CheckpointError::Invalid(
                "manifest shard/checksum count mismatch".to_string(),
            ));
        }
        let manifest = CheckpointManifest {
            schema_version: object
                .get("schema_version")
                .and_then(|v| v.as_u64())
                .unwrap_or(0) as u32,
            model_hash: string_field(object, "model_hash")?,
            binary_hash: string_field(object, "binary_hash")?,
            configuration_hash: string_field(object, "configuration_hash")?,
            shard: shards.first().cloned().unwrap_or_default(),
            shard_sha256: shard_sha256s.first().cloned().unwrap_or_default(),
            shards,
            shard_sha256s,
            state_hash: string_field(object, "state_hash")?,
            simulation_time: object
                .get("simulation_time")
                .and_then(|v| v.as_f64())
                .unwrap_or(0.0),
            filter_boundary: object
                .get("filter_boundary")
                .and_then(|v| v.as_u64())
                .unwrap_or(0),
            rank: object.get("rank").and_then(|v| v.as_u64()).unwrap_or(0) as u32,
            world_size: object
                .get("world_size")
                .and_then(|v| v.as_u64())
                .unwrap_or(1) as u32,
            complete: object
                .get("complete")
                .and_then(|v| v.as_bool())
                .unwrap_or(false),
            created_unix_seconds: object
                .get("created_unix_seconds")
                .and_then(|v| v.as_u64())
                .unwrap_or(0),
        };
        if !manifest.complete || manifest.schema_version != CHECKPOINT_VERSION {
            return Err(CheckpointError::Invalid(
                "manifest is incomplete or unsupported".to_string(),
            ));
        }
        if manifest.world_size == 0 || manifest.shards.len() != manifest.world_size as usize {
            return Err(CheckpointError::Invalid(
                "manifest does not list every rank shard".to_string(),
            ));
        }
        if manifest.rank != 0
            || manifest.shard != manifest.shards.first().cloned().unwrap_or_default()
            || manifest.shard_sha256 != manifest.shard_sha256s.first().cloned().unwrap_or_default()
            || !manifest.simulation_time.is_finite()
        {
            return Err(CheckpointError::Invalid(
                "manifest aggregate fields are inconsistent".to_string(),
            ));
        }
        let mut particles = Vec::new();
        for (rank, (shard, checksum)) in manifest
            .shards
            .iter()
            .zip(&manifest.shard_sha256s)
            .enumerate()
        {
            if shard != &format!("rank_{rank:04}.pld") {
                return Err(CheckpointError::Invalid(
                    "manifest rank shards are not in canonical order".to_string(),
                ));
            }
            if Path::new(shard).file_name().and_then(|name| name.to_str()) != Some(shard.as_str()) {
                return Err(CheckpointError::Invalid(format!(
                    "invalid shard path {shard}"
                )));
            }
            let bytes = fs::read(directory.join(shard))?;
            if sha256::digest_hex(&bytes) != *checksum {
                return Err(CheckpointError::Invalid(format!(
                    "shard checksum mismatch for {shard}"
                )));
            }
            particles.extend(decode_shard(&bytes)?);
        }
        let expected_hash = aggregate_state_hash(&particles);
        if expected_hash != manifest.state_hash {
            return Err(CheckpointError::Invalid(
                "manifest state hash mismatch".to_string(),
            ));
        }
        if particles.len() > 1
            && particles
                .iter()
                .enumerate()
                .any(|(index, particle)| particle.logical_id != index as u64)
        {
            return Err(CheckpointError::Invalid(
                "checkpoint particles are not in canonical logical order".to_string(),
            ));
        }
        if aggregate_simulation_time(&particles).to_bits() != manifest.simulation_time.to_bits() {
            return Err(CheckpointError::Invalid(
                "manifest simulation time mismatch".to_string(),
            ));
        }
        if particles
            .iter()
            .map(|particle| particle.filter_boundary)
            .max()
            .unwrap_or(0)
            != manifest.filter_boundary
        {
            return Err(CheckpointError::Invalid(
                "manifest filter boundary mismatch".to_string(),
            ));
        }
        Ok((manifest, particles))
    }
}

fn encode_shard(particles: &[ParticleState]) -> Result<Vec<u8>, CheckpointError> {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(b"PLSHARD1");
    put_u64(&mut bytes, particles.len() as u64);
    for particle in particles {
        let encoded = CheckpointStore::encode_particle(particle)?;
        put_u64(&mut bytes, encoded.len() as u64);
        bytes.extend_from_slice(&encoded);
    }
    Ok(bytes)
}
fn decode_shard(bytes: &[u8]) -> Result<Vec<ParticleState>, CheckpointError> {
    let mut reader = ByteReader::new(bytes);
    if reader.take(8)? != b"PLSHARD1" {
        return Err(CheckpointError::Invalid("bad shard magic".to_string()));
    }
    let count = bounded_count(reader.u64()?)?;
    let mut particles = Vec::with_capacity(count);
    for _ in 0..count {
        let length = bounded_count(reader.u64()?)?;
        particles.push(CheckpointStore::decode_particle(reader.take(length)?)?);
    }
    if reader.remaining() != 0 {
        return Err(CheckpointError::Invalid("trailing shard bytes".to_string()));
    }
    Ok(particles)
}
fn aggregate_state_hash(particles: &[ParticleState]) -> String {
    if particles.len() == 1 {
        return particles[0].state_hash();
    }
    sha256::digest_hex(
        &particles
            .iter()
            .flat_map(|particle| particle.state_hash().into_bytes())
            .collect::<Vec<_>>(),
    )
}
fn aggregate_simulation_time(particles: &[ParticleState]) -> f64 {
    particles
        .iter()
        .map(|particle| particle.time)
        .fold(None, |current, time| {
            Some(current.map_or(time, |value: f64| value.max(time)))
        })
        .unwrap_or(0.0)
}
fn string_field(
    object: &BTreeMap<String, JsonValue>,
    name: &str,
) -> Result<String, CheckpointError> {
    object
        .get(name)
        .and_then(|v| v.as_str())
        .map(str::to_string)
        .ok_or_else(|| CheckpointError::Invalid(format!("manifest missing {name}")))
}
fn bounded_count(value: u64) -> Result<usize, CheckpointError> {
    if value > 100_000_000 {
        Err(CheckpointError::Invalid(
            "declared array is too large".to_string(),
        ))
    } else {
        usize::try_from(value)
            .map_err(|_| CheckpointError::Invalid("array length overflow".to_string()))
    }
}
fn put_u32(buffer: &mut Vec<u8>, value: u32) {
    buffer.extend_from_slice(&value.to_le_bytes())
}
fn put_u64(buffer: &mut Vec<u8>, value: u64) {
    buffer.extend_from_slice(&value.to_le_bytes())
}
fn put_f64(buffer: &mut Vec<u8>, value: f64) {
    buffer.extend_from_slice(&value.to_bits().to_le_bytes())
}
fn put_string(buffer: &mut Vec<u8>, value: &str) {
    put_u64(buffer, value.len() as u64);
    buffer.extend_from_slice(value.as_bytes())
}
fn put_u8_vec(buffer: &mut Vec<u8>, values: &[u8]) {
    put_u64(buffer, values.len() as u64);
    buffer.extend_from_slice(values)
}
fn put_u32_vec(buffer: &mut Vec<u8>, values: &[u32]) {
    put_u64(buffer, values.len() as u64);
    for v in values {
        put_u32(buffer, *v)
    }
}
fn put_u64_vec(buffer: &mut Vec<u8>, values: &[u64]) {
    put_u64(buffer, values.len() as u64);
    for v in values {
        put_u64(buffer, *v)
    }
}
fn put_f64_vec(buffer: &mut Vec<u8>, values: &[f64]) {
    put_u64(buffer, values.len() as u64);
    for v in values {
        put_f64(buffer, *v)
    }
}
fn read_u8_vec(r: &mut ByteReader<'_>) -> Result<Vec<u8>, CheckpointError> {
    let n = bounded_count(r.u64()?)?;
    Ok(r.take(n)?.to_vec())
}
fn read_u32_vec(r: &mut ByteReader<'_>) -> Result<Vec<u32>, CheckpointError> {
    let n = bounded_count(r.u64()?)?;
    let mut v = Vec::with_capacity(n);
    for _ in 0..n {
        v.push(r.u32()?)
    }
    Ok(v)
}
fn read_u64_vec(r: &mut ByteReader<'_>) -> Result<Vec<u64>, CheckpointError> {
    let n = bounded_count(r.u64()?)?;
    let mut v = Vec::with_capacity(n);
    for _ in 0..n {
        v.push(r.u64()?)
    }
    Ok(v)
}
fn read_f64_vec(r: &mut ByteReader<'_>) -> Result<Vec<f64>, CheckpointError> {
    let n = bounded_count(r.u64()?)?;
    let mut v = Vec::with_capacity(n);
    for _ in 0..n {
        v.push(r.f64()?)
    }
    Ok(v)
}
fn atomic_write(path: &Path, bytes: &[u8]) -> Result<(), CheckpointError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?
    }
    let suffix = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let temp = path.with_extension(format!("tmp-{suffix}"));
    {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)?;
        file.write_all(bytes)?;
        file.flush()?;
        file.sync_all()?;
    }
    replace_file(&temp, path)?;
    Ok(())
}
fn replace_file(temp: &Path, path: &Path) -> Result<(), CheckpointError> {
    #[cfg(windows)]
    if path.exists() {
        fs::remove_file(path)?;
    }
    fs::rename(temp, path)?;
    Ok(())
}

fn encode_locality(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.locality;
    for v in [
        &x.population,
        &x.economic_output,
        &x.infrastructure,
        &x.administrative_capacity,
        &x.terrain_friction,
        &x.observability,
        &x.government_control,
        &x.insurgent_control,
        &x.violence,
        &x.disruption,
        &x.displaced_population,
        &x.government_governance,
        &x.insurgent_governance,
    ] {
        put_f64_vec(b, v)
    }
}
fn decode_locality(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.locality;
    x.population = read_f64_vec(r)?;
    x.economic_output = read_f64_vec(r)?;
    x.infrastructure = read_f64_vec(r)?;
    x.administrative_capacity = read_f64_vec(r)?;
    x.terrain_friction = read_f64_vec(r)?;
    x.observability = read_f64_vec(r)?;
    x.government_control = read_f64_vec(r)?;
    x.insurgent_control = read_f64_vec(r)?;
    x.violence = read_f64_vec(r)?;
    x.disruption = read_f64_vec(r)?;
    x.displaced_population = read_f64_vec(r)?;
    x.government_governance = read_f64_vec(r)?;
    x.insurgent_governance = read_f64_vec(r)?;
    Ok(())
}
fn encode_people(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.people;
    put_u32_vec(b, &x.locality);
    put_f64_vec(b, &x.represented_population);
    put_u32_vec(b, &x.household);
    put_f64_vec(b, &x.grievance);
    put_f64_vec(b, &x.fear);
    put_f64_vec(b, &x.efficacy);
    put_f64_vec(b, &x.trust);
    put_u32_vec(b, &x.home);
    put_u32_vec(b, &x.residence);
    put_f64_vec(b, &x.rebel_sympathy)
}
fn decode_people(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.people;
    x.locality = read_u32_vec(r)?;
    x.represented_population = read_f64_vec(r)?;
    x.household = read_u32_vec(r)?;
    x.grievance = read_f64_vec(r)?;
    x.fear = read_f64_vec(r)?;
    x.efficacy = read_f64_vec(r)?;
    x.trust = read_f64_vec(r)?;
    x.home = read_u32_vec(r)?;
    x.residence = read_u32_vec(r)?;
    x.rebel_sympathy = read_f64_vec(r)?;
    Ok(())
}
fn encode_zones(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.zones;
    for v in [
        &x.population_share,
        &x.infrastructure,
        &x.terrain_friction,
        &x.observability,
        &x.government_control,
        &x.insurgent_control,
        &x.government_presence,
        &x.insurgent_presence,
        &x.government_presence_updated_at,
        &x.insurgent_presence_updated_at,
    ] {
        put_f64_vec(b, v)
    }
}
fn decode_zones(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.zones;
    x.population_share = read_f64_vec(r)?;
    x.infrastructure = read_f64_vec(r)?;
    x.terrain_friction = read_f64_vec(r)?;
    x.observability = read_f64_vec(r)?;
    x.government_control = read_f64_vec(r)?;
    x.insurgent_control = read_f64_vec(r)?;
    x.government_presence = read_f64_vec(r)?;
    x.insurgent_presence = read_f64_vec(r)?;
    x.government_presence_updated_at = read_f64_vec(r)?;
    x.insurgent_presence_updated_at = read_f64_vec(r)?;
    Ok(())
}
fn encode_organizations(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.organizations;
    put_u8_vec(b, &x.kind);
    put_u8_vec(b, &x.active);
    for v in [
        &x.capital,
        &x.cohesion,
        &x.discipline,
        &x.accountability,
        &x.local_knowledge,
        &x.persistence,
        &x.mobility,
        &x.institutional_quality,
        &x.external_support,
        &x.member_population,
        &x.founded_at,
    ] {
        put_f64_vec(b, v)
    }
    put_u32_vec(b, &x.succession_count)
}
fn decode_organizations(
    r: &mut ByteReader<'_>,
    p: &mut ParticleState,
) -> Result<(), CheckpointError> {
    let x = &mut p.organizations;
    x.kind = read_u8_vec(r)?;
    x.active = read_u8_vec(r)?;
    x.capital = read_f64_vec(r)?;
    x.cohesion = read_f64_vec(r)?;
    x.discipline = read_f64_vec(r)?;
    x.accountability = read_f64_vec(r)?;
    x.local_knowledge = read_f64_vec(r)?;
    x.persistence = read_f64_vec(r)?;
    x.mobility = read_f64_vec(r)?;
    x.institutional_quality = read_f64_vec(r)?;
    x.external_support = read_f64_vec(r)?;
    x.member_population = read_f64_vec(r)?;
    x.founded_at = read_f64_vec(r)?;
    x.succession_count = read_u32_vec(r)?;
    Ok(())
}
fn encode_formations(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.formations;
    put_u32_vec(b, &x.organization);
    put_u32_vec(b, &x.locality);
    put_u32_vec(b, &x.microzone);
    for v in [
        &x.personnel,
        &x.quality,
        &x.cohesion,
        &x.readiness,
        &x.sustainment,
        &x.information,
        &x.mobility,
        &x.command,
        &x.embeddedness,
        &x.fatigue,
        &x.availability,
        &x.supply_stock,
        &x.supply_capacity,
        &x.cumulative_losses,
    ] {
        put_f64_vec(b, v)
    }
    put_u32_vec(b, &x.home_locality);
    for v in [
        &x.active,
        &x.moving,
        &x.operational_status,
        &x.outside_pineland,
        &x.operational_posture,
    ] {
        put_u8_vec(b, v)
    }
}
fn decode_formations(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.formations;
    x.organization = read_u32_vec(r)?;
    x.locality = read_u32_vec(r)?;
    x.microzone = read_u32_vec(r)?;
    x.personnel = read_f64_vec(r)?;
    x.quality = read_f64_vec(r)?;
    x.cohesion = read_f64_vec(r)?;
    x.readiness = read_f64_vec(r)?;
    x.sustainment = read_f64_vec(r)?;
    x.information = read_f64_vec(r)?;
    x.mobility = read_f64_vec(r)?;
    x.command = read_f64_vec(r)?;
    x.embeddedness = read_f64_vec(r)?;
    x.fatigue = read_f64_vec(r)?;
    x.availability = read_f64_vec(r)?;
    x.supply_stock = read_f64_vec(r)?;
    x.supply_capacity = read_f64_vec(r)?;
    x.cumulative_losses = read_f64_vec(r)?;
    x.home_locality = read_u32_vec(r)?;
    x.active = read_u8_vec(r)?;
    x.moving = read_u8_vec(r)?;
    x.operational_status = read_u8_vec(r)?;
    x.outside_pineland = read_u8_vec(r)?;
    x.operational_posture = read_u8_vec(r)?;
    Ok(())
}
fn encode_patrols(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.patrols;
    put_u32_vec(b, &x.formation);
    put_u32_vec(b, &x.route_position);
    put_u32_vec(b, &x.route_target);
    put_f64_vec(b, &x.last_departure);
    put_f64_vec(b, &x.next_available);
    put_u32_vec(b, &x.detections)
}
fn decode_patrols(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.patrols;
    x.formation = read_u32_vec(r)?;
    x.route_position = read_u32_vec(r)?;
    x.route_target = read_u32_vec(r)?;
    x.last_departure = read_f64_vec(r)?;
    x.next_available = read_f64_vec(r)?;
    x.detections = read_u32_vec(r)?;
    Ok(())
}
fn encode_security_posts(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.security_posts;
    put_u32_vec(b, &x.organization);
    put_u32_vec(b, &x.locality);
    put_u32_vec(b, &x.microzone);
    put_f64_vec(b, &x.presence);
    put_f64_vec(b, &x.detection_rate);
    put_f64_vec(b, &x.reliability);
    put_f64_vec(b, &x.updated_at);
    put_u8_vec(b, &x.staffed)
}
fn decode_security_posts(
    r: &mut ByteReader<'_>,
    p: &mut ParticleState,
) -> Result<(), CheckpointError> {
    let x = &mut p.security_posts;
    x.organization = read_u32_vec(r)?;
    x.locality = read_u32_vec(r)?;
    x.microzone = read_u32_vec(r)?;
    x.presence = read_f64_vec(r)?;
    x.detection_rate = read_f64_vec(r)?;
    x.reliability = read_f64_vec(r)?;
    x.updated_at = read_f64_vec(r)?;
    x.staffed = read_u8_vec(r)?;
    Ok(())
}
fn encode_footholds(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.footholds;
    put_u32_vec(b, &x.organization);
    put_u32_vec(b, &x.locality);
    for v in [
        &x.strength,
        &x.raw_signal,
        &x.membership,
        &x.embeddedness,
        &x.access,
        &x.target_knowledge,
        &x.infrastructure,
        &x.sustainment,
        &x.updated_at,
        &x.first_activated_at,
        &x.last_activated_at,
        &x.cumulative_active_days,
        &x.cumulative_arrivals,
        &x.cumulative_recruits,
        &x.cumulative_actions,
    ] {
        put_f64_vec(b, v)
    }
    put_u32_vec(b, &x.viable_activation_count);
    put_u32_vec(b, &x.renewal_count);
    put_u8_vec(b, &x.active)
}
fn decode_footholds(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.footholds;
    x.organization = read_u32_vec(r)?;
    x.locality = read_u32_vec(r)?;
    x.strength = read_f64_vec(r)?;
    x.raw_signal = read_f64_vec(r)?;
    x.membership = read_f64_vec(r)?;
    x.embeddedness = read_f64_vec(r)?;
    x.access = read_f64_vec(r)?;
    x.target_knowledge = read_f64_vec(r)?;
    x.infrastructure = read_f64_vec(r)?;
    x.sustainment = read_f64_vec(r)?;
    x.updated_at = read_f64_vec(r)?;
    x.first_activated_at = read_f64_vec(r)?;
    x.last_activated_at = read_f64_vec(r)?;
    x.cumulative_active_days = read_f64_vec(r)?;
    x.cumulative_arrivals = read_f64_vec(r)?;
    x.cumulative_recruits = read_f64_vec(r)?;
    x.cumulative_actions = read_f64_vec(r)?;
    x.viable_activation_count = read_u32_vec(r)?;
    x.renewal_count = read_u32_vec(r)?;
    x.active = read_u8_vec(r)?;
    Ok(())
}
fn encode_beliefs(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.beliefs;
    put_u64(b, x.keys.len() as u64);
    for k in &x.keys {
        put_u32(b, k.observer);
        put_u32(b, k.target);
        put_u32(b, k.locality);
        b.push(k.kind)
    }
    for v in [
        &x.presence,
        &x.control,
        &x.confidence,
        &x.updated_at,
        &x.last_reliable_observation_at,
        &x.contradiction,
        &x.source_confidence,
    ] {
        put_f64_vec(b, v)
    }
    put_u32_vec(b, &x.evidence_count);
    put_u32_vec(b, &x.dirty)
}
fn decode_beliefs(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let n = bounded_count(r.u64()?)?;
    let mut keys = Vec::with_capacity(n);
    for _ in 0..n {
        keys.push(BeliefKey {
            observer: r.u32()?,
            target: r.u32()?,
            locality: r.u32()?,
            kind: r.u8()?,
        })
    }
    p.beliefs.keys = keys;
    p.beliefs.presence = read_f64_vec(r)?;
    p.beliefs.control = read_f64_vec(r)?;
    p.beliefs.confidence = read_f64_vec(r)?;
    p.beliefs.updated_at = read_f64_vec(r)?;
    p.beliefs.last_reliable_observation_at = read_f64_vec(r)?;
    p.beliefs.contradiction = read_f64_vec(r)?;
    p.beliefs.source_confidence = read_f64_vec(r)?;
    p.beliefs.evidence_count = read_u32_vec(r)?;
    p.beliefs.dirty = read_u32_vec(r)?;
    Ok(())
}
fn encode_logistics(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.logistics;
    for v in [&x.source_stock, &x.source_capacity, &x.source_production] {
        put_f64_vec(b, v)
    }
    for v in [
        x.in_transit,
        x.cumulative_produced,
        x.cumulative_consumed,
        x.cumulative_lost,
        x.cumulative_shipped,
        x.cumulative_delivered,
    ] {
        put_f64(b, v)
    }
}
fn decode_logistics(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.logistics;
    x.source_stock = read_f64_vec(r)?;
    x.source_capacity = read_f64_vec(r)?;
    x.source_production = read_f64_vec(r)?;
    x.in_transit = r.f64()?;
    x.cumulative_produced = r.f64()?;
    x.cumulative_consumed = r.f64()?;
    x.cumulative_lost = r.f64()?;
    x.cumulative_shipped = r.f64()?;
    x.cumulative_delivered = r.f64()?;
    Ok(())
}
fn encode_scheduler(b: &mut Vec<u8>, p: &ParticleState) {
    put_u64(b, p.scheduler.next_sequence);
    put_u64(b, p.scheduler.processed);
    let events = p.scheduler.events_sorted();
    put_u64(b, events.len() as u64);
    for e in &events {
        encode_event(b, e)
    }
}
fn decode_scheduler(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    p.scheduler = crate::scheduler::Scheduler::new();
    p.scheduler.next_sequence = r.u64()?;
    p.scheduler.processed = r.u64()?;
    let n = bounded_count(r.u64()?)?;
    for _ in 0..n {
        p.scheduler
            .push_with_sequence(decode_event(r)?)
            .map_err(StateError::from)?;
    }
    Ok(())
}
fn encode_rng(b: &mut Vec<u8>, p: &ParticleState) {
    put_u64(b, p.rng.root_seed);
    put_string(b, &p.rng.namespace);
    put_u64(b, p.rng.streams.len() as u64);
    for (name, g) in &p.rng.streams {
        put_string(b, name);
        for word in g.raw_state() {
            put_u32(b, *word)
        }
        put_u32(b, g.raw_index() as u32);
        let state = g.state();
        match state.gauss_next {
            Some(v) => {
                b.push(1);
                put_f64(b, v)
            }
            None => b.push(0),
        }
    }
}
fn decode_rng(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let root = r.u64()?;
    let namespace = r.string()?;
    let n = bounded_count(r.u64()?)?;
    let mut streams = BTreeMap::new();
    for _ in 0..n {
        let name = r.string()?;
        let mut words = [0u32; 624];
        for word in &mut words {
            *word = r.u32()?
        }
        let index = r.u32()?;
        let gauss = if r.u8()? != 0 { Some(r.f64()?) } else { None };
        let g = PyRandomCompat::from_state(RngState {
            words,
            index,
            gauss_next: gauss,
        })
        .map_err(|e| CheckpointError::Invalid(e.to_string()))?;
        streams.insert(name, g);
    }
    p.rng = RngStreams {
        root_seed: root,
        namespace,
        streams,
    };
    Ok(())
}
fn encode_counters(b: &mut Vec<u8>, c: &Counters) {
    put_u64(b, c.event_counts.len() as u64);
    for (k, v) in &c.event_counts {
        put_string(b, k);
        put_u64(b, *v)
    }
    put_u64(b, c.contacts);
    put_u64(b, c.organized_actions);
    put_u64(b, c.recorded_events);
    put_u64(b, c.observations);
    put_f64(b, c.recruitment);
    put_f64(b, c.civilian_harm);
    put_f64(b, c.deaths);
    put_u64(b, c.checkpoints)
}
fn decode_counters(r: &mut ByteReader<'_>, c: &mut Counters) -> Result<(), CheckpointError> {
    let n = bounded_count(r.u64()?)?;
    c.event_counts.clear();
    for _ in 0..n {
        c.event_counts.insert(r.string()?, r.u64()?);
    }
    c.contacts = r.u64()?;
    c.organized_actions = r.u64()?;
    c.recorded_events = r.u64()?;
    c.observations = r.u64()?;
    c.recruitment = r.f64()?;
    c.civilian_harm = r.f64()?;
    c.deaths = r.f64()?;
    c.checkpoints = r.u64()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::CheckpointStore;
    use crate::ids::PatrolId;
    use crate::rng::RngStreams;
    use crate::scheduler::EventPayload;
    use crate::state::{BeliefKey, EventRecord, ObservationRecord, ParticleState};
    use std::time::{SystemTime, UNIX_EPOCH};

    fn representative_particle() -> ParticleState {
        let mut particle =
            ParticleState::new(2, 4, 2, 3, 4, RngStreams::new(99, "checkpoint-test"));
        particle.locality.population[0] = 100.0;
        particle.locality.government_control[0] = 0.8;
        particle.beliefs = crate::state::BeliefState::with_keys(vec![BeliefKey {
            observer: 0,
            target: 3,
            locality: 0,
            kind: 0,
        }]);
        particle.beliefs.confidence[0] = 0.75;
        particle.rng.get_mut("checkpoint").gauss(0.0, 1.0);
        particle
            .scheduler
            .schedule(
                2.5,
                10,
                EventPayload::Patrol {
                    patrol: PatrolId(3),
                },
            )
            .unwrap();
        particle.observations.push(ObservationRecord {
            time: 1.0,
            kind: 1,
            locality: 0,
            actor: 2,
            value: 0.4,
            confidence: 0.7,
        });
        particle.event_log.push(EventRecord {
            time: 1.0,
            sequence: 9,
            kind: "test".to_string(),
            locality: 0,
            value: 1.0,
        });
        particle.counters.contacts = 4;
        particle
            .counters
            .event_counts
            .insert("patrol".to_string(), 2);
        particle.filter_boundary = 12;
        particle.weights_log = -1.25;
        particle.validate().unwrap();
        particle
    }

    #[test]
    fn particle_binary_round_trip_is_exact() {
        let particle = representative_particle();
        let bytes = CheckpointStore::encode_particle(&particle).unwrap();
        let restored = CheckpointStore::decode_particle(&bytes).unwrap();
        assert_eq!(particle, restored);
        assert_eq!(particle.state_hash(), restored.state_hash());
    }

    #[test]
    fn directory_manifest_and_checksum_round_trip() {
        let particle = representative_particle();
        let directory =
            std::env::temp_dir().join(format!("pineland-checkpoint-test-{}", std::process::id()));
        let manifest = CheckpointStore::write_directory(
            &directory,
            std::slice::from_ref(&particle),
            "config",
            "model",
            "binary",
            0,
            1,
        )
        .unwrap();
        let (read_manifest, particles) = CheckpointStore::read_directory(&directory).unwrap();
        assert_eq!(manifest, read_manifest);
        assert_eq!(particles, vec![particle]);
        std::fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn multi_rank_shards_publish_only_after_every_rank_is_valid() {
        let mut first = representative_particle();
        first.logical_id = 0;
        let mut second = representative_particle();
        second.logical_id = 1;
        second.lineage = "root.1".to_string();
        second.time = 3.0;
        second.scheduler.clear();
        second.validate().unwrap();

        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let directory = std::env::temp_dir().join(format!("pineland-checkpoint-shards-{nonce}"));
        CheckpointStore::write_shard(&directory, &[first.clone()], 0).unwrap();
        assert!(
            CheckpointStore::finalize_directory(&directory, "config", "model", "binary", 2)
                .is_err()
        );
        assert!(!directory.join("manifest.json").exists());
        CheckpointStore::write_shard(&directory, &[second.clone()], 1).unwrap();
        let manifest =
            CheckpointStore::finalize_directory(&directory, "config", "model", "binary", 2)
                .unwrap();
        assert_eq!(manifest.shards, vec!["rank_0000.pld", "rank_0001.pld"]);
        let (read_manifest, particles) = CheckpointStore::read_directory(&directory).unwrap();
        assert_eq!(manifest, read_manifest);
        assert_eq!(particles, vec![first, second]);
        std::fs::remove_dir_all(directory).unwrap();
    }
}
