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
    ParticleState, PresenceKey, CONTROL_DIMENSIONS, INFORMATION_NONE,
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
    Contact,
}

type ControlHistoryEntry = InformationHistoryEntry;

fn append_history_entry(history: &mut Vec<ControlHistoryEntry>, entry: ControlHistoryEntry) {
    let cutoff = entry.time - 3.0;
    history.retain(|existing| {
        existing.target != entry.target
            || existing.locality != entry.locality
            || existing.observation_type != entry.observation_type
            || existing.time >= cutoff
    });
    history.push(entry);
}

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
    let source_id = patrol_source_id(particle, formation);
    let source_identity = source_identity_code(particle, topology, &source_id);
    if std::env::var_os("PINELAND_INFO_TRACE").is_some() && locality == 28 && time >= 0.0 {
        eprintln!(
            "PATROL_ID time={:.17} formation={} source={} identity={}",
            time, formation, source_id, source_identity
        );
    }
    append_history_entry(
        &mut particle.information_history,
        InformationHistoryEntry {
            target: target as u32,
            locality: locality as u32,
            observation_type: 1,
            time,
            source_identity,
        },
    );
}

pub(crate) fn patrol_source_id(particle: &ParticleState, formation: usize) -> String {
    format!("PATROL-{}", formation_name(particle, formation))
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
            Self::Contact => "contact",
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
    // Python ages every actor/control confidence row once at the beginning
    // of an information event.  This is separate from the contradiction
    // decay applied by an individual fusion: an untouched prior still loses
    // confidence as calendar time advances.  Keep the last boundary on the
    // particle so restart and same-time events remain exact.
    let elapsed = (time - particle.last_information_decay_at).max(0.0);
    if elapsed > 0.0 {
        let default_factor = python_exp(-config.information.default_decay_rate * elapsed);
        let formation_factor = python_exp(-config.information.formation_decay_rate * elapsed);
        for confidence in &mut particle.beliefs.confidence {
            *confidence = clamp01(*confidence * default_factor);
        }
        for confidence in &mut particle.zone_beliefs.confidence {
            *confidence = clamp01(*confidence * formation_factor);
        }
        particle
            .presence_beliefs
            .decay_confidence(default_factor, formation_factor);
        particle
            .node_presence_beliefs
            .decay_confidence(default_factor, formation_factor);
        particle.last_information_decay_at = time;
    }

    // Corroboration is part of the future-decision state.  The Python source
    // index prunes each key when a new observation for that key is appended,
    // rather than pruning every key at the current event clock.  In
    // particular, a report at t=0.25 must remain available to a relay whose
    // observation timestamp is t=3.25 even if no new local report for that
    // key was generated at the delivery event.
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
        if std::env::var_os("PINELAND_PRF17_TRACE").is_some()
            && formation_name(particle, formation) == "PRF-17"
            && (time - 49.0).abs() < 1.0e-9
        {
            eprintln!(
                "PRF17_ELIGIBILITY time={:.17} formation={} index={} moving={} available={:.17} personnel={:.17} locality={} status={} outside={}",
                time,
                formation_name(particle, formation),
                formation,
                particle.formations.moving[formation],
                available_personnel(particle, formation),
                particle.formations.personnel[formation],
                particle.formations.locality[formation],
                particle.formations.operational_status[formation],
                particle.formations.outside_pineland[formation],
            );
        }
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

    // Background reports are fused at their collection node immediately.  The
    // Python reference then delivers any command-network relays whose arrival
    // clock has matured, in relay-id order, before flushing the information
    // event.  Keep that boundary explicit: without it the native engine can
    // generate the right reports while silently omitting headquarters beliefs.
    deliver_due_relays(particle, topology, config, rng, time, &history);
    particle.information_history = history;
}

