//! Spatial armed contact opportunity and combat resolution.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{python_exp, python_sum, PyRandomCompat};
use pineland_core::scheduler::EventPayload;
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

pub fn schedule_contacts(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
) -> Result<(), pineland_core::scheduler::SchedulerError> {
    if !config.include_insurgency {
        return Ok(());
    }
    let mut candidates = Vec::new();
    for first in 0..particle.formations.personnel.len() {
        if particle.formations.active[first] == 0
            || particle.formations.organization[first] as usize != crate::INSURGENT
        {
            continue;
        }
        for second in 0..particle.formations.personnel.len() {
            if particle.formations.active[second] == 0
                || !matches!(
                    particle.formations.organization[second] as usize,
                    crate::MILITARY | crate::POLICE
                )
            {
                continue;
            }
            if first == second {
                continue;
            }
            let locality_a = particle.formations.locality[first] as usize;
            let locality_b = particle.formations.locality[second] as usize;
            let distance = topology.locality_distance(locality_a.into(), locality_b.into());
            if locality_a != locality_b && distance > 35.0 {
                continue;
            }
            let pressure = if locality_a == locality_b { 1.0 } else { 0.35 };
            let readiness = (particle.formations.effective_readiness(first)
                + particle.formations.effective_readiness(second))
                / 2.0;
            let probability = 1.0
                - (-config.contact_rate.max(0.0)
                    * config.intervals.contact
                    * pressure
                    * (0.2 + readiness))
                    .exp();
            if rng.random() < probability {
                candidates.push((
                    first,
                    second,
                    locality_a,
                    particle.formations.microzone[first] as usize,
                ));
            }
        }
    }
    candidates.sort_unstable();
    candidates.dedup();
    for (first, second, locality, microzone) in candidates {
        particle.scheduler.schedule(
            time,
            100,
            EventPayload::Contact {
                first: first.into(),
                second: second.into(),
                locality: locality.into(),
                microzone: microzone.into(),
            },
        )?;
    }
    Ok(())
}

fn logistic(value: f64) -> f64 {
    if value >= 0.0 {
        1.0 / (1.0 + python_exp(-value))
    } else {
        let exponential = python_exp(value);
        exponential / (1.0 + exponential)
    }
}

fn organization_is_insurgent(particle: &ParticleState, organization: usize) -> bool {
    particle.organizations.kind.get(organization).copied() == Some(3)
}

fn organizations_hostile(particle: &ParticleState, first: usize, second: usize) -> bool {
    if first == second {
        return false;
    }
    particle
        .relations
        .organization_a
        .iter()
        .zip(&particle.relations.organization_b)
        .zip(&particle.relations.status)
        .any(|((a, b), status)| {
            ((*a as usize == first && *b as usize == second)
                || (*a as usize == second && *b as usize == first))
                && *status == 4
        })
}

fn formation_microzone(
    particle: &ParticleState,
    topology: &StaticTopology,
    formation: usize,
) -> usize {
    let locality = particle.formations.locality[formation] as usize;
    let current = particle.formations.microzone[formation] as usize;
    if topology
        .microzone_to_locality
        .get(current)
        .copied()
        .is_some_and(|value| value as usize == locality)
    {
        return current;
    }
    if let Some(patrol) = particle
        .patrols
        .formation
        .iter()
        .position(|value| *value as usize == formation)
    {
        return particle.patrols.route_position[patrol] as usize;
    }
    if let Some(post) = particle
        .security_posts
        .formation
        .iter()
        .position(|value| *value as usize == formation)
    {
        return particle.security_posts.microzone[post] as usize;
    }
    topology
        .zones_for_locality(locality.into())
        .max_by(|left, right| {
            topology.zone_population_share[*left]
                .total_cmp(&topology.zone_population_share[*right])
                .then_with(|| right.cmp(left))
        })
        .unwrap_or_else(|| topology.primary_zone[locality] as usize)
}

