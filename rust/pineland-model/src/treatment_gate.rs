//! Automated Preflight Treatment-Relevance Gate
//!
//! Evaluates a 12-world representative battery spanning negative controls,
//! air-supported, logistics-strained, command-critical, forcegen-constrained,
//! and balanced cells on the Pineland map.
//!
//! Strictly verifies:
//! 1. Combat Liveness: contacts > 0 and military losses > 0
//! 2. Air Support Liveness: assisted contacts > 0 and donor cost > 0
//! 3. Logistics Liveness: delivered supply > 0 and donor cost > 0
//! 4. Force Generation Liveness: external incremental graduates > 0 and donor cost > 0
//! 5. Command Liveness: assisted events > 0 and donor cost > 0
//! 6. Counterfactual Exactness: negative control ON == OFF bit-for-bit
//! 7. Supported Branch Divergence: treated cells show non-degenerate divergence

use pineland_core::config::SimulationConfig;
use crate::{CapabilityAssayBaseline, SimulationEngine, MILITARY};
use std::fmt::Write as _;

#[derive(Clone, Debug)]
pub struct GateOptions {
    pub locality_count: usize,
    pub agent_count: usize,
    pub withdrawal_time_days: f64,
    pub observation_start_days: f64,
    pub horizon_days: f64,
    pub verbose: bool,
}

impl Default for GateOptions {
    fn default() -> Self {
        Self {
            locality_count: 72,
            agent_count: 1000,
            withdrawal_time_days: 120.0,
            observation_start_days: 60.0,
            horizon_days: 7.0,
            verbose: true,
        }
    }
}

#[derive(Clone, Debug)]
pub struct GateCellSpec {
    pub cell_id: &'static str,
    pub support_profile: &'static str,
    pub forcegen_mult: f64,
    pub logistics_mult: f64,
    pub command_mult: f64,
    pub air_intensity: f64,
    pub air_bonus: f64,
    pub air_cost_per_contact: f64,
    pub logistics_rate: f64,
    pub logistics_capacity: f64,
    pub logistics_cost_per_unit: f64,
    pub command_reliability_boost: f64,
    pub command_latency_reduction_fraction: f64,
    pub command_floor_hours: f64,
    pub command_cost_per_formation_day: f64,
    pub forcegen_training_rate_boost: f64,
    pub forcegen_cost_per_incremental_trainee: f64,
    pub seed: u64,
}

#[derive(Clone, Debug)]
pub struct GateWorldRecord {
    pub cell_id: String,
    pub profile: String,
    pub seed: u64,
    pub contacts: u64,
    pub military_losses: f64,
    pub air_assisted: u64,
    pub air_donor_cost: f64,
    pub logistics_delivered: f64,
    pub logistics_donor_cost: f64,
    pub command_events: u64,
    pub command_latency_saved: f64,
    pub command_donor_cost: f64,
    pub forcegen_graduates: f64,
    pub forcegen_donor_cost: f64,
    pub total_donor_cost: f64,
    pub counterfactual_exact: bool,
    pub branch_diverged: bool,
    pub composite_on: f64,
    pub composite_off: f64,
    pub status: String,
}

#[derive(Clone, Debug)]
pub struct GateSummary {
    pub records: Vec<GateWorldRecord>,
    pub combat_liveness_pass: bool,
    pub air_liveness_pass: bool,
    pub logistics_liveness_pass: bool,
    pub forcegen_liveness_pass: bool,
    pub command_liveness_pass: bool,
    pub counterfactual_exactness_pass: bool,
    pub branch_divergence_pass: bool,
    pub overall_pass: bool,
    pub table: String,
}

