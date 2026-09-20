use pineland_core::config::SimulationConfig;
use pineland_core::json::{parse as parse_json, JsonValue};
use pineland_model::{
    partner_force_formal::{ServiceChannel, StructuralAutonomyMetrics, StructuralServiceWindow},
    CapabilityAssayBaseline, CapabilityAssayResult, SimulationEngine, INSURGENT, MILITARY,
};
use std::collections::BTreeSet;
use std::env;
use std::fs::{self, File};
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};
use std::process::Command;

const SCHEMA_VERSION: &str = "pineland.partner_force_autonomy_raw_branch.v4";
const DISCOVERY_DESIGN_VERSION: &str = "pineland.partner_force_autonomy_stage3_discovery_design.v3";
const TRAJECTORY_SCHEMA_VERSION: &str = "pineland.partner_force_autonomy_trajectory.v2";
const TELEMETRY_STEP_DAYS: f64 = 7.0;
/// Reference-mission command requirement per military order. Indigenous and
/// supported command service are reliability * exp(-latency_hours / 24).
const COMMAND_SERVICE_REQUIREMENT_PER_ORDER: f64 = 0.5;

#[derive(Clone, Debug, Default)]
struct HoldoutOverrides {
    convoy_speed_factor: Option<f64>,
    shipment_loss_per_travel_hour: Option<f64>,
    route_interdiction_enabled: Option<bool>,
    route_interdiction_rate: Option<f64>,
    combat_interval_hours: Option<f64>,
    combat_base_attrition_rate: Option<f64>,
    security_recruitment_rate: Option<f64>,
    security_training_rate: Option<f64>,
    reserve_attrition_rate: Option<f64>,
    police_allocation_share: Option<f64>,
    insurgent_target_personnel: Option<f64>,
    surprise_initiative: Option<f64>,
    accidental_contact_fraction: Option<f64>,
}

#[derive(Clone, Debug)]
struct RunDesign {
    experiment_id: String,
    design_version: String,
    rng_namespace: String,
    seed_base: u64,
    seed_count: usize,
    withdrawal_time_days: f64,
    observation_start_days: f64,
    horizons_days: Vec<f64>,
    agent_count: usize,
    locality_count: usize,
    cells: Vec<Cell>,
}

#[derive(Clone, Debug)]
struct Cell {
    cell_id: String,
    support_profile: String,
    forcegen_mult: f64,
    logistics_mult: f64,
    command_mult: f64,
    air_intensity: f64,
    air_bonus: f64,
    air_cost_per_contact: f64,
    logistics_rate: f64,
    logistics_capacity: f64,
    logistics_cost_per_unit: f64,
    command_reliability_boost: f64,
    command_latency_reduction_fraction: f64,
    command_floor_hours: f64,
    command_cost_per_formation_day: f64,
    forcegen_training_rate_boost: f64,
    forcegen_cost_per_incremental_trainee: f64,
    overrides: HoldoutOverrides,
}

#[derive(Clone, Copy, Debug, Default)]
struct FlowSnapshot {
    indigenous_recruits: f64,
    indigenous_graduates: f64,
    military_losses: f64,
    indigenous_logistics_produced: f64,
    indigenous_logistics_delivered: f64,
    indigenous_logistics_consumed: f64,
    external_air_intensity: f64,
    external_logistics_offered: f64,
    external_logistics_delivered: f64,
    external_logistics_rejected: f64,
    external_logistics_lost: f64,
    command_opportunities: u64,
    command_indigenous_service: f64,
    command_supported_service: f64,
    external_command_events: u64,
    command_latency_hours_saved: f64,
    external_forcegen_graduates: f64,
    donor_cost_air: f64,
    donor_cost_logistics: f64,
    donor_cost_command: f64,
    donor_cost_forcegen: f64,
    donor_cost: f64,
    contacts: u64,
    organized_actions: u64,
    security_deployments: f64,
    external_air_opportunities: u64,
    external_air_assisted_contacts: u64,
    external_air_firepower_bonus: f64,
    command_reliability_boost: f64,
    logistics_system_lost: f64,
}

#[derive(Clone, Copy, Debug)]
struct StateAtWithdrawal {
    pre_supported_capability: f64,
    pre_government_control: f64,
    pre_insurgent_territorial_control: f64,
    pre_contested_localities: u64,
    pre_insurgent_personnel: f64,
    pre_insurgent_active_formations: u64,
    military_personnel: f64,
    trained_reserve: f64,
    recruit_pipeline: f64,
    readiness: f64,
    experience: f64,
    supply_stock: f64,
    supply_capacity: f64,
    command_reliability: f64,
    command_latency_hours: f64,
    operational_formations: u64,
    covered_localities: u64,
}

fn parse_f64(s: &str, name: &str) -> Result<f64, String> {
    s.parse::<f64>()
        .map_err(|_| format!("invalid {name} value '{s}'"))
}

fn load_cells(path: &Path) -> Result<Vec<Cell>, String> {
    let text = fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut lines = text.lines();
    let header = lines.next().ok_or("empty stage3 cell manifest")?;
    let expected = "cell_id,support_profile,forcegen_mult,logistics_mult,command_mult,air_intensity,air_bonus,air_cost_per_contact,logistics_rate,logistics_capacity,logistics_cost_per_unit,command_reliability_boost,command_latency_reduction_fraction,command_floor_hours,command_cost_per_formation_day,forcegen_training_rate_boost,forcegen_cost_per_incremental_trainee";
    if header.trim() != expected {
        return Err("stage3 cell manifest header does not match frozen v3 contract".to_string());
    }
    let mut cells = Vec::new();
    for (line_no, line) in lines.enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let p: Vec<&str> = line.split(',').collect();
        if p.len() != 17 {
            return Err(format!(
                "cell manifest line {} has {} columns, expected 17",
                line_no + 2,
                p.len()
            ));
        }
        cells.push(Cell {
            cell_id: p[0].to_string(),
            support_profile: p[1].to_string(),
            forcegen_mult: parse_f64(p[2], "forcegen_mult")?,
            logistics_mult: parse_f64(p[3], "logistics_mult")?,
            command_mult: parse_f64(p[4], "command_mult")?,
            air_intensity: parse_f64(p[5], "air_intensity")?,
            air_bonus: parse_f64(p[6], "air_bonus")?,
            air_cost_per_contact: parse_f64(p[7], "air_cost_per_contact")?,
            logistics_rate: parse_f64(p[8], "logistics_rate")?,
            logistics_capacity: parse_f64(p[9], "logistics_capacity")?,
            logistics_cost_per_unit: parse_f64(p[10], "logistics_cost_per_unit")?,
            command_reliability_boost: parse_f64(p[11], "command_reliability_boost")?,
            command_latency_reduction_fraction: parse_f64(
                p[12],
                "command_latency_reduction_fraction",
            )?,
            command_floor_hours: parse_f64(p[13], "command_floor_hours")?,
            command_cost_per_formation_day: parse_f64(p[14], "command_cost_per_formation_day")?,
            forcegen_training_rate_boost: parse_f64(p[15], "forcegen_training_rate_boost")?,
            forcegen_cost_per_incremental_trainee: parse_f64(
                p[16],
                "forcegen_cost_per_incremental_trainee",
            )?,
            overrides: HoldoutOverrides::default(),
        });
    }
    if cells.is_empty() {
        return Err("stage3 cell manifest contains no design cells".to_string());
    }
    Ok(cells)
}

fn json_required_str<'a>(value: &'a JsonValue, key: &str) -> Result<&'a str, String> {
    value
        .get(key)
        .and_then(JsonValue::as_str)
        .ok_or_else(|| format!("missing or invalid string field '{key}'"))
}

fn json_required_f64(value: &JsonValue, key: &str) -> Result<f64, String> {
    value
        .get(key)
        .and_then(JsonValue::as_f64)
        .ok_or_else(|| format!("missing or invalid numeric field '{key}'"))
}

fn json_optional_f64(value: &JsonValue, key: &str) -> Result<Option<f64>, String> {
    match value.get(key) {
        None | Some(JsonValue::Null) => Ok(None),
        Some(v) => v
            .as_f64()
            .map(Some)
            .ok_or_else(|| format!("invalid numeric field '{key}'")),
    }
}

fn json_optional_bool(value: &JsonValue, key: &str) -> Result<Option<bool>, String> {
    match value.get(key) {
        None | Some(JsonValue::Null) => Ok(None),
        Some(v) => v
            .as_bool()
            .map(Some)
            .ok_or_else(|| format!("invalid boolean field '{key}'")),
    }
}

fn support_cost_defaults(profile: &str) -> Option<(f64, f64, f64, f64, f64)> {
    match profile {
        "none" => Some((0.0, 0.0, 0.0, 0.0, 0.0)),
        "balanced" => Some((800.0, 8.0, 1.0, 80.0, 80.0)),
        "air_heavy" => Some((1300.0, 8.0, 1.0, 30.0, 80.0)),
        "logistics_heavy" => Some((600.0, 10.0, 1.0, 30.0, 80.0)),
        "command_heavy" => Some((600.0, 8.0, 0.5, 240.0, 80.0)),
        "forcegen_heavy" => Some((600.0, 8.0, 1.0, 30.0, 120.0)),
        _ => None,
    }
}

fn resolved_holdout_cost(
    cell: &JsonValue,
    key: &str,
    profile_defaults: Option<(f64, f64, f64, f64, f64)>,
    default_index: usize,
) -> Result<f64, String> {
    if let Some(value) = json_optional_f64(cell, key)? {
        return Ok(value);
    }
    let defaults = profile_defaults.ok_or_else(|| {
        format!(
            "holdout cell '{}' uses a novel support_profile and therefore must explicitly define '{key}'",
            cell.get("cell_id").and_then(JsonValue::as_str).unwrap_or("<unknown>")
        )
    })?;
    Ok(match default_index {
        0 => defaults.0,
        1 => defaults.1,
        2 => defaults.2,
        3 => defaults.3,
        4 => defaults.4,
        _ => unreachable!(),
    })
}