fn corroboration_weight(
    history: &[ControlHistoryEntry],
    target: usize,
    locality: usize,
    observation_type: u8,
    source_identity: u32,
    time: f64,
    config: &SimulationConfig,
    source_type: SourceType,
) -> f64 {
    if std::env::var_os("PINELAND_HISTORY_TRACE").is_some()
        && target == 0
        && (matches!(locality, 15 | 25 | 27) || (locality == 28 && (time - 8.25).abs() < 1.0e-9))
        && observation_type == 1
        && time >= 2.0
    {
        let rows = history
            .iter()
            .filter(|entry| {
                entry.target == target as u32
                    && entry.locality == locality as u32
                    && entry.observation_type == observation_type
            })
            .map(|entry| {
                (
                    entry.time,
                    entry.target,
                    entry.locality,
                    entry.observation_type,
                    entry.source_identity,
                )
            })
            .collect::<Vec<_>>();
        eprintln!("HISTORY_TRACE {:?}", rows);
    }
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
            && entry.observation_type == observation_type
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

/// Return the independent-source corroboration multiplier for a patrol
/// control report before that report is appended to the history. Patrols own
/// their local fusion transition, but they share the same three-day source
/// index as background information in the Python reference.
pub(crate) fn patrol_control_corroboration(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    target: usize,
    locality: usize,
    source_id: &str,
    time: f64,
) -> f64 {
    corroboration_weight(
        &particle.information_history,
        target,
        locality,
        1,
        source_identity_code(particle, topology, source_id),
        time,
        config,
        SourceType::Patrol,
    )
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
        SourceType::Contact => 8,
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
        8 => SourceType::Contact,
        _ => return None,
    })
}

fn deliver_due_relays(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
    history: &[ControlHistoryEntry],
) {
    // InformationRelay rows are allocated monotonically, so the vector order
    // is the same as Python's sorted due relay identifiers.  A relay is kept
    // after delivery in the standard/forensic state, but is never considered
    // again.
    let due = particle
        .information_relays
        .iter()
        .enumerate()
        .filter_map(|(index, relay)| {
            (relay.status == 0 && relay.arrives_at <= time + 1.0e-12).then_some(index)
        })
        .collect::<Vec<_>>();
    for relay_index in due {
        let (observation_sequence, organization, destination_node, reliability) = {
            let relay = &particle.information_relays[relay_index];
            (
                relay.observation,
                relay.organization as usize,
                relay.destination_node,
                relay.reliability,
            )
        };
        let relay_draw = rng.random();
        let delivered = relay_draw <= reliability;
        if std::env::var_os("PINELAND_RELAY_TRACE").is_some() && time >= 3.5 {
            let relay = &particle.information_relays[relay_index];
            eprintln!(
                "RELAY_TRACE time={:.17} seq={} observation={} arrives={:.17} org={} source_node={} destination_node={} reliability={:.17} draw={:.17} delivered={}",
                time,
                relay.sequence,
                relay.observation,
                relay.arrives_at,
                relay.organization,
                relay.source_node,
                relay.destination_node,
                relay.reliability,
                relay_draw,
                delivered,
            );
        }
        let Some(observation) = particle
            .information_observations
            .iter()
            .find(|observation| observation.sequence == observation_sequence)
            .cloned()
        else {
            particle.information_relays[relay_index].status = 2;
            continue;
        };
        if delivered {
            let source_type = source_type_from_code(observation.source_type);
            if let Some(source_type) = source_type {
                let source_name = observation_source_name(particle, topology, &observation);
                let organization_name =
                    crate::organization_name_for_particle(particle, organization);
                let destination_name = command_node_name(particle, topology, destination_node);
                fuse_recorded_observation(
                    particle,
                    topology,
                    config,
                    rng,
                    &observation,
                    organization,
                    &organization_name,
                    source_type,
                    &source_name,
                    time,
                    history,
                );
                fuse_recorded_observation(
                    particle,
                    topology,
                    config,
                    rng,
                    &observation,
                    organization,
                    &destination_name,
                    source_type,
                    &source_name,
                    time,
                    history,
                );
                if (observation.observer as usize) < particle.organizations.kind.len() {
                    let source_organization = observation.observer as usize;
                    if particle.organizations.kind[source_organization] != 3
                        && crate::GOVERNMENT < particle.organizations.kind.len()
                    {
                        let government_name =
                            crate::organization_name_for_particle(particle, crate::GOVERNMENT);
                        fuse_recorded_observation(
                            particle,
                            topology,
                            config,
                            rng,
                            &observation,
                            crate::GOVERNMENT,
                            &government_name,
                            source_type,
                            &source_name,
                            time,
                            history,
                        );
                    }
                }
            }
            particle.information_relays[relay_index].status = 1;
            particle.information_relays[relay_index].delivered_at = time;
        } else {
            particle.information_relays[relay_index].status = 2;
        }
    }
}