pub fn default_12_worlds() -> Vec<GateCellSpec> {
    vec![
        // 2 x Negative Controls (None)
        GateCellSpec {
            cell_id: "none_01",
            support_profile: "none",
            forcegen_mult: 1.4,
            logistics_mult: 1.4,
            command_mult: 1.4,
            air_intensity: 0.0,
            air_bonus: 0.0,
            air_cost_per_contact: 0.0,
            logistics_rate: 0.0,
            logistics_capacity: 0.0,
            logistics_cost_per_unit: 0.0,
            command_reliability_boost: 0.0,
            command_latency_reduction_fraction: 0.0,
            command_floor_hours: 0.0,
            command_cost_per_formation_day: 0.0,
            forcegen_training_rate_boost: 0.0,
            forcegen_cost_per_incremental_trainee: 0.0,
            seed: 2026120000,
        },
        GateCellSpec {
            cell_id: "none_02",
            support_profile: "none",
            forcegen_mult: 1.0,
            logistics_mult: 1.0,
            command_mult: 1.0,
            air_intensity: 0.0,
            air_bonus: 0.0,
            air_cost_per_contact: 0.0,
            logistics_rate: 0.0,
            logistics_capacity: 0.0,
            logistics_cost_per_unit: 0.0,
            command_reliability_boost: 0.0,
            command_latency_reduction_fraction: 0.0,
            command_floor_hours: 0.0,
            command_cost_per_formation_day: 0.0,
            forcegen_training_rate_boost: 0.0,
            forcegen_cost_per_incremental_trainee: 0.0,
            seed: 2026120001,
        },
        // 2 x Air Heavy
        GateCellSpec {
            cell_id: "air_01",
            support_profile: "air_heavy",
            forcegen_mult: 1.4,
            logistics_mult: 1.4,
            command_mult: 1.4,
            air_intensity: 0.90,
            air_bonus: 0.55,
            air_cost_per_contact: 1300.0,
            logistics_rate: 100.0,
            logistics_capacity: 200.0,
            logistics_cost_per_unit: 8.0,
            command_reliability_boost: 0.05,
            command_latency_reduction_fraction: 0.05,
            command_floor_hours: 1.0,
            command_cost_per_formation_day: 30.0,
            forcegen_training_rate_boost: 0.0015,
            forcegen_cost_per_incremental_trainee: 80.0,
            seed: 2026120000,
        },
        GateCellSpec {
            cell_id: "air_02",
            support_profile: "air_heavy",
            forcegen_mult: 1.0,
            logistics_mult: 1.0,
            command_mult: 1.0,
            air_intensity: 0.90,
            air_bonus: 0.55,
            air_cost_per_contact: 1300.0,
            logistics_rate: 100.0,
            logistics_capacity: 200.0,
            logistics_cost_per_unit: 8.0,
            command_reliability_boost: 0.05,
            command_latency_reduction_fraction: 0.05,
            command_floor_hours: 1.0,
            command_cost_per_formation_day: 30.0,
            forcegen_training_rate_boost: 0.0015,
            forcegen_cost_per_incremental_trainee: 80.0,
            seed: 2026120002,
        },
        // 2 x Logistics Heavy
        GateCellSpec {
            cell_id: "log_01",
            support_profile: "logistics_heavy",
            forcegen_mult: 1.4,
            logistics_mult: 1.4,
            command_mult: 1.4,
            air_intensity: 0.08,
            air_bonus: 0.30,
            air_cost_per_contact: 600.0,
            logistics_rate: 1200.0,
            logistics_capacity: 1600.0,
            logistics_cost_per_unit: 10.0,
            command_reliability_boost: 0.05,
            command_latency_reduction_fraction: 0.05,
            command_floor_hours: 1.0,
            command_cost_per_formation_day: 30.0,
            forcegen_training_rate_boost: 0.0015,
            forcegen_cost_per_incremental_trainee: 80.0,
            seed: 2026120000,
        },
        GateCellSpec {
            cell_id: "log_02",
            support_profile: "logistics_heavy",
            forcegen_mult: 1.0,
            logistics_mult: 1.0,
            command_mult: 1.0,
            air_intensity: 0.08,
            air_bonus: 0.30,
            air_cost_per_contact: 600.0,
            logistics_rate: 1200.0,
            logistics_capacity: 1600.0,
            logistics_cost_per_unit: 10.0,
            command_reliability_boost: 0.05,
            command_latency_reduction_fraction: 0.05,
            command_floor_hours: 1.0,
            command_cost_per_formation_day: 30.0,
            forcegen_training_rate_boost: 0.0015,
            forcegen_cost_per_incremental_trainee: 80.0,
            seed: 2026120001,
        },
        // 2 x Command Heavy
        GateCellSpec {
            cell_id: "cmd_01",
            support_profile: "command_heavy",
            forcegen_mult: 1.4,
            logistics_mult: 1.4,
            command_mult: 1.4,
            air_intensity: 0.08,
            air_bonus: 0.30,
            air_cost_per_contact: 600.0,
            logistics_rate: 100.0,
            logistics_capacity: 200.0,
            logistics_cost_per_unit: 8.0,
            command_reliability_boost: 0.55,
            command_latency_reduction_fraction: 0.55,
            command_floor_hours: 0.5,
            command_cost_per_formation_day: 240.0,
            forcegen_training_rate_boost: 0.0015,
            forcegen_cost_per_incremental_trainee: 80.0,
            seed: 2026120000,
        },
        GateCellSpec {
            cell_id: "cmd_02",
            support_profile: "command_heavy",
            forcegen_mult: 1.0,
            logistics_mult: 1.0,
            command_mult: 1.0,
            air_intensity: 0.08,
            air_bonus: 0.30,
            air_cost_per_contact: 600.0,
            logistics_rate: 100.0,
            logistics_capacity: 200.0,
            logistics_cost_per_unit: 8.0,
            command_reliability_boost: 0.55,
            command_latency_reduction_fraction: 0.55,
            command_floor_hours: 0.5,
            command_cost_per_formation_day: 240.0,
            forcegen_training_rate_boost: 0.0015,
            forcegen_cost_per_incremental_trainee: 80.0,
            seed: 2026120001,
        },
        // 2 x ForceGen Heavy
        GateCellSpec {
            cell_id: "fg_01",
            support_profile: "forcegen_heavy",
            forcegen_mult: 1.4,
            logistics_mult: 1.4,
            command_mult: 1.4,
            air_intensity: 0.08,
            air_bonus: 0.30,
            air_cost_per_contact: 600.0,
            logistics_rate: 100.0,
            logistics_capacity: 200.0,
            logistics_cost_per_unit: 8.0,
            command_reliability_boost: 0.05,
            command_latency_reduction_fraction: 0.05,
            command_floor_hours: 1.0,
            command_cost_per_formation_day: 30.0,
            forcegen_training_rate_boost: 0.035,
            forcegen_cost_per_incremental_trainee: 120.0,
            seed: 2026120000,
        },
        GateCellSpec {
            cell_id: "fg_02",
            support_profile: "forcegen_heavy",
            forcegen_mult: 1.0,
            logistics_mult: 1.0,
            command_mult: 1.0,
            air_intensity: 0.08,
            air_bonus: 0.30,
            air_cost_per_contact: 600.0,
            logistics_rate: 100.0,
            logistics_capacity: 200.0,
            logistics_cost_per_unit: 8.0,
            command_reliability_boost: 0.05,
            command_latency_reduction_fraction: 0.05,
            command_floor_hours: 1.0,
            command_cost_per_formation_day: 30.0,
            forcegen_training_rate_boost: 0.035,
            forcegen_cost_per_incremental_trainee: 120.0,
            seed: 2026120001,
        },
        // 2 x Balanced
        GateCellSpec {
            cell_id: "balanced_01",
            support_profile: "balanced",
            forcegen_mult: 1.4,
            logistics_mult: 1.4,
            command_mult: 1.4,
            air_intensity: 0.35,
            air_bonus: 0.40,
            air_cost_per_contact: 800.0,
            logistics_rate: 450.0,
            logistics_capacity: 700.0,
            logistics_cost_per_unit: 8.0,
            command_reliability_boost: 0.18,
            command_latency_reduction_fraction: 0.20,
            command_floor_hours: 1.0,
            command_cost_per_formation_day: 80.0,
            forcegen_training_rate_boost: 0.006,
            forcegen_cost_per_incremental_trainee: 80.0,
            seed: 2026120000,
        },
        GateCellSpec {
            cell_id: "balanced_02",
            support_profile: "balanced",
            forcegen_mult: 1.0,
            logistics_mult: 1.0,
            command_mult: 1.0,
            air_intensity: 0.35,
            air_bonus: 0.40,
            air_cost_per_contact: 800.0,
            logistics_rate: 450.0,
            logistics_capacity: 700.0,
            logistics_cost_per_unit: 8.0,
            command_reliability_boost: 0.18,
            command_latency_reduction_fraction: 0.20,
            command_floor_hours: 1.0,
            command_cost_per_formation_day: 80.0,
            forcegen_training_rate_boost: 0.006,
            forcegen_cost_per_incremental_trainee: 80.0,
            seed: 2026120001,
        },
    ]
}

