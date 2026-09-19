use pineland_core::config::SimulationConfig;
use pineland_model::{
    CapabilityAssayBaseline, CapabilityAssayResult, SimulationEngine, INSURGENT, MILITARY,
};
use std::env;
use std::fs::{self, File};
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};
use std::process::Command;

const SCHEMA_VERSION: &str = "pineland.partner_force_autonomy_raw_branch.v2";
const DESIGN_VERSION: &str = "pineland.partner_force_autonomy_stage3_discovery_design.v1";

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
}

#[derive(Clone, Copy, Debug)]
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
    external_command_events: u64,
    command_latency_hours_saved: f64,
    external_forcegen_graduates: f64,
    donor_cost_air: f64,
    donor_cost_logistics: f64,
    donor_cost_command: f64,
    donor_cost_forcegen: f64,
    donor_cost: f64,
    organized_actions: u64,
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
        return Err("stage3 cell manifest header does not match frozen v1 contract".to_string());
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
        });
    }
    if cells.is_empty() {
        return Err("stage3 cell manifest contains no design cells".to_string());
    }
    Ok(cells)
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
            trimmed.contains("rust/")
                || trimmed.contains("partner_force_autonomy")
                || trimmed.contains("pineland")
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

fn make_engine(
    cell: &Cell,
    seed: u64,
    horizon: f64,
    agent_count: usize,
    locality_count: usize,
) -> Result<SimulationEngine, String> {
    let mut config = SimulationConfig::default();
    config.seed = seed;
    config.initialization_seed = Some(seed);
    config.random_stream_namespace = "partner-force-autonomy-stage3-v1".to_string();
    config.agent_count = agent_count;
    config.locality_count = locality_count;
    config.horizon_days = horizon;
    config.burn_in_days = 0.0;
    config.state_regeneration.enabled = true;
    config.foreign_affairs.enabled = false;
    config.state_regeneration.security_recruitment_rate *= cell.forcegen_mult;
    config.state_regeneration.security_training_rate *= cell.forcegen_mult;
    config.logistics.source_daily_production_fraction *= cell.logistics_mult;

    let p = &mut config.partner_force_support;
    p.enabled = true;
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
        external_command_events: l.command.assisted_events,
        command_latency_hours_saved: l.command.cumulative_latency_reduction_hours,
        external_forcegen_graduates: l.force_generation.external_incremental_graduates,
        donor_cost_air: l.air.cumulative_donor_cost,
        donor_cost_logistics: l.logistics.cumulative_donor_cost,
        donor_cost_command: l.command.cumulative_donor_cost,
        donor_cost_forcegen: l.force_generation.cumulative_donor_cost,
        donor_cost: l.cumulative_donor_cost(),
        organized_actions: engine.particle.counters.organized_actions,
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
        organized_actions: b.organized_actions.saturating_sub(a.organized_actions),
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
    }
}

fn csv_header() -> &'static str {
    "schema_version,experiment_id,design_version,git_commit,world_id,pair_id,run_id,cell_id,support_profile,seed,withdrawal_time_days,horizon_days,branch,indigenous_forcegen_multiplier,indigenous_logistics_multiplier,indigenous_command_multiplier,pre_insurgent_personnel,pre_insurgent_active_formations,pre_insurgent_territorial_control,pre_recent_actions,pre_contested_localities,pre_supported_capability,pre_government_control,pre_military_personnel,pre_trained_reserve,pre_recruit_pipeline,pre_readiness,pre_experience,pre_supply_stock,pre_supply_capacity,pre_command_reliability,pre_command_latency_hours,window_indigenous_recruits,window_indigenous_graduates,window_military_losses,window_indigenous_logistics_produced,window_indigenous_logistics_delivered,window_indigenous_logistics_consumed,window_external_air_intensity,window_external_logistics_offered,window_external_logistics_delivered,window_external_logistics_rejected,window_external_logistics_lost,window_external_command_events,window_command_latency_hours_saved,window_external_forcegen_graduates,window_donor_cost_air,window_donor_cost_logistics,window_donor_cost_command,window_donor_cost_forcegen,window_donor_cost,support_air_intensity,support_air_bonus,support_logistics_rate,support_command_reliability_boost,support_command_latency_reduction_fraction,support_forcegen_training_rate_boost,c_government_control,c_military_personnel_retention,c_operational_formation_survival,c_geographic_coverage_retention,composite_capability,post_indigenous_recruits,post_indigenous_graduates,post_military_losses,post_indigenous_logistics_produced,post_indigenous_logistics_consumed,post_donor_cost_air,post_donor_cost_logistics,post_donor_cost_command,post_donor_cost_forcegen,post_donor_cost"
}

