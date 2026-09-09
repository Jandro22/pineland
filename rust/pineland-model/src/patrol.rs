//! Patrol movement, information collection, and presence-memory refresh.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{python_exp, PyRandomCompat};
use pineland_core::state::{clamp01, BeliefKey, ParticleState, CONTROL_DIMENSIONS};
use pineland_core::topology::StaticTopology;

const GOVERNMENT_KIND: u8 = 0;
const MILITARY_KIND: u8 = 1;
const POLICE_KIND: u8 = 2;
const INSURGENT_KIND: u8 = 3;

/// Execute the Python reference patrol transition in the native state.
///
/// The event owns four operations in the same order as the reference:
/// close patrol presence, collect reports, draw the route, and consume
/// supply/update fatigue and readiness.
pub fn advance(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    patrol: usize,
    time: f64,
) {
    advance_patrol_presence_memory(particle, topology, config, patrol, time);

    if patrol >= particle.patrols.active.len()
        || particle.patrols.active[patrol] == 0
        || patrol >= particle.patrols.formation.len()
    {
        return;
    }
    let formation = particle.patrols.formation[patrol] as usize;
    if formation >= particle.formations.personnel.len()
        || particle.formations.active[formation] == 0
        || particle.formations.personnel[formation] <= 0.0
        || particle.formations.moving[formation] != 0
        || particle.formations.outside_pineland[formation] != 0
        || particle.formations.operational_status[formation] == 0
    {
        return;
    }

    let locality = particle.formations.locality[formation] as usize;
    let current = particle.patrols.route_target[patrol] as usize;
    if current >= topology.microzone_count()
        || locality >= topology.locality_count()
        || topology.microzone_to_locality[current] as usize != locality
    {
        return;
    }

    // Python observes before drawing route noise. Negative reports consume
    // their quality/control RNG calls too, so route-only behavior is not
    // continuation-equivalent.
    observe_patrol(
        particle, topology, config, rng, formation, locality, current, time,
    );

    let mut candidates = topology
        .physical_edges
        .neighbors(current)
        .filter(|(candidate, _)| {
            topology.microzone_to_locality[*candidate as usize] as usize == locality
        })
        .collect::<Vec<_>>();
    candidates.sort_by_key(|(candidate, _)| *candidate);

    let mut moved_to = current;
    let mut travel_hours = config.intervals.patrol * 24.0;
    if !candidates.is_empty() {
        let mut weights = Vec::with_capacity(candidates.len());
        for (candidate, travel_time_hours) in &candidates {
            let zone = *candidate as usize;
            let belief_index = zone_belief_index(
                particle,
                particle.formations.organization[formation] as usize,
                zone,
            );
            let (estimate, confidence) = belief_index
                .map(|index| {
                    (
                        particle.zone_beliefs.estimate[index],
                        particle.zone_beliefs.confidence[index],
                    )
                })
                .unwrap_or((0.5, 0.35));
            let perceived_need = if config.physical.adaptive_patrol_routing {
                (1.0 - estimate) * (0.55 + 0.45 * confidence) + 0.18 * (1.0 - confidence)
            } else {
                0.5
            };
            let route_noise = rng.uniform(0.0, config.physical.patrol_route_randomness);
            let score = 2.5 * perceived_need
                - *travel_time_hours / config.physical.response_decay_hours
                + route_noise;
            weights.push(python_exp(score.clamp(-8.0, 8.0)));
        }
        let selected = rng
            .choices_indices(candidates.len(), Some(&weights), 1)
            .expect("non-empty patrol route has valid weights")[0];
        moved_to = candidates[selected].0 as usize;
        travel_hours = candidates[selected].1 / particle.formations.mobility[formation].max(0.2);
    }

    if moved_to != current {
        particle.patrols.route_position[patrol] = moved_to as u32;
        particle.patrols.route_target[patrol] = moved_to as u32;
        particle.patrols.last_departure[patrol] = time;
        particle.patrols.next_available[patrol] = time + travel_hours / 24.0;
        particle.patrols.presence_accounted_at[patrol] = particle.patrols.next_available[patrol];
    }

    // Demand uses available personnel before the patrol consumes supply.
    let demand = particle.formations.available_personnel(formation)
        * config.logistics.patrol_consumption_per_person_hour
        * travel_hours;
    let consumed = demand
        .max(0.0)
        .min(particle.formations.supply_stock[formation]);
    let shortfall = (demand.max(0.0) - consumed).max(0.0);
    particle.formations.supply_stock[formation] -= consumed;
    particle.formations.sustainment[formation] = supply_fraction(particle, formation);
    particle.logistics.cumulative_consumed += consumed;
    if shortfall > 0.0 {
        particle.formations.readiness[formation] =
            clamp01(particle.formations.readiness[formation] - 0.01 * shortfall / demand.max(1.0));
    }
    particle.formations.fatigue[formation] =
        clamp01(particle.formations.fatigue[formation] + 0.0008 * travel_hours);
    particle.formations.readiness[formation] =
        clamp01(particle.formations.readiness[formation] - 0.0003 * travel_hours);
}