fn load_holdout_contract(path: &Path) -> Result<RunDesign, String> {
    let text = fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let root = parse_json(&text).map_err(|e| format!("{}: {e}", path.display()))?;
    let schema_version = json_required_str(&root, "schema_version")?;
    if schema_version != "pineland.partner_force_holdout_contract.v1" {
        return Err(format!(
            "{} is not a partner-force holdout v1 contract",
            path.display()
        ));
    }
    let family_id = json_required_str(&root, "holdout_family_id")?;
    let rng_namespace = json_required_str(&root, "seed_namespace")?.to_string();
    let seed_base = root
        .get("seed_base")
        .and_then(JsonValue::as_u64)
        .ok_or_else(|| "missing or invalid holdout seed_base".to_string())?;
    let seed_count = root
        .get("default_seed_count")
        .and_then(JsonValue::as_usize)
        .ok_or_else(|| "missing or invalid holdout default_seed_count".to_string())?;
    let horizons_days = root
        .get("horizons_days")
        .and_then(JsonValue::as_array)
        .ok_or_else(|| "missing or invalid holdout horizons_days".to_string())?
        .iter()
        .map(|v| {
            v.as_f64()
                .ok_or_else(|| "holdout horizons_days must be numeric".to_string())
        })
        .collect::<Result<Vec<_>, _>>()?;
    if horizons_days.is_empty() {
        return Err("holdout horizons_days cannot be empty".to_string());
    }

    let environment = root.get("environment");
    let env_num = |key: &str, default: f64| -> Result<f64, String> {
        match environment.and_then(|e| e.get(key)) {
            None => Ok(default),
            Some(v) => v
                .as_f64()
                .ok_or_else(|| format!("invalid holdout environment.{key}")),
        }
    };
    let env_usize = |key: &str, default: usize| -> Result<usize, String> {
        match environment.and_then(|e| e.get(key)) {
            None => Ok(default),
            Some(v) => v
                .as_usize()
                .ok_or_else(|| format!("invalid holdout environment.{key}")),
        }
    };
    let agent_count = env_usize("agent_count", 1000)?;
    let locality_count = env_usize("locality_count", 72)?;
    let withdrawal_time_days = env_num("withdrawal_time_days", 120.0)?;
    let observation_start_days = env_num("observation_start_days", 60.0)?;

    let cell_values = root
        .get("cells")
        .and_then(JsonValue::as_array)
        .ok_or_else(|| "holdout contract missing cells array".to_string())?;
    let mut cells = Vec::with_capacity(cell_values.len());
    for cell in cell_values {
        let support_profile = json_required_str(cell, "support_profile")?.to_string();
        let profile_defaults = support_cost_defaults(&support_profile);
        cells.push(Cell {
            cell_id: json_required_str(cell, "cell_id")?.to_string(),
            support_profile,
            forcegen_mult: json_required_f64(cell, "forcegen_mult")?,
            logistics_mult: json_required_f64(cell, "logistics_mult")?,
            command_mult: json_required_f64(cell, "command_mult")?,
            air_intensity: json_required_f64(cell, "air_intensity")?,
            air_bonus: json_required_f64(cell, "air_bonus")?,
            air_cost_per_contact: resolved_holdout_cost(
                cell,
                "air_cost_per_contact",
                profile_defaults,
                0,
            )?,
            logistics_rate: json_required_f64(cell, "logistics_rate")?,
            logistics_capacity: json_required_f64(cell, "logistics_capacity")?,
            logistics_cost_per_unit: resolved_holdout_cost(
                cell,
                "logistics_cost_per_unit",
                profile_defaults,
                1,
            )?,
            command_reliability_boost: json_required_f64(cell, "command_reliability_boost")?,
            command_latency_reduction_fraction: json_required_f64(
                cell,
                "command_latency_reduction_fraction",
            )?,
            command_floor_hours: resolved_holdout_cost(
                cell,
                "command_floor_hours",
                profile_defaults,
                2,
            )?,
            command_cost_per_formation_day: resolved_holdout_cost(
                cell,
                "command_cost_per_formation_day",
                profile_defaults,
                3,
            )?,
            forcegen_training_rate_boost: json_required_f64(cell, "forcegen_training_rate_boost")?,
            forcegen_cost_per_incremental_trainee: resolved_holdout_cost(
                cell,
                "forcegen_cost_per_incremental_trainee",
                profile_defaults,
                4,
            )?,
            overrides: HoldoutOverrides {
                convoy_speed_factor: json_optional_f64(cell, "convoy_speed_factor")?,
                shipment_loss_per_travel_hour: json_optional_f64(
                    cell,
                    "shipment_loss_per_travel_hour",
                )?,
                route_interdiction_enabled: json_optional_bool(cell, "route_interdiction_enabled")?,
                route_interdiction_rate: json_optional_f64(cell, "route_interdiction_rate")?,
                combat_interval_hours: json_optional_f64(cell, "combat_interval_hours")?,
                combat_base_attrition_rate: json_optional_f64(cell, "combat_base_attrition_rate")?,
                security_recruitment_rate: json_optional_f64(cell, "security_recruitment_rate")?,
                security_training_rate: json_optional_f64(cell, "security_training_rate")?,
                reserve_attrition_rate: json_optional_f64(cell, "reserve_attrition_rate")?,
                police_allocation_share: json_optional_f64(cell, "police_allocation_share")?,
                insurgent_target_personnel: json_optional_f64(cell, "insurgent_target_personnel")?,
                surprise_initiative: json_optional_f64(cell, "surprise_initiative")?,
                accidental_contact_fraction: json_optional_f64(
                    cell,
                    "accidental_contact_fraction",
                )?,
            },
        });
    }
    if cells.is_empty() {
        return Err("holdout contract contains no cells".to_string());
    }
    if let Some(expected) = root.get("cells_count").and_then(JsonValue::as_usize) {
        if expected != cells.len() {
            return Err(format!(
                "holdout cells_count={expected} but parsed {} cells",
                cells.len()
            ));
        }
    }

    Ok(RunDesign {
        experiment_id: format!("partner_force_autonomy_holdout_{family_id}_v1"),
        design_version: schema_version.to_string(),
        rng_namespace,
        seed_base,
        seed_count,
        withdrawal_time_days,
        observation_start_days,
        horizons_days,
        agent_count,
        locality_count,
        cells,
    })
}

fn git_commit() -> String {
    Command::new("git")
        .args(["rev-parse", "HEAD"])
        .output()
        .ok()
        .filter(|o| o.status.success())
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|s| s.trim().to_string())
        .unwrap_or_else(|| "unknown".to_string())
}

fn sha256(data: &[u8]) -> String {
    let k: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2,
    ];

    let mut h: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab,
        0x5be0cd19,
    ];

    let bit_len = (data.len() as u64) * 8;
    let mut padded = data.to_vec();
    padded.push(0x80);
    while (padded.len() % 64) != 56 {
        padded.push(0x00);
    }
    padded.extend_from_slice(&bit_len.to_be_bytes());

    for chunk in padded.chunks_exact(64) {
        let mut w = [0u32; 64];
        for i in 0..16 {
            w[i] = u32::from_be_bytes([
                chunk[4 * i],
                chunk[4 * i + 1],
                chunk[4 * i + 2],
                chunk[4 * i + 3],
            ]);
        }
        for i in 16..64 {
            let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
            let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16]
                .wrapping_add(s0)
                .wrapping_add(w[i - 7])
                .wrapping_add(s1);
        }

        let mut a = h[0];
        let mut b = h[1];
        let mut c = h[2];
        let mut d = h[3];
        let mut e = h[4];
        let mut f = h[5];
        let mut g = h[6];
        let mut h_val = h[7];

        for i in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ ((!e) & g);
            let temp1 = h_val
                .wrapping_add(s1)
                .wrapping_add(ch)
                .wrapping_add(k[i])
                .wrapping_add(w[i]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let temp2 = s0.wrapping_add(maj);

            h_val = g;
            g = f;
            f = e;
            e = d.wrapping_add(temp1);
            d = c;
            c = b;
            b = a;
            a = temp1.wrapping_add(temp2);
        }

        h[0] = h[0].wrapping_add(a);
        h[1] = h[1].wrapping_add(b);
        h[2] = h[2].wrapping_add(c);
        h[3] = h[3].wrapping_add(d);
        h[4] = h[4].wrapping_add(e);
        h[5] = h[5].wrapping_add(f);
        h[6] = h[6].wrapping_add(g);
        h[7] = h[7].wrapping_add(h_val);
    }

    format!(
        "{:08x}{:08x}{:08x}{:08x}{:08x}{:08x}{:08x}{:08x}",
        h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7]
    )
}

fn parse_freeze_manifest(content: &str) -> Result<Vec<(String, String)>, String> {
    let root = parse_json(content).map_err(|e| format!("invalid freeze-manifest JSON: {e}"))?;
    let artifacts = root
        .get("frozen_artifacts")
        .and_then(JsonValue::as_object)
        .ok_or_else(|| "freeze manifest missing frozen_artifacts object".to_string())?;
    let mut entries = Vec::with_capacity(artifacts.len());
    for (artifact_id, value) in artifacts {
        let path = value
            .get("path")
            .and_then(JsonValue::as_str)
            .ok_or_else(|| format!("freeze artifact '{artifact_id}' missing path"))?;
        let digest = value
            .get("sha256")
            .and_then(JsonValue::as_str)
            .ok_or_else(|| format!("freeze artifact '{artifact_id}' missing sha256"))?;
        if digest.len() != 64 || !digest.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err(format!(
                "freeze artifact '{artifact_id}' has invalid SHA-256 digest"
            ));
        }
        entries.push((path.to_string(), digest.to_ascii_lowercase()));
    }
    Ok(entries)
}

fn verify_preregistration_freeze(freeze_path: &Path) -> Result<(), String> {
    if !freeze_path.exists() {
        return Err(format!(
            "Preregistration freeze manifest not found at {}. Refusing execution without frozen contracts. Use --allow-unfrozen or --smoke to override.",
            freeze_path.display()
        ));
    }
    let content = fs::read_to_string(freeze_path).map_err(|e| {
        format!(
            "Failed to read freeze manifest at {}: {e}",
            freeze_path.display()
        )
    })?;
    let entries = parse_freeze_manifest(&content)?;
    if entries.len() < 27 {
        return Err(format!(
            "Expected at least 27 frozen artifacts in manifest, found {}",
            entries.len()
        ));
    }
    for (rel_path, expected_hash) in &entries {
        let file_path = Path::new(rel_path);
        let bytes = fs::read(file_path)
            .map_err(|e| format!("Frozen artifact not found or unreadable at {rel_path}: {e}"))?;
        let actual_hash = sha256(&bytes);
        if actual_hash != *expected_hash {
            return Err(format!(
                "Preregistration freeze hash mismatch for {rel_path}!\nExpected: {expected_hash}\nActual:   {actual_hash}\nRefusing execution with modified contracts. Use --allow-unfrozen to override."
            ));
        }
    }
    println!(
        "Preregistration freeze verified: {} artifacts matched cryptographic manifest.",
        entries.len()
    );
    Ok(())
}