fn command_node_name(particle: &ParticleState, topology: &StaticTopology, node: u32) -> String {
    let organizations = particle.organizations.kind.len();
    let formations = particle.formations.personnel.len();
    let posts = particle.security_posts.organization.len();
    let auxiliary = auxiliary_node_ids(particle, topology).len();
    let command_start = organizations + formations + posts + auxiliary;
    let index = node as usize - command_start;
    let mut commands = command_node_ids(particle);
    commands.sort();
    commands
        .get(index)
        .cloned()
        .unwrap_or_else(|| {
            format!(
                "CMD:{}",
                crate::organization_name_for_particle(particle, crate::GOVERNMENT)
            )
        })
}

fn observation_source_name(
    particle: &ParticleState,
    _topology: &StaticTopology,
    observation: &InformationObservation,
) -> String {
    if observation.source_community != INFORMATION_NONE {
        return community_name(observation.source_community as usize);
    }
    if observation.source_formation != INFORMATION_NONE {
        return formation_name(particle, observation.source_formation as usize);
    }
    String::new()
}

fn presence_observer_code(
    particle: &ParticleState,
    topology: &StaticTopology,
    recipient: usize,
    recipient_name: &str,
) -> u32 {
    if recipient_name == crate::organization_name_for_particle(particle, recipient) {
        recipient as u32
    } else {
        dynamic_observer_code(particle, topology, recipient_name)
    }
}

fn record_presence_history(particle: &mut ParticleState, observation: &InformationObservation) {
    if observation.target == INFORMATION_NONE {
        return;
    }
    append_history_entry(
        &mut particle.information_history,
        InformationHistoryEntry {
            target: observation.target,
            locality: observation.locality,
            observation_type: observation.observation_type,
            time: observation.time,
            source_identity: observation.source_identity,
        },
    );
}

fn fuse_presence_observation(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    observation: &InformationObservation,
    recipient: usize,
    recipient_name: &str,
    source_type: SourceType,
    source_name: &str,
    time: f64,
    history: &[ControlHistoryEntry],
) {
    if observation.observation_type != 0 || observation.target == INFORMATION_NONE {
        return;
    }
    let target = observation.target as usize;
    let locality = observation.locality as usize;
    if target >= particle.organizations.kind.len() || locality >= topology.locality_count() {
        return;
    }
    let recipient_actor =
        if recipient_name == crate::organization_name_for_particle(particle, recipient) {
            recipient
        } else {
            observation.observer as usize
        };
    let trust = source_trust(particle, config, recipient_actor, source_type, source_name);
    let language = language_comprehension(
        particle,
        topology,
        config,
        recipient_actor,
        locality,
        source_type,
        source_name,
    );
    let age_quality = python_exp(-observation.decay_rate * (time - observation.time).max(0.0));
    let corroboration = corroboration_weight(
        history,
        target,
        locality,
        observation.observation_type,
        observation.source_identity,
        observation.time,
        config,
        source_type,
    );
    let weight = observation.confidence
        * observation.quality
        * trust
        * language.powf(config.information.language_fusion_weight)
        * age_quality
        * (1.0 + config.information.corroboration_bonus * corroboration.min(3.0));
    let observer = presence_observer_code(particle, topology, recipient, recipient_name);
    let targets = if observation.target_formation != INFORMATION_NONE {
        [observation.target_formation, INFORMATION_NONE]
    } else {
        [INFORMATION_NONE, INFORMATION_NONE]
    };
    let target_count = if observation.target_formation != INFORMATION_NONE {
        2
    } else {
        1
    };
    let state = if recipient_name == crate::organization_name_for_particle(particle, recipient) {
        &mut particle.presence_beliefs
    } else {
        &mut particle.node_presence_beliefs
    };
    let mut wildcard_index = None;
    for target_formation in targets.into_iter().take(target_count) {
        let index = state.ensure_key(PresenceKey {
            observer,
            target: observation.target,
            locality: observation.locality,
            microzone: observation.microzone,
            target_formation,
        });
        if state.confidence[index] == 0.0 && state.evidence_count[index] == 0 {
            state.confidence[index] = config.information.prior_confidence;
        }
        state.fuse(
            index,
            time,
            weight,
            observation.presence,
            observation.personnel,
            config.information.contradiction_memory_days,
            config.information.contradiction_penalty,
        );
        if target_formation == INFORMATION_NONE {
            wildcard_index = Some(index);
        }
    }
    if let Some(index) = wildcard_index {
        state.fuse_violence(index, weight, observation.violence);
    }
}