/// Integrate one patrol's dwell interval, matching the reference physical
/// memory accounting. A negative sentinel represents Python None.
fn advance_patrol_presence_memory(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    patrol: usize,
    time: f64,
) {
    if patrol >= particle.patrols.formation.len()
        || particle.patrols.active.get(patrol).copied().unwrap_or(0) == 0
    {
        return;
    }
    let formation = particle.patrols.formation[patrol] as usize;
    if formation >= particle.formations.personnel.len() {
        return;
    }
    let zone = particle.patrols.route_target[patrol] as usize;
    let locality = particle.formations.locality[formation] as usize;
    if zone >= topology.microzone_count()
        || locality >= topology.locality_count()
        || topology.microzone_to_locality[zone] as usize != locality
        || particle.formations.personnel[formation] <= 0.0
        || particle.formations.moving[formation] != 0
        || particle.formations.outside_pineland[formation] != 0
        || particle.formations.operational_status[formation] == 0
    {
        return;
    }
    let available_at = particle.patrols.next_available[patrol];
    if available_at > time {
        return;
    }
    let accounted = particle.patrols.presence_accounted_at[patrol];
    let start = if accounted < -1.0e250 {
        available_at
    } else {
        available_at.max(accounted)
    };
    let duration = (time - start).max(0.0);
    if duration <= 0.0 {
        particle.patrols.presence_accounted_at[patrol] = start.max(time);
        return;
    }

    let organization = particle.formations.organization[formation] as usize;
    let actor_is_insurgent = organization < particle.organizations.kind.len()
        && particle.organizations.kind[organization] == INSURGENT_KIND;
    let population = topology.locality_population[locality];
    let deployed_strength = particle.formations.effective_strength(formation)
        * clamp01(particle.patrols.response_fraction[patrol]);
    let normalized_strength = deployed_strength / 250.0_f64.max(population * 0.002);
    let target = config.physical.patrol_memory_gain * normalized_strength;
    if std::env::var_os("PINELAND_PHYS_TRACE").is_some() {
        eprintln!(
            "PRES patrol={} time={:.17} zone={} start={:.17} duration={:.17} personnel={:.17} availability={:.17} readiness={:.17} quality={:.17} cohesion={:.17} info={:.17} command={:.17} strength={:.17} target={:.17} actor_ins={}",
            patrol, time, zone, start, duration,
            particle.formations.personnel[formation],
            particle.formations.availability[formation],
            particle.formations.readiness[formation],
            particle.formations.quality[formation],
            particle.formations.cohesion[formation],
            particle.formations.information[formation],
            particle.formations.command[formation],
            deployed_strength, target, actor_is_insurgent
        );
    }
    let memory = config.physical.presence_memory_days.max(f64::MIN_POSITIVE);
    let (memory_values, updated_values) = if actor_is_insurgent {
        (
            &mut particle.zones.insurgent_presence,
            &mut particle.zones.insurgent_presence_updated_at,
        )
    } else {
        (
            &mut particle.zones.government_presence,
            &mut particle.zones.government_presence_updated_at,
        )
    };
    let age = (time - updated_values[zone]).max(0.0);
    memory_values[zone] *= python_exp(-age / memory);
    updated_values[zone] = time;
    memory_values[zone] += target * (1.0 - python_exp(-duration / memory));
    particle.patrols.presence_accounted_at[patrol] = time;
}

