//! Native observation, detection, and actor-local information fusion.
//!
//! The Python information layer is the oracle for this module.  In
//! particular, a report is not a shortcut from truth to a global belief: the
//! source availability draw, observation draw, quality draw, and control-noise
//! draws all remain in the reference order.  Keeping the source traversal in
//! one place is important because the process stream is part of the exact
//! continuation contract.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{python_exp, PyRandomCompat};
use pineland_core::state::{
    clamp01, BeliefKey, InformationHistoryEntry, InformationObservation, InformationRelay,
    ParticleState, CONTROL_DIMENSIONS, INFORMATION_NONE,
};
use pineland_core::topology::StaticTopology;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum SourceType {
    FixedPost,
    Civilian,
    SocialNetwork,
    Administrative,
    OrganizationMember,
    PoliticalElite,
    Interpreter,
    Patrol,
}

type ControlHistoryEntry = InformationHistoryEntry;

/// Persist the control-report identity produced by a patrol event.
///
/// Patrols execute before the first same-time background information event.
/// Python therefore exposes their reports to the three-day corroboration
/// operator even though the patrol module owns the local fusion transition.
/// Keeping this small boundary public lets patrol retain its historical RNG
/// and local-belief implementation while sharing the exact evidence index.
pub fn record_patrol_control_history(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    formation: usize,
    locality: usize,
    time: f64,
) {
    let observer = particle.formations.organization[formation] as usize;
    let target = control_target(observer);
    let source_id = format!("PATROL-{}", formation_name(particle, formation));
    particle.information_history.push(InformationHistoryEntry {
        target: target as u32,
        locality: locality as u32,
        observation_type: 1,
        time,
        source_identity: source_identity_code(particle, topology, &source_id),
    });
}

impl SourceType {
    fn name(self) -> &'static str {
        match self {
            Self::FixedPost => "fixed_post",
            Self::Civilian => "civilian",
            Self::SocialNetwork => "social_network",
            Self::Administrative => "administrative",
            Self::OrganizationMember => "organization_member",
            Self::PoliticalElite => "political_elite",
            Self::Interpreter => "interpreter",
            Self::Patrol => "patrol",
        }
    }

    fn is_community_channel(self) -> bool {
        matches!(
            self,
            Self::Civilian | Self::SocialNetwork | Self::PoliticalElite | Self::Interpreter
        )
    }
}

/// Generate the complete background information event in the same order as
/// `generate_background_observations` in the Python reference.
pub fn collect_and_fuse(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    _elapsed_days: f64,
    time: f64,
) {
    // Corroboration is part of the future-decision state.  Start each event
    // from the persisted three-day tail, including patrol reports generated
    // at an earlier scheduler event, then append this event in source order.
    particle
        .information_history
        .retain(|entry| entry.time >= time - 3.0);
    let mut history = particle.information_history.clone();
    let mut post_indices = (0..particle.security_posts.organization.len()).collect::<Vec<_>>();
    post_indices.sort_by(|left, right| {
        post_name(particle, topology, *left).cmp(&post_name(particle, topology, *right))
    });

    for post in post_indices {
        if particle
            .security_posts
            .available_fraction
            .get(post)
            .copied()
            .unwrap_or(0.0)
            <= 0.0
        {
            continue;
        }
        let formation = particle.security_posts.formation[post];
        if formation != u32::MAX {
            let formation = formation as usize;
            if formation >= particle.formations.personnel.len()
                || particle.formations.moving[formation] != 0
                || available_personnel(particle, formation) <= 0.0
            {
                continue;
            }
        }
        let locality = particle.security_posts.locality[post] as usize;
        if locality >= topology.locality_count() {
            continue;
        }
        let observer = particle.security_posts.organization[post] as usize;
        let source_id = post_name(particle, topology, post);
        let observer_node = if formation == u32::MAX {
            source_id.clone()
        } else {
            formation_name(particle, formation as usize)
        };
        observe_from_source(
            particle,
            topology,
            config,
            rng,
            observer,
            &observer_node,
            &source_id,
            SourceType::FixedPost,
            locality,
            time,
            &mut history,
        );
    }

    for locality in 0..topology.locality_count() {
        let communities = communities_for_locality(particle, locality);
        if communities.is_empty() {
            if particle
                .organizations
                .active
                .get(crate::GOVERNMENT)
                .copied()
                == Some(1)
            {
                let locality_id = locality_id(topology, locality);
                let admin_id = format!("ADMIN:{locality_id}");
                observe_from_source(
                    particle,
                    topology,
                    config,
                    rng,
                    crate::GOVERNMENT,
                    &admin_id,
                    &admin_id,
                    SourceType::Administrative,
                    locality,
                    time,
                    &mut history,
                );
                // The Python generator gives every populated coarse locality
                // an elite-capacity channel at initialization.  The native
                // state does not yet have a separate governance dictionary,
                // so population is the exact t=0 access predicate.
                if particle
                    .locality
                    .population
                    .get(locality)
                    .copied()
                    .unwrap_or(0.0)
                    > 0.0
                {
                    let elite_id = format!("ELITE-CAP:{locality_id}");
                    observe_from_source(
                        particle,
                        topology,
                        config,
                        rng,
                        crate::GOVERNMENT,
                        &elite_id,
                        &elite_id,
                        SourceType::PoliticalElite,
                        locality,
                        time,
                        &mut history,
                    );
                }
                if is_multilingual(topology, locality)
                    && particle
                        .locality
                        .population
                        .get(locality)
                        .copied()
                        .unwrap_or(0.0)
                        > 0.0
                {
                    let interpreter_id = format!("INTERPRETER-CAP:{locality_id}");
                    observe_from_source(
                        particle,
                        topology,
                        config,
                        rng,
                        crate::GOVERNMENT,
                        &interpreter_id,
                        &interpreter_id,
                        SourceType::Interpreter,
                        locality,
                        time,
                        &mut history,
                    );
                }
            }
            continue;
        }

        let community = select_community(particle, &communities, rng);
        let community_id = community_name(community);
        if particle
            .organizations
            .active
            .get(crate::GOVERNMENT)
            .copied()
            == Some(1)
        {
            for source_type in [SourceType::Civilian, SourceType::SocialNetwork] {
                observe_from_source(
                    particle,
                    topology,
                    config,
                    rng,
                    crate::GOVERNMENT,
                    &community_id,
                    &community_id,
                    source_type,
                    locality,
                    time,
                    &mut history,
                );
            }
            let admin_id = format!("ADMIN:{}", locality_id(topology, locality));
            observe_from_source(
                particle,
                topology,
                config,
                rng,
                crate::GOVERNMENT,
                &admin_id,
                &admin_id,
                SourceType::Administrative,
                locality,
                time,
                &mut history,
            );
            let elite_id = format!("ELITE:{community_id}");
            observe_from_source(
                particle,
                topology,
                config,
                rng,
                crate::GOVERNMENT,
                &elite_id,
                &elite_id,
                SourceType::PoliticalElite,
                locality,
                time,
                &mut history,
            );
        }

        if particle.organizations.active.get(crate::INSURGENT).copied() == Some(1) {
            observe_from_source(
                particle,
                topology,
                config,
                rng,
                crate::INSURGENT,
                &community_id,
                &community_id,
                SourceType::Civilian,
                locality,
                time,
                &mut history,
            );
        }
        if is_multilingual(topology, locality)
            && particle
                .organizations
                .active
                .get(crate::GOVERNMENT)
                .copied()
                == Some(1)
        {
            observe_from_source(
                particle,
                topology,
                config,
                rng,
                crate::GOVERNMENT,
                &community_id,
                &community_id,
                SourceType::Interpreter,
                locality,
                time,
                &mut history,
            );
        }
    }

    let mut formation_indices = (0..particle.formations.personnel.len()).collect::<Vec<_>>();
    formation_indices.sort_by(|left, right| {
        formation_name(particle, *left).cmp(&formation_name(particle, *right))
    });
    for formation in formation_indices {
        if particle.formations.moving[formation] != 0
            || available_personnel(particle, formation) <= 0.0
        {
            continue;
        }
        let locality = particle.formations.locality[formation] as usize;
        if locality >= topology.locality_count() {
            continue;
        }
        let source_id = formation_name(particle, formation);
        let observer = particle.formations.organization[formation] as usize;
        observe_from_source(
            particle,
            topology,
            config,
            rng,
            observer,
            &source_id,
            &source_id,
            SourceType::OrganizationMember,
            locality,
            time,
            &mut history,
        );
    }
    particle.information_history = history;
}