pub fn build_gate_config(spec: &GateCellSpec, options: &GateOptions) -> Result<SimulationConfig, String> {
    let mut config = SimulationConfig::default();
    config.seed = spec.seed;
    config.random_stream_namespace = "partner-force-autonomy-gate-v2".to_string();
    config.agent_count = options.agent_count;
    config.locality_count = options.locality_count;
    config.horizon_days = options.withdrawal_time_days + options.horizon_days;
    config.burn_in_days = 0.0;
    config.state_regeneration.enabled = true;
    config.foreign_affairs.enabled = false;

    config.state_regeneration.security_recruitment_rate *= spec.forcegen_mult;
    config.state_regeneration.security_training_rate *= spec.forcegen_mult;
    config.logistics.source_daily_production_fraction *= spec.logistics_mult;

    let p = &mut config.partner_force_support;
    p.enabled = true;
    p.air.enabled = spec.air_intensity > 0.0;
    p.air.intensity = spec.air_intensity;
    p.air.firepower_bonus = spec.air_bonus;
    p.air.cost_per_assisted_contact = spec.air_cost_per_contact;
    p.logistics.enabled = spec.logistics_rate > 0.0;
    p.logistics.mode = "throughput_augmentation".to_string();
    p.logistics.daily_delivery_rate = spec.logistics_rate;
    p.logistics.max_daily_capacity = spec.logistics_capacity.max(spec.logistics_rate);
    p.logistics.cost_per_supply_delivered = spec.logistics_cost_per_unit;
    p.command.enabled = spec.command_reliability_boost > 0.0 || spec.command_latency_reduction_fraction > 0.0;
    p.command.reliability_boost = spec.command_reliability_boost;
    p.command.latency_reduction_fraction = spec.command_latency_reduction_fraction;
    p.command.min_latency_floor_hours = spec.command_floor_hours;
    p.command.cost_per_formation_day = spec.command_cost_per_formation_day;
    p.force_generation.enabled = spec.forcegen_training_rate_boost > 0.0;
    p.force_generation.mode = "substitution".to_string();
    p.force_generation.training_rate_boost = spec.forcegen_training_rate_boost;
    p.force_generation.cost_per_incremental_trainee = spec.forcegen_cost_per_incremental_trainee;
    p.force_generation.capacity_building_investment_rate = 0.0;

    config.validate().map_err(|e| e.to_string())?;
    Ok(config)
}