fn capability(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    formation: usize,
    microzone: usize,
    initiative: f64,
) -> f64 {
    let terrain = particle
        .zones
        .terrain_friction
        .get(microzone)
        .copied()
        .or_else(|| topology.zone_terrain_friction.get(microzone).copied())
        .unwrap_or(1.0);
    let observability = particle
        .zones
        .observability
        .get(microzone)
        .copied()
        .or_else(|| topology.zone_observability.get(microzone).copied())
        .unwrap_or(0.5);
    let mobility = (particle.formations.mobility[formation] / terrain.max(0.35)).clamp(0.15, 1.0);
    let observation = 0.35 + 0.65 * observability;
    let embedded = 0.55 + 0.45 * particle.formations.embeddedness[formation].clamp(0.0, 1.0);
    // V2 separates accumulated field experience from structural quality.
    // At 0.5 experience the multiplier is exactly one; the extension is
    // gated so parity-era runs retain their historical capability equation.
    let experience = if config.state_regeneration.enabled {
        0.75 + 0.50 * particle.formations.experience[formation].clamp(0.0, 1.0)
    } else {
        1.0
    };
    (particle
        .formations
        .available_personnel(formation)
        .max(0.0)
        .powf(0.72)
        * particle.formations.quality[formation]
        * experience
        * particle.formations.cohesion[formation].max(0.05)
        * observation
        * mobility.powf(0.35)
        * embedded
        * initiative)
        .max(1.0e-9)
}

fn consume_formation_supply(
    particle: &mut ParticleState,
    formation: usize,
    demand: f64,
) -> (f64, f64) {
    let demanded = demand.max(0.0);
    let consumed = particle.formations.supply_stock[formation]
        .max(0.0)
        .min(demanded);
    particle.formations.supply_stock[formation] -= consumed;
    particle.formations.sustainment[formation] = particle.formations.supply_fraction(formation);
    particle.logistics.cumulative_consumed += consumed;
    (consumed, demanded - consumed)
}

fn presence_personnel(
    _particle: &ParticleState,
    state: &pineland_core::state::PresenceState,
    observer: u32,
    target: u32,
    locality: u32,
    microzone: u32,
    target_formation: u32,
) -> Option<f64> {
    state
        .keys
        .iter()
        .enumerate()
        .find(|(index, key)| {
            key.observer == observer
                && key.target == target
                && key.locality == locality
                && key.microzone == microzone
                && key.target_formation == target_formation
                && state.evidence_count.get(*index).copied().unwrap_or(0) > 0
                && state.personnel.get(*index).copied().unwrap_or(0.0) > 0.0
        })
        .and_then(|(index, _)| state.personnel.get(index).copied())
}

fn perceived_disadvantage(
    particle: &ParticleState,
    observer: usize,
    opponent: usize,
    locality: usize,
    microzone: usize,
    own_reference: f64,
) -> f64 {
    let node_observer = (particle.organizations.kind.len() + observer) as u32;
    let target = particle.formations.organization[opponent];
    let candidates = [
        presence_personnel(
            particle,
            &particle.node_presence_beliefs,
            node_observer,
            target,
            locality as u32,
            microzone as u32,
            opponent as u32,
        ),
        presence_personnel(
            particle,
            &particle.node_presence_beliefs,
            node_observer,
            target,
            locality as u32,
            microzone as u32,
            u32::MAX,
        ),
        presence_personnel(
            particle,
            &particle.presence_beliefs,
            particle.formations.organization[observer],
            target,
            locality as u32,
            microzone as u32,
            opponent as u32,
        ),
        presence_personnel(
            particle,
            &particle.presence_beliefs,
            particle.formations.organization[observer],
            target,
            locality as u32,
            microzone as u32,
            u32::MAX,
        ),
    ];
    let estimate = candidates
        .into_iter()
        .flatten()
        .next()
        .unwrap_or(own_reference);
    (estimate.max(1.0) / own_reference.max(1.0))
        .ln()
        .clamp(-3.0, 3.0)
}