/// Close every deployed patrol's presence-memory interval at a physical
/// refresh boundary.  Python performs this pass once before recomputing the
/// response and control fields; keeping the traversal in patrol-id order
/// makes the state transition deterministic and auditable.
pub fn advance_all_presence_memory(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    time: f64,
) {
    for patrol in 0..particle.patrols.formation.len() {
        advance_patrol_presence_memory(particle, topology, config, patrol, time);
    }
}

fn observe_patrol(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    formation: usize,
    locality: usize,
    microzone: usize,
    time: f64,
) {
    if rng.random() >= config.information.patrol_report_rate {
        return;
    }
    let observer_organization = particle.formations.organization[formation] as usize;
    for target_actor in target_actor_ids(particle, observer_organization) {
        let targets = target_formations(particle, topology, target_actor, locality);
        if targets.is_empty() {
            observe_target(
                particle,
                topology,
                config,
                rng,
                formation,
                target_actor,
                None,
                locality,
                microzone,
                time,
            );
        } else {
            for target in targets {
                observe_target(
                    particle,
                    topology,
                    config,
                    rng,
                    formation,
                    target_actor,
                    Some(target),
                    locality,
                    microzone,
                    time,
                );
            }
        }
    }
    observe_control(
        particle, topology, config, rng, formation, locality, microzone, time,
    );
}

/// None means the aggregate insurgent side. Some(index) is a concrete actor.
fn target_actor_ids(particle: &ParticleState, observer: usize) -> Vec<Option<usize>> {
    if observer >= particle.organizations.kind.len()
        || particle
            .organizations
            .active
            .get(observer)
            .copied()
            .unwrap_or(0)
            == 0
    {
        return Vec::new();
    }
    let observer_is_insurgent = particle.organizations.kind[observer] == INSURGENT_KIND;
    let insurgents = (0..particle.organizations.kind.len())
        .filter(|index| {
            *index != observer
                && particle
                    .organizations
                    .active
                    .get(*index)
                    .copied()
                    .unwrap_or(0)
                    != 0
                && particle.organizations.kind[*index] == INSURGENT_KIND
                && hostile_relation(particle, observer, *index)
        })
        .collect::<Vec<_>>();
    if observer_is_insurgent {
        let state_security = (0..particle.organizations.kind.len()).any(|index| {
            index != observer
                && particle
                    .organizations
                    .active
                    .get(index)
                    .copied()
                    .unwrap_or(0)
                    != 0
                && matches!(
                    particle.organizations.kind[index],
                    GOVERNMENT_KIND | MILITARY_KIND | POLICE_KIND
                )
                && hostile_relation(particle, observer, index)
        });
        let mut targets = if state_security {
            vec![None]
        } else {
            Vec::new()
        };
        targets.extend(insurgents.into_iter().map(Some));
        targets
    } else if insurgents.len() == 1 && insurgents[0] == crate::INSURGENT {
        vec![None]
    } else {
        insurgents.into_iter().map(Some).collect()
    }
}

fn hostile_relation(particle: &ParticleState, first: usize, second: usize) -> bool {
    particle
        .relations
        .organization_a
        .iter()
        .zip(&particle.relations.organization_b)
        .zip(&particle.relations.status)
        .any(|((left, right), status)| {
            ((*left as usize == first && *right as usize == second)
                || (*left as usize == second && *right as usize == first))
                && *status == 4
        })
}

fn target_formations(
    particle: &ParticleState,
    topology: &StaticTopology,
    target_actor: Option<usize>,
    locality: usize,
) -> Vec<usize> {
    (0..particle.formations.personnel.len())
        .filter(|formation| {
            let organization = particle.formations.organization[*formation] as usize;
            let matches = match target_actor {
                None => {
                    organization < particle.organizations.kind.len()
                        && particle.organizations.kind[organization] == INSURGENT_KIND
                }
                Some(target) => organization == target,
            };
            matches
                && particle.formations.active[*formation] != 0
                && particle.formations.personnel[*formation] > 0.0
                && particle.formations.locality[*formation] as usize == locality
                && particle.formations.moving[*formation] == 0
                && particle.formations.outside_pineland[*formation] == 0
                && particle.formations.operational_status[*formation] == 1
                && (particle.formations.microzone[*formation] as usize) < topology.microzone_count()
        })
        .collect()
}

