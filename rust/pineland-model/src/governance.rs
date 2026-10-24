//! Administrative and non-state governance transitions.
//!
//! This module follows `ProcessEngine.on_governance` in the Python oracle.
//! Government production is a locality flow funded from the government stock;
//! non-state governance is maintained per active franchise and then exposed
//! through the legacy aggregate insurgent control vector.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::python_exp;
use pineland_core::state::{clamp01, ParticleState, CONTROL_DIMENSIONS};
use pineland_core::topology::StaticTopology;

const PHYSICAL: usize = 1;
const ADMINISTRATIVE: usize = 2;
const LEGAL: usize = 3;
const FISCAL: usize = 4;
const SOCIAL: usize = 5;
const EXPECTED: usize = 6;
const PHENOTYPE_GOVERNANCE_INVESTMENT: usize = 2;

fn reference_scale(elapsed_days: f64, reference_days: f64) -> f64 {
    elapsed_days / reference_days
}

const FORMAL: usize = 0;

/// Background order that neither side's armed presence displaces: where
/// neither side holds ground, institutions are not "dominated" by anyone.
const BACKGROUND_ORDER: f64 = 0.05;

/// Insurgent physical dominance of a locality in [0,1): the insurgent share
/// of physical control, discounted by a background-order term so that a
/// locality nobody holds is not treated as insurgent-held.  This is the
/// single security signal the institutional dimensions respond to.
pub fn insurgent_dominance(particle: &ParticleState, locality: usize) -> f64 {
    let offset = locality * CONTROL_DIMENSIONS;
    let government = clamp01(
        particle
            .locality
            .government_control
            .get(offset + PHYSICAL)
            .copied()
            .unwrap_or(0.0),
    );
    let insurgent = clamp01(
        particle
            .locality
            .insurgent_control
            .get(offset + PHYSICAL)
            .copied()
            .unwrap_or(0.0),
    );
    clamp01(insurgent / (government + insurgent + BACKGROUND_ORDER))
}

/// Fraction of a relaxation gap closed over `elapsed_days` at `rate_per_30_days`.
fn relaxation(rate_per_30_days: f64, elapsed_days: f64) -> f64 {
    clamp01(1.0 - python_exp(-rate_per_30_days.max(0.0) * elapsed_days.max(0.0) / 30.0))
}

/// Contestation hazards (per 30 days at full insurgent dominance) under which
/// state institutions withdraw: tax collection goes first, then officials,
/// courts, and finally the social fabric of compliance.
const GOVERNMENT_EROSION: [(usize, f64); 4] =
    [(ADMINISTRATIVE, 0.20), (LEGAL, 0.15), (FISCAL, 0.25), (SOCIAL, 0.10)];

/// Reference expectation of state rule in an uncontested locality (the
/// initial EXPECTED level).  Expectations of who will rule follow the
/// physical balance over about two months.
const EXPECTED_REFERENCE: f64 = 0.70;
const EXPECTED_RATE: f64 = 0.5;

/// De jure (formal) authority is sticky: it erodes only under sustained
/// dominance, on a timescale of about a year, and never below half.
const FORMAL_REFERENCE: f64 = 0.98;
const FORMAL_RATE: f64 = 30.0 / 365.0;

/// Shadow-governance ceilings and build/decay rates (per 30 days) where the
/// insurgents dominate physically.  Extraction (fiscal) is built first and
/// fastest; dispute resolution (legal) and administration follow.
const SHADOW_GOVERNANCE: [(usize, f64, f64, f64); 4] = [
    (FISCAL, 0.70, 0.40, 0.20),
    (LEGAL, 0.50, 0.20, 0.10),
    (ADMINISTRATIVE, 0.45, 0.15, 0.10),
    (SOCIAL, 0.40, 0.10, 0.05),
];