pub(crate) fn update_relations(
    particle: &mut ParticleState,
    first: usize,
    second: usize,
    magnitude: f64,
    time: f64,
    config: &SimulationConfig,
) {
    if let Some(index) = particle
        .relations
        .organization_a
        .iter()
        .zip(&particle.relations.organization_b)
        .position(|(a, b)| {
            (*a as usize == first && *b as usize == second)
                || (*a as usize == second && *b as usize == first)
        })
    {
        let magnitude = clamp01(magnitude);
        if crate::trace_env!("PINELAND_RELATION_TRACE") {
            eprintln!(
                "RELATION_UPDATE first={} second={} index={} magnitude={:.17}",
                first, second, index, magnitude
            );
        }
        particle.relations.hostility_memory[index] =
            clamp01(1.0 - (1.0 - particle.relations.hostility_memory[index]) * (1.0 - magnitude));
        particle.relations.rivalry_memory[index] = clamp01(
            1.0 - (1.0 - particle.relations.rivalry_memory[index]) * (1.0 - 0.5 * magnitude),
        );
        particle.relations.cooperation_memory[index] *= 1.0 - magnitude;
        particle.relations.last_interaction_at[index] = time;
        particle.relations.updated_at[index] = time;
        particle.relations.has_last_interaction[index] = 1;
        if particle.relations.hostility_memory[index] >= config.relationships.hostility_threshold {
            particle.relations.status[index] = 4;
        } else if particle.relations.rivalry_memory[index] >= config.relationships.rivalry_threshold
        {
            particle.relations.status[index] = 3;
        }
    }
}

fn refresh_membership_projections(particle: &mut ParticleState) {
    let locality_count = particle.locality.population.len();
    let organization_count = particle.organizations.kind.len();
    for organization in 0..organization_count {
        let mut masses = Vec::new();
        for person in 0..particle.people.locality.len() {
            if particle.people.organization[person] as usize == organization {
                masses.push(
                    particle.people.represented_population[person]
                        * particle.people.armed_fraction[person],
                );
            }
        }
        particle.organizations.member_population[organization] = python_sum(&masses);
        for locality in 0..locality_count {
            let index = organization * locality_count + locality;
            if index >= particle.footholds.membership.len() {
                continue;
            }
            if !organization_is_insurgent(particle, organization) {
                particle.footholds.membership[index] = 0.0;
                continue;
            }
            let mut local_masses = Vec::new();
            for person in 0..particle.people.residence.len() {
                if particle.people.organization[person] as usize == organization
                    && particle.people.residence[person] as usize == locality
                {
                    local_masses.push(
                        particle.people.represented_population[person]
                            * particle.people.armed_fraction[person],
                    );
                }
            }
            particle.footholds.membership[index] =
                python_sum(&local_masses) / particle.locality.population[locality].max(1.0e-12);
        }
    }
}

fn apply_direct_civilian_harm(
    particle: &mut ParticleState,
    config: &SimulationConfig,
    locality: usize,
    district: usize,
    direct_harm: f64,
) -> (f64, f64) {
    let mut residents = Vec::new();
    let mut civilian_masses = Vec::new();
    for person in 0..particle.people.residence.len() {
        if particle.people.residence[person] as usize != locality
            || particle.people.external_state[person] != u32::MAX
            || particle.people.represented_population[person] <= 0.0
        {
            continue;
        }
        residents.push(person);
        civilian_masses.push(
            particle.people.represented_population[person]
                * (1.0 - particle.people.armed_fraction[person]).max(0.0),
        );
    }
    let represented = python_sum(&civilian_masses);
    let deaths = represented
        .min(direct_harm.max(0.0) * config.civilian_dynamics.fatality_fraction_of_direct_harm);
    let injuries = (represented - deaths)
        .max(0.0)
        .min(direct_harm.max(0.0) * config.civilian_dynamics.injury_fraction_of_direct_harm);
    if deaths > 0.0 && represented > 0.0 {
        for (person, civilian_mass) in residents
            .iter()
            .copied()
            .zip(civilian_masses.iter().copied())
        {
            let old_weight = particle.people.represented_population[person];
            let old_armed_mass = old_weight * particle.people.armed_fraction[person];
            let share = civilian_mass / represented;
            let new_weight = (old_weight - deaths * share).max(0.0);
            particle.people.represented_population[person] = new_weight;
            particle.people.armed_fraction[person] = if new_weight > 1.0e-12 {
                (old_armed_mass / new_weight).min(1.0)
            } else {
                0.0
            };
        }
        particle.locality.population[locality] =
            (particle.locality.population[locality] - deaths).max(0.0);
        if let Some(population) = particle.locality.district_population.get_mut(district) {
            *population = (*population - deaths).max(0.0);
        }
        if let Some(is_integer) = particle
            .locality
            .district_population_is_integer
            .get_mut(district)
        {
            // civilian.py assigns float(float(population) - deaths), even
            // when the resulting numeric value happens to be integral.
            *is_integer = 0;
        }
        particle.counters.deaths += deaths;
    }
    particle.counters.civilian_harm += direct_harm.max(0.0);
    refresh_membership_projections(particle);
    (deaths, injuries)
}