#[allow(clippy::too_many_arguments)]
fn write_row(
    out: &mut BufWriter<File>,
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
) -> Result<(), String> {
    let world_id = format!("{}_s{}", cell.cell_id, seed);
    let pair_id = format!("{}_T{}_h{}", world_id, withdrawal as u64, horizon as u64);
    let run_id = format!("{}_{}", pair_id, branch);
    writeln!(
        out,
        "{},{},{},{},{},{},{},{},{},{},{:.0},{:.0},{},{:.6},{:.6},{:.6},{:.9},{},{:.9},{},{},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9}",
        SCHEMA_VERSION,
        "partner_force_autonomy_stage3_discovery_v1",
        DESIGN_VERSION,
        commit,
        world_id,
        pair_id,
        run_id,
        cell.cell_id,
        cell.support_profile,
        seed,
        withdrawal,
        horizon,
        branch,
        cell.forcegen_mult,
        cell.logistics_mult,
        cell.command_mult,
        pre.pre_insurgent_personnel,
        pre.pre_insurgent_active_formations,
        pre.pre_insurgent_territorial_control,
        pre_window.organized_actions,
        pre.pre_contested_localities,
        pre.pre_supported_capability,
        pre.pre_government_control,
        pre.military_personnel,
        pre.trained_reserve,
        pre.recruit_pipeline,
        pre.readiness,
        pre.experience,
        pre.supply_stock,
        pre.supply_capacity,
        pre.command_reliability,
        pre.command_latency_hours,
        pre_window.indigenous_recruits,
        pre_window.indigenous_graduates,
        pre_window.military_losses,
        pre_window.indigenous_logistics_produced,
        pre_window.indigenous_logistics_delivered,
        pre_window.indigenous_logistics_consumed,
        pre_window.external_air_intensity,
        pre_window.external_logistics_offered,
        pre_window.external_logistics_delivered,
        pre_window.external_logistics_rejected,
        pre_window.external_logistics_lost,
        pre_window.external_command_events,
        pre_window.command_latency_hours_saved,
        pre_window.external_forcegen_graduates,
        pre_window.donor_cost_air,
        pre_window.donor_cost_logistics,
        pre_window.donor_cost_command,
        pre_window.donor_cost_forcegen,
        pre_window.donor_cost,
        cell.air_intensity,
        cell.air_bonus,
        cell.logistics_rate,
        cell.command_reliability_boost,
        cell.command_latency_reduction_fraction,
        cell.forcegen_training_rate_boost,
        assay.government_control,
        assay.military_personnel_retention,
        assay.operational_formation_survival,
        assay.geographic_coverage_retention,
        assay.composite_capability,
        post.indigenous_recruits,
        post.indigenous_graduates,
        post.military_losses,
        post.indigenous_logistics_produced,
        post.indigenous_logistics_consumed,
        post.donor_cost_air,
        post.donor_cost_logistics,
        post.donor_cost_command,
        post.donor_cost_forcegen,
        post.donor_cost,
    )
    .map_err(|e| e.to_string())
}

fn usage() {
    eprintln!("Usage: cargo run -p pineland-model --example partner_force_autonomy_stage3 -- [--design PATH] [--output PATH] [--seed-count N] [--seed-base N] [--max-cells N] [--agent-count N] [--locality-count N] [--allow-dirty] [--smoke] --execute");
    eprintln!("Without --execute the runner performs NO simulation and only prints the frozen design summary.");
}