fn observe_target(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    observer_formation: usize,
    target_actor: Option<usize>,
    target_formation: Option<usize>,
    locality: usize,
    microzone: usize,
    time: f64,
) {
    let mut personnel = 0.0;
    let mut chosen = None;
    for candidate in 0..particle.formations.personnel.len() {
        let organization = particle.formations.organization[candidate] as usize;
        let matches = match target_actor {
            None => {
                organization < particle.organizations.kind.len()
                    && particle.organizations.kind[organization] == INSURGENT_KIND
            }
            Some(target) => organization == target,
        };
        if !matches
            || particle.formations.active[candidate] == 0
            || particle.formations.personnel[candidate] <= 0.0
            || particle.formations.moving[candidate] != 0
            || particle.formations.outside_pineland[candidate] != 0
            || particle.formations.operational_status[candidate] != 1
            || particle.formations.locality[candidate] as usize != locality
            || target_formation.is_some_and(|target| target != candidate)
        {
            continue;
        }
        let current_zone = particle.formations.microzone[candidate] as usize;
        let patrol_present = (0..particle.patrols.formation.len()).any(|patrol| {
            particle.patrols.formation[patrol] as usize == candidate
                && particle.patrols.active[patrol] != 0
                && particle.patrols.route_target[patrol] as usize == microzone
        });
        if current_zone != microzone && !patrol_present {
            continue;
        }
        personnel += particle.formations.personnel[candidate];
        if chosen.is_none_or(|current| {
            particle.formations.personnel[candidate] > particle.formations.personnel[current]
        }) {
            chosen = Some(candidate);
        }
    }
    let present = chosen.is_some();
    let target_formation_for_probability = chosen.unwrap_or(observer_formation);
    let probability = if present {
        detection_probability(
            particle,
            topology,
            config,
            observer_formation,
            target_formation_for_probability,
            locality,
            microzone,
        )
    } else {
        false_positive_probability(
            particle,
            topology,
            config,
            observer_formation,
            locality,
            microzone,
        )
    };
    let detected = rng.random() < probability;
    let observer_organization = particle.formations.organization[observer_formation] as usize;
    let quality = source_quality(
        particle,
        topology,
        config,
        rng,
        observer_organization,
        locality,
    );
    let mut personnel_estimate = 0.0;
    let mut attribution_mistake = false;
    if detected {
        // The Python expression evaluates its positive personnel multiplier
        // before overriding false positives with a coarse uniform estimate.
        // Keep that draw even when no formation is actually present.
        personnel_estimate = personnel * (0.65 + 0.7 * rng.random());
        if present {
            attribution_mistake = rng.random() < config.information.attribution_error_rate;
        } else {
            personnel_estimate = rng.uniform(20.0, 250.0).max(1.0);
        }
    }
    let target_actor_id = target_actor.unwrap_or(crate::INSURGENT);
    let reported_target = if attribution_mistake {
        if particle.organizations.kind.get(target_actor_id).copied() == Some(INSURGENT_KIND) {
            crate::GOVERNMENT
        } else {
            crate::INSURGENT
        }
    } else {
        target_actor_id
    };
    let reported_formation = if attribution_mistake {
        None
    } else if target_formation.is_some() {
        if present && detected {
            chosen
        } else {
            target_formation
        }
    } else {
        None
    };
    crate::information::record_patrol_target_observation(
        particle,
        topology,
        config,
        observer_formation,
        reported_target,
        reported_formation,
        locality,
        microzone,
        time,
        quality,
        if detected {
            config.information.positive_report_confidence
        } else {
            config.information.negative_report_confidence
        },
        if detected { 1.0 } else { 0.0 },
        personnel_estimate,
        probability,
        detected,
    );
    particle.counters.observations = particle.counters.observations.saturating_add(1);
}