fn verify_selected_artifact_frozen(freeze_path: &Path, selected: &Path) -> Result<(), String> {
    let content = fs::read_to_string(freeze_path).map_err(|e| {
        format!(
            "failed to read freeze manifest {}: {e}",
            freeze_path.display()
        )
    })?;
    let entries = parse_freeze_manifest(&content)?;
    let selected_canonical = fs::canonicalize(selected).map_err(|e| {
        format!(
            "failed to resolve selected design {}: {e}",
            selected.display()
        )
    })?;
    for (path, _) in entries {
        if let Ok(candidate) = fs::canonicalize(&path) {
            if candidate == selected_canonical {
                return Ok(());
            }
        }
    }
    Err(format!(
        "Selected design artifact {} is not registered in preregistration freeze {}. Refusing execution; use --allow-unfrozen only for non-scientific smoke/development runs.",
        selected.display(),
        freeze_path.display()
    ))
}

fn check_git_clean() -> Result<(), String> {
    let output = Command::new("git")
        .args(["status", "--porcelain"])
        .output()
        .map_err(|e| format!("failed to run git status: {e}"))?;
    if !output.status.success() {
        return Err("git status failed".to_string());
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    let dirty_lines: Vec<&str> = stdout
        .lines()
        .filter(|line| {
            let trimmed = line.trim();
            let path = if trimmed.len() > 3 {
                trimmed[3..].trim().trim_matches('"')
            } else {
                trimmed
            };
            if path.starts_with("rust/hpc/")
                || path == "rust/BUILD.md"
                || path == "rust/README.md"
                || path == "tests/test_arc_hpc_campaign.py"
                || path.starts_with("studies/research_program/general_theory_v1/graph_markov_")
                || path.starts_with("studies/research_program/general_theory_v1/localflow_")
                || path.starts_with("studies/research_program/general_theory_v1/ring1_")
                || path.starts_with(
                    "studies/research_program/general_theory_v1/probabilistic_causal_cone_",
                )
            {
                return false;
            }
            path.starts_with("rust/pineland-core/")
                || path.starts_with("rust/pineland-model/")
                || path.contains("partner_force")
                || path.contains("stage3")
                || path.contains("stage4")
        })
        .collect();
    if !dirty_lines.is_empty() {
        return Err(format!(
            "Working tree has uncommitted changes in relevant files:\n{}\nRefusing discovery execution. Use --allow-dirty or --smoke to override.",
            dirty_lines.join("\n")
        ));
    }
    Ok(())
}

fn apply_indigenous_command_multiplier(engine: &mut SimulationEngine, multiplier: f64) {
    let m = multiplier.max(0.05);
    for r in &mut engine.particle.command_edges.reliability {
        *r = (*r * m).clamp(0.0, 1.0);
    }
    for l in &mut engine.particle.command_edges.latency_hours {
        *l = (*l / m).max(0.05);
    }
    for c in &mut engine.particle.formations.command {
        *c = (*c * m).clamp(0.0, 1.0);
    }
}

fn build_config(
    cell: &Cell,
    seed: u64,
    horizon: f64,
    agent_count: usize,
    locality_count: usize,
    rng_namespace: &str,
) -> Result<SimulationConfig, String> {
    let mut config = SimulationConfig::default();
    config.seed = seed;
    config.initialization_seed = Some(seed);
    config.random_stream_namespace = rng_namespace.to_string();
    config.agent_count = agent_count;
    config.locality_count = locality_count;
    config.horizon_days = horizon;
    config.burn_in_days = 0.0;
    config.state_regeneration.enabled = true;
    config.foreign_affairs.enabled = false;

    // Holdout contracts define concrete mechanism values first; indigenous
    // capacity multipliers then scale the partner-owned force-generation and
    // logistics base.  This preserves the intended factorial interpretation:
    // a forcegen_mult of 0.5 under a delayed-training regime is weaker than a
    // baseline-capacity force under that same regime.
    if let Some(v) = cell.overrides.convoy_speed_factor {
        config.logistics.convoy_speed_factor = v;
    }
    if let Some(v) = cell.overrides.shipment_loss_per_travel_hour {
        config.logistics.shipment_loss_per_travel_hour = v;
    }
    if let Some(v) = cell.overrides.route_interdiction_enabled {
        config.logistics.route_interdiction_enabled = v;
    }
    if let Some(v) = cell.overrides.route_interdiction_rate {
        config.logistics.route_interdiction_rate = v;
    }
    if let Some(v) = cell.overrides.combat_interval_hours {
        config.combat.interval_hours = v;
    }
    if let Some(v) = cell.overrides.combat_base_attrition_rate {
        config.combat.base_attrition_rate = v;
    }
    if let Some(v) = cell.overrides.security_recruitment_rate {
        config.state_regeneration.security_recruitment_rate = v;
    }
    if let Some(v) = cell.overrides.security_training_rate {
        config.state_regeneration.security_training_rate = v;
    }
    if let Some(v) = cell.overrides.reserve_attrition_rate {
        config.state_regeneration.reserve_attrition_rate = v;
    }
    if let Some(v) = cell.overrides.police_allocation_share {
        config.state_regeneration.police_allocation_share = v;
    }
    if let Some(v) = cell.overrides.insurgent_target_personnel {
        config.force_structure.insurgent_target_personnel = v;
    }
    if let Some(v) = cell.overrides.surprise_initiative {
        config.combat.surprise_initiative = v;
    }
    if let Some(v) = cell.overrides.accidental_contact_fraction {
        config.combat.accidental_contact_fraction = v;
    }

    config.state_regeneration.security_recruitment_rate *= cell.forcegen_mult;
    config.state_regeneration.security_training_rate *= cell.forcegen_mult;
    config.logistics.source_daily_production_fraction *= cell.logistics_mult;

    let p = &mut config.partner_force_support;
    p.enabled = false;
    p.air.enabled = cell.air_intensity > 0.0;
    p.air.intensity = cell.air_intensity;
    p.air.firepower_bonus = cell.air_bonus;
    p.air.cost_per_assisted_contact = cell.air_cost_per_contact;
    p.logistics.enabled = cell.logistics_rate > 0.0;
    p.logistics.mode = "throughput_augmentation".to_string();
    p.logistics.daily_delivery_rate = cell.logistics_rate;
    p.logistics.max_daily_capacity = cell.logistics_capacity.max(cell.logistics_rate);
    p.logistics.cost_per_supply_delivered = cell.logistics_cost_per_unit;
    p.command.enabled =
        cell.command_reliability_boost > 0.0 || cell.command_latency_reduction_fraction > 0.0;
    p.command.reliability_boost = cell.command_reliability_boost;
    p.command.latency_reduction_fraction = cell.command_latency_reduction_fraction;
    p.command.min_latency_floor_hours = cell.command_floor_hours;
    p.command.cost_per_formation_day = cell.command_cost_per_formation_day;
    p.force_generation.enabled = cell.forcegen_training_rate_boost > 0.0;
    p.force_generation.mode = "substitution".to_string();
    p.force_generation.training_rate_boost = cell.forcegen_training_rate_boost;
    p.force_generation.cost_per_incremental_trainee = cell.forcegen_cost_per_incremental_trainee;
    p.force_generation.capacity_building_investment_rate = 0.0;
    p.enabled =
        p.air.enabled || p.logistics.enabled || p.command.enabled || p.force_generation.enabled;

    config.validate().map_err(|e| e.to_string())?;
    Ok(config)
}

fn make_engine(
    cell: &Cell,
    seed: u64,
    horizon: f64,
    agent_count: usize,
    locality_count: usize,
    rng_namespace: &str,
) -> Result<SimulationEngine, String> {
    let config = build_config(
        cell,
        seed,
        horizon,
        agent_count,
        locality_count,
        rng_namespace,
    )?;
    let mut engine = SimulationEngine::new(config).map_err(|e| e.to_string())?;
    apply_indigenous_command_multiplier(&mut engine, cell.command_mult);
    Ok(engine)
}

fn military_losses(engine: &SimulationEngine) -> f64 {
    engine
        .particle
        .formations
        .cumulative_losses
        .iter()
        .enumerate()
        .filter(|(i, _)| engine.particle.formations.organization[*i] as usize == MILITARY)
        .map(|(_, x)| *x)
        .sum()
}

fn flow_snapshot(engine: &SimulationEngine) -> FlowSnapshot {
    let l = &engine.particle.partner_support;
    FlowSnapshot {
        indigenous_recruits: l.force_generation.indigenous_recruits,
        indigenous_graduates: l.force_generation.indigenous_graduates,
        military_losses: military_losses(engine),
        indigenous_logistics_produced: l.logistics.indigenous_cumulative_produced,
        indigenous_logistics_delivered: l.logistics.indigenous_cumulative_delivered,
        indigenous_logistics_consumed: l.logistics.indigenous_cumulative_consumed,
        external_air_intensity: l.air.cumulative_intensity,
        external_logistics_offered: l.logistics.cumulative_offered,
        external_logistics_delivered: l.logistics.cumulative_delivered,
        external_logistics_rejected: l.logistics.cumulative_rejected,
        external_logistics_lost: l.logistics.cumulative_lost,
        command_opportunities: l.command.opportunities,
        command_indigenous_service: l.command.cumulative_indigenous_service,
        command_supported_service: l.command.cumulative_supported_service,
        external_command_events: l.command.assisted_events,
        command_latency_hours_saved: l.command.cumulative_latency_reduction_hours,
        external_forcegen_graduates: l.force_generation.external_incremental_graduates,
        donor_cost_air: l.air.cumulative_donor_cost,
        donor_cost_logistics: l.logistics.cumulative_donor_cost,
        donor_cost_command: l.command.cumulative_donor_cost,
        donor_cost_forcegen: l.force_generation.cumulative_donor_cost,
        donor_cost: l.cumulative_donor_cost(),
        contacts: engine.particle.counters.contacts,
        organized_actions: engine.particle.counters.organized_actions,
        security_deployments: engine
            .particle
            .locality
            .government_cumulative_security_deployments
            .iter()
            .sum(),
        external_air_opportunities: l.air.opportunities,
        external_air_assisted_contacts: l.air.assisted_contacts,
        external_air_firepower_bonus: l.air.cumulative_firepower_bonus,
        command_reliability_boost: l.command.cumulative_reliability_boost,
        logistics_system_lost: engine.particle.logistics.cumulative_lost,
    }
}

fn diff(a: FlowSnapshot, b: FlowSnapshot) -> FlowSnapshot {
    FlowSnapshot {
        indigenous_recruits: (b.indigenous_recruits - a.indigenous_recruits).max(0.0),
        indigenous_graduates: (b.indigenous_graduates - a.indigenous_graduates).max(0.0),
        military_losses: (b.military_losses - a.military_losses).max(0.0),
        indigenous_logistics_produced: (b.indigenous_logistics_produced
            - a.indigenous_logistics_produced)
            .max(0.0),
        indigenous_logistics_delivered: (b.indigenous_logistics_delivered
            - a.indigenous_logistics_delivered)
            .max(0.0),
        indigenous_logistics_consumed: (b.indigenous_logistics_consumed
            - a.indigenous_logistics_consumed)
            .max(0.0),
        external_air_intensity: (b.external_air_intensity - a.external_air_intensity).max(0.0),
        external_logistics_offered: (b.external_logistics_offered - a.external_logistics_offered)
            .max(0.0),
        external_logistics_delivered: (b.external_logistics_delivered
            - a.external_logistics_delivered)
            .max(0.0),
        external_logistics_rejected: (b.external_logistics_rejected
            - a.external_logistics_rejected)
            .max(0.0),
        external_logistics_lost: (b.external_logistics_lost - a.external_logistics_lost).max(0.0),
        command_opportunities: b
            .command_opportunities
            .saturating_sub(a.command_opportunities),
        command_indigenous_service: (b.command_indigenous_service - a.command_indigenous_service)
            .max(0.0),
        command_supported_service: (b.command_supported_service - a.command_supported_service)
            .max(0.0),
        external_command_events: b
            .external_command_events
            .saturating_sub(a.external_command_events),
        command_latency_hours_saved: (b.command_latency_hours_saved
            - a.command_latency_hours_saved)
            .max(0.0),
        external_forcegen_graduates: (b.external_forcegen_graduates
            - a.external_forcegen_graduates)
            .max(0.0),
        donor_cost_air: (b.donor_cost_air - a.donor_cost_air).max(0.0),
        donor_cost_logistics: (b.donor_cost_logistics - a.donor_cost_logistics).max(0.0),
        donor_cost_command: (b.donor_cost_command - a.donor_cost_command).max(0.0),
        donor_cost_forcegen: (b.donor_cost_forcegen - a.donor_cost_forcegen).max(0.0),
        donor_cost: (b.donor_cost - a.donor_cost).max(0.0),
        contacts: b.contacts.saturating_sub(a.contacts),
        organized_actions: b.organized_actions.saturating_sub(a.organized_actions),
        security_deployments: (b.security_deployments - a.security_deployments).max(0.0),
        external_air_opportunities: b
            .external_air_opportunities
            .saturating_sub(a.external_air_opportunities),
        external_air_assisted_contacts: b
            .external_air_assisted_contacts
            .saturating_sub(a.external_air_assisted_contacts),
        external_air_firepower_bonus: (b.external_air_firepower_bonus
            - a.external_air_firepower_bonus)
            .max(0.0),
        command_reliability_boost: (b.command_reliability_boost - a.command_reliability_boost)
            .max(0.0),
        logistics_system_lost: (b.logistics_system_lost - a.logistics_system_lost).max(0.0),
    }
}

fn state_at_withdrawal(
    engine: &SimulationEngine,
    pre_assay: CapabilityAssayResult,
) -> StateAtWithdrawal {
    let p = &engine.particle;
    let locality_count = engine.topology.locality_count().max(1);

    let mut insurgent_control_sum = 0.0;
    let mut contested_count = 0u64;
    for l in 0..locality_count {
        let gov = p.locality.effective_control(l, 0);
        let ins = p.locality.effective_control(l, 1);
        insurgent_control_sum += ins;
        if gov > 0.05 && ins > 0.05 {
            contested_count += 1;
        }
    }
    let pre_insurgent_territorial_control = insurgent_control_sum / locality_count as f64;

    let mut pre_insurgent_personnel = 0.0;
    let mut pre_insurgent_active_formations = 0u64;
    for formation in 0..p.formations.personnel.len() {
        if p.formations.organization[formation] as usize == INSURGENT
            && p.formations.active[formation] != 0
            && p.formations.outside_pineland[formation] == 0
        {
            let pers = p.formations.personnel[formation].max(0.0);
            pre_insurgent_personnel += pers;
            if p.formations.operational_status[formation] == 1 && pers > 0.0 {
                pre_insurgent_active_formations += 1;
            }
        }
    }

    let military: Vec<usize> = (0..p.formations.personnel.len())
        .filter(|i| p.formations.organization[*i] as usize == MILITARY)
        .collect();
    let military_personnel: f64 = military
        .iter()
        .map(|i| p.formations.personnel[*i].max(0.0))
        .sum();
    let mut operational_formations = 0u64;
    let mut covered_localities = BTreeSet::new();
    for formation in &military {
        if p.formations.active[*formation] != 0
            && p.formations.operational_status[*formation] == 1
            && p.formations.outside_pineland[*formation] == 0
            && p.formations.personnel[*formation] > 0.0
        {
            operational_formations += 1;
            covered_localities.insert(p.formations.locality[*formation]);
        }
    }
    let weighted = |values: &[f64]| -> f64 {
        if military_personnel <= 1.0e-12 {
            0.0
        } else {
            military
                .iter()
                .map(|i| p.formations.personnel[*i].max(0.0) * values[*i])
                .sum::<f64>()
                / military_personnel
        }
    };
    let supply_stock: f64 = military
        .iter()
        .map(|i| p.formations.supply_stock[*i].max(0.0))
        .sum();
    let supply_capacity: f64 = military
        .iter()
        .map(|i| p.formations.supply_capacity[*i].max(0.0))
        .sum();
    let trained_reserve: f64 = p.locality.government_security_reserve.iter().sum();
    let recruit_pipeline: f64 = p.locality.government_security_recruit_pipeline.iter().sum();
    let mut n_edges = 0usize;
    let mut reliability = 0.0;
    let mut latency = 0.0;
    for i in 0..p.command_edges.organization.len() {
        if p.command_edges.organization[i] as usize == MILITARY {
            n_edges += 1;
            reliability += p.command_edges.reliability[i];
            latency += p.command_edges.latency_hours[i];
        }
    }
    StateAtWithdrawal {
        pre_supported_capability: pre_assay.composite_capability,
        pre_government_control: pre_assay.government_control,
        pre_insurgent_territorial_control,
        pre_contested_localities: contested_count,
        pre_insurgent_personnel,
        pre_insurgent_active_formations,
        military_personnel,
        trained_reserve,
        recruit_pipeline,
        readiness: weighted(&p.formations.readiness),
        experience: weighted(&p.formations.experience),
        supply_stock,
        supply_capacity,
        command_reliability: if n_edges > 0 {
            reliability / n_edges as f64
        } else {
            0.0
        },
        command_latency_hours: if n_edges > 0 {
            latency / n_edges as f64
        } else {
            0.0
        },
        operational_formations,
        covered_localities: covered_localities.len() as u64,
    }
}

fn structural_service_window(window: FlowSnapshot) -> StructuralServiceWindow {
    StructuralServiceWindow {
        forcegen: ServiceChannel::new(
            window.military_losses,
            window.indigenous_graduates,
            window.external_forcegen_graduates,
        ),
        logistics: ServiceChannel::new(
            window.indigenous_logistics_consumed,
            window.indigenous_logistics_delivered,
            window.external_logistics_delivered,
        ),
        command: ServiceChannel::new(
            window.command_opportunities as f64 * COMMAND_SERVICE_REQUIREMENT_PER_ORDER,
            window.command_indigenous_service,
            (window.command_supported_service - window.command_indigenous_service).max(0.0),
        ),
    }
}

fn ratio_or_sentinel(value: Option<f64>) -> f64 {
    value.unwrap_or(-1.0)
}

fn external_air_share(window: FlowSnapshot) -> f64 {
    if window.external_air_opportunities > 0 {
        (window.external_air_assisted_contacts as f64 / window.external_air_opportunities as f64)
            .clamp(0.0, 1.0)
    } else {
        0.0
    }
}

fn csv_header() -> &'static str {
    "schema_version,experiment_id,design_version,git_commit,world_id,pair_id,run_id,cell_id,support_profile,seed,withdrawal_time_days,horizon_days,branch,indigenous_forcegen_multiplier,indigenous_logistics_multiplier,indigenous_command_multiplier,pre_insurgent_personnel,pre_insurgent_active_formations,pre_insurgent_territorial_control,pre_recent_actions,pre_contested_localities,pre_supported_capability,pre_government_control,pre_military_personnel,pre_trained_reserve,pre_recruit_pipeline,pre_readiness,pre_experience,pre_supply_stock,pre_supply_capacity,pre_command_reliability,pre_command_latency_hours,window_indigenous_recruits,window_indigenous_graduates,window_military_losses,window_indigenous_logistics_produced,window_indigenous_logistics_delivered,window_indigenous_logistics_consumed,window_external_air_opportunities,window_external_air_assisted_contacts,window_external_air_intensity,window_external_logistics_offered,window_external_logistics_delivered,window_external_logistics_rejected,window_external_logistics_lost,window_command_opportunities,window_command_indigenous_service,window_command_supported_service,window_external_command_events,window_command_latency_hours_saved,window_external_forcegen_graduates,window_donor_cost_air,window_donor_cost_logistics,window_donor_cost_command,window_donor_cost_forcegen,window_donor_cost,support_air_intensity,support_air_bonus,support_logistics_rate,support_command_reliability_boost,support_command_latency_reduction_fraction,support_forcegen_training_rate_boost,c_government_control,c_military_personnel_retention,c_operational_formation_survival,c_geographic_coverage_retention,composite_capability,post_indigenous_recruits,post_indigenous_graduates,post_military_losses,post_indigenous_logistics_produced,post_indigenous_logistics_consumed,post_donor_cost_air,post_donor_cost_logistics,post_donor_cost_command,post_donor_cost_forcegen,post_donor_cost,external_share_logistics,external_share_forcegen,external_share_command,external_share_air,formal_q_indigenous,formal_q_supported,formal_support_lift,formal_regime,formal_bottleneck,formal_forcegen_ratio_indigenous,formal_logistics_ratio_indigenous,formal_command_ratio_indigenous,formal_forcegen_demand,formal_forcegen_indigenous_service,formal_forcegen_external_service,formal_forcegen_deficit,formal_forcegen_useful_external,formal_logistics_demand,formal_logistics_indigenous_service,formal_logistics_external_service,formal_logistics_deficit,formal_logistics_useful_external,formal_command_demand,formal_command_indigenous_service,formal_command_external_service,formal_command_deficit,formal_command_useful_external,command_service_requirement_per_order,manpower_burden,logistics_burden,omega_flow,t_c_deficit_90,t_readiness_collapse,t_supply_exhaustion,t_first_formation_loss"
}