/// Government side of territorial contestation for one locality.  State
/// institutions erode in proportion to insurgent physical dominance,
/// expectations of state rule track the balance, and formal authority erodes
/// slowly under sustained dominance.
pub fn contest_government_institutions(
    particle: &mut ParticleState,
    locality: usize,
    elapsed_days: f64,
) {
    if elapsed_days <= 0.0 || locality >= particle.locality.population.len() {
        return;
    }
    let dominance = insurgent_dominance(particle, locality);
    let offset = locality * CONTROL_DIMENSIONS;
    for (dimension, rate) in GOVERNMENT_EROSION {
        let lost = relaxation(rate * dominance, elapsed_days);
        let value = &mut particle.locality.government_control[offset + dimension];
        *value = clamp01(*value * (1.0 - lost));
    }
    let expected_target = EXPECTED_REFERENCE * (1.0 - dominance);
    let step = relaxation(EXPECTED_RATE, elapsed_days);
    let value = &mut particle.locality.government_control[offset + EXPECTED];
    *value = clamp01(*value + step * (expected_target - *value));
    let formal_target = FORMAL_REFERENCE * (1.0 - 0.5 * dominance);
    let step = relaxation(FORMAL_RATE, elapsed_days);
    let value = &mut particle.locality.government_control[offset + FORMAL];
    *value = clamp01(*value + step * (formal_target - *value));
}

/// Rate (per 30 days, at full funded production and security) at which
/// withdrawn state institutions return to a locality the state has secured.
/// Re-opening offices, courts and tax rolls is faster than building them from
/// nothing, but needs both budget-funded production and secure access.
const RECONSTITUTION_RATE: f64 = 0.25;

/// Government institutions withdrawn under contestation return toward their
/// pre-war reference (scaled by current administrative capacity) where the
/// state holds the ground and funds production.  Social compliance is not
/// restored administratively and is left to the social process.
pub fn reconstitute_government_institutions(
    particle: &mut ParticleState,
    locality: usize,
    funded_production: f64,
    elapsed_days: f64,
) {
    if elapsed_days <= 0.0 || locality >= particle.locality.population.len() {
        return;
    }
    let access = 1.0 - insurgent_dominance(particle, locality);
    let capacity = clamp01(particle.locality.administrative_capacity[locality]);
    let step = relaxation(
        RECONSTITUTION_RATE * clamp01(funded_production) * access * access,
        elapsed_days,
    );
    let offset = locality * CONTROL_DIMENSIONS;
    for (dimension, reference) in [
        (ADMINISTRATIVE, capacity),
        (LEGAL, 0.85 * capacity),
        (FISCAL, 0.65 * capacity),
    ] {
        let value = &mut particle.locality.government_control[offset + dimension];
        if *value < reference {
            *value = clamp01(*value + step * (reference - *value));
        }
    }
}

/// Insurgent shadow governance for one organization row: where the
/// organization holds the ground it extracts taxes, settles disputes and
/// administers; where it loses the ground those structures decay.
fn contest_shadow_governance(
    values: &mut [f64],
    dominance: f64,
    organization_share: f64,
    competence: f64,
    elapsed_days: f64,
) {
    let held = clamp01(dominance) * clamp01(organization_share);
    for (dimension, ceiling, build, decay) in SHADOW_GOVERNANCE {
        let target = ceiling * held * (0.5 + 0.5 * clamp01(competence));
        let current = clamp01(values[dimension]);
        let rate = if target > current {
            build * (0.25 + 0.75 * held)
        } else {
            decay * (0.5 + (1.0 - held))
        };
        values[dimension] = clamp01(current + relaxation(rate, elapsed_days) * (target - current));
    }
    let expected_target = EXPECTED_REFERENCE * held;
    let current = clamp01(values[EXPECTED]);
    values[EXPECTED] =
        clamp01(current + relaxation(EXPECTED_RATE, elapsed_days) * (expected_target - current));
}

fn continuous_capacity_update(
    current: f64,
    support: f64,
    gain_probability: f64,
    decay_probability: f64,
    elapsed_days: f64,
    reference_days: f64,
) -> f64 {
    if elapsed_days <= 0.0 {
        return clamp01(current);
    }
    let reference_days = reference_days.max(1.0e-12);
    let gain_probability = clamp01(gain_probability);
    let decay_probability = clamp01(decay_probability);
    let gain_hazard =
        -(1.0 - gain_probability).max(1.0e-15).ln() / reference_days * clamp01(support);
    let decay_hazard = -(1.0 - decay_probability).max(1.0e-15).ln() / reference_days;
    let total_hazard = gain_hazard + decay_hazard;
    if total_hazard <= 0.0 {
        return clamp01(current);
    }
    let equilibrium = gain_hazard / total_hazard;
    clamp01(
        equilibrium + (clamp01(current) - equilibrium) * python_exp(-total_hazard * elapsed_days),
    )
}