fn corroboration_weight(
    history: &[ControlHistoryEntry],
    target: usize,
    locality: usize,
    source_identity: u32,
    time: f64,
    config: &SimulationConfig,
    source_type: SourceType,
) -> f64 {
    let correlation = config
        .information
        .source_correlation
        .get(source_type.name())
        .copied()
        .unwrap_or(0.5);
    let mut sources = Vec::<u32>::new();
    let mut weight = 0.0;
    for entry in history.iter().rev() {
        if entry.time < time - 3.0 {
            break;
        }
        if entry.target == target as u32
            && entry.locality == locality as u32
            && entry.observation_type == 1
            && entry.source_identity != source_identity
            && (entry.time - time).abs() <= 3.0
            && !sources.contains(&entry.source_identity)
        {
            sources.push(entry.source_identity);
            weight += 1.0 - correlation;
            if weight >= 3.0 {
                return 3.0;
            }
        }
    }
    weight
}

fn source_type_code(source_type: SourceType) -> u8 {
    match source_type {
        SourceType::FixedPost => 0,
        SourceType::Civilian => 1,
        SourceType::SocialNetwork => 2,
        SourceType::Administrative => 3,
        SourceType::OrganizationMember => 4,
        SourceType::PoliticalElite => 5,
        SourceType::Interpreter => 6,
        SourceType::Patrol => 7,
    }
}

fn source_type_from_code(code: u8) -> Option<SourceType> {
    Some(match code {
        0 => SourceType::FixedPost,
        1 => SourceType::Civilian,
        2 => SourceType::SocialNetwork,
        3 => SourceType::Administrative,
        4 => SourceType::OrganizationMember,
        5 => SourceType::PoliticalElite,
        6 => SourceType::Interpreter,
        7 => SourceType::Patrol,
        _ => return None,
    })
}

fn command_node_ids(particle: &ParticleState) -> Vec<String> {
    let mut values = (0..particle.organizations.kind.len())
        .map(|organization| format!("CMD:{}", crate::organization_name(organization)))
        .collect::<Vec<_>>();
    values.sort();
    values
}

fn command_node_code(
    particle: &ParticleState,
    topology: &StaticTopology,
    node: &str,
) -> Option<u32> {
    let mut commands = command_node_ids(particle);
    let position = commands.iter().position(|value| value == node)?;
    let base = particle.organizations.kind.len()
        + particle.formations.personnel.len()
        + particle.security_posts.organization.len()
        + auxiliary_node_ids(particle, topology).len();
    commands.shrink_to_fit();
    Some((base + position) as u32)
}