#[allow(clippy::too_many_arguments)]
fn write_row(
    out: &mut BufWriter<File>,
    experiment_id: &str,
    design_version: &str,
    commit: &str,
    cell: &Cell,
    seed: u64,
    withdrawal: f64,
    horizon: f64,
    branch: &str,
    pre: StateAtWithdrawal,
    pre_window: FlowSnapshot,
    assay: &CapabilityAssayResult,
    post: FlowSnapshot,
    external_share_logistics: f64,
    external_share_forcegen: f64,
    external_share_command: f64,
    external_share_air: f64,
    structural_window: StructuralServiceWindow,
    structural: StructuralAutonomyMetrics,
    manpower_burden: f64,
    logistics_burden: f64,
    omega_flow: f64,
    t_c_deficit_90: f64,
    t_readiness_collapse: f64,
    t_supply_exhaustion: f64,
    t_first_formation_loss: f64,
) -> Result<(), String> {
    let world_id = format!("{}_s{}", cell.cell_id, seed);
    let pair_id = format!("{}_T{}_h{}", world_id, withdrawal as u64, horizon as u64);
    let run_id = format!("{}_{}", pair_id, branch);
    let f9 = |x: f64| format!("{x:.9}");
    let f6 = |x: f64| format!("{x:.6}");
    let f1 = |x: f64| format!("{x:.1}");
    let row = vec![
        SCHEMA_VERSION.to_string(),
        experiment_id.to_string(),
        design_version.to_string(),
        commit.to_string(),
        world_id,
        pair_id,
        run_id,
        cell.cell_id.clone(),
        cell.support_profile.clone(),
        seed.to_string(),
        format!("{withdrawal:.0}"),
        format!("{horizon:.0}"),
        branch.to_string(),
        f6(cell.forcegen_mult),
        f6(cell.logistics_mult),
        f6(cell.command_mult),
        f9(pre.pre_insurgent_personnel),
        pre.pre_insurgent_active_formations.to_string(),
        f9(pre.pre_insurgent_territorial_control),
        pre_window.organized_actions.to_string(),
        pre.pre_contested_localities.to_string(),
        f9(pre.pre_supported_capability),
        f9(pre.pre_government_control),
        f9(pre.military_personnel),
        f9(pre.trained_reserve),
        f9(pre.recruit_pipeline),
        f9(pre.readiness),
        f9(pre.experience),
        f9(pre.supply_stock),
        f9(pre.supply_capacity),
        f9(pre.command_reliability),
        f9(pre.command_latency_hours),
        f9(pre_window.indigenous_recruits),
        f9(pre_window.indigenous_graduates),
        f9(pre_window.military_losses),
        f9(pre_window.indigenous_logistics_produced),
        f9(pre_window.indigenous_logistics_delivered),
        f9(pre_window.indigenous_logistics_consumed),
        pre_window.external_air_opportunities.to_string(),
        pre_window.external_air_assisted_contacts.to_string(),
        f9(pre_window.external_air_intensity),
        f9(pre_window.external_logistics_offered),
        f9(pre_window.external_logistics_delivered),
        f9(pre_window.external_logistics_rejected),
        f9(pre_window.external_logistics_lost),
        pre_window.command_opportunities.to_string(),
        f9(pre_window.command_indigenous_service),
        f9(pre_window.command_supported_service),
        pre_window.external_command_events.to_string(),
        f9(pre_window.command_latency_hours_saved),
        f9(pre_window.external_forcegen_graduates),
        f9(pre_window.donor_cost_air),
        f9(pre_window.donor_cost_logistics),
        f9(pre_window.donor_cost_command),
        f9(pre_window.donor_cost_forcegen),
        f9(pre_window.donor_cost),
        f9(cell.air_intensity),
        f9(cell.air_bonus),
        f9(cell.logistics_rate),
        f9(cell.command_reliability_boost),
        f9(cell.command_latency_reduction_fraction),
        f9(cell.forcegen_training_rate_boost),
        f9(assay.government_control),
        f9(assay.military_personnel_retention),
        f9(assay.operational_formation_survival),
        f9(assay.geographic_coverage_retention),
        f9(assay.composite_capability),
        f9(post.indigenous_recruits),
        f9(post.indigenous_graduates),
        f9(post.military_losses),
        f9(post.indigenous_logistics_produced),
        f9(post.indigenous_logistics_consumed),
        f9(post.donor_cost_air),
        f9(post.donor_cost_logistics),
        f9(post.donor_cost_command),
        f9(post.donor_cost_forcegen),
        f9(post.donor_cost),
        f6(external_share_logistics),
        f6(external_share_forcegen),
        f6(external_share_command),
        f6(external_share_air),
        f9(structural.q_indigenous),
        f9(structural.q_supported),
        f9(structural.support_lift),
        structural.regime.as_str().to_string(),
        structural.bottleneck.as_str().to_string(),
        f9(ratio_or_sentinel(structural.forcegen_ratio_indigenous)),
        f9(ratio_or_sentinel(structural.logistics_ratio_indigenous)),
        f9(ratio_or_sentinel(structural.command_ratio_indigenous)),
        f9(structural_window.forcegen.demand),
        f9(structural_window.forcegen.indigenous),
        f9(structural_window.forcegen.external),
        f9(structural_window.forcegen.deficit()),
        f9(structural_window.forcegen.useful_external()),
        f9(structural_window.logistics.demand),
        f9(structural_window.logistics.indigenous),
        f9(structural_window.logistics.external),
        f9(structural_window.logistics.deficit()),
        f9(structural_window.logistics.useful_external()),
        f9(structural_window.command.demand),
        f9(structural_window.command.indigenous),
        f9(structural_window.command.external),
        f9(structural_window.command.deficit()),
        f9(structural_window.command.useful_external()),
        f9(COMMAND_SERVICE_REQUIREMENT_PER_ORDER),
        f6(manpower_burden),
        f6(logistics_burden),
        f6(omega_flow),
        f1(t_c_deficit_90),
        f1(t_readiness_collapse),
        f1(t_supply_exhaustion),
        f1(t_first_formation_loss),
    ];
    writeln!(out, "{}", row.join(",")).map_err(|e| e.to_string())
}