fn local_membership_rootedness(
    particle: &ParticleState,
    topology: &StaticTopology,
    organization: usize,
    locality: usize,
) -> (f64, f64, f64) {
    let mut represented_local = 0.0;
    let mut home_local = 0.0;
    let mut home_district = 0.0;
    let target_district = topology.locality_to_district[locality] as usize;
    for person in 0..particle.people.residence.len() {
        if particle.people.organization[person] as usize != organization
            || particle.people.armed_fraction[person] <= 0.0
            || particle.people.residence[person] as usize != locality
        {
            continue;
        }
        let represented =
            particle.people.represented_population[person] * particle.people.armed_fraction[person];
        if represented <= 0.0 {
            continue;
        }
        represented_local += represented;
        let home = particle.people.home[person] as usize;
        if home == locality {
            home_local += represented;
        }
        if topology
            .locality_to_district
            .get(home)
            .copied()
            .map(|district| district as usize == target_district)
            .unwrap_or(false)
        {
            home_district += represented;
        }
    }
    if represented_local <= 1.0e-12 {
        (0.0, 0.0, 0.0)
    } else {
        (
            represented_local,
            clamp01(home_local / represented_local),
            clamp01(home_district / represented_local),
        )
    }
}

fn aggregate_insurgent_control(
    particle: &mut ParticleState,
    locality: usize,
    dimensions: &[usize],
) {
    let organization_count = particle.organizations.kind.len();
    let locality_offset = locality * CONTROL_DIMENSIONS;
    let active_insurgents = (0..organization_count)
        .filter(|organization| {
            particle.organizations.active[*organization] != 0
                && particle.organizations.kind[*organization] == 3
        })
        .collect::<Vec<_>>();
    if active_insurgents.is_empty() {
        return;
    }
    // The initial Python franchise is itself named "insurgent" and its
    // locality vector is also the legacy aggregate row.  The oracle therefore
    // exposes the same row directly rather than taking a complement over a
    // second actor-specific entry.
    if active_insurgents.contains(&crate::INSURGENT) {
        let organization_offset = pineland_core::state::LocalityState::organization_control_offset(
            locality,
            crate::INSURGENT,
            organization_count,
        );
        for &dimension in dimensions {
            particle.locality.insurgent_control[locality_offset + dimension] = particle
                .locality
                .organization_control
                .get(organization_offset + dimension)
                .copied()
                .unwrap_or(particle.locality.insurgent_control[locality_offset + dimension]);
        }
        return;
    }
    for &dimension in dimensions {
        let mut complement = 1.0;
        for &organization in &active_insurgents {
            let offset = pineland_core::state::LocalityState::organization_control_offset(
                locality,
                organization,
                organization_count,
            );
            let value = particle
                .locality
                .organization_control
                .get(offset + dimension)
                .copied()
                .unwrap_or(0.0);
            complement *= 1.0 - clamp01(value);
        }
        particle.locality.insurgent_control[locality_offset + dimension] =
            clamp01(1.0 - complement);
    }
}