fn observe_control(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    observer_formation: usize,
    locality: usize,
    microzone: usize,
    time: f64,
) {
    let observer_organization = particle.formations.organization[observer_formation] as usize;
    let quality = source_quality(
        particle,
        topology,
        config,
        rng,
        observer_organization,
        locality,
    );
    let accountability = particle
        .organizations
        .accountability
        .get(observer_organization)
        .copied()
        .unwrap_or(0.5);
    let trust = (config
        .information
        .source_trust
        .get("patrol")
        .copied()
        .unwrap_or(0.5)
        * (0.7 + 0.3 * clamp01(accountability)))
    .clamp(0.02, 1.0);
    let language = (0.45
        + 0.45
            * local_organizational_embeddedness(
                particle,
                topology,
                config,
                observer_organization,
                locality,
            ))
    .clamp(0.1, 1.0);
    let noise = config.observation_noise * (1.35 - 0.55 * quality * language);
    let offset = locality * CONTROL_DIMENSIONS;
    let insurgent_observer = particle
        .organizations
        .kind
        .get(observer_organization)
        .copied()
        == Some(INSURGENT_KIND);
    let values = if insurgent_observer {
        &particle.locality.insurgent_control
    } else {
        &particle.locality.government_control
    };
    let mut observed = [0.0; CONTROL_DIMENSIONS];
    for dimension in 0..CONTROL_DIMENSIONS {
        let value = clamp01(values[offset + dimension] + rng.uniform(-noise, noise));
        observed[dimension] = value;
    }
    let _violence = clamp01(particle.locality.violence[locality] + rng.uniform(-noise, noise));
    let observation_confidence = (0.45 + 0.45 * trust).clamp(0.0, 1.0);
    let weight = observation_confidence
        * quality
        * trust
        * language.powf(config.information.language_fusion_weight)
        * (1.0
            + config.information.corroboration_bonus
                * crate::information::patrol_control_corroboration(
                    particle,
                    topology,
                    config,
                    if insurgent_observer {
                        crate::INSURGENT
                    } else {
                        crate::GOVERNMENT
                    },
                    locality,
                    &crate::information::patrol_source_id(particle, observer_formation),
                    time,
                )
                .min(3.0));
    if std::env::var_os("PINELAND_INFO_TRACE").is_some() && time >= 0.25 {
        eprintln!(
            "PATROL_CONTROL_TRACE formation={} time={:.17} quality={:.17} trust={:.17} language={:.17} confidence={:.17} weight={:.17} observed={:?}",
            observer_formation,
            time,
            quality,
            trust,
            language,
            observation_confidence,
            weight,
            observed,
        );
    }
    // The field node fuses the complete control vector into its own dynamic
    // control-belief row.  Python names this node by formation ID; the native
    // schema reserves codes after the seven fixed organizations for formation
    // observers and marks these rows with kind=3.
    let dynamic_observer = particle.organizations.kind.len() as u32 + observer_formation as u32;
    let target_actor = if insurgent_observer {
        crate::INSURGENT
    } else {
        crate::GOVERNMENT
    };
    let dynamic_key = BeliefKey {
        observer: dynamic_observer,
        target: target_actor as u32,
        locality: locality as u32,
        kind: 3,
    };
    let is_new = !particle.beliefs.keys.iter().any(|key| key == &dynamic_key);
    let dynamic_index = particle.beliefs.ensure_key(dynamic_key);
    if is_new {
        let offset = dynamic_index * CONTROL_DIMENSIONS;
        particle.beliefs.control[offset..offset + CONTROL_DIMENSIONS].fill(0.5);
        particle.beliefs.confidence[dynamic_index] = config.information.prior_confidence;
    }
    particle.beliefs.fuse_control(
        dynamic_index,
        time,
        weight,
        &observed,
        config.information.contradiction_memory_days,
        config.information.contradiction_penalty,
    );
    if let Some(index) = zone_belief_index(particle, observer_organization, microzone) {
        let prior_confidence = particle.zone_beliefs.confidence[index];
        let prior = prior_confidence.max(0.02);
        let denominator = prior + weight;
        let old = particle.zone_beliefs.estimate[index];
        let contradiction = particle.zone_beliefs.contradiction[index]
            * python_exp(
                -((time - particle.zone_beliefs.updated_at[index]).max(0.0))
                    / config.information.contradiction_memory_days,
            )
            + weight * (observed[1] - old).abs();
        particle.zone_beliefs.estimate[index] =
            clamp01((prior * old + weight * observed[1]) / denominator);
        particle.zone_beliefs.confidence[index] = clamp01(
            (prior + weight) / (1.0 + prior + weight)
                * python_exp(-config.information.contradiction_penalty * contradiction),
        );
        particle.zone_beliefs.contradiction[index] = contradiction;
        particle.zone_beliefs.updated_at[index] = time;
        particle.zone_beliefs.evidence_count[index] =
            particle.zone_beliefs.evidence_count[index].saturating_add(1);
        if weight >= 0.12 {
            particle.zone_beliefs.last_reliable_observation_at[index] = time;
        }
    }
    crate::information::record_patrol_control_history(
        particle,
        topology,
        observer_formation,
        locality,
        time,
    );
    crate::information::record_patrol_control_observation(
        particle,
        topology,
        config,
        observer_formation,
        locality,
        microzone,
        time,
        quality,
        observation_confidence,
        observed,
        _violence,
    );
    particle.counters.observations = particle.counters.observations.saturating_add(1);
}