fn trajectory_csv_header() -> &'static str {
    "schema_version,experiment_id,design_version,git_commit,world_id,cell_id,support_profile,seed,withdrawal_time_days,time_days,days_from_withdrawal,phase,capability_reference,state_hash,decision_hash,government_control,military_personnel_retention,operational_formation_survival,geographic_coverage_retention,composite_capability,military_personnel,operational_formations,covered_localities,trained_reserve,recruit_pipeline,readiness,experience,supply_stock,supply_capacity,command_reliability,command_latency_hours,insurgent_personnel,insurgent_active_formations,insurgent_territorial_control,contested_localities,interval_indigenous_recruits,interval_indigenous_graduates,interval_security_deployments,interval_military_losses,interval_indigenous_logistics_produced,interval_indigenous_logistics_delivered,interval_indigenous_logistics_consumed,interval_logistics_system_lost,interval_contacts,interval_organized_actions,interval_external_air_opportunities,interval_external_air_assisted_contacts,interval_external_air_intensity,interval_external_air_firepower_bonus,interval_external_logistics_offered,interval_external_logistics_delivered,interval_external_logistics_rejected,interval_external_logistics_lost,interval_command_opportunities,interval_command_indigenous_service,interval_command_supported_service,interval_external_command_events,interval_command_reliability_boost,interval_command_latency_hours_saved,interval_external_forcegen_graduates,interval_donor_cost_air,interval_donor_cost_logistics,interval_donor_cost_command,interval_donor_cost_forcegen,interval_donor_cost,interval_formal_active_services,interval_formal_q_indigenous,interval_formal_q_supported,interval_formal_support_lift,interval_formal_regime,interval_formal_bottleneck"
}

