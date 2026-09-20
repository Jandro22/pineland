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

const ADMINISTRATIVE: usize = 2;
const LEGAL: usize = 3;
const FISCAL: usize = 4;
const SOCIAL: usize = 5;
const EXPECTED: usize = 6;
const PHENOTYPE_GOVERNANCE_INVESTMENT: usize = 2;

fn reference_scale(elapsed_days: f64, reference_days: f64) -> f64 {
    elapsed_days / reference_days
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
        let production = if cycle_scale > 0.0 {
            (allocation / interval_need.max(1.0e-12)).min(capacity) * (1.0 - leakage)
        } else {
            0.0
        };
        let cost = allocation * 0.02;
        particle.organizations.capital[government] =
            (particle.organizations.capital[government] - cost).max(0.0);
        let offset = locality * CONTROL_DIMENSIONS;
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
    for locality in 0..locality_count {
        aggregate_insurgent_control(
            particle,
            locality,
            &[ADMINISTRATIVE, LEGAL, FISCAL, SOCIAL, EXPECTED],
        );
    }
}