#[allow(clippy::too_many_arguments)]
fn fuse_recorded_observation(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    _rng: &mut PyRandomCompat,
    observation: &InformationObservation,
    recipient: usize,
    recipient_name: &str,
    source_type: SourceType,
    source_name: &str,
    time: f64,
    history: &[ControlHistoryEntry],
) {
    if !matches!(observation.observation_type, 0 | 1) {
        return;
    }
    if observation.observation_type == 0 {
        fuse_presence_observation(
            particle,
            topology,
            config,
            observation,
            recipient,
            recipient_name,
            source_type,
            source_name,
            time,
            history,
        );
        return;
    }
    // Control rows are delivered through the reliability clock and update the
    // seven-dimensional control table. Detection rows take the branch above;
    // never turn a zero-filled detection payload into a spurious control row.
    if observation.target == INFORMATION_NONE {
        return;
    }
    let target = observation.target as usize;
    let locality = observation.locality as usize;
    if target >= particle.organizations.kind.len() || locality >= topology.locality_count() {
        return;
    }
    let recipient_actor =
        if recipient_name == crate::organization_name_for_particle(particle, recipient) {
            recipient
        } else {
            observation.observer as usize
        };
    let trust = source_trust(particle, config, recipient_actor, source_type, source_name);
    let language = language_comprehension(
        particle,
        topology,
        config,
        recipient_actor,
        locality,
        source_type,
        source_name,
    );
    let age_quality = python_exp(-observation.decay_rate * (time - observation.time).max(0.0));
    let corroboration = corroboration_weight(
        history,
        target,
        locality,
        observation.observation_type,
        observation.source_identity,
        observation.time,
        config,
        source_type,
    );
    let weight = observation.confidence
        * observation.quality
        * trust
        * language.powf(config.information.language_fusion_weight)
        * age_quality
        * (1.0 + config.information.corroboration_bonus * corroboration.min(3.0));
    if std::env::var_os("PINELAND_INFO_TRACE").is_some() && time >= 0.25 {
        eprintln!(
            "RELAY_CONTROL_TRACE delivery_time={:.17} seq={} recipient={} source_type={} observer={} source={} source_comm={} source_form={} target={} locality={} quality={:.17} trust={:.17} language={:.17} age={:.17} corr={:.17} weight={:.17}",
            time,
            observation.sequence,
            recipient_name,
            observation.source_type,
            observation.observer,
            observation.source,
            observation.source_community,
            observation.source_formation,
            target,
            locality,
            observation.quality,
            trust,
            language,
            age_quality,
            corroboration,
            weight,
        );
    }
    let (observer_code, kind) =
        if recipient_name == crate::organization_name_for_particle(particle, recipient) {
            let own_target = if particle.organizations.kind.get(recipient).copied() == Some(3) {
                crate::INSURGENT
            } else {
                crate::GOVERNMENT
            };
            let kind = if target == own_target { 1 } else { 2 };
            (recipient as u32, kind)
        } else {
            (dynamic_observer_code(particle, topology, recipient_name), 3)
        };
    let key = BeliefKey {
        observer: observer_code,
        target: target as u32,
        locality: locality as u32,
        kind,
    };
    let index = particle.beliefs.ensure_key(key);
    if particle.beliefs.confidence[index] == 0.0 && particle.beliefs.evidence_count[index] == 0 {
        particle.beliefs.control[index * CONTROL_DIMENSIONS..(index + 1) * CONTROL_DIMENSIONS]
            .fill(0.5);
        particle.beliefs.confidence[index] = config.information.prior_confidence;
    }
    particle.beliefs.fuse_control(
        index,
        time,
        weight,
        &observation.control,
        config.information.contradiction_memory_days,
        config.information.contradiction_penalty,
    );
    // The destination/organization names are represented by the same native
    // numeric observer code, so the existing zone and legacy mirrors can be
    // updated only when the recipient is a real field formation. Headquarters
    // rows intentionally have no zone-local mirror.
    let zone_organization = if let Some(formation) = formation_index(particle, recipient_name) {
        Some(particle.formations.organization[formation] as usize)
    } else if recipient_name == crate::organization_name_for_particle(particle, recipient) {
        // Python treats an organization-level relay as the organization
        // actor when updating its locality/microzone auxiliary belief.  A
        // headquarters command node is deliberately excluded because its
        // string ID is not an organization ID.
        Some(recipient)
    } else {
        None
    };
    if let Some(organization) = zone_organization {
        if let Some(zone_index) =
            zone_belief_index(particle, organization, observation.microzone as usize)
        {
            fuse_zone(
                particle,
                config,
                zone_index,
                time,
                weight,
                observation.control[1],
            );
        }
    }
    if kind != 3 {
        let own_target = if particle.organizations.kind.get(recipient).copied() == Some(3) {
            crate::INSURGENT
        } else {
            crate::GOVERNMENT
        };
        if target == own_target {
            let legacy_key = BeliefKey {
                observer: recipient as u32,
                // The Python ActorBelief row is the shared base row.  The
                // native compatibility key retains the historical insurgent
                // target tag even when a government-control observation is
                // mirrored into it.
                target: crate::INSURGENT as u32,
                locality: locality as u32,
                kind: 0,
            };
            let legacy = particle.beliefs.ensure_key(legacy_key);
            let offset = legacy * CONTROL_DIMENSIONS;
            let source_offset = index * CONTROL_DIMENSIONS;
            let source_control = particle.beliefs.control
                [source_offset..source_offset + CONTROL_DIMENSIONS]
                .to_vec();
            particle.beliefs.control[offset..offset + CONTROL_DIMENSIONS]
                .copy_from_slice(&source_control);
            particle.beliefs.presence[legacy] = particle.beliefs.presence[index];
            particle.beliefs.confidence[legacy] = particle.beliefs.confidence[index];
            particle.beliefs.updated_at[legacy] = particle.beliefs.updated_at[index];
            particle.beliefs.last_reliable_observation_at[legacy] =
                particle.beliefs.last_reliable_observation_at[index];
            particle.beliefs.contradiction[legacy] = particle.beliefs.contradiction[index];
            particle.beliefs.evidence_count[legacy] = particle.beliefs.evidence_count[index];
        }
    }
}