fn stable_hash_code(value: &str) -> u32 {
    let mut hash = 2_166_136_261u32;
    for byte in value.as_bytes() {
        hash ^= u32::from(*byte);
        hash = hash.wrapping_mul(16_777_619);
    }
    hash & 0x3fff_ffff
}

fn source_id_code(particle: &ParticleState, topology: &StaticTopology, source_id: &str) -> u32 {
    let organizations = particle.organizations.kind.len();
    if let Some(formation) = formation_index(particle, source_id) {
        return (organizations + formation) as u32;
    }
    let mut posts = (0..particle.security_posts.organization.len())
        .map(|index| (post_name(particle, topology, index), index))
        .collect::<Vec<_>>();
    posts.sort_by(|left, right| left.0.cmp(&right.0));
    if let Some(position) = posts.iter().position(|(name, _)| name == source_id) {
        return (organizations + particle.formations.personnel.len() + position) as u32;
    }
    let mut auxiliary = auxiliary_node_ids(particle, topology);
    auxiliary.sort();
    if let Some(position) = auxiliary
        .iter()
        .position(|identifier| identifier == source_id)
    {
        return (organizations + particle.formations.personnel.len() + posts.len() + position)
            as u32;
    }
    0x4000_0000u32 | stable_hash_code(source_id)
}

fn source_identity_code(
    particle: &ParticleState,
    topology: &StaticTopology,
    source_id: &str,
) -> u32 {
    if source_id.starts_with("PATROL-") {
        return 0x2000_0000u32 | stable_hash_code(source_id);
    }
    source_id_code(particle, topology, source_id)
}

fn information_observation_codebook(
    particle: &ParticleState,
    topology: &StaticTopology,
    source_id: &str,
) -> (u32, u32, u32) {
    let source = source_id_code(particle, topology, source_id);
    let community = if source_id.starts_with('C') {
        community_index(source_id)
            .filter(|index| *index < particle.communities.locality.len())
            .map(|index| index as u32)
            .unwrap_or(INFORMATION_NONE)
    } else {
        INFORMATION_NONE
    };
    let formation = formation_index(particle, source_id)
        .map(|index| index as u32)
        .unwrap_or(INFORMATION_NONE);
    (source, community, formation)
}

fn information_decay_rate(
    config: &SimulationConfig,
    observation_type: u8,
    target_formation: u32,
) -> f64 {
    if observation_type == 0 || target_formation != INFORMATION_NONE {
        config.information.formation_decay_rate
    } else {
        config.information.default_decay_rate
    }
}

#[allow(clippy::too_many_arguments)]
fn publish_information_observation(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    observer: usize,
    observer_node: &str,
    source_id: &str,
    source_type: SourceType,
    observation_type: u8,
    target: Option<usize>,
    target_formation: Option<usize>,
    locality: usize,
    microzone: usize,
    time: f64,
    quality: f64,
    confidence: f64,
    control: [f64; CONTROL_DIMENSIONS],
    violence: f64,
    presence: f64,
    personnel: f64,
    detection_probability: f64,
    detected: bool,
) {
    let sequence = particle.next_information_observation_sequence;
    particle.next_information_observation_sequence = sequence.saturating_add(1);
    let observer_node_code = dynamic_observer_code(particle, topology, observer_node);
    let (source, source_community, source_formation) =
        information_observation_codebook(particle, topology, source_id);
    let source_identity = source_identity_code(particle, topology, source_id);
    let target_code = target.map(|value| value as u32).unwrap_or(INFORMATION_NONE);
    let target_formation_code = target_formation
        .map(|value| value as u32)
        .unwrap_or(INFORMATION_NONE);
    particle
        .information_observations
        .push(InformationObservation {
            sequence,
            observer: observer as u32,
            observer_node: observer_node_code,
            source,
            source_identity,
            source_community,
            source_formation,
            source_type: source_type_code(source_type),
            observation_type,
            target: target_code,
            target_formation: target_formation_code,
            locality: locality as u32,
            microzone: microzone as u32,
            time,
            quality: clamp01(quality),
            confidence: clamp01(confidence),
            decay_rate: information_decay_rate(config, observation_type, target_formation_code),
            control,
            violence: clamp01(violence),
            presence: clamp01(presence),
            personnel: personnel.max(0.0),
            detection_probability: clamp01(detection_probability),
            detected: u8::from(detected),
        });
    queue_information_relay(
        particle,
        topology,
        config,
        sequence,
        observer,
        observer_node_code,
        locality,
        time,
        source_type,
    );
}