#[allow(clippy::too_many_arguments)]
fn write_trajectory_row(
    out: &mut BufWriter<File>,
    experiment_id: &str,
    design_version: &str,
    commit: &str,
    cell: &Cell,
    seed: u64,
    withdrawal: f64,
    time_days: f64,
    phase: &str,
    capability_reference: &str,
    engine: &SimulationEngine,
    assay: &CapabilityAssayResult,
    state: StateAtWithdrawal,
    interval: FlowSnapshot,
) -> Result<(), String> {
    let world_id = format!("{}_s{}", cell.cell_id, seed);
    let structural_window = structural_service_window(interval);
    let active_services = [
        structural_window.forcegen.active(),
        structural_window.logistics.active(),
        structural_window.command.active(),
    ]
    .into_iter()
    .filter(|x| *x)
    .count();
    let (q_indigenous, q_supported, support_lift, regime, bottleneck) =
        match structural_window.metrics() {
            Ok(m) => (
                m.q_indigenous,
                m.q_supported,
                m.support_lift,
                m.regime.as_str().to_string(),
                m.bottleneck.as_str().to_string(),
            ),
            Err(_) => (
                -1.0,
                -1.0,
                0.0,
                "NO_ACTIVE_DEMAND".to_string(),
                "none".to_string(),
            ),
        };
    let f9 = |x: f64| format!("{x:.9}");
    let row = vec![
        TRAJECTORY_SCHEMA_VERSION.to_string(),
        experiment_id.to_string(),
        design_version.to_string(),
        commit.to_string(),
        world_id,
        cell.cell_id.clone(),
        cell.support_profile.clone(),
        seed.to_string(),
        format!("{withdrawal:.0}"),
        f9(time_days),
        f9(time_days - withdrawal),
        phase.to_string(),
        capability_reference.to_string(),
        engine.state_hash(),
        engine.decision_hash(),
        f9(assay.government_control),
        f9(assay.military_personnel_retention),
        f9(assay.operational_formation_survival),
        f9(assay.geographic_coverage_retention),
        f9(assay.composite_capability),
        f9(state.military_personnel),
        state.operational_formations.to_string(),
        state.covered_localities.to_string(),
        f9(state.trained_reserve),
        f9(state.recruit_pipeline),
        f9(state.readiness),
        f9(state.experience),
        f9(state.supply_stock),
        f9(state.supply_capacity),
        f9(state.command_reliability),
        f9(state.command_latency_hours),
        f9(state.pre_insurgent_personnel),
        state.pre_insurgent_active_formations.to_string(),
        f9(state.pre_insurgent_territorial_control),
        state.pre_contested_localities.to_string(),
        f9(interval.indigenous_recruits),
        f9(interval.indigenous_graduates),
        f9(interval.security_deployments),
        f9(interval.military_losses),
        f9(interval.indigenous_logistics_produced),
        f9(interval.indigenous_logistics_delivered),
        f9(interval.indigenous_logistics_consumed),
        f9(interval.logistics_system_lost),
        interval.contacts.to_string(),
        interval.organized_actions.to_string(),
        interval.external_air_opportunities.to_string(),
        interval.external_air_assisted_contacts.to_string(),
        f9(interval.external_air_intensity),
        f9(interval.external_air_firepower_bonus),
        f9(interval.external_logistics_offered),
        f9(interval.external_logistics_delivered),
        f9(interval.external_logistics_rejected),
        f9(interval.external_logistics_lost),
        interval.command_opportunities.to_string(),
        f9(interval.command_indigenous_service),
        f9(interval.command_supported_service),
        interval.external_command_events.to_string(),
        f9(interval.command_reliability_boost),
        f9(interval.command_latency_hours_saved),
        f9(interval.external_forcegen_graduates),
        f9(interval.donor_cost_air),
        f9(interval.donor_cost_logistics),
        f9(interval.donor_cost_command),
        f9(interval.donor_cost_forcegen),
        f9(interval.donor_cost),
        active_services.to_string(),
        f9(q_indigenous),
        f9(q_supported),
        f9(support_lift),
        regime,
        bottleneck,
    ];
    writeln!(out, "{}", row.join(",")).map_err(|e| e.to_string())
}

fn sorted_unique_times(mut values: Vec<f64>) -> Vec<f64> {
    values.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    values.dedup_by(|a, b| (*a - *b).abs() < 1.0e-9);
    values
}

fn pre_telemetry_times(start: f64, withdrawal: f64) -> Vec<f64> {
    let mut values = vec![start, withdrawal];
    let mut t = start + TELEMETRY_STEP_DAYS;
    while t < withdrawal - 1.0e-9 {
        values.push(t);
        t += TELEMETRY_STEP_DAYS;
    }
    sorted_unique_times(values)
}

fn post_telemetry_offsets(max_horizon: f64, horizons: &[f64]) -> Vec<f64> {
    let mut values = horizons.to_vec();
    let mut t = TELEMETRY_STEP_DAYS;
    while t < max_horizon - 1.0e-9 {
        values.push(t);
        t += TELEMETRY_STEP_DAYS;
    }
    values.push(max_horizon);
    sorted_unique_times(values)
}

fn default_trajectory_output(output: &Path) -> PathBuf {
    let parent = output.parent().unwrap_or_else(|| Path::new("."));
    let name = output
        .file_name()
        .and_then(|x| x.to_str())
        .unwrap_or("partner_force_autonomy_raw.csv");
    let base = name.strip_suffix(".csv").unwrap_or(name);
    parent.join(format!("{base}.trajectory.csv"))
}

#[derive(Clone, Debug)]
struct DegeneracyWorldSummary {
    cell_id: String,
    profile: String,
    seed: u64,
    r_180: f64,
    pre_contacts: u64,
    pre_external_delivered: f64,
}

fn usage() {
    eprintln!("Usage: cargo run -p pineland-model --example partner_force_autonomy_stage3 -- [--preflight-gate] [--run-assays] [--pilot] [--design PATH | --holdout-contract PATH] [--freeze PATH] [--output PATH] [--trajectory-output PATH] [--seed-count N] [--seed-base N | --seed N] [--cell-id ID | --cell-index N] [--max-cells N] [--agent-count N] [--locality-count N] [--validate-configs] [--disable-diagnostic-telemetry] [--allow-dirty] [--allow-unfrozen] [--smoke] --execute");
    eprintln!("Without --execute, --preflight-gate, or --run-assays the runner performs NO simulation and only prints the frozen design summary.");
    eprintln!(
        "--cell-index is zero-based and, with --seed, is intended for ARC/Slurm array sharding."
    );
}

