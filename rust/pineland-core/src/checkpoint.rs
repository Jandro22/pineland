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
    decode_event, encode_event, BeliefKey, ByteReader, Counters, EventRecord,
    InformationHistoryEntry, InformationObservation, InformationRelay, ObservationRecord,
    ParticleState, PartnerSupportLedger, PresenceKey, PresenceState, StateError,
    SupportWindowSnapshot,
};
use std::collections::BTreeMap;
use std::fmt;
use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

pub const CHECKPOINT_MAGIC: &[u8; 8] = b"PINELAND";
pub const CHECKPOINT_VERSION: u32 = 15;

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
        encode_households(&mut buffer, particle);
        encode_communities(&mut buffer, particle);
        encode_protos(&mut buffer, particle);
        encode_social_edges(&mut buffer, particle);
        encode_zones(&mut buffer, particle);
        encode_zone_beliefs(&mut buffer, particle);
        encode_organizations(&mut buffer, particle);
        encode_formations(&mut buffer, particle);
        encode_patrols(&mut buffer, particle);
        encode_security_posts(&mut buffer, particle);
        encode_footholds(&mut buffer, particle);
        encode_beliefs(&mut buffer, particle);
        encode_presence_state(&mut buffer, &particle.presence_beliefs);
        encode_presence_state(&mut buffer, &particle.node_presence_beliefs);
        encode_logistics(&mut buffer, particle);
        encode_command_edges(&mut buffer, particle);
        encode_manpower(&mut buffer, particle);
        encode_leaders(&mut buffer, particle);
        encode_political(&mut buffer, particle);
        encode_foreign(&mut buffer, particle);
        encode_foreign_interventions(&mut buffer, particle);
        encode_relations(&mut buffer, particle);
        encode_access_restrictions(&mut buffer, particle);
        encode_scheduler(&mut buffer, particle);
        encode_rng(&mut buffer, particle);
        put_u64(&mut buffer, particle.movement_order_count);
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
        encode_information_state(&mut buffer, particle);
        put_u64(&mut buffer, particle.event_log.len() as u64);
        for record in &particle.event_log {
            put_f64(&mut buffer, record.time);
            put_u64(&mut buffer, record.sequence);
            put_string(&mut buffer, &record.kind);
            put_u32(&mut buffer, record.locality);
            put_f64(&mut buffer, record.value);
        }
        encode_partner_support(&mut buffer, &particle.partner_support);
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
        decode_locality(&mut reader, &mut particle).map_err(|e| section_error("locality", e))?;
        decode_people(&mut reader, &mut particle).map_err(|e| section_error("people", e))?;
        decode_households(&mut reader, &mut particle)
            .map_err(|e| section_error("households", e))?;
        decode_communities(&mut reader, &mut particle)
            .map_err(|e| section_error("communities", e))?;
        decode_protos(&mut reader, &mut particle).map_err(|e| section_error("protos", e))?;
        decode_social_edges(&mut reader, &mut particle)
            .map_err(|e| section_error("social_edges", e))?;
        decode_zones(&mut reader, &mut particle).map_err(|e| section_error("zones", e))?;
        decode_zone_beliefs(&mut reader, &mut particle)
            .map_err(|e| section_error("zone_beliefs", e))?;
        decode_organizations(&mut reader, &mut particle)
            .map_err(|e| section_error("organizations", e))?;
        decode_formations(&mut reader, &mut particle)
            .map_err(|e| section_error("formations", e))?;
        decode_patrols(&mut reader, &mut particle).map_err(|e| section_error("patrols", e))?;
        decode_security_posts(&mut reader, &mut particle)
            .map_err(|e| section_error("security_posts", e))?;
        decode_footholds(&mut reader, &mut particle).map_err(|e| section_error("footholds", e))?;
        decode_beliefs(&mut reader, &mut particle).map_err(|e| section_error("beliefs", e))?;
        decode_presence_state(&mut reader, &mut particle.presence_beliefs)
            .map_err(|e| section_error("presence_beliefs", e))?;
        decode_presence_state(&mut reader, &mut particle.node_presence_beliefs)
            .map_err(|e| section_error("node_presence_beliefs", e))?;
        decode_logistics(&mut reader, &mut particle).map_err(|e| section_error("logistics", e))?;
        decode_command_edges(&mut reader, &mut particle)
            .map_err(|e| section_error("command_edges", e))?;
        decode_manpower(&mut reader, &mut particle).map_err(|e| section_error("manpower", e))?;
        decode_leaders(&mut reader, &mut particle).map_err(|e| section_error("leaders", e))?;
        decode_political(&mut reader, &mut particle).map_err(|e| section_error("political", e))?;
        decode_foreign(&mut reader, &mut particle).map_err(|e| section_error("foreign", e))?;
        decode_foreign_interventions(&mut reader, &mut particle)
            .map_err(|e| section_error("foreign_interventions", e))?;
        decode_relations(&mut reader, &mut particle).map_err(|e| section_error("relations", e))?;
        decode_access_restrictions(&mut reader, &mut particle)
            .map_err(|e| section_error("access_restrictions", e))?;
        decode_scheduler(&mut reader, &mut particle).map_err(|e| section_error("scheduler", e))?;
        decode_rng(&mut reader, &mut particle).map_err(|e| section_error("rng", e))?;
        particle.movement_order_count = reader.u64()?;
        decode_counters(&mut reader, &mut particle.counters)
            .map_err(|e| section_error("counters", e))?;
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
        decode_information_state(&mut reader, &mut particle)?;
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
        decode_partner_support(&mut reader, &mut particle.partner_support)
            .map_err(|e| section_error("partner_support", e))?;
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
fn section_error(section: &str, error: CheckpointError) -> CheckpointError {
    match error {
        CheckpointError::Invalid(message) => {
            CheckpointError::Invalid(format!("{section}: {message}"))
        }
        other => other,
    }
}
fn bounded_count(value: u64) -> Result<usize, CheckpointError> {
    if value > 100_000_000 {
        Err(CheckpointError::Invalid(format!(
            "declared array is too large: {value}"
        )))
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
        &x.district_population,
        &x.economic_output,
        &x.infrastructure,
        &x.administrative_capacity,
        &x.terrain_friction,
        &x.observability,
        &x.government_control,
        &x.insurgent_control,
        &x.organization_control,
        &x.violence,
        &x.disruption,
        &x.displaced_population,
        &x.government_governance,
        &x.insurgent_governance,
        &x.government_security_recruit_pipeline,
        &x.government_security_reserve,
        &x.government_intelligence_penetration,
        &x.government_cumulative_security_recruits,
        &x.government_cumulative_security_deployments,
        &x.government_cumulative_admin_rebuild,
        &x.government_cumulative_underground_disruption,
    ] {
        put_f64_vec(b, v)
    }
    put_u8_vec(b, &x.district_population_is_integer);
}
fn decode_locality(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.locality;
    x.population = read_f64_vec(r)?;
    x.district_population = read_f64_vec(r)?;
    x.economic_output = read_f64_vec(r)?;
    x.infrastructure = read_f64_vec(r)?;
    x.administrative_capacity = read_f64_vec(r)?;
    x.terrain_friction = read_f64_vec(r)?;
    x.observability = read_f64_vec(r)?;
    x.government_control = read_f64_vec(r)?;
    x.insurgent_control = read_f64_vec(r)?;
    x.organization_control = read_f64_vec(r)?;
    x.violence = read_f64_vec(r)?;
    x.disruption = read_f64_vec(r)?;
    x.displaced_population = read_f64_vec(r)?;
    x.government_governance = read_f64_vec(r)?;
    x.insurgent_governance = read_f64_vec(r)?;
    x.government_security_recruit_pipeline = read_f64_vec(r)?;
    x.government_security_reserve = read_f64_vec(r)?;
    x.government_intelligence_penetration = read_f64_vec(r)?;
    x.government_cumulative_security_recruits = read_f64_vec(r)?;
    x.government_cumulative_security_deployments = read_f64_vec(r)?;
    x.government_cumulative_admin_rebuild = read_f64_vec(r)?;
    x.government_cumulative_underground_disruption = read_f64_vec(r)?;
    x.district_population_is_integer = read_u8_vec(r)?;
    Ok(())
}
fn encode_people(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.people;
    put_u32_vec(b, &x.locality);
    put_f64_vec(b, &x.represented_population);
    put_u32_vec(b, &x.household);
    put_u8_vec(b, &x.age);
    put_f64_vec(b, &x.languages);
    put_f64_vec(b, &x.identities);
    put_f64_vec(b, &x.preferences);
    put_f64_vec(b, &x.party_legitimacy);
    put_f64_vec(b, &x.grievance);
    put_f64_vec(b, &x.fear);
    put_f64_vec(b, &x.efficacy);
    put_f64_vec(b, &x.trust);
    put_f64_vec(b, &x.trust_insurgent);
    put_f64_vec(b, &x.resources);
    put_u32_vec(b, &x.home);
    put_u32_vec(b, &x.residence);
    put_f64_vec(b, &x.rebel_sympathy);
    put_u32_vec(b, &x.organization);
    put_f64_vec(b, &x.armed_fraction);
    put_u32_vec(b, &x.community);
    put_u8_vec(b, &x.public_behavior);
    put_f64_vec(b, &x.expected_control);
    put_f64_vec(b, &x.expected_destination_control);
    put_u8_vec(b, &x.expected_destination_control_present);
    put_f64_vec(b, &x.state_legitimacy);
    put_f64_vec(b, &x.government_legitimacy);
    put_f64_vec(b, &x.political_access);
    put_u8_vec(b, &x.displaced);
    put_u32_vec(b, &x.displacement_count);
    put_f64_vec(b, &x.displaced_since);
    put_u32_vec(b, &x.displacement_origin);
    put_f64_vec(b, &x.origin_tie_strength);
    put_u32_vec(b, &x.external_state);
    put_u8_vec(b, &x.migration_status);
    put_f64_vec(b, &x.insurgent_affinity);
    put_f64_vec(b, &x.social_exposure);
}
fn decode_people(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.people;
    x.locality = read_u32_vec(r)?;
    x.represented_population = read_f64_vec(r)?;
    x.household = read_u32_vec(r)?;
    x.age = read_u8_vec(r)?;
    x.languages = read_f64_vec(r)?;
    x.identities = read_f64_vec(r)?;
    x.preferences = read_f64_vec(r)?;
    x.party_legitimacy = read_f64_vec(r)?;
    x.grievance = read_f64_vec(r)?;
    x.fear = read_f64_vec(r)?;
    x.efficacy = read_f64_vec(r)?;
    x.trust = read_f64_vec(r)?;
    x.trust_insurgent = read_f64_vec(r)?;
    x.resources = read_f64_vec(r)?;
    x.home = read_u32_vec(r)?;
    x.residence = read_u32_vec(r)?;
    x.rebel_sympathy = read_f64_vec(r)?;
    x.organization = read_u32_vec(r)?;
    x.armed_fraction = read_f64_vec(r)?;
    x.community = read_u32_vec(r)?;
    x.public_behavior = read_u8_vec(r)?;
    x.expected_control = read_f64_vec(r)?;
    x.expected_destination_control = read_f64_vec(r)?;
    x.expected_destination_control_present = read_u8_vec(r)?;
    x.state_legitimacy = read_f64_vec(r)?;
    x.government_legitimacy = read_f64_vec(r)?;
    x.political_access = read_f64_vec(r)?;
    x.displaced = read_u8_vec(r)?;
    x.displacement_count = read_u32_vec(r)?;
    x.displaced_since = read_f64_vec(r)?;
    x.displacement_origin = read_u32_vec(r)?;
    x.origin_tie_strength = read_f64_vec(r)?;
    x.external_state = read_u32_vec(r)?;
    x.migration_status = read_u8_vec(r)?;
    x.insurgent_affinity = read_f64_vec(r)?;
    x.social_exposure = read_f64_vec(r)?;
    Ok(())
}