fn queue_information_relay(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    observation: u64,
    observer: usize,
    source_node: u32,
    _locality: usize,
    time: f64,
    source_type: SourceType,
) {
    let destination_name = format!("CMD:{}", crate::organization_name(observer));
    let Some(destination_node) = command_node_code(particle, topology, &destination_name) else {
        return;
    };
    if source_node == destination_node {
        return;
    }
    let mut reliability = config.information.relay_base_reliability;
    let mut latency_hours = 0.0;
    let mut route = vec![source_node, destination_node];
    let formation_code = source_node as usize;
    let formation_start = particle.organizations.kind.len();
    let formation_end = formation_start + particle.formations.personnel.len();
    if (formation_start..formation_end).contains(&formation_code) {
        let formation = formation_code - formation_start;
        if let Some(edge) = (0..particle.command_edges.organization.len()).find(|index| {
            particle.command_edges.organization[*index] as usize == observer
                && particle.command_edges.formation[*index] as usize == formation
        }) {
            reliability = particle.command_edges.reliability[edge];
            latency_hours = particle.command_edges.latency_hours[edge];
        }
    } else {
        reliability *= 0.7
            + 0.3
                * particle
                    .organizations
                    .institutional_quality
                    .get(observer)
                    .copied()
                    .unwrap_or(0.5);
    }
    latency_hours += config
        .information
        .source_latency_hours
        .get(source_type.name())
        .copied()
        .unwrap_or(0.0);
    let sequence = particle.next_information_relay_sequence;
    particle.next_information_relay_sequence = sequence.saturating_add(1);
    particle.information_relays.push(InformationRelay {
        sequence,
        observation,
        organization: observer as u32,
        source_node,
        destination_node,
        route: std::mem::take(&mut route),
        sent_at: time,
        arrives_at: time + latency_hours.max(0.0) / 24.0,
        reliability: clamp01(reliability),
        latency_hours: latency_hours.max(0.0),
        status: 0,
        delivered_at: -1.0e9,
    });
}

fn observe_from_source(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    observer: usize,
    observer_node: &str,
    source_id: &str,
    source_type: SourceType,
    locality: usize,
    time: f64,
    history: &mut Vec<ControlHistoryEntry>,
) {
    let targets = target_actors(particle, observer);
    if rng.random()
        >= report_probability(particle, config, observer, source_type, source_id, locality)
    {
        return;
    }
    let node = observer_node.to_string();
    if targets.is_empty() {
        let target = control_target(observer);
        observe_control(
            particle,
            topology,
            config,
            rng,
            observer,
            &node,
            source_id,
            source_type,
            locality,
            target,
            time,
            history,
        );
        return;
    }

    let microzone = topology.primary_zone[locality] as usize;
    for target in targets {
        let target_id = if matches!(
            source_type,
            SourceType::OrganizationMember | SourceType::Interpreter
        ) {
            target_formations(particle, target, locality)
                .first()
                .copied()
        } else {
            None
        };
        observe_target(
            particle,
            topology,
            config,
            rng,
            observer_node,
            source_id,
            source_type,
            locality,
            target,
            target_id,
            microzone,
            time,
        );
    }
    observe_control(
        particle,
        topology,
        config,
        rng,
        observer,
        &node,
        source_id,
        source_type,
        locality,
        control_target(observer),
        time,
        history,
    );
}

fn observe_target(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    observer_node: &str,
    source_id: &str,
    source_type: SourceType,
    locality: usize,
    target: usize,
    target_formation: Option<usize>,
    microzone: usize,
    _time: f64,
) {
    let (present, personnel, actual_formation) =
        actual_target_presence(particle, target, locality, target_formation, microzone);
    let probability = if present {
        detection_probability(
            particle,
            topology,
            config,
            observer_node,
            actual_formation.or(target_formation),
            locality,
            source_type,
            microzone,
        )
    } else {
        false_positive_probability(
            particle,
            topology,
            config,
            observer_node,
            locality,
            source_type,
            microzone,
        )
    };
    let detected = rng.random() < probability;

    // Source quality is sampled for negative reports too.  This seemingly
    // redundant draw is part of the Python observation contract.
    let _quality = source_quality(particle, config, rng, source_type, locality);
    if detected {
        if present {
            let _estimate = personnel * (0.65 + 0.7 * rng.random());
            let _attribution_mistake = rng.random() < config.information.attribution_error_rate;
        } else {
            let _estimate = rng.uniform(20.0, 250.0).max(1.0);
        }
    }
    let _ = source_id;
    particle.counters.observations = particle.counters.observations.saturating_add(1);
}

fn observe_control(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    observer: usize,
    observer_node: &str,
    source_id: &str,
    source_type: SourceType,
    locality: usize,
    target: usize,
    time: f64,
    history: &mut Vec<ControlHistoryEntry>,
) {
    let quality = source_quality(particle, config, rng, source_type, locality);
    let trust = source_trust(particle, config, observer, source_type, source_id);
    let language = language_comprehension(
        particle,
        topology,
        config,
        observer,
        locality,
        source_type,
        source_id,
    );
    let noise = config.observation_noise * (1.35 - 0.55 * quality * language);
    let values = control_values(particle, locality, target);
    let mut observed = [0.0; CONTROL_DIMENSIONS];
    for dimension in 0..CONTROL_DIMENSIONS {
        observed[dimension] = clamp01(values[dimension] + rng.uniform(-noise, noise));
    }
    let _violence = clamp01(
        particle
            .locality
            .violence
            .get(locality)
            .copied()
            .unwrap_or(0.0)
            + rng.uniform(-noise, noise),
    );
    let confidence = clamp01(0.45 + 0.45 * trust);
    let base_weight =
        confidence * quality * trust * language.powf(config.information.language_fusion_weight);
    let corroboration = corroboration_weight(
        history,
        target,
        locality,
        source_identity_code(particle, topology, source_id),
        time,
        config,
        source_type,
    );
    let weight =
        base_weight * (1.0 + config.information.corroboration_bonus * corroboration.min(3.0));

    let dynamic_observer = dynamic_observer_code(particle, topology, observer_node);
    let key = BeliefKey {
        observer: dynamic_observer,
        target: target as u32,
        locality: locality as u32,
        kind: 3,
    };
    let is_new = !particle
        .beliefs
        .keys
        .iter()
        .any(|existing| existing == &key);
    let index = particle.beliefs.ensure_key(key);
    if is_new {
        let offset = index * CONTROL_DIMENSIONS;
        particle.beliefs.control[offset..offset + CONTROL_DIMENSIONS].fill(0.5);
        particle.beliefs.confidence[index] = config.information.prior_confidence;
    }
    particle.beliefs.fuse_control(
        index,
        time,
        weight,
        &observed,
        config.information.contradiction_memory_days,
        config.information.contradiction_penalty,
    );

    // A field formation also receives the physical-control scalar in its
    // zone-local belief. Auxiliary and fixed police-post nodes have no native
    // zone belief row, matching the Python recipient boundary.
    if let Some(formation) = formation_index(particle, observer_node) {
        let organization = particle.formations.organization[formation] as usize;
        if let Some(zone_index) = zone_belief_index(
            particle,
            organization,
            topology.primary_zone[locality] as usize,
        ) {
            fuse_zone(particle, config, zone_index, time, weight, observed[1]);
        }
    }
    let source_identity = source_identity_code(particle, topology, source_id);
    history.push(ControlHistoryEntry {
        target: target as u32,
        locality: locality as u32,
        observation_type: 1,
        time,
        source_identity,
    });
    publish_information_observation(
        particle,
        topology,
        config,
        observer,
        observer_node,
        source_id,
        source_type,
        1,
        Some(target),
        None,
        locality,
        topology.primary_zone[locality] as usize,
        time,
        quality,
        confidence,
        observed,
        _violence,
        0.0,
        0.0,
        0.0,
        true,
    );
    particle.counters.observations = particle.counters.observations.saturating_add(1);
}