fn main() -> Result<(), String> {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.iter().any(|x| x == "--help" || x == "-h") {
        usage();
        return Ok(());
    }
    let mut design = PathBuf::from("studies/research_program/general_theory_v1/partner_force_autonomy/configs/stage3_discovery_cells_v1.csv");
    let mut output = PathBuf::from("studies/research_program/general_theory_v1/partner_force_autonomy/outputs/partner_force_autonomy_stage3_raw_v2.csv");
    let mut seed_count = 12usize;
    let mut seed_base = 2_026_120_000u64;
    let mut max_cells: Option<usize> = None;
    let mut custom_agent_count: Option<usize> = None;
    let mut custom_locality_count: Option<usize> = None;
    let execute = args.iter().any(|x| x == "--execute");
    let smoke = args.iter().any(|x| x == "--smoke");
    let allow_dirty = args.iter().any(|x| x == "--allow-dirty");

    let mut i = 0usize;
    while i < args.len() {
        match args[i].as_str() {
            "--design" | "--output" | "--seed-count" | "--seed-base" | "--max-cells"
            | "--agent-count" | "--locality-count" => {
                if i + 1 >= args.len() {
                    return Err(format!("{} requires a value", args[i]));
                }
                match args[i].as_str() {
                    "--design" => design = PathBuf::from(&args[i + 1]),
                    "--output" => output = PathBuf::from(&args[i + 1]),
                    "--seed-count" => {
                        seed_count = args[i + 1].parse().map_err(|_| "invalid --seed-count")?
                    }
                    "--seed-base" => {
                        seed_base = args[i + 1].parse().map_err(|_| "invalid --seed-base")?
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
            "--execute" | "--smoke" | "--allow-dirty" => i += 1,
            other => return Err(format!("unknown argument '{other}'")),
        }
    }

    let default_agent_count = if smoke { 300 } else { 1000 };
    let default_locality_count = if smoke { 34 } else { 72 };
    let agent_count = custom_agent_count.unwrap_or(default_agent_count);
    let locality_count = custom_locality_count.unwrap_or(default_locality_count);

    let mut cells = load_cells(&design)?;
    if let Some(n) = max_cells {
        cells.truncate(n);
    }
    if smoke {
        cells.truncate(1);
        seed_count = 1;
    }
    println!("Stage-3 design: {} cells x {} seeds; scale: {} agents, {} localities; T=120d; horizons=7,30,90,180d", cells.len(), seed_count, agent_count, locality_count);
    println!("Design manifest: {}", design.display());
    if !execute {
        println!("NO COMPUTE: --execute not supplied; no SimulationEngine was created.");
        return Ok(());
    }

    if !smoke && !allow_dirty {
        check_git_clean()?;
    }

    if let Some(parent) = output.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let file = File::create(&output).map_err(|e| e.to_string())?;
    let mut out = BufWriter::new(file);
    writeln!(out, "{}", csv_header()).map_err(|e| e.to_string())?;
    let commit = git_commit();
    let withdrawal = 120.0;
    let observation_start = 60.0;
    let horizons: Vec<f64> = if smoke {
        vec![7.0]
    } else {
        vec![7.0, 30.0, 90.0, 180.0]
    };
    let max_horizon = *horizons.last().unwrap();

    for (cell_index, cell) in cells.iter().enumerate() {
        for s in 0..seed_count {
            let seed = seed_base + s as u64;
            let mut engine = make_engine(
                cell,
                seed,
                withdrawal + max_horizon,
                agent_count,
                locality_count,
            )?;
            engine
                .advance_until(observation_start)
                .map_err(|e| e.to_string())?;
            let obs_baseline: CapabilityAssayBaseline = engine.capability_assay_baseline();
            let flow_start = flow_snapshot(&engine);
            engine
                .advance_until(withdrawal)
                .map_err(|e| e.to_string())?;
            let pre_assay = engine.capability_assay(&obs_baseline);
            let pre_state = state_at_withdrawal(&engine, pre_assay);
            let flow_t = flow_snapshot(&engine);
            let pre_window = diff(flow_start, flow_t);
            let outcome_baseline = engine.capability_assay_baseline();

            let mut on = engine.clone();
            let mut off = engine.clone();
            off.withdraw_external_partner_support();
            for h in &horizons {
                let target = withdrawal + *h;
                on.advance_until(target).map_err(|e| e.to_string())?;
                off.advance_until(target).map_err(|e| e.to_string())?;
                let assay_on = on.capability_assay(&outcome_baseline);
                let assay_off = off.capability_assay(&outcome_baseline);
                if cell.support_profile == "none" {
                    assert!(
                        (assay_on.composite_capability - assay_off.composite_capability).abs() < 1e-12,
                        "Negative control violation: none profile produced differing ON and OFF capability"
                    );
                }
                let post_on = diff(flow_t, flow_snapshot(&on));
                let post_off = diff(flow_t, flow_snapshot(&off));
                write_row(
                    &mut out,
                    &commit,
                    cell,
                    seed,
                    withdrawal,
                    *h,
                    "SUPPORT_ON",
                    pre_state,
                    pre_window,
                    &assay_on,
                    post_on,
                )?;
                write_row(
                    &mut out,
                    &commit,
                    cell,
                    seed,
                    withdrawal,
                    *h,
                    "SUPPORT_OFF",
                    pre_state,
                    pre_window,
                    &assay_off,
                    post_off,
                )?;
            }
        }
        eprintln!(
            "completed design cell {}/{}: {}",
            cell_index + 1,
            cells.len(),
            cell.cell_id
        );
    }
    out.flush().map_err(|e| e.to_string())?;
    println!("Wrote raw paired branch data: {}", output.display());
    Ok(())
}