fn encode_households(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.households;
    put_u32_vec(b, &x.locality);
    put_u32_vec(b, &x.residence);
    put_f64_vec(b, &x.resources);
    put_u32_vec(b, &x.dependents);
    put_u32_vec(b, &x.member_offsets);
    put_u32_vec(b, &x.member_indices);
}

fn decode_households(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.households;
    x.locality = read_u32_vec(r)?;
    x.residence = read_u32_vec(r)?;
    x.resources = read_f64_vec(r)?;
    x.dependents = read_u32_vec(r)?;
    x.member_offsets = read_u32_vec(r)?;
    x.member_indices = read_u32_vec(r)?;
    Ok(())
}

fn encode_communities(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.communities;
    put_u32_vec(b, &x.locality);
    for values in [
        &x.cohesion,
        &x.government_cooperation,
        &x.insurgent_sympathy,
        &x.language_profile,
    ] {
        put_f64_vec(b, values);
    }
    put_u32_vec(b, &x.member_offsets);
    put_u32_vec(b, &x.member_indices);
    put_u32_vec(b, &x.bridge_offsets);
    put_u32_vec(b, &x.bridge_members);
}

fn decode_communities(
    r: &mut ByteReader<'_>,
    p: &mut ParticleState,
) -> Result<(), CheckpointError> {
    let x = &mut p.communities;
    x.locality = read_u32_vec(r)?;
    x.cohesion = read_f64_vec(r)?;
    x.government_cooperation = read_f64_vec(r)?;
    x.insurgent_sympathy = read_f64_vec(r)?;
    x.language_profile = read_f64_vec(r)?;
    x.member_offsets = read_u32_vec(r)?;
    x.member_indices = read_u32_vec(r)?;
    x.bridge_offsets = read_u32_vec(r)?;
    x.bridge_members = read_u32_vec(r)?;
    Ok(())
}

fn encode_protos(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.protos;
    put_u32_vec(b, &x.community);
    put_u32_vec(b, &x.locality);
    put_u8_vec(b, &x.status);
    put_u32_vec(b, &x.member_offsets);
    put_u32_vec(b, &x.member_indices);
    for values in [
        &x.capital_social,
        &x.capital_political,
        &x.capital_organizational,
        &x.capital_material,
        &x.represented_membership,
        &x.ideology_reform,
        &x.ideology_separatism,
        &x.leadership_potential,
        &x.created_at,
    ] {
        put_f64_vec(b, values);
    }
}

fn decode_protos(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.protos;
    x.community = read_u32_vec(r)?;
    x.locality = read_u32_vec(r)?;
    x.status = read_u8_vec(r)?;
    x.member_offsets = read_u32_vec(r)?;
    x.member_indices = read_u32_vec(r)?;
    x.capital_social = read_f64_vec(r)?;
    x.capital_political = read_f64_vec(r)?;
    x.capital_organizational = read_f64_vec(r)?;
    x.capital_material = read_f64_vec(r)?;
    x.represented_membership = read_f64_vec(r)?;
    x.ideology_reform = read_f64_vec(r)?;
    x.ideology_separatism = read_f64_vec(r)?;
    x.leadership_potential = read_f64_vec(r)?;
    x.created_at = read_f64_vec(r)?;
    Ok(())
}

fn encode_social_edges(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.social_edges;
    put_u32_vec(b, &x.person_a);
    put_u32_vec(b, &x.person_b);
    put_u8_vec(b, &x.layers);
    for values in [
        &x.weight,
        &x.language_compatibility,
        &x.trust,
        &x.represented_relationships,
    ] {
        put_f64_vec(b, values);
    }
    put_u32_vec(b, &x.neighbor_offsets);
    put_u32_vec(b, &x.neighbor_indices);
}