fn source_quality(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    _observer_organization: usize,
    locality: usize,
) -> f64 {
    let coverage = config
        .information
        .source_coverage
        .get("patrol")
        .copied()
        .unwrap_or(0.4);
    let quality = coverage
        * (0.55 + 0.45 * particle.locality.observability[locality])
        * (0.85 + 0.3 * rng.random());
    let _ = topology;
    clamp01(quality)
}

fn false_positive_probability(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    observer_formation: usize,
    locality: usize,
    microzone: usize,
) -> f64 {
    let observability = topology.zone_observability[microzone];
    let observer_organization = particle.formations.organization[observer_formation] as usize;
    let embeddedness = local_organizational_embeddedness(
        particle,
        topology,
        config,
        observer_organization,
        locality,
    );
    let language =
        (0.35 + 0.55 * particle.formations.information[observer_formation] + 0.1 * embeddedness)
            .clamp(0.1, 1.0);
    let base = config
        .information
        .false_positive_rate
        .clamp(1.0e-6, 1.0 - 1.0e-6);
    let score = (base / (1.0 - base)).ln() + 0.3 * (1.0 - observability) + 0.25 * (1.0 - language);
    clamp01(1.0 / (1.0 + python_exp(-score)))
}

fn detection_probability(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    observer_formation: usize,
    target_formation: usize,
    locality: usize,
    microzone: usize,
) -> f64 {
    let observer_organization = particle.formations.organization[observer_formation] as usize;
    let target_organization = particle.formations.organization[target_formation] as usize;
    let observer_readiness = particle
        .formations
        .fatigue_adjusted_readiness(observer_formation);
    let deployment_fraction = particle.formations.deployable_personnel(observer_formation)
        / particle.formations.personnel[observer_formation].max(1.0);
    let pressure = clamp01(
        deployment_fraction
            * particle.formations.quality[observer_formation]
            * particle.formations.cohesion[observer_formation]
            * (0.5 + particle.formations.information[observer_formation])
            / 2.0,
    );
    let embeddedness = local_organizational_embeddedness(
        particle,
        topology,
        config,
        observer_organization,
        locality,
    );
    let language =
        (0.35 + 0.55 * particle.formations.information[observer_formation] + 0.1 * embeddedness)
            .clamp(0.1, 1.0);
    let observability = topology.zone_observability[microzone];
    let exposure = clamp01(
        0.35 + 0.45 * observability - 0.25 * particle.formations.embeddedness[target_formation],
    );
    let terrain_penalty = clamp01(particle.locality.terrain_friction[locality] / 2.5);
    let base = config
        .information
        .true_positive_rate
        .clamp(1.0e-6, 1.0 - 1.0e-6);
    let mut score = (base / (1.0 - base)).ln()
        + config.information.detection_pressure_bonus * pressure
        + config.information.detection_exposure_bonus * exposure
        + config.information.detection_language_bonus * language
        + config.information.detection_observability_bonus * observability
        + config.information.detection_readiness_bonus * observer_readiness
        - config.information.detection_terrain_penalty * terrain_penalty;
    if target_organization < particle.organizations.kind.len()
        && particle.organizations.kind[target_organization] == INSURGENT_KIND
    {
        let dispersion = particle.organizations.phenotype[target_organization * 8 + 3];
        score -= 0.9 * config.information.insurgent_concealment * (0.5 + 0.5 * clamp01(dispersion));
    }
    clamp01(1.0 / (1.0 + python_exp(-score)))
}

