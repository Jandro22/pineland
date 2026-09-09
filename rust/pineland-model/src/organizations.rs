//! Endogenous organization ecology over the fixed numeric organization table.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{python_exp, PyRandomCompat};
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

fn local_embeddedness(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
) -> f64 {
    let threshold = config
        .organization_ecology
        .minimum_formation_personnel
        .max(1e-12);
    let target_district = topology.locality_to_district[locality] as usize;
    let mut represented_local = 0.0;
    let mut home_local = 0.0;
    let mut home_district = 0.0;
    for person in 0..particle.people.locality.len() {
        if particle.people.organization[person] as usize != organization
            || particle.people.locality[person] as usize != locality
            || particle.people.armed_fraction[person] <= 0.0
        {
            continue;
        }
        let represented =
            particle.people.represented_population[person] * particle.people.armed_fraction[person];
        if represented <= 0.0 {
            continue;
        }
        represented_local += represented;
        if particle.people.home[person] as usize == locality {
            home_local += represented;
        }
        if topology
            .locality_to_district
            .get(particle.people.home[person] as usize)
            .copied()
            .unwrap_or(u32::MAX) as usize
            == target_district
        {
            home_district += represented;
        }
    }
    let member_depth = (represented_local
        / config
            .organization_ecology
            .minimum_proto_represented_population
            .max(1e-12))
    .clamp(0.0, 1.0);
    let origin_depth = if represented_local > 0.0 {
        ((home_local / represented_local + home_district / represented_local) / 2.0).clamp(0.0, 1.0)
    } else {
        0.0
    };
    let member_channel = member_depth * (0.5 + 0.5 * origin_depth);

    let mut pooled = 0.0;
    let mut reserve = 0.0;
    for index in 0..particle.manpower.pool.len() {
        if particle.manpower.organization[index] as usize == organization
            && particle.manpower.locality[index] as usize == locality
        {
            pooled += particle.manpower.pool[index].max(0.0);
            reserve += particle.manpower.supply_reserve[index].max(0.0);
        }
    }
    let supply_per_fighter = (config.logistics.formation_supply_days
        * config.logistics.initial_supply_fraction)
        .max(1e-12);
    let pool_depth = (pooled.min(reserve / supply_per_fighter) / threshold).clamp(0.0, 1.0);
    let pool_channel = pool_depth
        * particle
            .organizations
            .local_knowledge
            .get(organization)
            .copied()
            .unwrap_or(0.0)
            .clamp(0.0, 1.0);

    let formation_indices = (0..particle.formations.personnel.len())
        .filter(|&formation| {
            particle.formations.organization[formation] as usize == organization
                && particle.formations.locality[formation] as usize == locality
                && particle.formations.personnel[formation] > 0.0
                && particle.formations.moving[formation] == 0
                && particle.formations.outside_pineland[formation] == 0
                && particle.formations.operational_status[formation] == 1
        })
        .collect::<Vec<_>>();
    let fielded = formation_indices
        .iter()
        .map(|&formation| particle.formations.personnel[formation].max(0.0))
        .sum::<f64>();
    let formation_channel = if fielded > 0.0 {
        let weighted = formation_indices
            .iter()
            .map(|&formation| {
                particle.formations.personnel[formation].max(0.0)
                    * particle.formations.embeddedness[formation].clamp(0.0, 1.0)
            })
            .sum::<f64>();
        (fielded / threshold).clamp(0.0, 1.0) * weighted / fielded
    } else {
        0.0
    };
    let offset = locality * pineland_core::state::CONTROL_DIMENSIONS;
    let institutional_channel = if organization == crate::INSURGENT {
        ((particle.locality.insurgent_control[offset + 5]
            + particle.locality.insurgent_control[offset + 2]
            + particle.locality.insurgent_control[offset + 6])
            / 3.0)
            .clamp(0.0, 1.0)
    } else {
        0.0
    };
    let mut complement = 1.0;
    for value in [
        member_channel,
        pool_channel,
        formation_channel,
        institutional_channel,
    ] {
        complement *= 1.0 - value.clamp(0.0, 1.0);
    }
    (1.0 - complement).clamp(0.0, 1.0)
}