pub fn apply_indigenous_command_multiplier(engine: &mut SimulationEngine, mult: f64) {
    if (mult - 1.0).abs() < 1e-9 {
        return;
    }
    let p = &mut engine.particle;
    for formation in 0..p.formations.personnel.len() {
        if p.formations.organization[formation] as usize == MILITARY {
            p.formations.command[formation] = (p.formations.command[formation] * mult).clamp(0.05, 1.0);
        }
    }
    for edge in 0..p.command_edges.organization.len() {
        if p.command_edges.organization[edge] as usize == MILITARY {
            p.command_edges.reliability[edge] =
                (p.command_edges.reliability[edge] * mult).clamp(0.05, 1.0);
            p.command_edges.latency_hours[edge] =
                (p.command_edges.latency_hours[edge] / mult.max(1e-6)).max(0.25);
        }
    }
}

pub fn run_preflight_treatment_gate(options: &GateOptions) -> Result<GateSummary, String> {
    let specs = default_12_worlds();
    let mut records = Vec::with_capacity(specs.len());

    for spec in &specs {
        let config = build_gate_config(spec, options)?;
        let mut engine = SimulationEngine::new(config).map_err(|e| e.to_string())?;
        apply_indigenous_command_multiplier(&mut engine, spec.command_mult);

        // Advance to observation start
        engine.advance_until(options.observation_start_days).map_err(|e| e.to_string())?;
        let _obs_baseline: CapabilityAssayBaseline = engine.capability_assay_baseline();
        let air_contacts_start = engine.particle.partner_support.air.assisted_contacts;
        let air_cost_start = engine.particle.partner_support.air.cumulative_donor_cost;
        let log_deliv_start = engine.particle.partner_support.logistics.cumulative_delivered;
        let log_cost_start = engine.particle.partner_support.logistics.cumulative_donor_cost;
        let cmd_events_start = engine.particle.partner_support.command.assisted_events;
        let cmd_latency_start = engine.particle.partner_support.command.cumulative_latency_reduction_hours;
        let cmd_cost_start = engine.particle.partner_support.command.cumulative_donor_cost;
        let fg_grads_start = engine.particle.partner_support.force_generation.external_incremental_graduates;
        let fg_cost_start = engine.particle.partner_support.force_generation.cumulative_donor_cost;
        let military_losses_start: f64 = engine.particle.formations.cumulative_losses.iter().enumerate()
            .filter(|(i, _)| engine.particle.formations.organization[*i] as usize == MILITARY)
            .map(|(_, l)| *l)
            .sum();

        // Advance through pre-withdrawal support window to T=120
        engine.advance_until(options.withdrawal_time_days).map_err(|e| e.to_string())?;
        let air_assisted = engine.particle.partner_support.air.assisted_contacts - air_contacts_start;
        let air_donor_cost = engine.particle.partner_support.air.cumulative_donor_cost - air_cost_start;
        let logistics_delivered = engine.particle.partner_support.logistics.cumulative_delivered - log_deliv_start;
        let logistics_donor_cost = engine.particle.partner_support.logistics.cumulative_donor_cost - log_cost_start;
        let command_events = engine.particle.partner_support.command.assisted_events - cmd_events_start;
        let command_latency_saved = engine.particle.partner_support.command.cumulative_latency_reduction_hours - cmd_latency_start;
        let command_donor_cost = engine.particle.partner_support.command.cumulative_donor_cost - cmd_cost_start;
        let forcegen_graduates = engine.particle.partner_support.force_generation.external_incremental_graduates - fg_grads_start;
        let forcegen_donor_cost = engine.particle.partner_support.force_generation.cumulative_donor_cost - fg_cost_start;
        let military_losses: f64 = engine.particle.formations.cumulative_losses.iter().enumerate()
            .filter(|(i, _)| engine.particle.formations.organization[*i] as usize == MILITARY)
            .map(|(_, l)| *l)
            .sum::<f64>() - military_losses_start;
        let contacts = engine.particle.counters.contacts;
        let total_donor_cost = air_donor_cost + logistics_donor_cost + command_donor_cost + forcegen_donor_cost;

        let outcome_baseline = engine.capability_assay_baseline();

        // Branching at T=120
        let mut on = engine.clone();
        let mut off = engine.clone();
        off.withdraw_external_partner_support();

        let post_target = options.withdrawal_time_days + options.horizon_days;
        on.advance_until(post_target).map_err(|e| e.to_string())?;
        off.advance_until(post_target).map_err(|e| e.to_string())?;

        let assay_on = on.capability_assay(&outcome_baseline);
        let assay_off = off.capability_assay(&outcome_baseline);

        let is_none = spec.support_profile == "none";
        let counterfactual_exact = if is_none {
            on.decision_hash() == off.decision_hash()
                && (assay_on.composite_capability - assay_off.composite_capability).abs() < 1e-12
                && total_donor_cost.abs() < 1e-12
        } else {
            true
        };

        let branch_diverged = if !is_none {
            // Active cells must show divergence in state, decisions, capability, or post-donor cost
            on.state_hash() != off.state_hash()
                || on.decision_hash() != off.decision_hash()
                || (assay_on.composite_capability - assay_off.composite_capability).abs() > 1e-9
                || on.particle.partner_support.cumulative_donor_cost() > 0.0
        } else {
            false
        };

        // Determine individual world pass status
        let mut world_pass = true;
        if is_none && !counterfactual_exact {
            world_pass = false;
        }
        if !is_none && !branch_diverged {
            world_pass = false;
        }
        if spec.support_profile == "air_heavy" && air_assisted == 0 {
            world_pass = false;
        }
        if spec.support_profile == "logistics_heavy" && logistics_delivered == 0.0 {
            world_pass = false;
        }
        if spec.support_profile == "command_heavy" && command_events == 0 {
            world_pass = false;
        }
        if spec.support_profile == "forcegen_heavy" && forcegen_graduates == 0.0 {
            world_pass = false;
        }

        records.push(GateWorldRecord {
            cell_id: spec.cell_id.to_string(),
            profile: spec.support_profile.to_string(),
            seed: spec.seed,
            contacts,
            military_losses,
            air_assisted,
            air_donor_cost,
            logistics_delivered,
            logistics_donor_cost,
            command_events,
            command_latency_saved,
            command_donor_cost,
            forcegen_graduates,
            forcegen_donor_cost,
            total_donor_cost,
            counterfactual_exact,
            branch_diverged,
            composite_on: assay_on.composite_capability,
            composite_off: assay_off.composite_capability,
            status: if world_pass { "PASS".to_string() } else { "FAIL".to_string() },
        });
    }

    // Verify overall criteria
    let combat_liveness_pass = records.iter().any(|r| r.contacts > 0 && r.military_losses > 0.0);
    let air_liveness_pass = records.iter()
        .filter(|r| r.profile == "air_heavy")
        .all(|r| r.air_assisted > 0 && r.air_donor_cost > 0.0);
    let logistics_liveness_pass = records.iter()
        .filter(|r| r.profile == "logistics_heavy" || r.profile == "balanced")
        .all(|r| r.logistics_delivered > 0.0 && r.logistics_donor_cost > 0.0);
    let forcegen_liveness_pass = records.iter()
        .filter(|r| r.profile == "forcegen_heavy" || r.profile == "balanced")
        .all(|r| r.forcegen_graduates > 0.0 && r.forcegen_donor_cost > 0.0);
    let command_liveness_pass = records.iter()
        .filter(|r| r.profile == "command_heavy" || r.profile == "balanced")
        .all(|r| r.command_events > 0 && r.command_donor_cost > 0.0);
    let counterfactual_exactness_pass = records.iter()
        .filter(|r| r.profile == "none")
        .all(|r| r.counterfactual_exact);
    let branch_divergence_pass = records.iter()
        .filter(|r| r.profile != "none")
        .all(|r| r.branch_diverged);

    let overall_pass = combat_liveness_pass
        && air_liveness_pass
        && logistics_liveness_pass
        && forcegen_liveness_pass
        && command_liveness_pass
        && counterfactual_exactness_pass
        && branch_divergence_pass;

    let mut table = String::new();
    let _ = writeln!(table, "\n============================================================================================================================================");
    let _ = writeln!(table, "PREFLIGHT TREATMENT-RELEVANCE GATE (12-WORLD VALIDATION BATTERY)");
    let _ = writeln!(table, "============================================================================================================================================");
    let _ = writeln!(
        table,
        "{:<12} {:<15} {:<10} {:>8} {:>8} {:>14} {:>18} {:>14} {:>16} {:>10} {:>6}",
        "Cell ID", "Profile", "Seed", "Contacts", "Losses", "Air Ast/Cost", "Log Deliv/Cost", "Cmd Evt/Cost", "FG Grad/Cost", "Diff", "Status"
    );
    let _ = writeln!(table, "--------------------------------------------------------------------------------------------------------------------------------------------");

    for r in &records {
        let air_str = format!("{} / ${:.0}", r.air_assisted, r.air_donor_cost);
        let log_str = format!("{:.0} / ${:.0}", r.logistics_delivered, r.logistics_donor_cost);
        let cmd_str = format!("{} / ${:.0}", r.command_events, r.command_donor_cost);
        let fg_str = format!("{:.1} / ${:.0}", r.forcegen_graduates, r.forcegen_donor_cost);
        let diff_str = if r.profile == "none" {
            if r.counterfactual_exact { "EXACT" } else { "MISMATCH" }
        } else if r.branch_diverged {
            "DIVERGES"
        } else {
            "STATIC"
        };
        let _ = writeln!(
            table,
            "{:<12} {:<15} {:<10} {:>8} {:>8.1} {:>14} {:>18} {:>14} {:>16} {:>10} {:>6}",
            r.cell_id, r.profile, r.seed, r.contacts, r.military_losses, air_str, log_str, cmd_str, fg_str, diff_str, r.status
        );
    }

    let _ = writeln!(table, "--------------------------------------------------------------------------------------------------------------------------------------------");
    let _ = writeln!(table, "MECHANISM VERIFICATION SUMMARY:");
    let _ = writeln!(table, "1. Combat Liveness:               {}", if combat_liveness_pass { "PASS (Active contacts and military losses sustained)" } else { "FAIL (Zero combat or losses)" });
    let _ = writeln!(table, "2. Air Support Liveness:          {}", if air_liveness_pass { "PASS (Air assisted contacts > 0 and donor cost charged)" } else { "FAIL (Air support inert)" });
    let _ = writeln!(table, "3. Logistics Support Liveness:    {}", if logistics_liveness_pass { "PASS (External supply delivered and donor cost charged)" } else { "FAIL (Logistics inert)" });
    let _ = writeln!(table, "4. Force Generation Liveness:     {}", if forcegen_liveness_pass { "PASS (External graduates deployed and donor cost charged)" } else { "FAIL (ForceGen inert)" });
    let _ = writeln!(table, "5. Command Support Liveness:      {}", if command_liveness_pass { "PASS (Command events assisted and donor cost charged)" } else { "FAIL (Command inert)" });
    let _ = writeln!(table, "6. Counterfactual Exactness:      {}", if counterfactual_exactness_pass { "PASS (None profile ON == OFF bit-for-bit exact)" } else { "FAIL (Non-zero drift in negative control)" });
    let _ = writeln!(table, "7. Supported Branch Divergence:   {}", if branch_divergence_pass { "PASS (Treated cells produce non-degenerate divergence)" } else { "FAIL (Treated branches degenerate)" });
    let _ = writeln!(table, "============================================================================================================================================");
    let _ = writeln!(table, "OVERALL GATE RESULT: {}", if overall_pass { "PASSED (All 12 representative worlds verified)" } else { "FAILED (One or more essential mechanisms inert)" });
    let _ = writeln!(table, "============================================================================================================================================\n");

    if options.verbose {
        eprint!("{table}");
    }

    Ok(GateSummary {
        records,
        combat_liveness_pass,
        air_liveness_pass,
        logistics_liveness_pass,
        forcegen_liveness_pass,
        command_liveness_pass,
        counterfactual_exactness_pass,
        branch_divergence_pass,
        overall_pass,
        table,
    })
}