pub fn update(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    _time: f64,
    elapsed_days: f64,
) {
    if elapsed_days <= 0.0 {
        return;
    }
    let locality_count = topology.locality_count();
    let organization_count = particle.organizations.kind.len();
    particle
        .locality
        .ensure_organization_capacity(organization_count);
    let cycle_scale = reference_scale(elapsed_days, 30.0);
    let government = crate::GOVERNMENT;
    if crate::trace_env!("PINELAND_TERRITORY") {
        trace_territory(particle, topology, config, _time);
    }

    // Python's government production is ordered locality-by-locality because
    // each allocation charges the shared government account immediately.
    for locality in 0..locality_count {
        let capacity = particle.locality.administrative_capacity[locality];
        let leakage = topology
            .locality_governance_leakage
            .get(locality)
            .copied()
            .unwrap_or(0.0);
        let reference_need = particle.locality.economic_output[locality] * 0.01;
        let interval_need = reference_need * cycle_scale;
        let allocation = (particle.organizations.capital[government]
            / locality_count.max(1) as f64)
            .min(interval_need);
        let offset = locality * CONTROL_DIMENSIONS;
        // Institutions need physical security: production scales with the
        // government's share of armed presence, and insurgent physical control
        // erodes the non-physical dimensions it can contest.
        let security_access = 1.0 - insurgent_dominance(particle, locality);
        let production = if cycle_scale > 0.0 {
            (allocation / interval_need.max(1.0e-12)).min(capacity)
                * (1.0 - leakage)
                * security_access
        } else {
            0.0
        };
        contest_government_institutions(particle, locality, elapsed_days);
        reconstitute_government_institutions(particle, locality, production, elapsed_days);
        let cost = allocation * 0.02;
        particle.organizations.capital[government] =
            (particle.organizations.capital[government] - cost).max(0.0);
        particle.locality.government_control[offset + ADMINISTRATIVE] = clamp01(
            particle.locality.government_control[offset + ADMINISTRATIVE]
                + 0.006 * production * cycle_scale,
        );
        particle.locality.government_control[offset + LEGAL] = clamp01(
            particle.locality.government_control[offset + LEGAL] + 0.004 * production * cycle_scale,
        );
        particle.locality.government_control[offset + FISCAL] = clamp01(
            particle.locality.government_control[offset + FISCAL]
                + 0.003 * production * cycle_scale,
        );
        particle.locality.government_control[offset + SOCIAL] = clamp01(
            particle.locality.government_control[offset + SOCIAL]
                + 0.003 * production * cycle_scale,
        );
        particle.locality.government_control[offset + EXPECTED] = clamp01(
            particle.locality.government_control[offset + EXPECTED]
                + 0.002 * production * cycle_scale,
        );
    }

    if !config.nonstate_governance.enabled {
        return;
    }
    let active_insurgents = (0..organization_count)
        .filter(|organization| {
            particle.organizations.kind[*organization] == 3
                && particle.organizations.active[*organization] != 0
        })
        .collect::<Vec<_>>();
    // For the original `insurgent` organization, Python uses the legacy
    // aggregate row as the organization row.  Earlier social/physical/action
    // handlers can update that aggregate between governance events, so mirror
    // its current complete vector before applying the capacity transition.
    if active_insurgents.contains(&crate::INSURGENT) {
        for locality in 0..locality_count {
            let aggregate_offset = locality * CONTROL_DIMENSIONS;
            let organization_offset =
                pineland_core::state::LocalityState::organization_control_offset(
                    locality,
                    crate::INSURGENT,
                    organization_count,
                );
            let current = particle.locality.insurgent_control
                [aggregate_offset..aggregate_offset + CONTROL_DIMENSIONS]
                .to_vec();
            particle.locality.organization_control
                [organization_offset..organization_offset + CONTROL_DIMENSIONS]
                .copy_from_slice(&current);
        }
    }
    for organization in active_insurgents {
        for locality in 0..locality_count {
            let (represented_local, home_locality_share, home_district_share) =
                local_membership_rootedness(particle, topology, organization, locality);
            let member_capacity = clamp01(
                represented_local
                    / config
                        .organization_ecology
                        .minimum_proto_represented_population
                        .max(1.0e-12),
            );
            let force_capacity = clamp01(
                crate::actions::committed_fighter_equivalents(
                    particle,
                    organization,
                    locality,
                    config,
                ) / config
                    .organization_ecology
                    .minimum_formation_personnel
                    .max(1.0e-12),
            );
            let local_capacity = member_capacity.max(force_capacity);
            let rooted_share = home_locality_share.max(home_district_share);
            let institutional_capacity = clamp01(
                0.5 * particle.organizations.institutional_quality[organization]
                    + 0.5 * particle.organizations.capital_organizational[organization],
            );
            let phenotype_offset = organization * 8 + PHENOTYPE_GOVERNANCE_INVESTMENT;
            let investment = particle
                .organizations
                .phenotype
                .get(phenotype_offset)
                .copied()
                .unwrap_or(0.0)
                .clamp(0.0, 1.0);
            let support = clamp01(
                local_capacity * (0.5 + 0.5 * rooted_share) * institutional_capacity * investment,
            );
            let control_offset = pineland_core::state::LocalityState::organization_control_offset(
                locality,
                organization,
                organization_count,
            );
            for dimension in [ADMINISTRATIVE, LEGAL, FISCAL, EXPECTED] {
                let effective_support =
                    if local_capacity >= config.nonstate_governance.minimum_local_capacity {
                        support
                    } else {
                        0.0
                    };
                let old = particle.locality.organization_control[control_offset + dimension];
                particle.locality.organization_control[control_offset + dimension] =
                    continuous_capacity_update(
                        old,
                        effective_support,
                        config.nonstate_governance.gain_per_30_days,
                        config.nonstate_governance.decay_per_30_days,
                        elapsed_days,
                        30.0,
                    );
            }
        }
    }
    // Territorial contestation: shadow institutions follow who holds the
    // ground.  Local strength shares split the insurgent-held ground between
    // concurrently active insurgent organizations.
    let active_insurgents = (0..organization_count)
        .filter(|organization| {
            particle.organizations.kind[*organization] == 3
                && particle.organizations.active[*organization] != 0
        })
        .collect::<Vec<_>>();
    for locality in 0..locality_count {
        let dominance = insurgent_dominance(particle, locality);
        let strengths = active_insurgents
            .iter()
            .map(|&organization| {
                crate::actions::committed_fighter_equivalents(
                    particle,
                    organization,
                    locality,
                    config,
                )
                .max(0.0)
            })
            .collect::<Vec<_>>();
        let total: f64 = strengths.iter().sum();
        for (index, &organization) in active_insurgents.iter().enumerate() {
            let share = if active_insurgents.len() == 1 {
                1.0
            } else if total > 1.0e-9 {
                strengths[index] / total
            } else {
                1.0 / active_insurgents.len() as f64
            };
            let competence = clamp01(
                0.5 * particle.organizations.institutional_quality[organization]
                    + 0.5 * particle.organizations.capital_organizational[organization],
            );
            let offset = pineland_core::state::LocalityState::organization_control_offset(
                locality,
                organization,
                organization_count,
            );
            contest_shadow_governance(
                &mut particle.locality.organization_control[offset..offset + CONTROL_DIMENSIONS],
                dominance,
                share,
                competence,
                elapsed_days,
            );
        }
    }
    for locality in 0..locality_count {
        aggregate_insurgent_control(
            particle,
            locality,
            &[ADMINISTRATIVE, LEGAL, FISCAL, SOCIAL, EXPECTED],
        );
    }
}