/// Renew/decay the persistent locality foothold stock at the same event
/// boundaries as Python's `advance_local_footholds`.  This transition is
/// deterministic and must not consume an ecology/process RNG draw.
pub fn advance_footholds(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    time: f64,
) {
    if !config.organization_ecology.enabled {
        return;
    }
    let threshold = config
        .organization_ecology
        .local_foothold_viability_threshold
        .clamp(0.0, 1.0);
    let base_memory = config
        .organization_ecology
        .local_foothold_memory_days
        .max(1e-9);
    let locality_count = topology.locality_count();
    for organization in 0..particle.organizations.kind.len() {
        for locality in 0..locality_count {
            let index = organization * locality_count + locality;
            if index >= particle.footholds.strength.len() {
                continue;
            }
            if particle.footholds.active[index] == 0 {
                continue;
            }
            let elapsed = (time - particle.footholds.updated_at[index]).max(0.0);
            let memory_days = base_memory
                * (0.5
                    + particle
                        .organizations
                        .persistence
                        .get(organization)
                        .copied()
                        .unwrap_or(0.0)
                        .clamp(0.0, 1.0));
            let retention = python_exp(-elapsed / memory_days.max(1e-9));
            let previous = particle.footholds.strength[index].clamp(0.0, 1.0);
            let raw = local_embeddedness(particle, topology, config, organization, locality);
            if raw > 1e-12 {
                particle.footholds.renewal_count[index] =
                    particle.footholds.renewal_count[index].saturating_add(1);
            }
            if previous >= threshold {
                particle.footholds.cumulative_active_days[index] += elapsed;
            }
            let updated = (previous * retention).max(raw).clamp(0.0, 1.0);
            if previous < threshold && updated >= threshold {
                particle.footholds.viable_activation_count[index] =
                    particle.footholds.viable_activation_count[index].saturating_add(1);
                if particle.footholds.first_activated_at[index] < -1.0e8 {
                    particle.footholds.first_activated_at[index] = time;
                }
                particle.footholds.last_activated_at[index] = time;
            } else if updated >= threshold {
                particle.footholds.last_activated_at[index] = time;
            }
            particle.footholds.strength[index] = updated;
            particle.footholds.raw_signal[index] = raw;
            // The legacy native component named `embeddedness` is the
            // Python foothold strength projection used by the certificate.
            particle.footholds.embeddedness[index] = updated;
            particle.footholds.updated_at[index] = time;
        }
    }
}

/// Record a realized violent organized action as local organizational
/// renewal.  Python applies this after the action handler, before the second
/// same-boundary foothold advance; keeping the small mutation explicit lets
/// callers preserve that ordering without adding a stochastic draw.
pub(crate) fn record_foothold_action(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    organization: usize,
    locality: usize,
) {
    if organization >= particle.organizations.kind.len() || locality >= topology.locality_count() {
        return;
    }
    let index = organization * topology.locality_count() + locality;
    if index >= particle.footholds.cumulative_actions.len() {
        return;
    }
    particle.footholds.active[index] = 1;
    particle.footholds.cumulative_actions[index] += 1.0;
    particle.footholds.renewal_count[index] =
        particle.footholds.renewal_count[index].saturating_add(1);
}

pub fn update(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
    elapsed_days: f64,
) {
    // The Python process engine treats the initialization-time ecology event
    // as a true no-op.  In particular, it must not consume the ecology RNG
    // stream or mutate organization/foothold state before a positive ecology
    // interval has elapsed.
    if !config.organization_ecology.enabled || elapsed_days <= 0.0 {
        return;
    }
    for organization in 0..particle.organizations.active.len() {
        if particle.organizations.active[organization] == 0 {
            continue;
        }
        let adaptation = config.organization_ecology.adaptation_rate * 0.01;
        particle.organizations.cohesion[organization] = clamp01(
            particle.organizations.cohesion[organization]
                + adaptation * (0.6 - particle.organizations.cohesion[organization]),
        );
        particle.organizations.capital[organization] = (particle.organizations.capital
            [organization]
            + particle.organizations.external_support[organization] * 0.01)
            .max(0.0);
        if rng.random()
            < config.organization_ecology.succession_base_hazard
                * config.organization_ecology.interval_days
        {
            particle.organizations.succession_count[organization] =
                particle.organizations.succession_count[organization].saturating_add(1);
            particle.organizations.persistence[organization] =
                clamp01(particle.organizations.persistence[organization] + 0.02);
        }
    }
    let n = topology.locality_count();
    for locality in 0..n {
        let index = crate::INSURGENT * n + locality;
        let age = (time - particle.footholds.updated_at[index]).max(0.0);
        let recent = (-age
            / config
                .organization_ecology
                .local_foothold_memory_days
                .max(f64::MIN_POSITIVE))
        .exp();
        particle.footholds.sustainment[index] =
            clamp01(particle.footholds.sustainment[index] * (0.98 + 0.02 * recent));
        if particle.footholds.strength[index]
            > config.organization_ecology.minimum_formation_personnel
        {
            particle.footholds.viable_activation_count[index] =
                particle.footholds.viable_activation_count[index].saturating_add(1);
        }
        if rng.random()
            < config.organization_ecology.collapse_base_hazard
                * config.organization_ecology.interval_days
                * (1.0 - particle.footholds.sustainment[index])
        {
            particle.footholds.active[index] = 0;
            particle.footholds.strength[index] *= 0.5;
        }
    }
}

pub fn onset_hazard(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    locality: usize,
) -> f64 {
    if locality >= topology.locality_count() {
        return 0.0;
    }
    let offset = locality * pineland_core::state::CONTROL_DIMENSIONS;
    config.organization_ecology.birth_base_hazard
        * (1.0 - particle.locality.government_control[offset + 5])
        * (1.0 + particle.locality.violence[locality])
}