fn local_organizational_embeddedness(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
) -> f64 {
    if organization >= particle.organizations.kind.len() {
        return 0.0;
    }
    let threshold = config
        .organization_ecology
        .minimum_formation_personnel
        .max(1.0e-12);
    let mut represented_local = 0.0;
    let mut home_local = 0.0;
    let mut home_district = 0.0;
    let target_district = topology.locality_to_district[locality] as usize;
    for person in 0..particle.people.locality.len() {
        if particle.people.organization[person] as usize != organization
            || particle.people.residence[person] as usize != locality
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
        let home = particle.people.home[person] as usize;
        if home < topology.locality_to_district.len()
            && topology.locality_to_district[home] as usize == target_district
        {
            home_district += represented;
        }
    }
    let (member_depth, origin_depth) = if represented_local <= 1.0e-12 {
        (0.0, 0.0)
    } else {
        (
            clamp01(
                represented_local
                    / config
                        .organization_ecology
                        .minimum_proto_represented_population
                        .max(1.0e-12),
            ),
            (clamp01(home_local / represented_local) + clamp01(home_district / represented_local))
                / 2.0,
        )
    };
    let member_channel = member_depth * (0.5 + 0.5 * origin_depth);

    let supply_per_fighter = (config.logistics.formation_supply_days
        * config.logistics.initial_supply_fraction)
        .max(1.0e-12);
    let mut pool = 0.0;
    let mut reserve = 0.0;
    for index in 0..particle.manpower.pool.len() {
        if particle.manpower.organization[index] as usize == organization
            && particle.manpower.locality[index] as usize == locality
        {
            pool += particle.manpower.pool[index].max(0.0);
            reserve += particle.manpower.supply_reserve[index].max(0.0);
        }
    }
    let pool_channel = clamp01(pool.min(reserve / supply_per_fighter) / threshold)
        * clamp01(particle.organizations.local_knowledge[organization]);

    let mut fielded = 0.0;
    let mut weighted_embeddedness = 0.0;
    for formation in 0..particle.formations.personnel.len() {
        if particle.formations.organization[formation] as usize != organization
            || particle.formations.locality[formation] as usize != locality
            || particle.formations.personnel[formation] <= 0.0
            || particle.formations.moving[formation] != 0
            || particle.formations.outside_pineland[formation] != 0
            || particle.formations.operational_status[formation] != 1
        {
            continue;
        }
        fielded += particle.formations.personnel[formation];
        weighted_embeddedness += particle.formations.personnel[formation]
            * clamp01(particle.formations.embeddedness[formation]);
    }
    let formation_channel = if fielded > 0.0 {
        clamp01(fielded / threshold) * clamp01(weighted_embeddedness / fielded)
    } else {
        0.0
    };

    // Concrete FDF/police locality controls are not materialized in the
    // current native state. Do not infer them from federal government truth.
    let institutional_channel = 0.0;
    let mut complement = 1.0;
    for value in [
        member_channel,
        pool_channel,
        formation_channel,
        institutional_channel,
    ] {
        complement *= 1.0 - clamp01(value);
    }
    clamp01(1.0 - complement)
}

fn zone_belief_index(particle: &ParticleState, observer: usize, zone: usize) -> Option<usize> {
    particle
        .zone_beliefs
        .keys
        .iter()
        .position(|key| key.observer as usize == observer && key.zone as usize == zone)
}

fn supply_fraction(particle: &ParticleState, formation: usize) -> f64 {
    if particle.formations.supply_capacity[formation] > 0.0 {
        clamp01(
            particle.formations.supply_stock[formation]
                / particle.formations.supply_capacity[formation],
        )
    } else {
        clamp01(particle.formations.sustainment[formation])
    }
}

pub fn route_cost(topology: &StaticTopology, source: usize, target: usize, terrain: f64) -> f64 {
    topology.distance(source.into(), target.into()) * terrain.max(0.01)
}