fn main() -> Result<(), String> {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.iter().any(|x| x == "--help" || x == "-h") {
        usage();
        return Ok(());
    }

    if args.iter().any(|x| x == "--run-assays") {
        let smoke = args.iter().any(|x| x == "--smoke");
        let options = pineland_model::treatment_gate::GateOptions {
            locality_count: if smoke { 34 } else { 72 },
            agent_count: if smoke { 300 } else { 1000 },
            withdrawal_time_days: 120.0,
            observation_start_days: 60.0,
            horizon_days: 7.0,
            verbose: true,
        };
        println!("=== Running Pineland Stage 3 v2 Safeguards & Assays Suite ===");
        let s1 = pineland_model::assays::run_outcome_sensitivity_assay(&options)?;
        println!(
            "[Assay 1: Outcome Sensitivity] pass={}; {}",
            s1.pass, s1.detail
        );
        let s2 = pineland_model::assays::run_channel_isolation_assay(&options)?;
        println!(
            "[Assay 2: Channel Isolation] pass={}; {} channels verified",
            s2.pass,
            s2.results.len()
        );
        let s3 = pineland_model::assays::run_binding_constraint_assay(&options)?;
        println!(
            "[Assay 3: Binding Constraints] pass={}; {} channels bound under stress",
            s3.pass,
            s3.results.len()
        );
        let s4 = pineland_model::assays::run_dose_sanity_assay(&options)?;
        println!(
            "[Assay 4: Dose Sanity Curves] pass={}; {} channels monotonic",
            s4.pass,
            s4.results.len()
        );
        let s5 = pineland_model::assays::run_withdrawal_shock_assay(&options)?;
        println!(
            "[Assay 5: Withdrawal Shock] pass={}; immediate cessation confirmed",
            s5.immediate_severing_verified
        );
        let s6 = pineland_model::assays::run_horizon_sufficiency_assay(&options)?;
        println!(
            "[Assay 6: Horizon Sufficiency] pass={}; 180d_div={:.4}, 360d_div={:.4}, post180_change={:.1}%",
            s6.horizon_180d_sufficient,
            s6.divergence_180d,
            s6.divergence_360d,
            100.0 * s6.relative_change_after_180
        );
        let s7 = pineland_model::assays::run_end_to_end_causal_trace(&options)?;
        println!(
            "[Assay 7: End-to-End Causal Trace] pass={}; final_C={:.4}",
            s7.chain_verified, s7.final_composite_capability
        );
        let all_pass = s1.pass
            && s2.pass
            && s3.pass
            && s4.pass
            && s5.support_withdrawn_at_t
            && s5.immediate_severing_verified
            && s6.horizon_180d_sufficient
            && s7.chain_verified;
        if !all_pass {
            return Err("One or more Stage 3 v3 safeguards/assays failed; refusing scientific campaign launch.".to_string());
        }
        println!("All 7 experimental safeguards and assays passed successfully.");
        return Ok(());
    }

    if args.iter().any(|x| x == "--preflight-gate") {
        let smoke = args.iter().any(|x| x == "--smoke");
        let options = pineland_model::treatment_gate::GateOptions {
            locality_count: if smoke { 34 } else { 72 },
            agent_count: if smoke { 300 } else { 1000 },
            withdrawal_time_days: 120.0,
            observation_start_days: 60.0,
            horizon_days: 7.0,
            verbose: true,
        };
        let summary = pineland_model::treatment_gate::run_preflight_treatment_gate(&options)?;
        if summary.overall_pass {
            println!("Preflight Treatment-Relevance Gate passed successfully.");
            return Ok(());
        } else {
            return Err(
                "Preflight Treatment-Relevance Gate failed. Halting campaign launch.".to_string(),
            );
        }
    }
    let mut design = PathBuf::from("studies/research_program/general_theory_v1/partner_force_autonomy/configs/stage3_discovery_cells_v3.csv");
    let mut design_explicit = false;
    let mut holdout_contract: Option<PathBuf> = None;
    let mut freeze = PathBuf::from("studies/research_program/general_theory_v1/partner_force_autonomy/contracts/partner_force_autonomy_preregistration_freeze_v3.json");
    let mut output: Option<PathBuf> = None;
    let mut trajectory_output: Option<PathBuf> = None;
    let mut seed_count_override: Option<usize> = None;
    let mut seed_base_override: Option<u64> = None;
    let mut single_seed: Option<u64> = None;
    let mut cell_id: Option<String> = None;
    let mut cell_index: Option<usize> = None;
    let mut max_cells: Option<usize> = None;
    let mut custom_agent_count: Option<usize> = None;
    let mut custom_locality_count: Option<usize> = None;
    let execute = args.iter().any(|x| x == "--execute");
    let validate_configs = args.iter().any(|x| x == "--validate-configs");
    let smoke = args.iter().any(|x| x == "--smoke");
    let pilot = args.iter().any(|x| x == "--pilot");
    let allow_dirty = args.iter().any(|x| x == "--allow-dirty");
    let allow_unfrozen = args.iter().any(|x| x == "--allow-unfrozen");
    // Engineering audit only: bypass weekly diagnostic observation boundaries.
    // Scientific production must leave this false.
    let disable_diagnostic_telemetry = args.iter().any(|x| x == "--disable-diagnostic-telemetry");

    let mut i = 0usize;
    while i < args.len() {
        match args[i].as_str() {
            "--design"
            | "--holdout-contract"
            | "--freeze"
            | "--output"
            | "--trajectory-output"
            | "--seed-count"
            | "--seed-base"
            | "--seed"
            | "--cell-id"
            | "--cell-index"
            | "--max-cells"
            | "--agent-count"
            | "--locality-count" => {
                if i + 1 >= args.len() {
                    return Err(format!("{} requires a value", args[i]));
                }
                match args[i].as_str() {
                    "--design" => {
                        design = PathBuf::from(&args[i + 1]);
                        design_explicit = true;
                    }
                    "--holdout-contract" => holdout_contract = Some(PathBuf::from(&args[i + 1])),
                    "--freeze" => freeze = PathBuf::from(&args[i + 1]),
                    "--output" => output = Some(PathBuf::from(&args[i + 1])),
                    "--trajectory-output" => trajectory_output = Some(PathBuf::from(&args[i + 1])),
                    "--seed-count" => {
                        seed_count_override =
                            Some(args[i + 1].parse().map_err(|_| "invalid --seed-count")?)
                    }
                    "--seed-base" => {
                        seed_base_override =
                            Some(args[i + 1].parse().map_err(|_| "invalid --seed-base")?)
                    }
                    "--seed" => {
                        single_seed = Some(args[i + 1].parse().map_err(|_| "invalid --seed")?)
                    }
                    "--cell-id" => cell_id = Some(args[i + 1].clone()),
                    "--cell-index" => {
                        cell_index = Some(args[i + 1].parse().map_err(|_| "invalid --cell-index")?)
                    }
                    "--max-cells" => {
                        max_cells = Some(args[i + 1].parse().map_err(|_| "invalid --max-cells")?)
                    }
                    "--agent-count" => {
                        custom_agent_count =
                            Some(args[i + 1].parse().map_err(|_| "invalid --agent-count")?)
                    }
                    "--locality-count" => {
                        custom_locality_count = Some(
                            args[i + 1]
                                .parse()
                                .map_err(|_| "invalid --locality-count")?,
                        )
                    }
                    _ => unreachable!(),
                }
                i += 2;
            }
            "--execute"
            | "--validate-configs"
            | "--smoke"
            | "--pilot"
            | "--allow-dirty"
            | "--allow-unfrozen"
            | "--preflight-gate"
            | "--run-assays"
            | "--disable-diagnostic-telemetry" => i += 1,
            other => return Err(format!("unknown argument '{other}'")),
        }
    }

    if design_explicit && holdout_contract.is_some() {
        return Err("--design and --holdout-contract are mutually exclusive".to_string());
    }
    if seed_base_override.is_some() && single_seed.is_some() {
        return Err("--seed-base and --seed are mutually exclusive".to_string());
    }
    if cell_id.is_some() && cell_index.is_some() {
        return Err("--cell-id and --cell-index are mutually exclusive".to_string());
    }

    let mut run_design = if let Some(ref contract_path) = holdout_contract {
        load_holdout_contract(contract_path)?
    } else {
        RunDesign {
            experiment_id: "partner_force_autonomy_stage3_discovery_v3".to_string(),
            design_version: DISCOVERY_DESIGN_VERSION.to_string(),
            rng_namespace: "partner-force-autonomy-stage3-v2".to_string(),
            seed_base: 2_026_120_000,
            seed_count: 12,
            withdrawal_time_days: 120.0,
            observation_start_days: 60.0,
            horizons_days: vec![7.0, 30.0, 90.0, 180.0],
            agent_count: 1000,
            locality_count: 72,
            cells: load_cells(&design)?,
        }
    };

    if pilot {
        let pilot_cell_ids = [
            "none_01",
            "none_02",
            "balanced_01",
            "balanced_02",
            "air_01",
            "air_02",
            "log_01",
            "log_02",
            "cmd_01",
            "cmd_02",
            "fg_01",
            "fg_02",
        ];
        run_design
            .cells
            .retain(|c| pilot_cell_ids.contains(&c.cell_id.as_str()));
        run_design.seed_count = 3;
        run_design.seed_base = 2_026_120_000;
        if output.is_none() {
            output = Some(PathBuf::from("studies/research_program/general_theory_v1/partner_force_autonomy/outputs/partner_force_autonomy_stage3_pilot_raw_v3.csv"));
        }
    }

    if let Some(n) = seed_count_override {
        run_design.seed_count = n;
    }
    if let Some(seed) = seed_base_override {
        run_design.seed_base = seed;
    }
    if let Some(seed) = single_seed {
        run_design.seed_base = seed;
        run_design.seed_count = 1;
    }
    if let Some(id) = cell_id.as_deref() {
        run_design.cells.retain(|c| c.cell_id == id);
        if run_design.cells.is_empty() {
            return Err(format!("cell-id '{id}' was not found in selected design"));
        }
    }
    if let Some(index) = cell_index {
        let selected = run_design.cells.get(index).cloned().ok_or_else(|| {
            format!(
                "cell-index {index} is outside 0..{}",
                run_design.cells.len()
            )
        })?;
        run_design.cells = vec![selected];
    }
    if let Some(n) = max_cells {
        run_design.cells.truncate(n);
    }
    if smoke {
        run_design.cells.truncate(1);
        run_design.seed_count = 1;
        run_design.agent_count = 300;
        run_design.locality_count = 34;
        run_design.horizons_days = vec![7.0];
    }
    if run_design.cells.is_empty() {
        return Err("selected design contains no cells".to_string());
    }
    let agent_count = custom_agent_count.unwrap_or(run_design.agent_count);
    let locality_count = custom_locality_count.unwrap_or(run_design.locality_count);
    let selected_artifact = holdout_contract.as_ref().unwrap_or(&design);
    let output = output.unwrap_or_else(|| {
        let file_name = if holdout_contract.is_some() {
            format!("{}_raw_v2.csv", run_design.experiment_id)
        } else {
            "partner_force_autonomy_stage3_raw_v2.csv".to_string()
        };
        PathBuf::from("studies/research_program/general_theory_v1/partner_force_autonomy/outputs")
            .join(file_name)
    });
    let trajectory_output = trajectory_output.unwrap_or_else(|| default_trajectory_output(&output));
    println!(
        "Experiment: {}; design: {} cells x {} seeds; scale: {} agents, {} localities; T={}d; horizons={:?}",
        run_design.experiment_id,
        run_design.cells.len(),
        run_design.seed_count,
        agent_count,
        locality_count,
        run_design.withdrawal_time_days,
        run_design.horizons_days
    );
    println!("Design artifact: {}", selected_artifact.display());
    if validate_configs {
        let max_horizon = run_design
            .horizons_days
            .iter()
            .copied()
            .fold(0.0_f64, f64::max);
        for cell in &run_design.cells {
            build_config(
                cell,
                run_design.seed_base,
                run_design.withdrawal_time_days + max_horizon,
                agent_count,
                locality_count,
                &run_design.rng_namespace,
            )?;
        }
        println!(
            "CONFIG_VALIDATION_PASS: {} selected cells map to valid SimulationConfig values; no SimulationEngine was created.",
            run_design.cells.len()
        );
    }
    if !execute {
        println!("NO COMPUTE: --execute not supplied; no SimulationEngine was created.");
        return Ok(());
    }

    if disable_diagnostic_telemetry && !allow_unfrozen {
        return Err("--disable-diagnostic-telemetry is engineering-audit-only and requires --allow-unfrozen".to_string());
    }
    if !smoke && !allow_unfrozen {
        verify_preregistration_freeze(&freeze)?;
        verify_selected_artifact_frozen(&freeze, selected_artifact)?;
    }

    if !smoke && !allow_dirty {
        check_git_clean()?;
    }

    if let Some(parent) = output.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    if let Some(parent) = trajectory_output.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let file = File::create(&output).map_err(|e| e.to_string())?;
    let mut out = BufWriter::new(file);
    writeln!(out, "{}", csv_header()).map_err(|e| e.to_string())?;
    let trajectory_file = File::create(&trajectory_output).map_err(|e| e.to_string())?;
    let mut trajectory_out = BufWriter::new(trajectory_file);
    writeln!(trajectory_out, "{}", trajectory_csv_header()).map_err(|e| e.to_string())?;
    let commit = git_commit();
    let withdrawal = run_design.withdrawal_time_days;
    let observation_start = run_design.observation_start_days;
    let horizons = run_design.horizons_days.clone();
    let max_horizon = *horizons.last().unwrap();

    let mut degeneracy_summaries: Vec<DegeneracyWorldSummary> = Vec::new();

    for (cell_position, cell) in run_design.cells.iter().enumerate() {
        for s in 0..run_design.seed_count {
            let seed = run_design.seed_base + s as u64;
            let mut engine = make_engine(
                cell,
                seed,
                withdrawal + max_horizon,
                agent_count,
                locality_count,
                &run_design.rng_namespace,
            )?;
            engine
                .advance_until(observation_start)
                .map_err(|e| e.to_string())?;
            let obs_baseline: CapabilityAssayBaseline = engine.capability_assay_baseline();
            let flow_start = flow_snapshot(&engine);
            let assay_start = engine.capability_assay(&obs_baseline);
            let state_start = state_at_withdrawal(&engine, assay_start.clone());
            if !disable_diagnostic_telemetry {
                write_trajectory_row(
                    &mut trajectory_out,
                    &run_design.experiment_id,
                    &run_design.design_version,
                    &commit,
                    cell,
                    seed,
                    withdrawal,
                    observation_start,
                    "PRE_SUPPORTED",
                    "DAY60_BASELINE",
                    &engine,
                    &assay_start,
                    state_start,
                    FlowSnapshot::default(),
                )?;
            }
            let mut pre_flow_previous = flow_start;
            let pre_targets: Vec<f64> = if disable_diagnostic_telemetry {
                vec![withdrawal]
            } else {
                pre_telemetry_times(observation_start, withdrawal)
                    .into_iter()
                    .skip(1)
                    .collect()
            };
            for target in pre_targets {
                engine.advance_until(target).map_err(|e| e.to_string())?;
                let assay = engine.capability_assay(&obs_baseline);
                let state = state_at_withdrawal(&engine, assay.clone());
                let flow_now = flow_snapshot(&engine);
                let interval = diff(pre_flow_previous, flow_now);
                if !disable_diagnostic_telemetry {
                    write_trajectory_row(
                        &mut trajectory_out,
                        &run_design.experiment_id,
                        &run_design.design_version,
                        &commit,
                        cell,
                        seed,
                        withdrawal,
                        target,
                        "PRE_SUPPORTED",
                        "DAY60_BASELINE",
                        &engine,
                        &assay,
                        state,
                        interval,
                    )?;
                }
                pre_flow_previous = flow_now;
            }
            let pre_assay = engine.capability_assay(&obs_baseline);
            let pre_state = state_at_withdrawal(&engine, pre_assay.clone());
            let flow_t = flow_snapshot(&engine);
            let pre_window = diff(flow_start, flow_t);
            let outcome_baseline = engine.capability_assay_baseline();

            let structural_window = structural_service_window(pre_window);
            let structural = structural_window.metrics()?;
            let external_share_logistics = structural_window.logistics.external_share();
            let external_share_forcegen = structural_window.forcegen.external_share();
            let external_share_command = structural_window.command.external_share();
            let external_share_air = external_air_share(pre_window);

            let manpower_burden = pineland_core::state::PartnerSupportLedger::manpower_burden(
                pre_window.military_losses,
                pre_window.indigenous_graduates,
            );
            let logistics_burden = pineland_core::state::PartnerSupportLedger::logistics_burden(
                pre_window.indigenous_logistics_consumed,
                pre_window.indigenous_logistics_produced,
            );
            let omega_flow = pineland_core::state::PartnerSupportLedger::omega_flow(
                manpower_burden.max(logistics_burden),
            );

            let mut t_c_deficit_90_off = -1.0;
            let mut t_readiness_collapse_off = -1.0;
            let mut t_supply_exhaustion_off = -1.0;
            let mut t_first_formation_loss_off = -1.0;

            let t_c_deficit_90_on = -1.0;
            let mut t_readiness_collapse_on = -1.0;
            let mut t_supply_exhaustion_on = -1.0;
            let mut t_first_formation_loss_on = -1.0;

            let mut on = engine.clone();
            let mut off = engine.clone();
            off.withdraw_external_partner_support();
            let mut on_flow_previous = flow_t;
            let mut off_flow_previous = flow_t;
            let post_offsets = if disable_diagnostic_telemetry {
                horizons.clone()
            } else {
                post_telemetry_offsets(max_horizon, &horizons)
            };
            for h in post_offsets {
                let target = withdrawal + h;
                on.advance_until(target).map_err(|e| e.to_string())?;
                off.advance_until(target).map_err(|e| e.to_string())?;
                let assay_on = on.capability_assay(&outcome_baseline);
                let assay_off = off.capability_assay(&outcome_baseline);
                let state_on = state_at_withdrawal(&on, assay_on.clone());
                let state_off = state_at_withdrawal(&off, assay_off.clone());
                let flow_on = flow_snapshot(&on);
                let flow_off = flow_snapshot(&off);
                let interval_on = diff(on_flow_previous, flow_on);
                let interval_off = diff(off_flow_previous, flow_off);
                if !disable_diagnostic_telemetry {
                    write_trajectory_row(
                        &mut trajectory_out,
                        &run_design.experiment_id,
                        &run_design.design_version,
                        &commit,
                        cell,
                        seed,
                        withdrawal,
                        target,
                        "SUPPORT_ON",
                        "WITHDRAWAL_BASELINE",
                        &on,
                        &assay_on,
                        state_on,
                        interval_on,
                    )?;
                    write_trajectory_row(
                        &mut trajectory_out,
                        &run_design.experiment_id,
                        &run_design.design_version,
                        &commit,
                        cell,
                        seed,
                        withdrawal,
                        target,
                        "SUPPORT_OFF",
                        "WITHDRAWAL_BASELINE",
                        &off,
                        &assay_off,
                        state_off,
                        interval_off,
                    )?;
                }

                on_flow_previous = flow_on;
                off_flow_previous = flow_off;

                if t_c_deficit_90_off < 0.0
                    && assay_off.composite_capability < 0.9 * assay_on.composite_capability
                {
                    t_c_deficit_90_off = h;
                }
                if t_readiness_collapse_off < 0.0 && off.mean_military_readiness() < 0.5 {
                    t_readiness_collapse_off = h;
                }
                if t_supply_exhaustion_off < 0.0
                    && off.min_operational_military_supply_stock() <= 1e-6
                {
                    t_supply_exhaustion_off = h;
                }
                if t_first_formation_loss_off < 0.0
                    && off.active_operational_military_formations()
                        < outcome_baseline.operational_formations
                {
                    t_first_formation_loss_off = h;
                }

                if t_readiness_collapse_on < 0.0 && on.mean_military_readiness() < 0.5 {
                    t_readiness_collapse_on = h;
                }
                if t_supply_exhaustion_on < 0.0
                    && on.min_operational_military_supply_stock() <= 1e-6
                {
                    t_supply_exhaustion_on = h;
                }
                if t_first_formation_loss_on < 0.0
                    && on.active_operational_military_formations()
                        < outcome_baseline.operational_formations
                {
                    t_first_formation_loss_on = h;
                }

                if !horizons
                    .iter()
                    .any(|expected| (*expected - h).abs() < 1.0e-9)
                {
                    continue;
                }
                if (h - 180.0).abs() < 1e-6 {
                    let r_180 =
                        assay_off.composite_capability / assay_on.composite_capability.max(1e-9);
                    degeneracy_summaries.push(DegeneracyWorldSummary {
                        cell_id: cell.cell_id.clone(),
                        profile: cell.support_profile.clone(),
                        seed,
                        r_180,
                        pre_contacts: pre_window.contacts,
                        pre_external_delivered: pre_window.external_logistics_delivered
                            + pre_window.external_forcegen_graduates
                            + pre_window.external_command_events as f64
                            + pre_window.external_air_assisted_contacts as f64,
                    });
                }
                if cell.support_profile == "none" {
                    assert!(
                        (assay_on.composite_capability - assay_off.composite_capability).abs() < 1e-12,
                        "Negative control violation: none profile produced differing ON and OFF capability"
                    );
                }
                let post_on = diff(flow_t, flow_on);
                let post_off = diff(flow_t, flow_off);
                write_row(
                    &mut out,
                    &run_design.experiment_id,
                    &run_design.design_version,
                    &commit,
                    cell,
                    seed,
                    withdrawal,
                    h,
                    "SUPPORT_ON",
                    pre_state,
                    pre_window,
                    &assay_on,
                    post_on,
                    external_share_logistics,
                    external_share_forcegen,
                    external_share_command,
                    external_share_air,
                    structural_window,
                    structural,
                    manpower_burden,
                    logistics_burden,
                    omega_flow,
                    t_c_deficit_90_on,
                    t_readiness_collapse_on,
                    t_supply_exhaustion_on,
                    t_first_formation_loss_on,
                )?;
                write_row(
                    &mut out,
                    &run_design.experiment_id,
                    &run_design.design_version,
                    &commit,
                    cell,
                    seed,
                    withdrawal,
                    h,
                    "SUPPORT_OFF",
                    pre_state,
                    pre_window,
                    &assay_off,
                    post_off,
                    external_share_logistics,
                    external_share_forcegen,
                    external_share_command,
                    external_share_air,
                    structural_window,
                    structural,
                    manpower_burden,
                    logistics_burden,
                    omega_flow,
                    t_c_deficit_90_off,
                    t_readiness_collapse_off,
                    t_supply_exhaustion_off,
                    t_first_formation_loss_off,
                )?;
            }
        }
        eprintln!(
            "completed design cell {}/{}: {}",
            cell_position + 1,
            run_design.cells.len(),
            cell.cell_id
        );
    }

    // Degeneracy Safeguard Alarm Verification
    let treated_180: Vec<&DegeneracyWorldSummary> = degeneracy_summaries
        .iter()
        .filter(|w| w.profile != "none")
        .collect();
    if !treated_180.is_empty() {
        let near_zero_count = treated_180
            .iter()
            .filter(|w| w.r_180 >= 0.995 && w.r_180 <= 1.005)
            .count();
        let near_zero_fraction = near_zero_count as f64 / treated_180.len() as f64;
        let zero_opportunity_count = treated_180.iter().filter(|w| w.pre_contacts == 0).count();
        let zero_delivery_count = treated_180
            .iter()
            .filter(|w| w.pre_external_delivered == 0.0)
            .count();

        let mean_r: f64 =
            treated_180.iter().map(|w| w.r_180).sum::<f64>() / treated_180.len() as f64;
        let var_r: f64 = treated_180
            .iter()
            .map(|w| (w.r_180 - mean_r).powi(2))
            .sum::<f64>()
            / treated_180.len() as f64;

        println!("=== Degeneracy Safeguard Diagnostics ===");
        println!("Treated worlds evaluated at 180d: {}", treated_180.len());
        println!(
            "Near-zero effect (|R_180 - 1.0| <= 0.005): {}/{} ({:.1}%)",
            near_zero_count,
            treated_180.len(),
            near_zero_fraction * 100.0
        );
        println!(
            "Zero combat opportunity worlds: {}/{}",
            zero_opportunity_count,
            treated_180.len()
        );
        println!(
            "Zero external delivery worlds: {}/{}",
            zero_delivery_count,
            treated_180.len()
        );
        println!(
            "Mean R_180: {:.4}, Variance: {:.6} (std={:.4})",
            mean_r,
            var_r,
            var_r.sqrt()
        );

        if near_zero_fraction > 0.90 && !smoke {
            return Err(format!(
                "Degeneracy Alarm: {:.1}% of treated worlds exhibit near-zero response (|R_180 - 1.0| <= 0.005), exceeding 90% threshold!",
                near_zero_fraction * 100.0
            ));
        }
        if var_r < 1e-6 && treated_180.len() > 1 && !smoke {
            return Err("Degeneracy Alarm: R_180 variance is essentially zero (< 1e-6) across treated worlds!".to_string());
        }
    }

    out.flush().map_err(|e| e.to_string())?;
    trajectory_out.flush().map_err(|e| e.to_string())?;
    println!("Wrote raw paired branch data: {}", output.display());
    println!(
        "Wrote diagnostic trajectory data: {}",
        trajectory_output.display()
    );
    Ok(())
}