fn fuse_zone(
    particle: &mut ParticleState,
    config: &SimulationConfig,
    index: usize,
    time: f64,
    weight: f64,
    observed: f64,
) {
    let prior_confidence = particle.zone_beliefs.confidence[index];
    let prior = prior_confidence.max(0.02);
    let denominator = prior + weight;
    let old = particle.zone_beliefs.estimate[index];
    let contradiction = particle.zone_beliefs.contradiction[index]
        * python_exp(
            -((time - particle.zone_beliefs.updated_at[index]).max(0.0))
                / config
                    .information
                    .contradiction_memory_days
                    .max(f64::MIN_POSITIVE),
        )
        + weight * (observed - old).abs();
    particle.zone_beliefs.estimate[index] =
        clamp01((prior * old + weight * observed) / denominator);
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

fn target_actors(particle: &ParticleState, observer: usize) -> Vec<usize> {
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
    if particle.organizations.kind[observer] == 3 {
        let has_state_security = (0..particle.organizations.kind.len()).any(|organization| {
            organization != observer
                && particle.organizations.active.get(organization).copied() == Some(1)
                && matches!(particle.organizations.kind[organization], 0 | 1 | 2)
        });
        if has_state_security {
            return vec![crate::GOVERNMENT];
        }
        return Vec::new();
    }
    if particle.organizations.active.get(crate::INSURGENT).copied() == Some(1) {
        vec![crate::INSURGENT]
    } else {
        Vec::new()
    }
}

fn control_target(observer: usize) -> usize {
    if observer == crate::INSURGENT {
        crate::INSURGENT
    } else {
        crate::GOVERNMENT
    }
}

fn actual_target_presence(
    particle: &ParticleState,
    target: usize,
    locality: usize,
    target_formation: Option<usize>,
    microzone: usize,
) -> (bool, f64, Option<usize>) {
    let mut personnel = 0.0;
    let mut chosen = None;
    for formation in 0..particle.formations.personnel.len() {
        if target_formation.is_some_and(|value| value != formation)
            || !formation_matches_target(particle, formation, target)
            || particle.formations.active[formation] == 0
            || particle.formations.personnel[formation] <= 0.0
            || particle.formations.locality[formation] as usize != locality
            || particle.formations.moving[formation] != 0
            || particle.formations.outside_pineland[formation] != 0
            || particle.formations.operational_status[formation] != 1
        {
            continue;
        }
        let current_zone = particle.formations.microzone[formation] as usize;
        let patrol_present = (0..particle.patrols.formation.len()).any(|patrol| {
            particle.patrols.active.get(patrol).copied().unwrap_or(0) != 0
                && particle.patrols.formation[patrol] as usize == formation
                && particle.patrols.route_target[patrol] as usize == microzone
        });
        if current_zone != microzone && !patrol_present {
            continue;
        }
        personnel += particle.formations.personnel[formation];
        if chosen.is_none_or(|current| {
            particle.formations.personnel[formation] > particle.formations.personnel[current]
        }) {
            chosen = Some(formation);
        }
    }
    (chosen.is_some(), personnel, chosen)
}

fn formation_matches_target(particle: &ParticleState, formation: usize, target: usize) -> bool {
    let organization = particle.formations.organization[formation] as usize;
    if target == crate::INSURGENT {
        particle.organizations.kind.get(organization).copied() == Some(3)
    } else if target == crate::GOVERNMENT {
        matches!(
            particle.organizations.kind.get(organization).copied(),
            Some(0 | 1 | 2)
        )
    } else {
        organization == target
    }
}

fn target_formations(particle: &ParticleState, target: usize, locality: usize) -> Vec<usize> {
    (0..particle.formations.personnel.len())
        .filter(|formation| {
            formation_matches_target(particle, *formation, target)
                && particle.formations.active[*formation] != 0
                && particle.formations.personnel[*formation] > 0.0
                && particle.formations.locality[*formation] as usize == locality
                && particle.formations.moving[*formation] == 0
        })
        .collect()
}

fn detection_probability(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    observer_node: &str,
    target_formation: Option<usize>,
    locality: usize,
    source_type: SourceType,
    microzone: usize,
) -> f64 {
    let observer_formation = formation_index(particle, observer_node);
    let observer_actor = observer_formation
        .map(|formation| particle.formations.organization[formation] as usize)
        .unwrap_or(crate::GOVERNMENT);
    let zone_observability = topology
        .zone_observability
        .get(microzone)
        .copied()
        .unwrap_or(particle.locality.observability[locality]);
    let readiness = observer_formation
        .map(|formation| fatigue_adjusted_readiness(particle, formation))
        .unwrap_or_else(|| {
            particle
                .organizations
                .institutional_quality
                .get(observer_actor)
                .copied()
                .unwrap_or(0.5)
                .clamp(0.0, 1.0)
        });
    let target_embeddedness = target_formation
        .map(|formation| clamp01(particle.formations.embeddedness[formation]))
        .unwrap_or(0.5);
    let language = language_comprehension(
        particle,
        topology,
        config,
        observer_actor,
        locality,
        source_type,
        observer_node,
    );
    let pressure = observer_formation
        .map(|formation| {
            let deployment = deployable_personnel(particle, formation)
                / particle.formations.personnel[formation].max(1.0);
            clamp01(
                deployment
                    * particle.formations.quality[formation]
                    * particle.formations.cohesion[formation]
                    * (0.5 + particle.formations.information[formation])
                    / 2.0,
            )
        })
        .unwrap_or(0.5);
    let exposure = clamp01(0.35 + 0.45 * zone_observability - 0.25 * target_embeddedness);
    let terrain_penalty = clamp01(particle.locality.terrain_friction[locality] / 2.5);
    let mut score = logit(config.information.true_positive_rate)
        + config.information.detection_pressure_bonus * pressure
        + config.information.detection_exposure_bonus * exposure
        + config.information.detection_language_bonus * language
        + config.information.detection_observability_bonus * zone_observability
        + config.information.detection_readiness_bonus * readiness
        - config.information.detection_terrain_penalty * terrain_penalty;
    if let Some(formation) = target_formation {
        let organization = particle.formations.organization[formation] as usize;
        if particle.organizations.kind.get(organization).copied() == Some(3) {
            let dispersion = particle
                .organizations
                .phenotype
                .get(organization * 8 + 3)
                .copied()
                .unwrap_or(0.5);
            let concealment = config.information.insurgent_concealment * (0.5 + 0.5 * dispersion);
            score -= 0.9 * concealment;
        }
    }
    clamp01(logistic(score))
}

fn false_positive_probability(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    observer_node: &str,
    locality: usize,
    source_type: SourceType,
    microzone: usize,
) -> f64 {
    let observability = topology
        .zone_observability
        .get(microzone)
        .copied()
        .unwrap_or(particle.locality.observability[locality]);
    let language = formation_index(particle, observer_node)
        .map(|formation| {
            let organization = particle.formations.organization[formation] as usize;
            language_comprehension(
                particle,
                topology,
                config,
                organization,
                locality,
                source_type,
                observer_node,
            )
        })
        .unwrap_or(0.25);
    let score = logit(config.information.false_positive_rate)
        + 0.3 * (1.0 - observability)
        + 0.25 * (1.0 - language);
    clamp01(logistic(score))
}

fn source_quality(
    particle: &ParticleState,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    source_type: SourceType,
    locality: usize,
) -> f64 {
    let coverage = config
        .information
        .source_coverage
        .get(source_type.name())
        .copied()
        .unwrap_or(0.4);
    clamp01(
        coverage
            * (0.55 + 0.45 * particle.locality.observability[locality])
            * (0.85 + 0.3 * rng.random()),
    )
}

fn source_trust(
    particle: &ParticleState,
    config: &SimulationConfig,
    observer: usize,
    source_type: SourceType,
    source_id: &str,
) -> f64 {
    let mut trust = config
        .information
        .source_trust
        .get(source_type.name())
        .copied()
        .unwrap_or(0.5);
    trust *= 0.7
        + 0.3
            * particle
                .organizations
                .accountability
                .get(observer)
                .copied()
                .unwrap_or(0.5)
                .clamp(0.0, 1.0);
    if matches!(
        source_type,
        SourceType::Civilian | SourceType::SocialNetwork
    ) && community_index(source_id).is_some()
    {
        let community = community_index(source_id).unwrap();
        let cooperation = if observer == crate::INSURGENT {
            particle
                .communities
                .insurgent_sympathy
                .get(community)
                .copied()
                .unwrap_or(0.0)
        } else {
            particle
                .communities
                .government_cooperation
                .get(community)
                .copied()
                .unwrap_or(0.0)
        };
        trust *= 0.7 + 0.6 * clamp01(cooperation);
    }
    trust.clamp(0.02, 1.0)
}

fn report_probability(
    particle: &ParticleState,
    config: &SimulationConfig,
    observer: usize,
    source_type: SourceType,
    source_id: &str,
    locality: usize,
) -> f64 {
    let mut probability = match source_type {
        SourceType::Civilian => config.information.civilian_report_rate,
        SourceType::SocialNetwork => config.information.social_report_rate,
        SourceType::Administrative => config.information.administrative_report_rate,
        SourceType::PoliticalElite => config.information.elite_report_rate,
        SourceType::OrganizationMember => config.information.member_report_rate,
        SourceType::FixedPost => config.information.fixed_post_report_rate,
        SourceType::Interpreter => config.information.interpreter_report_rate,
        SourceType::Patrol => config.information.patrol_report_rate,
    };
    if source_type == SourceType::Administrative {
        probability *= 0.35 + 0.95 * clamp01(particle.locality.administrative_capacity[locality]);
    } else if source_type == SourceType::PoliticalElite {
        // At t=0 the Python governance defaults are representation=.5 and
        // elite access=1 for populated localities.  The state extension will
        // carry these fields explicitly before long-horizon parity is sealed.
        let elite_access = if particle
            .locality
            .population
            .get(locality)
            .copied()
            .unwrap_or(0.0)
            > 0.0
        {
            1.0
        } else {
            0.0
        };
        probability *= (0.45 + 0.65 * 0.5) * elite_access;
    }
    if let Some(community) = community_index(source_id) {
        let cooperation = if observer == crate::INSURGENT {
            particle
                .communities
                .insurgent_sympathy
                .get(community)
                .copied()
                .unwrap_or(0.0)
        } else {
            particle
                .communities
                .government_cooperation
                .get(community)
                .copied()
                .unwrap_or(0.0)
        };
        probability *= 0.35 + 1.1 * clamp01(cooperation);
    }
    reference_probability(clamp01(probability), config.intervals.information, 0.25)
}

fn language_comprehension(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    observer: usize,
    locality: usize,
    source_type: SourceType,
    source_id: &str,
) -> f64 {
    if observer >= particle.organizations.kind.len() {
        return 0.25;
    }
    let embeddedness =
        local_organizational_embeddedness(particle, topology, config, observer, locality);
    let district = topology.locality_to_district[locality] as usize;
    let pattern = topology
        .district_language_patterns
        .get(district)
        .map(String::as_str)
        .unwrap_or("FS");
    let primary = pattern.split('/').next().unwrap_or("FS");
    let multilingual = pattern.contains('/');
    if source_type.is_community_channel() {
        let mut base = 0.28 + 0.48 * embeddedness;
        if primary != "FS" {
            base -= 0.18;
        }
        if multilingual {
            base += 0.07;
        }
        if source_type == SourceType::Interpreter {
            base += 0.2;
        }
        if let Some(community) = community_index(source_id) {
            let start = community * 4;
            let maximum = particle
                .communities
                .language_profile
                .get(start..start + 4)
                .unwrap_or(&[])
                .iter()
                .copied()
                .fold(0.0, f64::max);
            base = 0.22 + 0.62 * maximum;
            if source_type == SourceType::Interpreter {
                base += 0.15;
            }
        }
        clamp01(base.max(0.08))
    } else if let Some(formation) = formation_index(particle, source_id) {
        clamp01(0.35 + 0.55 * particle.formations.information[formation] + 0.1 * embeddedness)
            .max(0.1)
    } else {
        clamp01(0.45 + 0.45 * embeddedness).max(0.1)
    }
}

fn local_organizational_embeddedness(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
) -> f64 {
    if organization >= particle.organizations.kind.len() || locality >= topology.locality_count() {
        return 0.0;
    }
    let threshold = config
        .organization_ecology
        .minimum_formation_personnel
        .max(1.0e-12);
    let mut represented_local = 0.0;
    let mut home_local = 0.0;
    let mut home_district = 0.0;
    let target_district = topology.locality_to_district[locality];
    for person in 0..particle.people.locality.len() {
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
        if particle.people.home[person] as usize == locality {
            home_local += represented;
        }
        let home = particle.people.home[person] as usize;
        if topology.locality_to_district.get(home).copied() == Some(target_district) {
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

    let offset = locality * CONTROL_DIMENSIONS;
    let institutional_channel = match organization {
        crate::GOVERNMENT => clamp01(
            (particle.locality.government_control[offset + 5]
                + particle.locality.government_control[offset + 2]
                + particle.locality.government_control[offset + 6])
                / 3.0,
        ),
        crate::INSURGENT => clamp01(
            (particle.locality.insurgent_control[offset + 5]
                + particle.locality.insurgent_control[offset + 2]
                + particle.locality.insurgent_control[offset + 6])
                / 3.0,
        ),
        _ => 0.0,
    };
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

fn available_personnel(particle: &ParticleState, formation: usize) -> f64 {
    particle.formations.available_personnel(formation)
}

fn deployable_personnel(particle: &ParticleState, formation: usize) -> f64 {
    particle.formations.deployable_personnel(formation)
}

fn fatigue_adjusted_readiness(particle: &ParticleState, formation: usize) -> f64 {
    particle.formations.fatigue_adjusted_readiness(formation)
}

fn control_values(
    particle: &ParticleState,
    locality: usize,
    target: usize,
) -> [f64; CONTROL_DIMENSIONS] {
    let offset = locality * CONTROL_DIMENSIONS;
    let values = if target == crate::INSURGENT {
        &particle.locality.insurgent_control
    } else {
        &particle.locality.government_control
    };
    let mut result = [0.0; CONTROL_DIMENSIONS];
    result.copy_from_slice(&values[offset..offset + CONTROL_DIMENSIONS]);
    result
}

fn formation_index(particle: &ParticleState, identifier: &str) -> Option<usize> {
    (0..particle.formations.personnel.len())
        .find(|index| formation_name(particle, *index) == identifier)
}

fn formation_name(particle: &ParticleState, formation: usize) -> String {
    let organization = particle.formations.organization[formation] as usize;
    let rank = (0..=formation)
        .filter(|index| particle.formations.organization[*index] as usize == organization)
        .count();
    if particle.organizations.kind.get(organization).copied() == Some(3) {
        format!("PRF-{rank:02}")
    } else {
        format!("FDF-{rank:02}")
    }
}

fn post_name(particle: &ParticleState, topology: &StaticTopology, post: usize) -> String {
    if post < topology.locality_count() {
        format!("POST-{}-POLICE", locality_id(topology, post))
    } else {
        let formation = particle.security_posts.formation[post] as usize;
        if formation < particle.formations.personnel.len() {
            format!("POST-{}", formation_name(particle, formation))
        } else {
            format!("POST-{post:05}")
        }
    }
}

fn dynamic_observer_code(particle: &ParticleState, topology: &StaticTopology, node: &str) -> u32 {
    let organizations = particle.organizations.kind.len();
    if let Some(formation) = formation_index(particle, node) {
        return (organizations + formation) as u32;
    }
    let mut posts = (0..particle.security_posts.organization.len())
        .map(|index| (post_name(particle, topology, index), index))
        .collect::<Vec<_>>();
    posts.sort_by(|left, right| left.0.cmp(&right.0));
    if let Some(position) = posts.iter().position(|(name, _)| name == node) {
        return (organizations + particle.formations.personnel.len() + position) as u32;
    }
    let mut auxiliary = auxiliary_node_ids(particle, topology);
    auxiliary.sort();
    if let Some(position) = auxiliary.iter().position(|identifier| identifier == node) {
        return (organizations + particle.formations.personnel.len() + posts.len() + position)
            as u32;
    }
    if let Some(code) = command_node_code(particle, topology, node) {
        return code;
    }
    // All internally generated nodes are in one of the registries above. The
    // deterministic fallback keeps externally supplied diagnostic nodes from
    // aliasing the first auxiliary node.
    let base = organizations
        + particle.formations.personnel.len()
        + posts.len()
        + auxiliary.len()
        + command_node_ids(particle).len();
    base as u32 + (stable_hash_code(node) & 0x3fff_ffff)
}

fn auxiliary_node_ids(particle: &ParticleState, topology: &StaticTopology) -> Vec<String> {
    let mut values = Vec::new();
    for community in 0..particle.communities.locality.len() {
        values.push(community_name(community));
        values.push(format!("ELITE:{}", community_name(community)));
    }
    for locality in 0..topology.locality_count() {
        let id = locality_id(topology, locality);
        values.push(format!("ADMIN:{id}"));
        values.push(format!("ELITE-CAP:{id}"));
        values.push(format!("INTERPRETER-CAP:{id}"));
    }
    values.sort();
    values.dedup();
    values
}

fn locality_id(topology: &StaticTopology, locality: usize) -> String {
    let zone = topology.primary_zone[locality] as usize;
    topology
        .microzone_names
        .get(zone)
        .and_then(|name| name.split_once("-Z").map(|(id, _)| id.to_string()))
        .unwrap_or_else(|| format!("L{:03}", locality + 1))
}

fn community_name(community: usize) -> String {
    format!("C{community:06}")
}

fn community_index(identifier: &str) -> Option<usize> {
    identifier
        .strip_prefix('C')
        .and_then(|value| value.parse::<usize>().ok())
}

fn communities_for_locality(particle: &ParticleState, locality: usize) -> Vec<usize> {
    (0..particle.communities.locality.len())
        .filter(|community| particle.communities.locality[*community] as usize == locality)
        .collect()
}

fn select_community(
    particle: &ParticleState,
    communities: &[usize],
    rng: &mut PyRandomCompat,
) -> usize {
    if communities.len() == 1 {
        let _ = rng.random();
        return communities[0];
    }
    let mut cumulative = Vec::with_capacity(communities.len());
    let mut total = 0.0;
    for community in communities {
        let start = particle.communities.member_offsets[*community] as usize;
        let end = particle.communities.member_offsets[*community + 1] as usize;
        let mut weight = 0.0;
        for person in &particle.communities.member_indices[start..end] {
            weight += particle.people.represented_population[*person as usize];
        }
        total += weight.max(1.0);
        cumulative.push(total);
    }
    let draw = rng.random() * total;
    communities[cumulative
        .iter()
        .position(|value| *value > draw)
        .unwrap_or(communities.len() - 1)]
}

fn is_multilingual(topology: &StaticTopology, locality: usize) -> bool {
    let district = topology.locality_to_district[locality] as usize;
    topology
        .district_language_patterns
        .get(district)
        .map(|pattern| pattern.contains('/'))
        .unwrap_or(false)
}

fn zone_belief_index(particle: &ParticleState, observer: usize, zone: usize) -> Option<usize> {
    particle
        .zone_beliefs
        .keys
        .iter()
        .position(|key| key.observer as usize == observer && key.zone as usize == zone)
}

fn logit(probability: f64) -> f64 {
    let probability = probability.clamp(1.0e-6, 1.0 - 1.0e-6);
    (probability / (1.0 - probability)).ln()
}

fn logistic(value: f64) -> f64 {
    if value >= 0.0 {
        1.0 / (1.0 + python_exp(-value))
    } else {
        let exponential = python_exp(value);
        exponential / (1.0 + exponential)
    }
}

fn reference_probability(probability: f64, elapsed_days: f64, reference_days: f64) -> f64 {
    if probability <= 0.0 || elapsed_days <= 0.0 {
        return 0.0;
    }
    if probability >= 1.0 {
        return 1.0;
    }
    1.0 - (1.0 - probability).powf(elapsed_days / reference_days)
}