pub(crate) fn command_node_ids(particle: &ParticleState) -> Vec<String> {
    let mut values = (0..particle.organizations.kind.len())
        .map(|organization| format!("CMD:{}", crate::organization_name_for_particle(particle, organization)))
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
) -> InformationObservation {
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
    let observation = InformationObservation {
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
        reported_momentum: 0.0,
        reported_civilian_harm: 0.0,
        attributed_actor: INFORMATION_NONE,
    };
    particle.information_observations.push(observation.clone());
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
    observation
}

/// Record one of the two noisy reports emitted by an armed engagement.
///
/// Engagement outcomes are intentionally retained as execution records but
/// are not fused into the presence/control tables: that is the Python
/// contract for `observation_type == "engagement_outcome"`.  The report still
/// enters the command relay so later delivery consumes the same reliability
/// clock and continuation state as the reference engine.
#[allow(clippy::too_many_arguments)]
pub(crate) fn record_engagement_observation(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    observer_formation: usize,
    target_formation: usize,
    engagement_id: &str,
    locality: usize,
    microzone: usize,
    time: f64,
    signal: f64,
    civilian_harm: f64,
) -> (f64, f64) {
    let observer_organization = particle.formations.organization[observer_formation] as usize;
    let target_organization = particle.formations.organization[target_formation] as usize;
    let noise = config.reporting_error;
    let perceived = clamp01(signal + rng.normalvariate(0.0, noise));
    let attributed_actor = if rng.random() < config.information.attribution_error_rate {
        observer_organization
    } else {
        target_organization
    };
    let reported_harm = (civilian_harm * rng.uniform(1.0 - noise, 1.0 + noise)).max(0.0);
    let source_id = format!("ENGAGEMENT:{engagement_id}");
    let observer_node = formation_name(particle, observer_formation);
    let observation = publish_information_observation(
        particle,
        topology,
        config,
        observer_organization,
        &observer_node,
        &source_id,
        SourceType::Contact,
        2,
        Some(target_organization),
        Some(target_formation),
        locality,
        microzone,
        time,
        0.9,
        0.84,
        [0.0; CONTROL_DIMENSIONS],
        0.0,
        0.0,
        0.0,
        0.0,
        true,
    );
    let index = particle.information_observations.len().saturating_sub(1);
    particle.information_observations[index].reported_momentum = perceived;
    particle.information_observations[index].reported_civilian_harm = reported_harm;
    particle.information_observations[index].attributed_actor = attributed_actor as u32;
    if std::env::var_os("PINELAND_COMBAT_TRACE").is_some() {
        eprintln!(
            "COMBAT_OBS engagement={} observer={} target={} signal={:.17} perceived={:.17} reported_harm={:.17} attribution={}",
            engagement_id,
            observer_organization,
            target_organization,
            signal,
            perceived,
            reported_harm,
            attributed_actor,
        );
    }
    let _ = observation;
    (perceived, reported_harm)
}