fn update_perceived_momentum(
    particle: &mut ParticleState,
    config: &SimulationConfig,
    locality: usize,
    signal: f64,
    civilian_harm: f64,
    first: usize,
    second: usize,
    rng: &mut PyRandomCompat,
) {
    let trace = crate::trace_env!("PINELAND_MOMENTUM_TRACE");
    if trace {
        eprintln!(
            "MOMENTUM_BEGIN time-locality={} signal={:.17} first_org={} second_org={}",
            locality,
            signal,
            particle.formations.organization[first],
            particle.formations.organization[second],
        );
    }
    let first_insurgent =
        organization_is_insurgent(particle, particle.formations.organization[first] as usize);
    let second_insurgent =
        organization_is_insurgent(particle, particle.formations.organization[second] as usize);
    let state_vs_insurgent = first_insurgent != second_insurgent;
    let both_insurgent = first_insurgent && second_insurgent;
    let harm_scale = civilian_harm / (particle.locality.population[locality] * 0.001).max(1.0);
    for person in 0..particle.people.residence.len() {
        if particle.people.residence[person] as usize != locality {
            continue;
        }
        let reach = clamp01(
            0.15 + 0.55 * particle.locality.observability[locality]
                + 0.3 * particle.people.efficacy[person],
        );
        let reach_draw = rng.random();
        if reach_draw > reach {
            continue;
        }
        let interpretation_noise = rng.normalvariate(0.0, config.reporting_error);
        let interpretation = clamp01(signal + interpretation_noise);
        if trace {
            eprintln!(
                "MOMENTUM_DETAIL person={} reach_draw={:.17} reach={:.17} noise={:.17} interpretation={:.17}",
                person, reach_draw, reach, interpretation_noise, interpretation
            );
        }
        if state_vs_insurgent {
            let attribution = harm_scale
                * (1.0
                    - particle
                        .organizations
                        .discipline
                        .get(crate::GOVERNMENT)
                        .copied()
                        .unwrap_or(0.5));
            let government_offset = person * 2;
            particle.people.expected_control[government_offset] = clamp01(
                particle.people.expected_control[government_offset]
                    + config.combat.momentum_learning_rate * (interpretation - 0.5)
                    - 0.04 * attribution,
            );
            if particle
                .organizations
                .kind
                .iter()
                .enumerate()
                .any(|(organization, kind)| {
                    *kind == 3
                        && particle.organizations.active.get(organization).copied() == Some(1)
                })
            {
                let insurgent_offset = person * 2 + 1;
                particle.people.expected_control[insurgent_offset] = clamp01(
                    particle.people.expected_control[insurgent_offset]
                        + config.combat.momentum_learning_rate * (0.5 - interpretation)
                        + 0.02 * attribution,
                );
            }
            if trace {
                eprintln!(
                    "MOMENTUM_PERSON person={} state government={:.17} insurgent={:.17}",
                    person,
                    particle.people.expected_control[government_offset],
                    particle.people.expected_control[person * 2 + 1],
                );
            }
        } else if both_insurgent {
            // Distinct insurgent organizations use dynamic keys in Python.
            // Preserve the literal `insurgent` slot when one participant is
            // the canonical initial actor; splinter-only keys are intentionally
            // outside the compact two-slot person schema.
            let first_literal =
                particle.formations.organization[first] as usize == crate::INSURGENT;
            let second_literal =
                particle.formations.organization[second] as usize == crate::INSURGENT;
            if first_literal {
                let offset = person * 2 + 1;
                particle.people.expected_control[offset] = clamp01(
                    particle.people.expected_control[offset]
                        + config.combat.momentum_learning_rate * (interpretation - 0.5),
                );
                if trace {
                    eprintln!(
                        "MOMENTUM_PERSON person={} both-first insurgent={:.17}",
                        person, particle.people.expected_control[offset]
                    );
                }
            } else if second_literal {
                let offset = person * 2 + 1;
                particle.people.expected_control[offset] = clamp01(
                    particle.people.expected_control[offset]
                        + config.combat.momentum_learning_rate * (0.5 - interpretation),
                );
                if trace {
                    eprintln!(
                        "MOMENTUM_PERSON person={} both-second insurgent={:.17}",
                        person, particle.people.expected_control[offset]
                    );
                }
            }
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn resolve_engagement(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
    first: usize,
    second: usize,
    detected_first: bool,
    detected_second: bool,
    initiator_organization: usize,
    contact_cause: &str,
) {
    if first >= particle.formations.personnel.len()
        || second >= particle.formations.personnel.len()
        || first == second
        || particle.formations.active[first] == 0
        || particle.formations.active[second] == 0
        || !organizations_hostile(
            particle,
            particle.formations.organization[first] as usize,
            particle.formations.organization[second] as usize,
        )
        || particle.formations.operational_status[first] != 1
        || particle.formations.operational_status[second] != 1
        || particle.formations.personnel[first] <= 0.0
        || particle.formations.personnel[second] <= 0.0
        || particle.formations.moving[first] != 0
        || particle.formations.moving[second] != 0
        || particle.formations.outside_pineland[first] != 0
        || particle.formations.outside_pineland[second] != 0
        || particle.formations.locality[first] != particle.formations.locality[second]
    {
        return;
    }
    let locality = particle.formations.locality[first] as usize;
    let microzone = formation_microzone(particle, topology, first);
    if formation_microzone(particle, topology, second) != microzone {
        return;
    }
    let initiative_first = 1.0
        + if detected_first && !detected_second {
            config.combat.surprise_initiative
        } else {
            0.0
        };
    let initiative_second = 1.0
        + if detected_second && !detected_first {
            config.combat.surprise_initiative
        } else {
            0.0
        };
    let capability_first = capability(particle, topology, config, first, microzone, initiative_first);
    let capability_second = capability(particle, topology, config, second, microzone, initiative_second);
    let advantage = capability_first.ln() - capability_second.ln();
    let observability = particle
        .zones
        .observability
        .get(microzone)
        .copied()
        .unwrap_or(0.5);
    let terrain = particle
        .zones
        .terrain_friction
        .get(microzone)
        .copied()
        .unwrap_or(1.0);
    let exposure = (observability / terrain.max(0.55)).clamp(0.2, 1.35);
    let frac_first = (config.combat.base_attrition_rate
        * exposure
        * python_exp(-0.45 * advantage + rng.normalvariate(0.0, config.combat.stochastic_sigma)))
    .min(config.combat.max_loss_fraction);
    let frac_second = (config.combat.base_attrition_rate
        * exposure
        * python_exp(0.45 * advantage + rng.normalvariate(0.0, config.combat.stochastic_sigma)))
    .min(config.combat.max_loss_fraction);
    if crate::trace_env!("PINELAND_COMBAT_TRACE") {
        eprintln!(
            "COMBAT_CORE first={} second={} locality={} microzone={} detected={} {} initiative={:.17} {:.17} cap={:.17} {:.17} advantage={:.17} obs={:.17} terrain={:.17} exposure={:.17} frac={:.17} {:.17}",
            first,
            second,
            locality,
            microzone,
            detected_first,
            detected_second,
            initiative_first,
            initiative_second,
            capability_first,
            capability_second,
            advantage,
            observability,
            terrain,
            exposure,
            frac_first,
            frac_second,
        );
    }
    let old_personnel_first = particle.formations.personnel[first];
    let old_personnel_second = particle.formations.personnel[second];
    let loss_first = old_personnel_first.min(old_personnel_first * frac_first);
    let loss_second = old_personnel_second.min(old_personnel_second * frac_second);
    let old_cohesion_first = particle.formations.cohesion[first];
    let old_cohesion_second = particle.formations.cohesion[second];
    let old_readiness_first = particle.formations.readiness[first];
    let old_readiness_second = particle.formations.readiness[second];
    particle.formations.personnel[first] -= loss_first;
    particle.formations.personnel[second] -= loss_second;
    particle.formations.cumulative_losses[first] += loss_first;
    particle.formations.cumulative_losses[second] += loss_second;
    let realized_first =
        loss_first / (particle.formations.personnel[first] + loss_first).max(1.0e-12);
    let realized_second =
        loss_second / (particle.formations.personnel[second] + loss_second).max(1.0e-12);
    particle.formations.cohesion[first] = clamp01(
        particle.formations.cohesion[first]
            - config.combat.cohesion_loss_multiplier
                * realized_first
                * (1.25 - particle.formations.quality[first]),
    );
    particle.formations.cohesion[second] = clamp01(
        particle.formations.cohesion[second]
            - config.combat.cohesion_loss_multiplier
                * realized_second
                * (1.25 - particle.formations.quality[second]),
    );
    particle.formations.readiness[first] = clamp01(
        particle.formations.readiness[first]
            - config.combat.readiness_cost_multiplier * realized_first,
    );
    particle.formations.readiness[second] = clamp01(
        particle.formations.readiness[second]
            - config.combat.readiness_cost_multiplier * realized_second,
    );

    // Surviving a real engagement creates formation-level learning even when
    // the tactical outcome is poor.  Losses do not themselves erase the
    // experience of survivors; later replacement flow dilutes the stock.
    if config.state_regeneration.enabled {
        for formation in [first, second] {
            let current = particle.formations.experience[formation].clamp(0.0, 1.0);
            let learning = config.combat.momentum_learning_rate
                * 0.025
                * exposure
                * (1.0 - current);
            particle.formations.experience[formation] = clamp01(current + learning);
        }
    }

    let mut disengaged = [false, false];
    for (slot, (formation, opponent, realized)) in [
        (first, second, realized_first),
        (second, first, realized_second),
    ]
    .into_iter()
    .enumerate()
    {
        let demand = particle.formations.personnel[formation].max(0.0)
            * particle.formations.availability[formation].clamp(0.0, 1.0)
            * config.combat.interval_hours
            * config.combat.supply_per_person_hour
            * (0.7 + 0.3 * exposure);
        let (_, shortfall) = consume_formation_supply(particle, formation, demand);
        if shortfall > 0.0 {
            particle.formations.readiness[formation] = clamp01(
                particle.formations.readiness[formation] - 0.08 * shortfall / demand.max(1.0),
            );
            particle.formations.cohesion[formation] = clamp01(
                particle.formations.cohesion[formation] - 0.04 * shortfall / demand.max(1.0),
            );
        }
        let own_reference = (particle.formations.personnel[formation]
            + if slot == 0 { loss_first } else { loss_second })
            * particle.formations.availability[formation].clamp(0.0, 1.0);
        let disadvantage = perceived_disadvantage(
            particle,
            formation,
            opponent,
            locality,
            microzone,
            own_reference.max(1.0),
        );
        let remain = logistic(
            1.1 * particle.formations.cohesion[formation]
                + particle.formations.effective_readiness(formation)
                - 2.1 * realized
                - disadvantage,
        );
        if rng.random() < config.combat.disengagement_base + (1.0 - remain) * 0.55 {
            disengaged[slot] = true;
            particle.formations.availability[formation] =
                clamp01(particle.formations.availability[formation] - 0.12);
        }
        if particle.formations.personnel[formation] <= 0.0
            || particle.formations.cohesion[formation] <= config.combat.ineffective_cohesion
            || particle.formations.effective_readiness(formation)
                <= config.combat.ineffective_readiness
        {
            particle.formations.operational_status[formation] = 0;
            particle.formations.availability[formation] =
                particle.formations.availability[formation].min(0.08);
        }
    }

    let intensity =
        (frac_first + frac_second) / (2.0 * config.combat.base_attrition_rate).max(0.001);
    particle.locality.violence[locality] =
        clamp01(particle.locality.violence[locality] * 0.85 + 0.25 * intensity.min(1.0));
    let civilian_harm = particle.locality.population[locality]
        * particle
            .zones
            .population_share
            .get(microzone)
            .copied()
            .unwrap_or(0.0)
        * config.combat.civilian_exposure_rate
        * intensity.min(1.0)
        * exposure
        * rng.expovariate(1.0).unwrap_or(0.0);
    let district = topology
        .locality_to_district
        .get(locality)
        .copied()
        .unwrap_or(0) as usize;
    let _ = apply_direct_civilian_harm(particle, config, locality, district, civilian_harm);
    update_relations(
        particle,
        particle.formations.organization[first] as usize,
        particle.formations.organization[second] as usize,
        (frac_first + frac_second).min(1.0),
        time,
        config,
    );
    let signal = logistic((frac_second - frac_first) * 18.0 + 0.35 * advantage);
    // Python materializes withdrawal orders before engagement observations;
    // their command-reliability draws therefore belong to this combat RNG
    // stream and their live state must block the next command cycle.
    for (slot, disengaged_slot) in disengaged.iter().copied().enumerate() {
        if disengaged_slot {
            let formation = if slot == 0 { first } else { second };
            let _ = crate::movement::issue_withdrawal_order(
                particle, topology, config, formation, time, rng,
            );
        }
    }
    for (formation, loss) in [(first, loss_first), (second, loss_second)] {
        let loss_fraction = loss / (particle.formations.personnel[formation] + loss).max(1.0e-12);
        let _ = crate::movement::issue_reinforcement_order(
            particle,
            topology,
            config,
            formation,
            loss_fraction,
            time,
            rng,
        );
    }
    if crate::trace_env!("PINELAND_COMBAT_TRACE") {
        eprintln!(
            "COMBAT_RESULT first={} second={} signal={:.17} civilian_harm={:.17} contacts={} disengaged={:?}",
            first, second, signal, civilian_harm, particle.counters.contacts, disengaged
        );
    }
    let engagement_id = format!("ENG{:010}", particle.counters.contacts + 1);
    let (first_momentum, first_harm) = crate::information::record_engagement_observation(
        particle,
        topology,
        config,
        rng,
        first,
        second,
        &engagement_id,
        locality,
        microzone,
        time,
        signal,
        civilian_harm,
    );
    let (second_momentum, second_harm) = crate::information::record_engagement_observation(
        particle,
        topology,
        config,
        rng,
        second,
        first,
        &engagement_id,
        locality,
        microzone,
        time,
        1.0 - signal,
        civilian_harm,
    );
    let first_value =
        if organization_is_insurgent(particle, particle.formations.organization[first] as usize) {
            1.0 - first_momentum
        } else {
            first_momentum
        };
    let second_value =
        if organization_is_insurgent(particle, particle.formations.organization[second] as usize) {
            1.0 - second_momentum
        } else {
            second_momentum
        };
    update_perceived_momentum(
        particle,
        config,
        locality,
        (first_value + second_value) / 2.0,
        (first_harm + second_harm) / 2.0,
        first,
        second,
        rng,
    );
    crate::organizations::record_foothold_action(
        particle,
        topology,
        initiator_organization,
        locality,
    );
    particle.counters.contacts = particle.counters.contacts.saturating_add(1);
    let _ = (
        initiator_organization,
        contact_cause,
        old_cohesion_first,
        old_cohesion_second,
        old_readiness_first,
        old_readiness_second,
        disengaged,
    );
}

#[allow(clippy::too_many_arguments)]
pub fn resolve_organized_engagement(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
    first: usize,
    second: usize,
    initiator_organization: usize,
    defender_aware: bool,
) {
    resolve_engagement(
        particle,
        topology,
        config,
        rng,
        time,
        first,
        second,
        true,
        defender_aware,
        initiator_organization,
        "organized_action_armed_confrontation",
    );
}

#[allow(clippy::too_many_arguments)]
pub fn resolve_contact(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
    first: usize,
    second: usize,
    _locality: usize,
    _microzone: usize,
) {
    let initiator = particle
        .formations
        .organization
        .get(first)
        .copied()
        .unwrap_or(u32::MAX) as usize;
    resolve_engagement(
        particle, topology, config, rng, time, first, second, true, true, initiator, "contact",
    );
}

pub fn effective_capability(particle: &ParticleState, formation: usize) -> f64 {
    particle.formations.effective_strength(formation)
}