/// Diagnostic per-locality territorial trace (PINELAND_TERRITORY=1).
pub fn trace_territory(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    time: f64,
) {
    for locality in 0..topology.locality_count() {
        let (mut gp, mut gs, mut ip, mut is) = (0.0, 0.0, 0.0, 0.0);
        for f in 0..particle.formations.personnel.len() {
            if particle.formations.locality[f] as usize != locality
                || particle.formations.active[f] == 0
                || particle.formations.personnel[f] <= 0.0
            {
                continue;
            }
            let org = particle.formations.organization[f] as usize;
            if org == crate::INSURGENT || particle.organizations.kind.get(org) == Some(&3) {
                ip += particle.formations.personnel[f];
                is += particle.formations.effective_strength(f);
            } else {
                gp += particle.formations.personnel[f];
                gs += particle.formations.effective_strength(f);
            }
        }
        let mut post = String::new();
        for p in 0..particle.security_posts.locality.len() {
            if particle.security_posts.locality[p] as usize == locality {
                post.push_str(&format!(
                    "{}:{:.0}/{} ",
                    particle.security_posts.organization[p],
                    particle.security_posts.personnel[p],
                    particle.security_posts.staffed[p]
                ));
            }
        }
        let fighters = crate::actions::committed_fighter_equivalents(
            particle,
            crate::INSURGENT,
            locality,
            config,
        );
        let o = locality * CONTROL_DIMENSIONS;
        eprintln!(
            "TERR t={:.0} loc={} pop={:.0} gform={:.0}/{:.0} iform={:.0}/{:.0} ifight={:.0} posts=[{}] g={:?} i={:?} eff={:.3}/{:.3}",
            time,
            locality,
            particle.locality.population[locality],
            gp,
            gs,
            ip,
            is,
            fighters,
            post.trim(),
            particle.locality.government_control[o..o + CONTROL_DIMENSIONS]
                .iter()
                .map(|v| (v * 100.0).round() / 100.0)
                .collect::<Vec<_>>(),
            particle.locality.insurgent_control[o..o + CONTROL_DIMENSIONS]
                .iter()
                .map(|v| (v * 100.0).round() / 100.0)
                .collect::<Vec<_>>(),
            particle.locality.effective_control(locality, 0),
            particle.locality.effective_control(locality, 1),
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::SimulationEngine;

    fn engine() -> SimulationEngine {
        let config = SimulationConfig {
            seed: 2026091019,
            initialization_seed: Some(2026091019),
            agent_count: 300,
            locality_count: 17,
            horizon_days: 60.0,
            output_mode: "ensemble".to_string(),
            ..SimulationConfig::default()
        };
        SimulationEngine::new(config).expect("engine")
    }

    fn set_physical(particle: &mut ParticleState, locality: usize, government: f64, insurgent: f64) {
        let offset = locality * CONTROL_DIMENSIONS;
        particle.locality.government_control[offset + PHYSICAL] = government;
        particle.locality.insurgent_control[offset + PHYSICAL] = insurgent;
    }

    fn assert_bounded(values: &[f64]) {
        for value in values {
            assert!(value.is_finite() && (0.0..=1.0).contains(value), "{value}");
        }
    }

    #[test]
    fn dominance_follows_physical_balance_with_background_order() {
        let mut engine = engine();
        let particle = &mut engine.particle;
        set_physical(particle, 0, 0.3, 0.0);
        assert_eq!(insurgent_dominance(particle, 0), 0.0);
        set_physical(particle, 0, 0.0, 0.0);
        assert_eq!(insurgent_dominance(particle, 0), 0.0);
        // A trace of insurgent presence where nobody holds ground is not
        // dominance; a strong insurgent presence against a hollow state is.
        set_physical(particle, 0, 0.0, 0.01);
        assert!(insurgent_dominance(particle, 0) < 0.2);
        set_physical(particle, 0, 0.02, 0.4);
        let dominance = insurgent_dominance(particle, 0);
        assert!(dominance > 0.85 && dominance < 1.0, "{dominance}");
    }

    #[test]
    fn insurgent_dominance_erodes_state_institutions_but_not_uncontested_ones() {
        let mut engine = engine();
        let particle = &mut engine.particle;
        set_physical(particle, 0, 0.02, 0.4);
        set_physical(particle, 1, 0.3, 0.0);
        let before0 = particle.locality.government_control[0..CONTROL_DIMENSIONS].to_vec();
        let offset1 = CONTROL_DIMENSIONS;
        let before1 =
            particle.locality.government_control[offset1..offset1 + CONTROL_DIMENSIONS].to_vec();
        contest_government_institutions(particle, 0, 90.0);
        contest_government_institutions(particle, 1, 90.0);
        let after0 = particle.locality.government_control[0..CONTROL_DIMENSIONS].to_vec();
        let after1 =
            particle.locality.government_control[offset1..offset1 + CONTROL_DIMENSIONS].to_vec();
        assert_bounded(&after0);
        assert_bounded(&after1);
        for dimension in [ADMINISTRATIVE, LEGAL, FISCAL, SOCIAL, EXPECTED] {
            assert!(after0[dimension] < before0[dimension], "dim {dimension}");
        }
        assert!(after0[FISCAL] < 0.6 * before0[FISCAL]);
        assert!(after0[ADMINISTRATIVE] < 0.7 * before0[ADMINISTRATIVE]);
        // Formal authority is sticky: it moves, but slowly and never below half.
        assert!(after0[FORMAL] < before0[FORMAL] && after0[FORMAL] > 0.85 * before0[FORMAL]);
        for dimension in [ADMINISTRATIVE, LEGAL, FISCAL, SOCIAL] {
            assert_eq!(after1[dimension], before1[dimension], "dim {dimension}");
        }
        assert!((after1[EXPECTED] - EXPECTED_REFERENCE).abs() <= (before1[EXPECTED] - EXPECTED_REFERENCE).abs());
        // Long-run floor for formal authority.
        for _ in 0..200 {
            contest_government_institutions(particle, 0, 30.0);
        }
        assert!(particle.locality.government_control[FORMAL] >= 0.49 * FORMAL_REFERENCE);
        assert_bounded(&particle.locality.government_control[0..CONTROL_DIMENSIONS]);
    }

    #[test]
    fn withdrawn_institutions_return_only_where_the_state_holds_ground() {
        let mut engine = engine();
        let particle = &mut engine.particle;
        for locality in [0usize, 1] {
            let offset = locality * CONTROL_DIMENSIONS;
            particle.locality.government_control[offset + ADMINISTRATIVE] = 0.05;
            particle.locality.administrative_capacity[locality] = 0.7;
        }
        set_physical(particle, 0, 0.4, 0.0);
        set_physical(particle, 1, 0.0, 0.4);
        reconstitute_government_institutions(particle, 0, 0.5, 90.0);
        reconstitute_government_institutions(particle, 1, 0.5, 90.0);
        let secured = particle.locality.government_control[ADMINISTRATIVE] - 0.05;
        let dominated =
            particle.locality.government_control[CONTROL_DIMENSIONS + ADMINISTRATIVE] - 0.05;
        assert!(secured > 0.15, "{secured}");
        assert!(dominated >= 0.0 && dominated < 0.05 * secured, "{dominated}");
        // Never pushes above the reference.
        for _ in 0..100 {
            reconstitute_government_institutions(particle, 0, 1.0, 30.0);
        }
        assert!(particle.locality.government_control[ADMINISTRATIVE] <= 0.7 + 1.0e-12);
    }

    #[test]
    fn shadow_governance_builds_where_held_and_decays_where_lost() {
        let mut values = [0.0; CONTROL_DIMENSIONS];
        contest_shadow_governance(&mut values, 0.9, 1.0, 0.5, 90.0);
        assert_bounded(&values);
        assert!(values[FISCAL] > 0.2, "{:?}", values);
        assert!(values[FISCAL] > values[LEGAL] && values[LEGAL] > values[SOCIAL]);
        assert!(values[EXPECTED] > 0.3);
        let built = values;
        // A franchise holding only a sliver of the contested ground builds less.
        let mut minority = [0.0; CONTROL_DIMENSIONS];
        contest_shadow_governance(&mut minority, 0.9, 0.2, 0.5, 90.0);
        assert!(minority[FISCAL] < built[FISCAL]);
        // Once the ground is lost the structures decay.
        contest_shadow_governance(&mut values, 0.0, 1.0, 0.5, 180.0);
        assert_bounded(&values);
        assert!(values[FISCAL] < 0.5 * built[FISCAL]);
        assert!(values[EXPECTED] < 0.2 * built[EXPECTED]);
        // Out-of-range inputs stay bounded.
        let mut extreme = [2.0, -1.0, 5.0, 1.0, 1.0, 1.0, 1.0];
        contest_shadow_governance(&mut extreme, 7.0, 3.0, -2.0, 1.0e6);
        assert_bounded(&extreme[2..]);
    }

    #[test]
    fn governance_update_shifts_locality_control_toward_dominant_side() {
        let mut engine = engine();
        let topology = engine.topology.clone();
        let config = engine.config.clone();
        let particle = &mut engine.particle;
        let government_before = particle.locality.effective_control(0, 0);
        let insurgent_before = particle.locality.effective_control(0, 1);
        let secure_before = particle.locality.effective_control(1, 0);
        for step in 0..6 {
            set_physical(particle, 0, 0.02, 0.4);
            set_physical(particle, 1, 0.4, 0.0);
            update(particle, &topology, &config, 30.0 * (step + 1) as f64, 30.0);
        }
        let government_after = particle.locality.effective_control(0, 0);
        let insurgent_after = particle.locality.effective_control(0, 1);
        assert!(government_after < government_before - 0.08, "{government_before} -> {government_after}");
        assert!(insurgent_after > insurgent_before + 0.08, "{insurgent_before} -> {insurgent_after}");
        assert!(particle.locality.effective_control(1, 0) >= secure_before - 0.02);
        assert_bounded(&particle.locality.government_control);
        assert_bounded(&particle.locality.insurgent_control);
    }
}