/// Publish the control report already fused by the patrol module.
///
/// Patrols retain a separate hot path because their detection and local
/// control transition is part of the Native-v1 process boundary.  The report
/// still belongs to the common information ledger, however: Python stores it
/// as an observation and sends it through the same command relay as every
/// other source.
#[allow(clippy::too_many_arguments)]
pub(crate) fn record_patrol_control_observation(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    formation: usize,
    locality: usize,
    microzone: usize,
    time: f64,
    quality: f64,
    confidence: f64,
    control: [f64; CONTROL_DIMENSIONS],
    violence: f64,
) {
    let observer = particle.formations.organization[formation] as usize;
    let source_id = patrol_source_id(particle, formation);
    let observer_node = formation_name(particle, formation);
    let _observation = publish_information_observation(
        particle,
        topology,
        config,
        observer,
        &observer_node,
        &source_id,
        SourceType::Patrol,
        1,
        Some(control_target(observer)),
        None,
        locality,
        microzone,
        time,
        quality,
        confidence,
        control,
        violence,
        0.0,
        0.0,
        0.0,
        true,
    );
}

/// Publish a patrol detection after the patrol module has consumed the
/// historical detection/quality RNG draws.
#[allow(clippy::too_many_arguments)]
pub(crate) fn record_patrol_target_observation(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    observer_formation: usize,
    target_actor: usize,
    target_formation: Option<usize>,
    locality: usize,
    microzone: usize,
    time: f64,
    quality: f64,
    confidence: f64,
    presence: f64,
    personnel: f64,
    detection_probability: f64,
    detected: bool,
) {
    let observer = particle.formations.organization[observer_formation] as usize;
    let source_id = patrol_source_id(particle, observer_formation);
    let observer_node = formation_name(particle, observer_formation);
    let observation = publish_information_observation(
        particle,
        topology,
        config,
        observer,
        &observer_node,
        &source_id,
        SourceType::Patrol,
        0,
        Some(target_actor),
        target_formation,
        locality,
        microzone,
        time,
        quality,
        confidence,
        [0.0; CONTROL_DIMENSIONS],
        0.0,
        presence,
        personnel,
        detection_probability,
        detected,
    );
    let history = particle.information_history.clone();
    fuse_presence_observation(
        particle,
        topology,
        config,
        &observation,
        observer,
        &observer_node,
        SourceType::Patrol,
        &source_id,
        time,
        &history,
    );
    record_presence_history(particle, &observation);
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
    let destination_name = format!("CMD:{}", crate::organization_name_for_particle(particle, observer));
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
    let report_probability =
        report_probability(particle, config, observer, source_type, source_id, locality);
    let report_draw = rng.random();
    if std::env::var_os("PINELAND_PRF17_TRACE").is_some() && (time - 49.0).abs() < 1.0e-9 {
        eprintln!(
            "SOURCE_TRACE source={} time={:.17} observer={} type={} locality={} draw={:.17} probability={:.17} targets={:?}",
            source_id,
            time,
            observer,
            source_type.name(),
            locality,
            report_draw,
            report_probability,
            targets,
        );
    }
    if std::env::var_os("PINELAND_INFO_TRACE").is_some() && time >= 0.5 {
        eprintln!(
            "INFO_SOURCE_TRACE time={:.17} observer={} node={} source={} type={} locality={} draw={:.17} probability={:.17} targets={:?}",
            time,
            observer,
            observer_node,
            source_id,
            source_type.name(),
            locality,
            report_draw,
            report_probability,
            targets,
        );
    }
    if report_draw >= report_probability {
        trace_source_end(rng, source_id, source_type, locality, time);
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
        trace_source_end(rng, source_id, source_type, locality, time);
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
            observer,
            observer_node,
            source_id,
            source_type,
            locality,
            target,
            target_id,
            microzone,
            time,
            history,
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
    trace_source_end(rng, source_id, source_type, locality, time);
}

fn trace_source_end(
    rng: &PyRandomCompat,
    source_id: &str,
    source_type: SourceType,
    locality: usize,
    time: f64,
) {
    if std::env::var_os("PINELAND_PRF17_TRACE").is_some() && (time - 49.0).abs() < 1.0e-9 {
        let mut probe = rng.clone();
        eprintln!(
            "SOURCE_END source={} type={} locality={} next={:.17}",
            source_id,
            source_type.name(),
            locality,
            probe.random(),
        );
    }
}

fn observe_target(
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
    target_formation: Option<usize>,
    microzone: usize,
    time: f64,
    history: &mut Vec<ControlHistoryEntry>,
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
    let detection_draw = rng.random();
    let detected = detection_draw < probability;
    if std::env::var_os("PINELAND_PRF17_TRACE").is_some()
        && source_id == "C000038"
        && observer == crate::INSURGENT
        && (time - 49.0).abs() < 1.0e-9
    {
        eprintln!(
            "TARGET_C038 present={} personnel={:.17} probability={:.17} draw={:.17} detected={}",
            present, personnel, probability, detection_draw, detected,
        );
    }
    if std::env::var_os("PINELAND_INFO_TRACE").is_some() && time >= 0.5 {
        eprintln!(
            "INFO_TARGET_TRACE time={:.17} observer={} node={} source={} type={} locality={} target={} target_formation={:?} present={} personnel={:.17} probability={:.17} draw={:.17} detected={}",
            time,
            observer,
            observer_node,
            source_id,
            source_type.name(),
            locality,
            target,
            target_formation,
            present,
            personnel,
            probability,
            detection_draw,
            detected,
        );
    }

    // Source quality is sampled for negative reports too.  This seemingly
    // redundant draw is part of the Python observation contract.
    let quality = source_quality(particle, config, rng, source_type, locality);
    let confidence = if detected {
        config.information.positive_report_confidence
    } else {
        config.information.negative_report_confidence
    };
    let mut personnel_estimate = 0.0;
    let mut attribution_mistake = false;
    if detected {
        // Python evaluates the positive personnel-estimate expression before
        // replacing it with a false-positive draw.  Preserve that seemingly
        // redundant RNG draw: it is part of the continuation contract.
        personnel_estimate = personnel * (0.65 + 0.7 * rng.random());
        if present {
            attribution_mistake = rng.random() < config.information.attribution_error_rate;
        } else {
            personnel_estimate = rng.uniform(20.0, 250.0).max(1.0);
        }
    }
    if std::env::var_os("PINELAND_INFO_TRACE").is_some() && time >= 0.5 {
        let mut peek = rng.clone();
        eprintln!(
            "INFO_TARGET_FINAL time={:.17} observer={} source={} locality={} quality={:.17} estimate={:.17} next_draw={:.17}",
            time,
            observer,
            source_id,
            locality,
            quality,
            personnel_estimate,
            peek.random(),
        );
    }
    let reported_target = if attribution_mistake {
        if particle.organizations.kind.get(target).copied() == Some(3) {
            crate::GOVERNMENT
        } else {
            crate::INSURGENT
        }
    } else {
        target
    };
    let reported_formation = if attribution_mistake {
        None
    } else if target_formation.is_some() {
        if present && detected {
            actual_formation
        } else {
            target_formation
        }
    } else {
        None
    };
    let observation = publish_information_observation(
        particle,
        topology,
        config,
        observer,
        observer_node,
        source_id,
        source_type,
        0,
        Some(reported_target),
        reported_formation,
        locality,
        microzone,
        time,
        quality,
        confidence,
        [0.0; CONTROL_DIMENSIONS],
        0.0,
        if detected { 1.0 } else { 0.0 },
        personnel_estimate,
        probability,
        detected,
    );
    fuse_presence_observation(
        particle,
        topology,
        config,
        &observation,
        observer,
        observer_node,
        source_type,
        source_id,
        time,
        history,
    );
    append_history_entry(
        history,
        InformationHistoryEntry {
            target: observation.target,
            locality: observation.locality,
            observation_type: observation.observation_type,
            time: observation.time,
            source_identity: observation.source_identity,
        },
    );
    particle.counters.observations = particle.counters.observations.saturating_add(1);
    if std::env::var_os("PINELAND_PRF17_TRACE").is_some()
        && source_id == "C000038"
        && observer == crate::INSURGENT
        && (time - 49.0).abs() < 1.0e-9
    {
        let mut probe = rng.clone();
        eprintln!("TARGET_C038_END next={:.17}", probe.random());
    }
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
        1,
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
    if std::env::var_os("PINELAND_INFO_TRACE").is_some()
        && source_id == "C000069"
        && locality == 28
        && (time - 8.25).abs() < 1.0e-9
    {
        eprintln!(
            "NATIVE_CONTROL_PRE source={} type={} observer={} node={} target={} locality={} quality={:.17} trust={:.17} language={:.17} confidence={:.17} corr={:.17} weight={:.17} observed={:?} prior_conf={:.17} prior_updated={:.17} prior_contra={:.17}",
            source_id,
            source_type.name(),
            observer,
            observer_node,
            target,
            locality,
            quality,
            trust,
            language,
            confidence,
            corroboration,
            weight,
            observed,
            particle.beliefs.confidence[index],
            particle.beliefs.updated_at[index],
            particle.beliefs.contradiction[index],
        );
    }
    particle.beliefs.fuse_control(
        index,
        time,
        weight,
        &observed,
        config.information.contradiction_memory_days,
        config.information.contradiction_penalty,
    );
    if std::env::var_os("PINELAND_INFO_TRACE").is_some()
        && source_id == "C000069"
        && locality == 28
        && (time - 8.25).abs() < 1.0e-9
    {
        eprintln!(
            "NATIVE_CONTROL_POST source={} type={} observer={} confidence={:.17} updated={:.17} contra={:.17} evidence={}",
            source_id,
            source_type.name(),
            observer,
            particle.beliefs.confidence[index],
            particle.beliefs.updated_at[index],
            particle.beliefs.contradiction[index],
            particle.beliefs.evidence_count[index],
        );
    }

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
    if std::env::var_os("PINELAND_INFO_TRACE").is_some()
        && source_type != SourceType::Contact
        && locality == 28
        && time >= 0.0
    {
        eprintln!(
            "NATIVE_CONTROL_ID time={:.17} observer={} node={} source={} type={} identity={}",
            time,
            observer,
            observer_node,
            source_id,
            source_type.name(),
            source_identity,
        );
    }
    append_history_entry(
        history,
        ControlHistoryEntry {
            target: target as u32,
            locality: locality as u32,
            observation_type: 1,
            time,
            source_identity,
        },
    );
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
    if std::env::var_os("PINELAND_PRF17_TRACE").is_some()
        && source_id == "C000038"
        && observer == crate::INSURGENT
        && (time - 49.0).abs() < 1.0e-9
    {
        let mut probe = rng.clone();
        eprintln!("CONTROL_C038_END next={:.17}", probe.random());
    }
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
    // Python permits a stationary formation to publish through its historical
    // organization identity even after that organization has collapsed.  The
    // formation loop already owns the personnel/mobility eligibility check;
    // rejecting inactive observers here would suppress the report, consume a
    // different RNG suffix, and shift every later fusion in the event.
    if observer >= particle.organizations.kind.len() {
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
            || particle.formations.personnel[formation] <= 0.0
            || particle.formations.locality[formation] as usize != locality
            || particle.formations.moving[formation] != 0
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
        SourceType::Contact => 0.0,
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
    if particle.organizations.kind.get(organization).copied() == Some(crate::foreign::FOREIGN_KIND) {
        let org_name = crate::organization_name_for_particle(particle, organization);
        return format!("{}-01", org_name.to_ascii_uppercase());
    }
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

pub(crate) fn auxiliary_node_ids(particle: &ParticleState, topology: &StaticTopology) -> Vec<String> {
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