fn decode_social_edges(
    r: &mut ByteReader<'_>,
    p: &mut ParticleState,
) -> Result<(), CheckpointError> {
    let x = &mut p.social_edges;
    x.person_a = read_u32_vec(r)?;
    x.person_b = read_u32_vec(r)?;
    x.layers = read_u8_vec(r)?;
    x.weight = read_f64_vec(r)?;
    x.language_compatibility = read_f64_vec(r)?;
    x.trust = read_f64_vec(r)?;
    x.represented_relationships = read_f64_vec(r)?;
    x.neighbor_offsets = read_u32_vec(r)?;
    x.neighbor_indices = read_u32_vec(r)?;
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

fn encode_zone_beliefs(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.zone_beliefs;
    put_u64(b, x.keys.len() as u64);
    for key in &x.keys {
        put_u32(b, key.observer);
        put_u32(b, key.zone);
    }
    put_f64_vec(b, &x.estimate);
    put_f64_vec(b, &x.confidence);
    put_f64_vec(b, &x.updated_at);
    put_f64_vec(b, &x.last_reliable_observation_at);
    put_u32_vec(b, &x.evidence_count);
    put_f64_vec(b, &x.contradiction);
}

fn decode_zone_beliefs(
    r: &mut ByteReader<'_>,
    p: &mut ParticleState,
) -> Result<(), CheckpointError> {
    let count = bounded_count(r.u64()?)?;
    let mut keys = Vec::with_capacity(count);
    for _ in 0..count {
        keys.push(crate::state::ZoneBeliefKey {
            observer: r.u32()?,
            zone: r.u32()?,
        });
    }
    p.zone_beliefs.keys = keys;
    p.zone_beliefs.estimate = read_f64_vec(r)?;
    p.zone_beliefs.confidence = read_f64_vec(r)?;
    p.zone_beliefs.updated_at = read_f64_vec(r)?;
    p.zone_beliefs.last_reliable_observation_at = read_f64_vec(r)?;
    p.zone_beliefs.evidence_count = read_u32_vec(r)?;
    p.zone_beliefs.contradiction = read_f64_vec(r)?;
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
        &x.capital_social,
        &x.capital_political,
        &x.capital_organizational,
        &x.capital_material,
        &x.phenotype,
        &x.ideology,
        &x.external_sanctuary,
        &x.adaptation_rate,
    ] {
        put_f64_vec(b, v)
    }
    put_u32_vec(b, &x.succession_count);
    put_u32_vec(b, &x.leader);
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
    x.capital_social = read_f64_vec(r)?;
    x.capital_political = read_f64_vec(r)?;
    x.capital_organizational = read_f64_vec(r)?;
    x.capital_material = read_f64_vec(r)?;
    x.phenotype = read_f64_vec(r)?;
    x.ideology = read_f64_vec(r)?;
    x.external_sanctuary = read_f64_vec(r)?;
    x.adaptation_rate = read_f64_vec(r)?;
    x.succession_count = read_u32_vec(r)?;
    x.leader = read_u32_vec(r)?;
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
        &x.experience,
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
    put_u32_vec(b, &x.movement_destination);
    put_u32_vec(b, &x.movement_origin);
    for v in [
        &x.movement_execute_at,
        &x.movement_arrives_at,
        &x.movement_travel_hours,
        &x.movement_distance_km,
        &x.movement_supply_cost,
    ] {
        put_f64_vec(b, v)
    }
    put_u64_vec(b, &x.movement_order_sequence);
    put_u8_vec(b, &x.movement_status);
    put_u8_vec(b, &x.movement_purpose);
    put_u32_vec(b, &x.external_state);
}
fn decode_formations(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.formations;
    x.organization = read_u32_vec(r).map_err(|e| section_error("organization", e))?;
    x.locality = read_u32_vec(r).map_err(|e| section_error("locality", e))?;
    x.microzone = read_u32_vec(r).map_err(|e| section_error("microzone", e))?;
    x.personnel = read_f64_vec(r).map_err(|e| section_error("personnel", e))?;
    x.quality = read_f64_vec(r).map_err(|e| section_error("quality", e))?;
    x.experience = read_f64_vec(r).map_err(|e| section_error("experience", e))?;
    x.cohesion = read_f64_vec(r).map_err(|e| section_error("cohesion", e))?;
    x.readiness = read_f64_vec(r).map_err(|e| section_error("readiness", e))?;
    x.sustainment = read_f64_vec(r).map_err(|e| section_error("sustainment", e))?;
    x.information = read_f64_vec(r).map_err(|e| section_error("information", e))?;
    x.mobility = read_f64_vec(r).map_err(|e| section_error("mobility", e))?;
    x.command = read_f64_vec(r).map_err(|e| section_error("command", e))?;
    x.embeddedness = read_f64_vec(r).map_err(|e| section_error("embeddedness", e))?;
    x.fatigue = read_f64_vec(r).map_err(|e| section_error("fatigue", e))?;
    x.availability = read_f64_vec(r).map_err(|e| section_error("availability", e))?;
    x.supply_stock = read_f64_vec(r).map_err(|e| section_error("supply_stock", e))?;
    x.supply_capacity = read_f64_vec(r).map_err(|e| section_error("supply_capacity", e))?;
    x.cumulative_losses = read_f64_vec(r).map_err(|e| section_error("cumulative_losses", e))?;
    x.home_locality = read_u32_vec(r).map_err(|e| section_error("home_locality", e))?;
    x.active = read_u8_vec(r).map_err(|e| section_error("active", e))?;
    x.moving = read_u8_vec(r).map_err(|e| section_error("moving", e))?;
    x.operational_status = read_u8_vec(r).map_err(|e| section_error("operational_status", e))?;
    x.outside_pineland = read_u8_vec(r).map_err(|e| section_error("outside_pineland", e))?;
    x.operational_posture = read_u8_vec(r).map_err(|e| section_error("operational_posture", e))?;
    x.movement_destination =
        read_u32_vec(r).map_err(|e| section_error("movement_destination", e))?;
    x.movement_origin = read_u32_vec(r).map_err(|e| section_error("movement_origin", e))?;
    x.movement_execute_at = read_f64_vec(r).map_err(|e| section_error("movement_execute_at", e))?;
    x.movement_arrives_at = read_f64_vec(r).map_err(|e| section_error("movement_arrives_at", e))?;
    x.movement_travel_hours =
        read_f64_vec(r).map_err(|e| section_error("movement_travel_hours", e))?;
    x.movement_distance_km =
        read_f64_vec(r).map_err(|e| section_error("movement_distance_km", e))?;
    x.movement_supply_cost =
        read_f64_vec(r).map_err(|e| section_error("movement_supply_cost", e))?;
    x.movement_order_sequence =
        read_u64_vec(r).map_err(|e| section_error("movement_order_sequence", e))?;
    x.movement_status = read_u8_vec(r).map_err(|e| section_error("movement_status", e))?;
    x.movement_purpose = read_u8_vec(r).map_err(|e| section_error("movement_purpose", e))?;
    x.external_state = read_u32_vec(r).map_err(|e| section_error("external_state", e))?;
    Ok(())
}
fn encode_patrols(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.patrols;
    put_u32_vec(b, &x.formation);
    put_u8_vec(b, &x.active);
    put_u32_vec(b, &x.route_position);
    put_u32_vec(b, &x.route_target);
    put_f64_vec(b, &x.last_departure);
    put_f64_vec(b, &x.next_available);
    put_f64_vec(b, &x.response_fraction);
    put_f64_vec(b, &x.presence_accounted_at);
    put_u32_vec(b, &x.detections)
}
fn decode_patrols(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.patrols;
    x.formation = read_u32_vec(r)?;
    x.active = read_u8_vec(r)?;
    x.route_position = read_u32_vec(r)?;
    x.route_target = read_u32_vec(r)?;
    x.last_departure = read_f64_vec(r)?;
    x.next_available = read_f64_vec(r)?;
    x.response_fraction = read_f64_vec(r)?;
    x.presence_accounted_at = read_f64_vec(r)?;
    x.detections = read_u32_vec(r)?;
    Ok(())
}
fn encode_security_posts(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.security_posts;
    put_u32_vec(b, &x.organization);
    put_u32_vec(b, &x.locality);
    put_u32_vec(b, &x.microzone);
    put_f64_vec(b, &x.personnel);
    put_f64_vec(b, &x.presence);
    put_f64_vec(b, &x.available_fraction);
    put_u32_vec(b, &x.formation);
    put_f64_vec(b, &x.detection_rate);
    put_f64_vec(b, &x.reliability);
    put_f64_vec(b, &x.professionalism);
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
    x.personnel = read_f64_vec(r)?;
    x.presence = read_f64_vec(r)?;
    x.available_fraction = read_f64_vec(r)?;
    x.formation = read_u32_vec(r)?;
    x.detection_rate = read_f64_vec(r)?;
    x.reliability = read_f64_vec(r)?;
    x.professionalism = read_f64_vec(r)?;
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

fn encode_presence_state(b: &mut Vec<u8>, x: &PresenceState) {
    put_u64(b, x.keys.len() as u64);
    for key in &x.keys {
        put_u32(b, key.observer);
        put_u32(b, key.target);
        put_u32(b, key.locality);
        put_u32(b, key.microzone);
        put_u32(b, key.target_formation);
    }
    for values in [
        &x.estimate,
        &x.personnel,
        &x.confidence,
        &x.updated_at,
        &x.last_reliable_observation_at,
        &x.contradiction,
        &x.violence,
    ] {
        put_f64_vec(b, values);
    }
    put_u32_vec(b, &x.evidence_count);
}

fn decode_presence_state(
    r: &mut ByteReader<'_>,
    x: &mut PresenceState,
) -> Result<(), CheckpointError> {
    let count = bounded_count(r.u64()?)?;
    let mut keys = Vec::with_capacity(count);
    for _ in 0..count {
        keys.push(PresenceKey {
            observer: r.u32()?,
            target: r.u32()?,
            locality: r.u32()?,
            microzone: r.u32()?,
            target_formation: r.u32()?,
        });
    }
    x.keys = keys;
    x.estimate = read_f64_vec(r)?;
    x.personnel = read_f64_vec(r)?;
    x.confidence = read_f64_vec(r)?;
    x.updated_at = read_f64_vec(r)?;
    x.last_reliable_observation_at = read_f64_vec(r)?;
    x.contradiction = read_f64_vec(r)?;
    x.violence = read_f64_vec(r)?;
    x.evidence_count = read_u32_vec(r)?;
    Ok(())
}

fn encode_information_state(b: &mut Vec<u8>, p: &ParticleState) {
    put_u64(b, p.next_information_observation_sequence);
    put_u64(b, p.next_information_relay_sequence);
    put_f64(b, p.last_information_decay_at);
    put_u64(b, p.information_observations.len() as u64);
    for observation in &p.information_observations {
        put_u64(b, observation.sequence);
        for value in [
            observation.observer,
            observation.observer_node,
            observation.source,
            observation.source_identity,
            observation.source_community,
            observation.source_formation,
            observation.target,
            observation.target_formation,
            observation.locality,
            observation.microzone,
        ] {
            put_u32(b, value);
        }
        b.push(observation.source_type);
        b.push(observation.observation_type);
        put_f64(b, observation.time);
        put_f64(b, observation.quality);
        put_f64(b, observation.confidence);
        put_f64(b, observation.decay_rate);
        for value in observation.control {
            put_f64(b, value);
        }
        put_f64(b, observation.violence);
        put_f64(b, observation.presence);
        put_f64(b, observation.personnel);
        put_f64(b, observation.detection_probability);
        b.push(observation.detected);
        put_f64(b, observation.reported_momentum);
        put_f64(b, observation.reported_civilian_harm);
        put_u32(b, observation.attributed_actor);
    }
    put_u64(b, p.information_relays.len() as u64);
    for relay in &p.information_relays {
        put_u64(b, relay.sequence);
        put_u64(b, relay.observation);
        put_u32(b, relay.organization);
        put_u32(b, relay.source_node);
        put_u32(b, relay.destination_node);
        put_u64(b, relay.route.len() as u64);
        for value in &relay.route {
            put_u32(b, *value);
        }
        put_f64(b, relay.sent_at);
        put_f64(b, relay.arrives_at);
        put_f64(b, relay.reliability);
        put_f64(b, relay.latency_hours);
        b.push(relay.status);
        put_f64(b, relay.delivered_at);
    }
    put_u64(b, p.information_history.len() as u64);
    for entry in &p.information_history {
        put_u32(b, entry.target);
        put_u32(b, entry.locality);
        b.push(entry.observation_type);
        put_f64(b, entry.time);
        put_u32(b, entry.source_identity);
    }
}

fn decode_information_state(
    r: &mut ByteReader<'_>,
    p: &mut ParticleState,
) -> Result<(), CheckpointError> {
    p.next_information_observation_sequence = r.u64()?;
    p.next_information_relay_sequence = r.u64()?;
    p.last_information_decay_at = r.f64()?;
    let observation_count = bounded_count(r.u64()?)?;
    p.information_observations = Vec::with_capacity(observation_count);
    for _ in 0..observation_count {
        let mut observation = InformationObservation::new(r.u64()?);
        observation.observer = r.u32()?;
        observation.observer_node = r.u32()?;
        observation.source = r.u32()?;
        observation.source_identity = r.u32()?;
        observation.source_community = r.u32()?;
        observation.source_formation = r.u32()?;
        observation.target = r.u32()?;
        observation.target_formation = r.u32()?;
        observation.locality = r.u32()?;
        observation.microzone = r.u32()?;
        observation.source_type = r.u8()?;
        observation.observation_type = r.u8()?;
        observation.time = r.f64()?;
        observation.quality = r.f64()?;
        observation.confidence = r.f64()?;
        observation.decay_rate = r.f64()?;
        for value in &mut observation.control {
            *value = r.f64()?;
        }
        observation.violence = r.f64()?;
        observation.presence = r.f64()?;
        observation.personnel = r.f64()?;
        observation.detection_probability = r.f64()?;
        observation.detected = r.u8()?;
        observation.reported_momentum = r.f64()?;
        observation.reported_civilian_harm = r.f64()?;
        observation.attributed_actor = r.u32()?;
        p.information_observations.push(observation);
    }
    let relay_count = bounded_count(r.u64()?)?;
    p.information_relays = Vec::with_capacity(relay_count);
    for _ in 0..relay_count {
        let sequence = r.u64()?;
        let observation = r.u64()?;
        let organization = r.u32()?;
        let source_node = r.u32()?;
        let destination_node = r.u32()?;
        let route_count = bounded_count(r.u64()?)?;
        let mut route = Vec::with_capacity(route_count);
        for _ in 0..route_count {
            route.push(r.u32()?);
        }
        p.information_relays.push(InformationRelay {
            sequence,
            observation,
            organization,
            source_node,
            destination_node,
            route,
            sent_at: r.f64()?,
            arrives_at: r.f64()?,
            reliability: r.f64()?,
            latency_hours: r.f64()?,
            status: r.u8()?,
            delivered_at: r.f64()?,
        });
    }
    let history_count = bounded_count(r.u64()?)?;
    p.information_history = Vec::with_capacity(history_count);
    for _ in 0..history_count {
        p.information_history.push(InformationHistoryEntry {
            target: r.u32()?,
            locality: r.u32()?,
            observation_type: r.u8()?,
            time: r.f64()?,
            source_identity: r.u32()?,
        });
    }
    Ok(())
}
fn encode_logistics(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.logistics;
    put_u32_vec(b, &x.organization);
    put_u32_vec(b, &x.locality);
    for v in [&x.source_stock, &x.source_capacity, &x.source_production] {
        put_f64_vec(b, v)
    }
    for v in [
        &x.shipment_source,
        &x.shipment_formation,
        &x.shipment_origin_locality,
        &x.shipment_destination_locality,
        &x.shipment_route_offsets,
        &x.shipment_route_nodes,
    ] {
        put_u32_vec(b, v)
    }
    for v in [
        &x.shipment_departed_at,
        &x.shipment_arrives_at,
        &x.shipment_quantity_sent,
        &x.shipment_quantity_deliverable,
        &x.shipment_loss,
    ] {
        put_f64_vec(b, v)
    }
    put_u8_vec(b, &x.shipment_status);
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
    x.organization = read_u32_vec(r)?;
    x.locality = read_u32_vec(r)?;
    x.source_stock = read_f64_vec(r)?;
    x.source_capacity = read_f64_vec(r)?;
    x.source_production = read_f64_vec(r)?;
    x.shipment_source = read_u32_vec(r)?;
    x.shipment_formation = read_u32_vec(r)?;
    x.shipment_origin_locality = read_u32_vec(r)?;
    x.shipment_destination_locality = read_u32_vec(r)?;
    x.shipment_route_offsets = read_u32_vec(r)?;
    x.shipment_route_nodes = read_u32_vec(r)?;
    x.shipment_departed_at = read_f64_vec(r)?;
    x.shipment_arrives_at = read_f64_vec(r)?;
    x.shipment_quantity_sent = read_f64_vec(r)?;
    x.shipment_quantity_deliverable = read_f64_vec(r)?;
    x.shipment_loss = read_f64_vec(r)?;
    x.shipment_status = read_u8_vec(r)?;
    x.in_transit = r.f64()?;
    x.cumulative_produced = r.f64()?;
    x.cumulative_consumed = r.f64()?;
    x.cumulative_lost = r.f64()?;
    x.cumulative_shipped = r.f64()?;
    x.cumulative_delivered = r.f64()?;
    Ok(())
}

fn encode_command_edges(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.command_edges;
    put_u32_vec(b, &x.organization);
    put_u32_vec(b, &x.formation);
    put_f64_vec(b, &x.reliability);
    put_f64_vec(b, &x.latency_hours);
}

fn decode_command_edges(
    r: &mut ByteReader<'_>,
    p: &mut ParticleState,
) -> Result<(), CheckpointError> {
    let x = &mut p.command_edges;
    x.organization = read_u32_vec(r)?;
    x.formation = read_u32_vec(r)?;
    x.reliability = read_f64_vec(r)?;
    x.latency_hours = read_f64_vec(r)?;
    Ok(())
}

fn encode_manpower(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.manpower;
    put_u32_vec(b, &x.organization);
    put_u32_vec(b, &x.locality);
    put_f64_vec(b, &x.pool);
    put_f64_vec(b, &x.supply_reserve);
}

fn decode_manpower(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.manpower;
    x.organization = read_u32_vec(r)?;
    x.locality = read_u32_vec(r)?;
    x.pool = read_f64_vec(r)?;
    x.supply_reserve = read_f64_vec(r)?;
    Ok(())
}

fn encode_leaders(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.leaders;
    put_u32_vec(b, &x.organization);
    for values in [
        &x.competence,
        &x.charisma,
        &x.risk_tolerance,
        &x.ideological_rigidity,
        &x.political_skill,
        &x.organizational_skill,
    ] {
        put_f64_vec(b, values);
    }
    put_u8_vec(b, &x.active);
}

fn decode_leaders(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.leaders;
    x.organization = read_u32_vec(r)?;
    x.competence = read_f64_vec(r)?;
    x.charisma = read_f64_vec(r)?;
    x.risk_tolerance = read_f64_vec(r)?;
    x.ideological_rigidity = read_f64_vec(r)?;
    x.political_skill = read_f64_vec(r)?;
    x.organizational_skill = read_f64_vec(r)?;
    x.active = read_u8_vec(r)?;
    Ok(())
}

fn encode_political(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.political;
    put_u8_vec(b, &x.institution_type);
    put_u8_vec(b, &x.institution_level);
    put_u32_vec(b, &x.institution_locality);
    put_u32_vec(b, &x.institution_district);
    for values in [
        &x.institution_capacity,
        &x.institution_autonomy,
        &x.institution_compliance,
        &x.institution_reach,
        &x.institution_integrity,
        &x.institution_resources,
    ] {
        put_f64_vec(b, values);
    }
    put_u32_vec(b, &x.institution_governing_party);
    put_u32_vec(b, &x.branch_party);
    put_u32_vec(b, &x.branch_locality);
    for values in [
        &x.branch_resources,
        &x.branch_patronage,
        &x.branch_electoral_support,
        &x.branch_institutional_influence,
    ] {
        put_f64_vec(b, values);
    }
    put_u32_vec(b, &x.branch_member_offsets);
    put_u32_vec(b, &x.branch_member_indices);
    put_u32_vec(b, &x.branch_broker_offsets);
    put_u32_vec(b, &x.branch_broker_indices);
    put_u32_vec(b, &x.elite_person);
    put_u32_vec(b, &x.elite_locality);
    for values in [
        &x.elite_network_centrality,
        &x.elite_resources,
        &x.elite_legitimacy,
        &x.elite_institutional_ties,
    ] {
        put_f64_vec(b, values);
    }
    put_u32_vec(b, &x.elite_party_alignment);
    put_u32(b, x.ruling_party);
    put_f64(b, x.private_diversion_stock);
}

fn decode_political(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.political;
    x.institution_type = read_u8_vec(r)?;
    x.institution_level = read_u8_vec(r)?;
    x.institution_locality = read_u32_vec(r)?;
    x.institution_district = read_u32_vec(r)?;
    x.institution_capacity = read_f64_vec(r)?;
    x.institution_autonomy = read_f64_vec(r)?;
    x.institution_compliance = read_f64_vec(r)?;
    x.institution_reach = read_f64_vec(r)?;
    x.institution_integrity = read_f64_vec(r)?;
    x.institution_resources = read_f64_vec(r)?;
    x.institution_governing_party = read_u32_vec(r)?;
    x.branch_party = read_u32_vec(r)?;
    x.branch_locality = read_u32_vec(r)?;
    x.branch_resources = read_f64_vec(r)?;
    x.branch_patronage = read_f64_vec(r)?;
    x.branch_electoral_support = read_f64_vec(r)?;
    x.branch_institutional_influence = read_f64_vec(r)?;
    x.branch_member_offsets = read_u32_vec(r)?;
    x.branch_member_indices = read_u32_vec(r)?;
    x.branch_broker_offsets = read_u32_vec(r)?;
    x.branch_broker_indices = read_u32_vec(r)?;
    x.elite_person = read_u32_vec(r)?;
    x.elite_locality = read_u32_vec(r)?;
    x.elite_network_centrality = read_f64_vec(r)?;
    x.elite_resources = read_f64_vec(r)?;
    x.elite_legitimacy = read_f64_vec(r)?;
    x.elite_institutional_ties = read_f64_vec(r)?;
    x.elite_party_alignment = read_u32_vec(r)?;
    x.ruling_party = r.u32()?;
    x.private_diversion_stock = r.f64()?;
    Ok(())
}

fn encode_foreign(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.foreign;
    for values in [
        &x.resources,
        &x.stability_preference,
        &x.government_alignment,
        &x.ideological_alignment,
        &x.border_security_priority,
        &x.regional_influence,
        &x.commercial_interest,
        &x.humanitarian_preference,
        &x.cost_sensitivity,
        &x.domestic_opposition,
        &x.willingness,
        &x.language_profile,
        &x.opportunity,
    ] {
        put_f64_vec(b, values);
    }
    put_u32_vec(b, &x.rival_offsets);
    put_u32_vec(b, &x.rival_indices);
    put_f64_vec(b, &x.cumulative_cost);
    put_f64_vec(b, &x.cumulative_casualties);
    put_u32_vec(b, &x.border_foreign_state);
    put_u32_vec(b, &x.border_district);
    put_u32_vec(b, &x.border_locality);
    for values in [
        &x.border_terrain_friction,
        &x.border_infrastructure,
        &x.border_legal_permeability,
        &x.border_social_permeability,
        &x.border_language_overlap,
        &x.border_kinship_overlap,
        &x.border_state_monitoring,
    ] {
        put_f64_vec(b, values);
    }
    put_u32_vec(b, &x.belief_foreign_state);
    put_u32_vec(b, &x.belief_locality);
    for values in [
        &x.belief_government_control,
        &x.belief_insurgent_presence,
        &x.belief_confidence,
        &x.belief_updated_at,
    ] {
        put_f64_vec(b, values);
    }
    put_u32_vec(b, &x.interpreter_person);
    put_u32_vec(b, &x.interpreter_foreign_state);
    put_u32_vec(b, &x.interpreter_locality);
    for values in [
        &x.interpreter_foreign_language,
        &x.interpreter_local_language,
        &x.interpreter_foreign_trust,
        &x.interpreter_local_trust,
        &x.interpreter_cultural_knowledge,
    ] {
        put_f64_vec(b, values);
    }
    put_u32_vec(b, &x.diaspora_person);
    put_u32_vec(b, &x.diaspora_foreign_state);
    put_u32_vec(b, &x.diaspora_origin_locality);
    for values in [
        &x.diaspora_social_strength,
        &x.diaspora_financial_capacity,
        &x.diaspora_information_reliability,
        &x.diaspora_created_at,
    ] {
        put_f64_vec(b, values);
    }
    put_u32_vec(b, &x.support_foreign_state);
    put_u32_vec(b, &x.support_recipient);
    put_f64_vec(b, &x.support_total);
    put_f64(b, x.cumulative_external_remittances);
}

fn decode_foreign(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.foreign;
    x.resources = read_f64_vec(r)?;
    x.stability_preference = read_f64_vec(r)?;
    x.government_alignment = read_f64_vec(r)?;
    x.ideological_alignment = read_f64_vec(r)?;
    x.border_security_priority = read_f64_vec(r)?;
    x.regional_influence = read_f64_vec(r)?;
    x.commercial_interest = read_f64_vec(r)?;
    x.humanitarian_preference = read_f64_vec(r)?;
    x.cost_sensitivity = read_f64_vec(r)?;
    x.domestic_opposition = read_f64_vec(r)?;
    x.willingness = read_f64_vec(r)?;
    x.language_profile = read_f64_vec(r)?;
    x.opportunity = read_f64_vec(r)?;
    x.rival_offsets = read_u32_vec(r)?;
    x.rival_indices = read_u32_vec(r)?;
    x.cumulative_cost = read_f64_vec(r)?;
    x.cumulative_casualties = read_f64_vec(r)?;
    x.border_foreign_state = read_u32_vec(r)?;
    x.border_district = read_u32_vec(r)?;
    x.border_locality = read_u32_vec(r)?;
    x.border_terrain_friction = read_f64_vec(r)?;
    x.border_infrastructure = read_f64_vec(r)?;
    x.border_legal_permeability = read_f64_vec(r)?;
    x.border_social_permeability = read_f64_vec(r)?;
    x.border_language_overlap = read_f64_vec(r)?;
    x.border_kinship_overlap = read_f64_vec(r)?;
    x.border_state_monitoring = read_f64_vec(r)?;
    x.belief_foreign_state = read_u32_vec(r)?;
    x.belief_locality = read_u32_vec(r)?;
    x.belief_government_control = read_f64_vec(r)?;
    x.belief_insurgent_presence = read_f64_vec(r)?;
    x.belief_confidence = read_f64_vec(r)?;
    x.belief_updated_at = read_f64_vec(r)?;
    x.interpreter_person = read_u32_vec(r)?;
    x.interpreter_foreign_state = read_u32_vec(r)?;
    x.interpreter_locality = read_u32_vec(r)?;
    x.interpreter_foreign_language = read_f64_vec(r)?;
    x.interpreter_local_language = read_f64_vec(r)?;
    x.interpreter_foreign_trust = read_f64_vec(r)?;
    x.interpreter_local_trust = read_f64_vec(r)?;
    x.interpreter_cultural_knowledge = read_f64_vec(r)?;
    x.diaspora_person = read_u32_vec(r)?;
    x.diaspora_foreign_state = read_u32_vec(r)?;
    x.diaspora_origin_locality = read_u32_vec(r)?;
    x.diaspora_social_strength = read_f64_vec(r)?;
    x.diaspora_financial_capacity = read_f64_vec(r)?;
    x.diaspora_information_reliability = read_f64_vec(r)?;
    x.diaspora_created_at = read_f64_vec(r)?;
    x.support_foreign_state = read_u32_vec(r)?;
    x.support_recipient = read_u32_vec(r)?;
    x.support_total = read_f64_vec(r)?;
    x.cumulative_external_remittances = r.f64()?;
    Ok(())
}

fn encode_foreign_interventions(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.foreign_interventions;
    put_u32_vec(b, &x.foreign_state);
    put_u32_vec(b, &x.recipient);
    put_f64_vec(b, &x.started_at);
    put_u8_vec(b, &x.mode);
    put_f64_vec(b, &x.provided_capacity);
    put_f64_vec(b, &x.transfer_efficiency);
    put_f64_vec(b, &x.crowding_out);
    put_u32_vec(b, &x.force_formation);
    put_u8_vec(b, &x.status);
    put_f64_vec(b, &x.withdrawal_rate);
    put_f64_vec(b, &x.cumulative_transferred_capacity);
    put_f64_vec(b, &x.cumulative_retained_host_capacity);
    put_f64_vec(b, &x.cumulative_crowding_out);
    put_f64_vec(b, &x.peak_provided_capacity);
    put_f64_vec(b, &x.withdrawn_capacity);
}

fn decode_foreign_interventions(
    r: &mut ByteReader<'_>,
    p: &mut ParticleState,
) -> Result<(), CheckpointError> {
    let x = &mut p.foreign_interventions;
    x.foreign_state = read_u32_vec(r)?;
    x.recipient = read_u32_vec(r)?;
    x.started_at = read_f64_vec(r)?;
    x.mode = read_u8_vec(r)?;
    x.provided_capacity = read_f64_vec(r)?;
    x.transfer_efficiency = read_f64_vec(r)?;
    x.crowding_out = read_f64_vec(r)?;
    x.force_formation = read_u32_vec(r)?;
    x.status = read_u8_vec(r)?;
    x.withdrawal_rate = read_f64_vec(r)?;
    x.cumulative_transferred_capacity = read_f64_vec(r)?;
    x.cumulative_retained_host_capacity = read_f64_vec(r)?;
    x.cumulative_crowding_out = read_f64_vec(r)?;
    x.peak_provided_capacity = read_f64_vec(r)?;
    x.withdrawn_capacity = read_f64_vec(r)?;
    Ok(())
}

fn encode_relations(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.relations;
    put_u32_vec(b, &x.organization_a);
    put_u32_vec(b, &x.organization_b);
    put_u8_vec(b, &x.status);
    put_f64_vec(b, &x.rivalry_memory);
    put_f64_vec(b, &x.hostility_memory);
    put_f64_vec(b, &x.cooperation_memory);
    put_f64_vec(b, &x.updated_at);
    put_f64_vec(b, &x.last_interaction_at);
    put_u8_vec(b, &x.has_last_interaction);
}

fn decode_relations(r: &mut ByteReader<'_>, p: &mut ParticleState) -> Result<(), CheckpointError> {
    let x = &mut p.relations;
    x.organization_a = read_u32_vec(r)?;
    x.organization_b = read_u32_vec(r)?;
    x.status = read_u8_vec(r)?;
    x.rivalry_memory = read_f64_vec(r)?;
    x.hostility_memory = read_f64_vec(r)?;
    x.cooperation_memory = read_f64_vec(r)?;
    x.updated_at = read_f64_vec(r)?;
    x.last_interaction_at = read_f64_vec(r)?;
    x.has_last_interaction = read_u8_vec(r)?;
    Ok(())
}

fn encode_access_restrictions(b: &mut Vec<u8>, p: &ParticleState) {
    let x = &p.access_restrictions;
    put_u32_vec(b, &x.owner);
    put_u32_vec(b, &x.first_locality);
    put_u32_vec(b, &x.second_locality);
    put_f64_vec(b, &x.level);
    put_f64_vec(b, &x.cumulative_effort);
    put_f64_vec(b, &x.updated_at);
}

fn decode_access_restrictions(
    r: &mut ByteReader<'_>,
    p: &mut ParticleState,
) -> Result<(), CheckpointError> {
    let x = &mut p.access_restrictions;
    x.owner = read_u32_vec(r)?;
    x.first_locality = read_u32_vec(r)?;
    x.second_locality = read_u32_vec(r)?;
    x.level = read_f64_vec(r)?;
    x.cumulative_effort = read_f64_vec(r)?;
    x.updated_at = read_f64_vec(r)?;
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

fn encode_partner_support(b: &mut Vec<u8>, s: &PartnerSupportLedger) {
    put_string(b, &s.schema_version);
    b.push(if s.support_withdrawn { 1 } else { 0 });
    match s.withdrawal_time {
        Some(t) => {
            b.push(1);
            put_f64(b, t);
        }
        None => b.push(0),
    }
    // air
    put_u64(b, s.air.opportunities);
    put_u64(b, s.air.assisted_contacts);
    put_f64(b, s.air.cumulative_intensity);
    put_f64(b, s.air.cumulative_firepower_bonus);
    put_f64(b, s.air.cumulative_donor_cost);
    // logistics
    put_f64(b, s.logistics.cumulative_offered);
    put_f64(b, s.logistics.cumulative_delivered);
    put_f64(b, s.logistics.cumulative_rejected);
    put_f64(b, s.logistics.cumulative_lost);
    put_f64(b, s.logistics.cumulative_donor_cost);
    // command
    put_u64(b, s.command.assisted_events);
    put_f64(b, s.command.cumulative_reliability_boost);
    put_f64(b, s.command.cumulative_latency_reduction_hours);
    put_f64(b, s.command.cumulative_donor_cost);
    // force_generation
    put_f64(b, s.force_generation.indigenous_recruits);
    put_f64(b, s.force_generation.external_recruits);
    put_f64(b, s.force_generation.indigenous_graduates);
    put_f64(b, s.force_generation.external_incremental_graduates);
    put_f64(b, s.force_generation.cumulative_donor_cost);
    // snapshots
    put_u64(b, s.window_snapshots.len() as u64);
    for snap in &s.window_snapshots {
        put_f64(b, snap.time_days);
        put_f64(b, snap.air_intensity);
        put_f64(b, snap.air_donor_cost);
        put_f64(b, snap.logistics_delivered);
        put_f64(b, snap.logistics_donor_cost);
        put_u64(b, snap.command_assisted_events);
        put_f64(b, snap.command_donor_cost);
        put_f64(b, snap.forcegen_incremental_graduates);
        put_f64(b, snap.forcegen_donor_cost);
        put_f64(b, snap.total_donor_cost);
    }
}

fn decode_partner_support(
    r: &mut ByteReader<'_>,
    s: &mut PartnerSupportLedger,
) -> Result<(), CheckpointError> {
    s.schema_version = r.string()?;
    s.support_withdrawn = r.u8()? != 0;
    let has_wt = r.u8()? != 0;
    s.withdrawal_time = if has_wt { Some(r.f64()?) } else { None };
    // air
    s.air.opportunities = r.u64()?;
    s.air.assisted_contacts = r.u64()?;
    s.air.cumulative_intensity = r.f64()?;
    s.air.cumulative_firepower_bonus = r.f64()?;
    s.air.cumulative_donor_cost = r.f64()?;
    // logistics
    s.logistics.cumulative_offered = r.f64()?;
    s.logistics.cumulative_delivered = r.f64()?;
    s.logistics.cumulative_rejected = r.f64()?;
    s.logistics.cumulative_lost = r.f64()?;
    s.logistics.cumulative_donor_cost = r.f64()?;
    // command
    s.command.assisted_events = r.u64()?;
    s.command.cumulative_reliability_boost = r.f64()?;
    s.command.cumulative_latency_reduction_hours = r.f64()?;
    s.command.cumulative_donor_cost = r.f64()?;
    // force_generation
    s.force_generation.indigenous_recruits = r.f64()?;
    s.force_generation.external_recruits = r.f64()?;
    s.force_generation.indigenous_graduates = r.f64()?;
    s.force_generation.external_incremental_graduates = r.f64()?;
    s.force_generation.cumulative_donor_cost = r.f64()?;
    // snapshots
    let n = bounded_count(r.u64()?)?;
    s.window_snapshots = Vec::with_capacity(n);
    for _ in 0..n {
        s.window_snapshots.push(SupportWindowSnapshot {
            time_days: r.f64()?,
            air_intensity: r.f64()?,
            air_donor_cost: r.f64()?,
            logistics_delivered: r.f64()?,
            logistics_donor_cost: r.f64()?,
            command_assisted_events: r.u64()?,
            command_donor_cost: r.f64()?,
            forcegen_incremental_graduates: r.f64()?,
            forcegen_donor_cost: r.f64()?,
            total_donor_cost: r.f64()?,
        });
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::CheckpointStore;
    use crate::ids::PatrolId;
    use crate::rng::RngStreams;
    use crate::scheduler::EventPayload;
    use crate::state::{
        BeliefKey, CommunityState, EventRecord, ForeignSystemState, HouseholdState,
        ObservationRecord, OrganizationRelationState, ParticleState, PersonState, SocialEdgeState,
        ZoneBeliefKey,
    };
    use std::time::{SystemTime, UNIX_EPOCH};

    fn representative_particle() -> ParticleState {
        let mut particle =
            ParticleState::new(2, 4, 2, 3, 4, RngStreams::new(99, "checkpoint-test"));
        particle.people = PersonState::new(2)
            .with_organizations(2)
            .with_destination_localities(2);
        particle.people.locality = vec![0, 1];
        particle.people.party_legitimacy = vec![0.2; 6];
        particle.people.insurgent_affinity = vec![0.1; 4];
        particle.people.social_exposure = vec![0.05; 4];
        particle.households = HouseholdState::new(1);
        particle.households.locality[0] = 0;
        particle.households.residence[0] = 1;
        particle.households.resources[0] = 12.5;
        particle.households.dependents[0] = 1;
        particle.households.member_offsets = vec![0, 2];
        particle.households.member_indices = vec![0, 1];
        particle.communities = CommunityState::new(1);
        particle.communities.locality[0] = 0;
        particle.communities.cohesion[0] = 0.7;
        particle.communities.government_cooperation[0] = 0.4;
        particle.communities.insurgent_sympathy[0] = 0.3;
        particle.communities.language_profile = vec![0.6, 0.2, 0.1, 0.1];
        particle.communities.member_offsets = vec![0, 2];
        particle.communities.member_indices = vec![0, 1];
        particle.communities.bridge_offsets = vec![0, 1];
        particle.communities.bridge_members = vec![1];
        particle.social_edges = SocialEdgeState::new(2);
        particle.social_edges.person_a = vec![0];
        particle.social_edges.person_b = vec![1];
        particle.social_edges.layers = vec![3];
        particle.social_edges.weight = vec![0.8];
        particle.social_edges.language_compatibility = vec![0.9];
        particle.social_edges.trust = vec![0.6];
        particle.social_edges.represented_relationships = vec![1.0];
        particle.social_edges.neighbor_offsets = vec![0, 1, 2];
        particle.social_edges.neighbor_indices = vec![1, 0];
        particle.zone_beliefs = crate::state::ZoneBeliefState::new(vec![ZoneBeliefKey {
            observer: 0,
            zone: 0,
        }]);
        particle.zone_beliefs.estimate[0] = 0.25;
        particle.zone_beliefs.confidence[0] = 0.5;
        particle.command_edges.organization = vec![0];
        particle.command_edges.formation = vec![0];
        particle.command_edges.reliability = vec![0.8];
        particle.command_edges.latency_hours = vec![2.0];
        particle.manpower.organization = vec![1];
        particle.manpower.locality = vec![0];
        particle.manpower.pool = vec![25.0];
        particle.manpower.supply_reserve = vec![4.0];
        particle.leaders.organization = vec![1];
        particle.leaders.competence = vec![0.7];
        particle.leaders.charisma = vec![0.6];
        particle.leaders.risk_tolerance = vec![0.4];
        particle.leaders.ideological_rigidity = vec![0.3];
        particle.leaders.political_skill = vec![0.5];
        particle.leaders.organizational_skill = vec![0.8];
        particle.leaders.active = vec![1];
        particle.political.institution_type = vec![0];
        particle.political.institution_level = vec![0];
        particle.political.institution_locality = vec![u32::MAX];
        particle.political.institution_district = vec![u32::MAX];
        particle.political.institution_capacity = vec![0.7];
        particle.political.institution_autonomy = vec![0.2];
        particle.political.institution_compliance = vec![0.8];
        particle.political.institution_reach = vec![0.9];
        particle.political.institution_integrity = vec![0.6];
        particle.political.institution_resources = vec![0.0];
        particle.political.institution_governing_party = vec![0];
        particle.political.branch_party = vec![0];
        particle.political.branch_locality = vec![0];
        particle.political.branch_resources = vec![0.0];
        particle.political.branch_patronage = vec![0.0];
        particle.political.branch_electoral_support = vec![0.4];
        particle.political.branch_institutional_influence = vec![0.2];
        particle.political.branch_member_offsets = vec![0, 1];
        particle.political.branch_member_indices = vec![0];
        particle.political.branch_broker_offsets = vec![0, 1];
        particle.political.branch_broker_indices = vec![0];
        particle.political.elite_person = vec![0];
        particle.political.elite_locality = vec![0];
        particle.political.elite_network_centrality = vec![0.1];
        particle.political.elite_resources = vec![0.0];
        particle.political.elite_legitimacy = vec![0.5];
        particle.political.elite_institutional_ties = vec![0.4];
        particle.political.elite_party_alignment = vec![0];
        particle.political.ruling_party = 0;
        particle.foreign = ForeignSystemState::new();
        particle.foreign.resources = vec![1_000_000.0];
        particle.foreign.stability_preference = vec![0.5];
        particle.foreign.government_alignment = vec![0.2];
        particle.foreign.ideological_alignment = vec![0.1];
        particle.foreign.border_security_priority = vec![0.5];
        particle.foreign.regional_influence = vec![0.4];
        particle.foreign.commercial_interest = vec![0.3];
        particle.foreign.humanitarian_preference = vec![0.6];
        particle.foreign.cost_sensitivity = vec![0.5];
        particle.foreign.domestic_opposition = vec![0.2];
        particle.foreign.willingness = vec![0.5];
        particle.foreign.language_profile = vec![0.8, 0.1, 0.05, 0.05];
        particle.foreign.opportunity = vec![0.7];
        particle.foreign.rival_offsets = vec![0, 1];
        particle.foreign.rival_indices = vec![0];
        particle.foreign.cumulative_cost = vec![0.0];
        particle.foreign.cumulative_casualties = vec![0.0];
        particle.foreign.border_foreign_state = vec![0];
        particle.foreign.border_district = vec![u32::MAX];
        particle.foreign.border_locality = vec![0];
        particle.foreign.border_terrain_friction = vec![0.5];
        particle.foreign.border_infrastructure = vec![0.5];
        particle.foreign.border_legal_permeability = vec![0.5];
        particle.foreign.border_social_permeability = vec![0.5];
        particle.foreign.border_language_overlap = vec![0.8];
        particle.foreign.border_kinship_overlap = vec![0.4];
        particle.foreign.border_state_monitoring = vec![0.5];
        particle.foreign.belief_foreign_state = vec![0];
        particle.foreign.belief_locality = vec![0];
        particle.foreign.belief_government_control = vec![0.5];
        particle.foreign.belief_insurgent_presence = vec![0.2];
        particle.foreign.belief_confidence = vec![0.12];
        particle.foreign.belief_updated_at = vec![0.0];
        particle.foreign.interpreter_person = vec![0];
        particle.foreign.interpreter_foreign_state = vec![0];
        particle.foreign.interpreter_locality = vec![0];
        particle.foreign.interpreter_foreign_language = vec![0.8];
        particle.foreign.interpreter_local_language = vec![0.9];
        particle.foreign.interpreter_foreign_trust = vec![0.55];
        particle.foreign.interpreter_local_trust = vec![0.6];
        particle.foreign.interpreter_cultural_knowledge = vec![0.4];
        particle.relations = OrganizationRelationState {
            organization_a: vec![0],
            organization_b: vec![1],
            status: vec![0],
            rivalry_memory: vec![0.0],
            hostility_memory: vec![0.0],
            cooperation_memory: vec![1.0],
            updated_at: vec![0.0],
            last_interaction_at: vec![0.0],
            has_last_interaction: vec![0],
        };
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

    #[test]
    fn partner_support_round_trip_is_exact() {
        let mut particle = representative_particle();
        particle.partner_support.support_withdrawn = true;
        particle.partner_support.withdrawal_time = Some(45.5);
        particle.partner_support.air.opportunities = 10;
        particle.partner_support.air.assisted_contacts = 8;
        particle.partner_support.air.cumulative_intensity = 150.0;
        particle.partner_support.air.cumulative_firepower_bonus = 35.0;
        particle.partner_support.air.cumulative_donor_cost = 50_000.0;
        particle.partner_support.logistics.cumulative_offered = 200.0;
        particle.partner_support.logistics.cumulative_delivered = 180.0;
        particle.partner_support.logistics.cumulative_rejected = 20.0;
        particle.partner_support.logistics.cumulative_lost = 5.0;
        particle.partner_support.logistics.cumulative_donor_cost = 25_000.0;
        particle.partner_support.command.assisted_events = 14;
        particle.partner_support.command.cumulative_reliability_boost = 0.75;
        particle.partner_support.command.cumulative_latency_reduction_hours = 12.0;
        particle.partner_support.command.cumulative_donor_cost = 15_000.0;
        particle.partner_support.force_generation.indigenous_recruits = 50.0;
        particle.partner_support.force_generation.external_recruits = 30.0;
        particle.partner_support.force_generation.indigenous_graduates = 45.0;
        particle.partner_support.force_generation.external_incremental_graduates = 25.0;
        particle.partner_support.force_generation.cumulative_donor_cost = 10_000.0;
        particle.partner_support.take_snapshot(30.0);
        particle.partner_support.take_snapshot(45.5);

        let bytes = CheckpointStore::encode_particle(&particle).unwrap();
        let restored = CheckpointStore::decode_particle(&bytes).unwrap();
        assert_eq!(particle, restored);
        assert_eq!(particle.state_hash(), restored.state_hash());
    }
}
