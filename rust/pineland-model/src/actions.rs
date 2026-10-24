//! Belief-routed organized actions.
//!
//! Organized actions are deliberately event-local. A contact scan schedules
//! one event for one actor/locality pair; executing that event must consume the
//! same capacity, supply, and RNG sequence as Python's
//! `ProcessEngine.on_organized_action`. In particular, this module must not
//! loop over every locality when handling one scheduled action.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{python_exp, python_sum, PyRandomCompat};
use pineland_core::scheduler::EventPayload;
use pineland_core::state::{clamp01, ParticleState, CONTROL_DIMENSIONS};
use pineland_core::topology::StaticTopology;

const BELIEF_KIND_CONTROL: u8 = 2;
const PHYSICAL: usize = 1;
const ADMINISTRATIVE: usize = 2;
const FISCAL: usize = 4;
const SOCIAL: usize = 5;
const EXPECTED: usize = 6;

const WAIT: usize = 0;
const ARMED_CONFRONTATION: usize = 1;
const NONFIELDED_HUMAN_TARGET: usize = 2;
const ASSET_VIOLENCE: usize = 3;
const COERCION: usize = 4;
const ACCESS_RESTRICTION: usize = 5;

#[derive(Clone, Copy)]
struct HumanTarget {
    /// `true` for a pooled manpower row and `false` for a fixed security post.
    pooled: bool,
    index: usize,
    organization: usize,
    personnel: f64,
    available_fraction: f64,
}

fn action_organization(kind: u8) -> bool {
    // Python ACTION_ORGANIZATION_KINDS: insurgent, military, police, foreign.
    matches!(kind, 1 | 2 | 3 | 5 | 6 | 7)
}

fn is_insurgent(particle: &ParticleState, organization: usize) -> bool {
    organization == crate::INSURGENT
        || particle.organizations.kind.get(organization).copied() == Some(3)
}

fn observer_matches_organization(
    particle: &ParticleState,
    observer_code: u32,
    organization: usize,
) -> bool {
    if observer_code as usize == organization {
        return true;
    }
    let formation = observer_code as usize;
    let formation_start = particle.organizations.kind.len();
    let formation_index = formation.checked_sub(formation_start);
    formation_index
        .filter(|index| *index < particle.formations.organization.len())
        .is_some_and(|index| particle.formations.organization[index] as usize == organization)
}

fn target_matches_side(
    particle: &ParticleState,
    target: usize,
    target_side_insurgent: bool,
) -> bool {
    if target_side_insurgent {
        return target == crate::INSURGENT
            || particle.organizations.kind.get(target).copied() == Some(3);
    }
    matches!(
        particle.organizations.kind.get(target).copied(),
        Some(0 | 1 | 2 | 5)
    )
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

fn belief_control(
    particle: &ParticleState,
    observer: usize,
    target: usize,
    locality: usize,
    dimension: usize,
) -> f64 {
    let key = particle.beliefs.keys.iter().position(|key| {
        key.observer as usize == observer
            && key.target as usize == target
            && key.locality as usize == locality
            && key.kind == BELIEF_KIND_CONTROL
    });
    key.and_then(|index| {
        particle
            .beliefs
            .control
            .get(index * CONTROL_DIMENSIONS + dimension)
            .copied()
    })
    .unwrap_or(0.5)
}

fn has_target_evidence(
    particle: &ParticleState,
    observer: usize,
    target_side_insurgent: bool,
    locality: usize,
) -> bool {
    let control_evidence = particle
        .beliefs
        .keys
        .iter()
        .enumerate()
        .any(|(index, key)| {
            key.observer as usize == observer
                && key.locality as usize == locality
                && matches!(key.kind, 1 | 2)
                && particle
                    .beliefs
                    .evidence_count
                    .get(index)
                    .copied()
                    .unwrap_or(0)
                    > 0
                && target_matches_side(particle, key.target as usize, target_side_insurgent)
        });
    if control_evidence {
        return true;
    }
    [&particle.presence_beliefs, &particle.node_presence_beliefs]
        .iter()
        .any(|state| {
            state.keys.iter().enumerate().any(|(index, key)| {
                observer_matches_organization(particle, key.observer, observer)
                    && key.locality as usize == locality
                    && state.evidence_count.get(index).copied().unwrap_or(0) > 0
                    && target_matches_side(particle, key.target as usize, target_side_insurgent)
            })
        })
}

fn evidenced_hostile_physical(
    particle: &ParticleState,
    observer: usize,
    target_side_insurgent: bool,
    locality: usize,
) -> Option<f64> {
    particle
        .beliefs
        .keys
        .iter()
        .enumerate()
        .filter(|(index, key)| {
            key.observer as usize == observer
                && key.locality as usize == locality
                && key.kind == BELIEF_KIND_CONTROL
                && particle
                    .beliefs
                    .evidence_count
                    .get(*index)
                    .copied()
                    .unwrap_or(0)
                    > 0
                && target_matches_side(particle, key.target as usize, target_side_insurgent)
        })
        .map(|(index, _)| particle.beliefs.control[index * CONTROL_DIMENSIONS + PHYSICAL])
        .max_by(f64::total_cmp)
}

/// Highest evidenced presence-report estimate of the target side in a
/// locality, ignoring any control-based prior.
/// Reports are discounted by age, `exp(-age / report_decay_days)`, so a
/// sighting from weeks ago no longer draws strikes.
fn evidenced_presence(
    particle: &ParticleState,
    observer: usize,
    target_side_insurgent: bool,
    locality: usize,
    time: f64,
    report_decay_days: f64,
) -> Option<f64> {
    let mut evidenced = None;
    for state in [&particle.presence_beliefs, &particle.node_presence_beliefs] {
        for (index, key) in state.keys.iter().enumerate() {
            if observer_matches_organization(particle, key.observer, observer)
                && key.locality as usize == locality
                && state.evidence_count.get(index).copied().unwrap_or(0) > 0
                && target_matches_side(particle, key.target as usize, target_side_insurgent)
            {
                let age = (time - state.updated_at.get(index).copied().unwrap_or(time)).max(0.0);
                let value = clamp01(state.estimate[index])
                    * python_exp(-age / report_decay_days.max(1.0e-9));
                evidenced = Some(evidenced.map_or(value, |old: f64| old.max(value)));
            }
        }
    }
    evidenced
}

pub(crate) fn opponent_presence_belief(
    particle: &ParticleState,
    observer: usize,
    target_side_insurgent: bool,
    locality: usize,
) -> f64 {
    // Presence rows are kept separate from the control vector. Once such a
    // row has evidence, its estimate is authoritative even when it is zero;
    // otherwise use the actor's physical-control prior as Python does. Both
    // organization and field-node observations are decision-visible.
    let mut evidenced = None;
    for state in [&particle.presence_beliefs, &particle.node_presence_beliefs] {
        for (index, key) in state.keys.iter().enumerate() {
            if observer_matches_organization(particle, key.observer, observer)
                && key.locality as usize == locality
                && state.evidence_count.get(index).copied().unwrap_or(0) > 0
                && target_matches_side(particle, key.target as usize, target_side_insurgent)
            {
                let value = clamp01(state.estimate[index]);
                evidenced = Some(evidenced.map_or(value, |old: f64| old.max(value)));
            }
        }
    }
    evidenced.unwrap_or_else(|| {
        belief_control(
            particle,
            observer,
            if target_side_insurgent {
                crate::INSURGENT
            } else {
                crate::GOVERNMENT
            },
            locality,
            PHYSICAL,
        )
    })
}

fn locality_reach(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    organization: usize,
    source: usize,
    destination: usize,
    edge_cost: f64,
) -> f64 {
    if source == destination {
        return 1.0;
    }
    let infrastructure = (topology
        .locality_infrastructure
        .get(source)
        .copied()
        .unwrap_or(0.5)
        + topology
            .locality_infrastructure
            .get(destination)
            .copied()
            .unwrap_or(0.5))
        / 2.0;
    let terrain_cost = edge_cost.max(0.0);
    let distance_km = 18.0 + 22.0 * terrain_cost;
    let mobility = particle
        .organizations
        .mobility
        .get(organization)
        .copied()
        .unwrap_or(0.5);
    let speed = 42.0 * mobility.max(0.15) * infrastructure.max(0.2) / terrain_cost.max(0.5);
    let travel_hours = distance_km / speed.max(f64::MIN_POSITIVE);
    let restriction =
        crate::access::edge_restriction_level(particle, source, destination, Some(organization));
    let adjusted_hours =
        travel_hours * (1.0 + config.access_restriction.hostile_movement_penalty * restriction);
    python_exp(-adjusted_hours.max(0.0) / 24.0)
}

fn target_belief_weight(
    particle: &ParticleState,
    observer: usize,
    target_side_insurgent: bool,
    locality: usize,
    channel: usize,
) -> f64 {
    let target = if target_side_insurgent {
        crate::INSURGENT
    } else {
        crate::GOVERNMENT
    };
    match channel {
        NONFIELDED_HUMAN_TARGET => {
            (belief_control(particle, observer, target, locality, 0)
                + belief_control(particle, observer, target, locality, PHYSICAL))
                / 2.0
        }
        ASSET_VIOLENCE => {
            (belief_control(particle, observer, target, locality, ADMINISTRATIVE)
                + belief_control(particle, observer, target, locality, 3)
                + belief_control(particle, observer, target, locality, FISCAL))
                / 3.0
        }
        _ => 0.0,
    }
}

fn operational_target(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
    channel: usize,
    rng: &mut PyRandomCompat,
) -> Option<usize> {
    let target_side_insurgent = !is_insurgent(particle, organization);
    let mut candidates = Vec::new();
    candidates.push((locality, 1.0));
    let mut neighbors = topology
        .locality_edges
        .neighbors(locality)
        .collect::<Vec<_>>();
    // Python's operational_reach_candidates iterates sorted adjacency keys.
    // The topology graph preserves generation insertion order for civilian
    // mobility, so action targeting must sort its own view explicitly.
    neighbors.sort_by_key(|(destination, _)| *destination);
    for (destination, cost) in neighbors {
        candidates.push((
            destination as usize,
            locality_reach(
                particle,
                topology,
                config,
                organization,
                locality,
                destination as usize,
                cost,
            ),
        ));
    }
    let mut weights = Vec::with_capacity(candidates.len());
    for (index, (destination, reach)) in candidates.iter().copied().enumerate() {
        let available = index == 0
            || has_target_evidence(particle, organization, target_side_insurgent, destination);
        weights.push(if available {
            reach
                * target_belief_weight(
                    particle,
                    organization,
                    target_side_insurgent,
                    destination,
                    channel,
                )
        } else {
            0.0
        });
    }
    if weights.iter().sum::<f64>() <= 0.0 {
        return Some(locality);
    }
    let selected = rng
        .choices_indices(candidates.len(), Some(&weights), 1)
        .ok()?[0];
    Some(candidates[selected].0)
}

fn reachable_target_belief(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
    channel: usize,
) -> f64 {
    let target_side_insurgent = !is_insurgent(particle, organization);
    let source_weight = target_belief_weight(
        particle,
        organization,
        target_side_insurgent,
        locality,
        channel,
    );
    let mut best = source_weight;
    let mut neighbors = topology
        .locality_edges
        .neighbors(locality)
        .collect::<Vec<_>>();
    neighbors.sort_by_key(|(destination, _)| *destination);
    for (destination, cost) in neighbors {
        let destination = destination as usize;
        if !has_target_evidence(particle, organization, target_side_insurgent, destination) {
            continue;
        }
        let reach = locality_reach(
            particle,
            topology,
            config,
            organization,
            locality,
            destination,
            cost,
        );
        best = best.max(
            reach
                * target_belief_weight(
                    particle,
                    organization,
                    target_side_insurgent,
                    destination,
                    channel,
                ),
        );
    }
    clamp01(best)
}

/// True when the action layer runs the operational-reach armed channel.
///
/// `multichannel_v5` is the frozen Stage-4 architecture and is left
/// byte-identical. `multichannel_v6` lets an armed confrontation be launched
/// from a formation's locality into an adjacent locality where the actor holds
/// evidence of hostile presence, as a strike that returns to its origin.
fn operational_reach_enabled(config: &SimulationConfig) -> bool {
    config.combat.organized_action_architecture == "multichannel_v6"
}

/// The strongest staffed standalone (police-style) post of the opposing side
/// in a locality. Formation-attached posts are fought through their formation.
fn hostile_post(particle: &ParticleState, organization: usize, locality: usize) -> Option<usize> {
    let target_side_insurgent = !is_insurgent(particle, organization);
    let posts = &particle.security_posts;
    (0..posts.personnel.len())
        .filter(|&post| {
            posts.locality[post] as usize == locality
                && posts.staffed[post] != 0
                && posts.formation[post] == u32::MAX
                && posts.personnel[post] > 0.0
                && target_matches_side(particle, posts.organization[post] as usize, target_side_insurgent)
                && organizations_hostile(particle, organization, posts.organization[post] as usize)
        })
        .max_by(|a, b| posts.presence[*a].total_cmp(&posts.presence[*b]).then(b.cmp(a)))
}

fn hostile_post_presence(particle: &ParticleState, organization: usize, locality: usize) -> f64 {
    hostile_post(particle, organization, locality)
        .map_or(0.0, |post| clamp01(particle.security_posts.presence[post]))
}

/// Hostile presence the actor believes it can reach this interval: its own
/// locality, or an evidenced neighbor discounted by `locality_reach`. In v6 a
/// neighbor only counts when the actor holds actionable intelligence there
/// (see `actionable_hit_probability`) or a fixed hostile post is there, so the
/// armed channel is not chosen on stale or uncorroborated sightings.
#[allow(clippy::too_many_arguments)]
fn reachable_presence(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
    time: f64,
) -> f64 {
    let target_side_insurgent = !is_insurgent(particle, organization);
    let mut best =
        opponent_presence_belief(particle, organization, target_side_insurgent, locality).max(
            evidenced_hostile_physical(particle, organization, target_side_insurgent, locality)
                .unwrap_or(0.0),
        )
        .max(hostile_post_presence(particle, organization, locality));
    let mut neighbors = topology
        .locality_edges
        .neighbors(locality)
        .collect::<Vec<_>>();
    neighbors.sort_by_key(|(destination, _)| *destination);
    let prior = hostile_presence_prior(particle, topology, organization);
    for (destination, cost) in neighbors {
        let destination = destination as usize;
        let post = hostile_post_presence(particle, organization, destination);
        if post <= 0.0
            && !has_target_evidence(particle, organization, target_side_insurgent, destination)
        {
            continue;
        }
        let reach = locality_reach(
            particle,
            topology,
            config,
            organization,
            locality,
            destination,
            cost,
        );
        let formation = actionable_hit_probability(
            particle,
            topology,
            config,
            organization,
            destination,
            time,
            prior,
        );
        best = best.max(reach * formation.max(post));
    }
    clamp01(best)
}

/// Order-of-battle prior that a given locality hosts at least one hostile
/// formation: `N` active hostile formations spread over `K` localities gives
/// `1 - (1 - 1/K)^N`. Actors know roughly how many enemy formations exist,
/// not where they are.
fn hostile_presence_prior(
    particle: &ParticleState,
    topology: &StaticTopology,
    organization: usize,
) -> f64 {
    let localities = topology.locality_count().max(1) as f64;
    let f = &particle.formations;
    let hostile = (0..f.personnel.len())
        .filter(|&formation| {
            let target = f.organization[formation] as usize;
            f.personnel[formation] > 0.0
                && f.outside_pineland[formation] == 0
                && particle.organizations.active.get(target).copied() == Some(1)
                && organizations_hostile(particle, organization, target)
        })
        .count() as f64;
    (1.0 - (1.0 - 1.0 / localities).powf(hostile)).clamp(0.01, 0.95)
}

/// Believed probability that a strike into `locality` finds a hostile
/// formation, from the actor's own presence reports.
///
/// Each microzone starts at the order-of-battle prior (split so the locality
/// total equals `prior`). Every evidenced wildcard presence row the actor or
/// one of its formations holds for that microzone adds the log-likelihood
/// ratio of its estimate under the nominal source reliability
/// (`information.true_positive_rate` / `false_positive_rate`), weighted by
/// freshness `exp(-age / strike_report_decay_days)`, the expected dwell time
/// of a reported formation. The locality probability is the chance that at
/// least one microzone holds the enemy. A single uncorroborated positive
/// among fresh negative reports therefore stays unlikely, while repeated
/// independent sightings compound, as with the two-source rule for acting on
/// human intelligence.
fn strike_hit_probability(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
    time: f64,
    prior: f64,
) -> f64 {
    let target_side_insurgent = !is_insurgent(particle, organization);
    let start = topology
        .locality_zone_offsets
        .get(locality)
        .copied()
        .unwrap_or(0) as usize;
    let end = topology
        .locality_zone_offsets
        .get(locality + 1)
        .copied()
        .map_or(start + 1, |value| (value as usize).max(start + 1));
    let zones = end - start;
    let primary = topology
        .primary_zone
        .get(locality)
        .map_or(0, |zone| (*zone as usize).saturating_sub(start).min(zones - 1));
    let prior = prior.clamp(1.0e-6, 1.0 - 1.0e-6);
    let zone_prior = 1.0 - (1.0 - prior).powf(1.0 / zones as f64);
    let base = (zone_prior / (1.0 - zone_prior)).ln();
    let tpr = config.information.true_positive_rate.clamp(0.01, 0.99);
    let fpr = config.information.false_positive_rate.clamp(1.0e-4, tpr - 1.0e-3);
    let positive = (tpr / fpr).ln();
    let negative = ((1.0 - tpr) / (1.0 - fpr)).ln();
    let decay = config.combat.strike_report_decay_days.max(1.0e-9);
    let mut evidence = vec![0.0; zones];
    for state in [&particle.presence_beliefs, &particle.node_presence_beliefs] {
        for (index, key) in state.keys.iter().enumerate() {
            if key.locality as usize != locality
                || key.target_formation != u32::MAX
                || state.evidence_count.get(index).copied().unwrap_or(0) == 0
                || !observer_matches_organization(particle, key.observer, organization)
                || !target_matches_side(particle, key.target as usize, target_side_insurgent)
            {
                continue;
            }
            let zone = (key.microzone as usize)
                .checked_sub(start)
                .filter(|zone| *zone < zones)
                .unwrap_or(primary);
            let age = (time - state.updated_at.get(index).copied().unwrap_or(time)).max(0.0);
            let estimate = clamp01(state.estimate[index]);
            evidence[zone] += python_exp(-age / decay)
                * (estimate * positive + (1.0 - estimate) * negative);
        }
    }
    let miss = evidence
        .iter()
        .map(|log_ratio| 1.0 - 1.0 / (1.0 + python_exp(-(base + log_ratio))))
        .product::<f64>();
    clamp01(1.0 - miss)
}

/// The hit probability of a formation strike into `locality`, or zero when
/// launching is not worth it: the actor's intelligence must raise the odds
/// above the order-of-battle prior, and the expected value of the strike,
/// `p * gain - (1 - p) * dry-hole loss`, must be non-negative, i.e.
/// `p >= combat.strike_min_hit_probability`.
fn actionable_hit_probability(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
    time: f64,
    prior: f64,
) -> f64 {
    let probability =
        strike_hit_probability(particle, topology, config, organization, locality, time, prior);
    if probability > prior && probability >= config.combat.strike_min_hit_probability {
        probability
    } else {
        0.0
    }
}

/// Pick the locality an armed strike is aimed at. Candidates are fixed hostile
/// posts (known, predictable targets) and neighbors where the actor holds
/// actionable intelligence of an enemy formation, weighted by reach times hit
/// probability. The returned edge cost is zero for the source locality.
fn armed_strike_target(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
    time: f64,
    rng: &mut PyRandomCompat,
) -> Option<(usize, f64)> {
    let target_side_insurgent = !is_insurgent(particle, organization);
    let mut neighbors = topology
        .locality_edges
        .neighbors(locality)
        .collect::<Vec<_>>();
    neighbors.sort_by_key(|(destination, _)| *destination);
    let mut candidates = Vec::new();
    let mut weights = Vec::new();
    let local_post = hostile_post_presence(particle, organization, locality);
    if local_post > 0.0 {
        candidates.push((locality, 0.0));
        weights.push(local_post);
    }
    let prior = hostile_presence_prior(particle, topology, organization);
    for (destination, cost) in neighbors {
        let destination = destination as usize;
        let post = hostile_post_presence(particle, organization, destination);
        if post <= 0.0
            && !has_target_evidence(particle, organization, target_side_insurgent, destination)
        {
            continue;
        }
        let reach = locality_reach(
            particle,
            topology,
            config,
            organization,
            locality,
            destination,
            cost,
        );
        // Strike a formation only on actionable presence reports, never on a
        // control prior or a stale or uncorroborated sighting.
        let formation = actionable_hit_probability(
            particle,
            topology,
            config,
            organization,
            destination,
            time,
            prior,
        );
        let weight = reach * formation.max(post);
        if weight > 0.0 {
            candidates.push((destination, cost));
            weights.push(weight);
        }
    }
    if candidates.is_empty() {
        return None;
    }
    let selected = rng
        .choices_indices(candidates.len(), Some(&weights), 1)
        .ok()?[0];
    Some(candidates[selected])
}

/// Trace-only (`PINELAND_FUNNEL`) description of the intelligence behind a
/// strike: hit probability, the freshest best presence row, the last positive
/// report (`pos_p` is that report's detection probability; ~0.04 marks a
/// false positive), and how many hostile formations left the target since.
fn strike_intel_trace(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    organization: usize,
    target: usize,
    time: f64,
) -> String {
    let side = !is_insurgent(particle, organization);
    let decay = config.combat.strike_report_decay_days.max(1.0e-9);
    let mut best: Option<(f64, f64, f64, f64, u32)> = None;
    for state in [&particle.presence_beliefs, &particle.node_presence_beliefs] {
        for (index, key) in state.keys.iter().enumerate() {
            if observer_matches_organization(particle, key.observer, organization)
                && key.locality as usize == target
                && state.evidence_count[index] > 0
                && target_matches_side(particle, key.target as usize, side)
            {
                let age = (time - state.updated_at[index]).max(0.0);
                let value = clamp01(state.estimate[index]) * python_exp(-age / decay);
                if best.map_or(true, |b| value > b.0) {
                    best = Some((
                        value,
                        age,
                        state.estimate[index],
                        state.confidence[index],
                        state.evidence_count[index],
                    ));
                }
            }
        }
    }
    let last_positive = particle
        .information_observations
        .iter()
        .rev()
        .find(|o| {
            o.observation_type == 0
                && o.detected == 1
                && o.locality as usize == target
                && o.observer as usize == organization
                && target_matches_side(particle, o.target as usize, side)
        })
        .map(|o| (o.time, o.source_type, o.detection_probability));
    let since = last_positive.map_or(time - decay, |p| p.0);
    let f = &particle.formations;
    let moved_away = (0..f.personnel.len())
        .filter(|&x| {
            f.personnel[x] > 0.0
                && f.movement_origin.get(x).copied() == Some(target as u32)
                && f.movement_execute_at.get(x).copied().unwrap_or(-1.0) >= since - 0.25
                && f.locality[x] as usize != target
                && organizations_hostile(particle, organization, f.organization[x] as usize)
        })
        .count();
    let prior = hostile_presence_prior(particle, topology, organization);
    let p_hit = strike_hit_probability(particle, topology, config, organization, target, time, prior);
    let (value, age, estimate, confidence, evidence) = best.unwrap_or((0.0, -1.0, 0.0, 0.0, 0));
    format!(
        "side={} p_hit={:.3} prior={:.3} value={:.3} age={:.2} est={:.3} conf={:.3} ev={} pos_age={:.2} pos_src={} pos_p={:.3} moved_away={}",
        if is_insurgent(particle, organization) { "ins" } else { "gov" },
        p_hit,
        prior,
        value,
        age,
        estimate,
        confidence,
        evidence,
        last_positive.map_or(-1.0, |p| time - p.0),
        last_positive.map_or(255, |p| p.1),
        last_positive.map_or(-1.0, |p| p.2),
        moved_away
    )
}

/// v6 only: a strike that sweeps a locality and finds no opponent is itself a
/// strong negative presence report. It is fused (weight
/// `combat.strike_dry_hole_downgrade`) into every presence row the actor and
/// its formations hold for that locality, refreshing their timestamps, so the
/// failed sweep keeps outweighing a later single uncorroborated sighting
/// instead of being erased by it.
fn downgrade_presence_belief(
    particle: &mut ParticleState,
    config: &SimulationConfig,
    observer: usize,
    target_side_insurgent: bool,
    locality: usize,
    time: f64,
) {
    let weight = config.combat.strike_dry_hole_downgrade.clamp(0.0, 1.0);
    if weight <= 0.0 {
        return;
    }
    for node in [false, true] {
        let matches = {
            let state = if node {
                &particle.node_presence_beliefs
            } else {
                &particle.presence_beliefs
            };
            state
                .keys
                .iter()
                .enumerate()
                .filter(|(_, key)| {
                    observer_matches_organization(particle, key.observer, observer)
                        && key.locality as usize == locality
                        && target_matches_side(particle, key.target as usize, target_side_insurgent)
                })
                .map(|(index, _)| index)
                .collect::<Vec<_>>()
        };
        let state = if node {
            &mut particle.node_presence_beliefs
        } else {
            &mut particle.presence_beliefs
        };
        for index in matches {
            state.fuse(
                index,
                time,
                weight,
                0.0,
                0.0,
                config.information.contradiction_memory_days,
                config.information.contradiction_penalty,
            );
        }
    }
}

/// v6 only: what a dry hole still yields. Residents questioned during the
/// sweep may say where an enemy formation that recently left went. With
/// probability equal to the locality's cooperation with the actor (government
/// cooperation, or insurgent sympathy for insurgents), the most recent such
/// departure becomes a fresh presence report on the formation's current
/// locality. Returns that locality when a lead was produced.
fn sweep_exploitation_lead(
    particle: &mut ParticleState,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    organization: usize,
    locality: usize,
    time: f64,
) -> Option<usize> {
    let insurgent = is_insurgent(particle, organization);
    let communities = &particle.communities;
    let (sum, count) = (0..communities.locality.len())
        .filter(|&community| communities.locality[community] as usize == locality)
        .fold((0.0, 0usize), |(sum, count), community| {
            let value = if insurgent {
                communities.insurgent_sympathy.get(community)
            } else {
                communities.government_cooperation.get(community)
            };
            (sum + clamp01(value.copied().unwrap_or(0.0)), count + 1)
        });
    if count == 0 {
        return None;
    }
    let cooperation = sum / count as f64;
    let window = config.combat.strike_report_decay_days.max(0.0);
    let f = &particle.formations;
    let departed = (0..f.personnel.len())
        .filter(|&formation| {
            let target = f.organization[formation] as usize;
            f.personnel[formation] > 0.0
                && f.outside_pineland[formation] == 0
                && f.locality[formation] as usize != locality
                && f.movement_origin.get(formation).copied() == Some(locality as u32)
                && f.movement_execute_at.get(formation).copied().unwrap_or(f64::NEG_INFINITY)
                    >= time - window
                && particle.organizations.active.get(target).copied() == Some(1)
                && organizations_hostile(particle, organization, target)
        })
        .max_by(|a, b| {
            f.movement_execute_at[*a]
                .total_cmp(&f.movement_execute_at[*b])
                .then(b.cmp(a))
        })?;
    if rng.random() >= cooperation {
        return None;
    }
    let key = pineland_core::state::PresenceKey {
        observer: organization as u32,
        target: particle.formations.organization[departed],
        locality: particle.formations.locality[departed],
        microzone: particle.formations.microzone[departed],
        target_formation: u32::MAX,
    };
    let destination = key.locality as usize;
    let personnel = particle.formations.personnel[departed];
    let state = &mut particle.presence_beliefs;
    let index = state.ensure_key(key);
    if state.confidence[index] == 0.0 && state.evidence_count[index] == 0 {
        state.confidence[index] = config.information.prior_confidence;
    }
    state.fuse(
        index,
        time,
        config.information.positive_report_confidence * cooperation,
        1.0,
        personnel,
        config.information.contradiction_memory_days,
        config.information.contradiction_penalty,
    );
    Some(destination)
}

fn bump_event(particle: &mut ParticleState, name: &str) {
    *particle
        .counters
        .event_counts
        .entry(name.to_string())
        .or_insert(0) += 1;
}

fn local_information(
    particle: &ParticleState,
    topology: &StaticTopology,
    organization: usize,
    locality: usize,
    target: usize,
) -> f64 {
    let target_is_security = matches!(
        particle.organizations.kind.get(target).copied(),
        Some(0 | 1 | 2 | 5)
    );
    let belief_target_matches = |candidate: usize| {
        candidate == target || (target_is_security && candidate == crate::GOVERNMENT)
    };
    let mut evidence: f64 = 0.0;
    for (index, key) in particle.beliefs.keys.iter().enumerate() {
        if key.observer as usize != organization
            || key.locality as usize != locality
            || !belief_target_matches(key.target as usize)
            || particle
                .beliefs
                .evidence_count
                .get(index)
                .copied()
                .unwrap_or(0)
                == 0
        {
            continue;
        }
        if key.kind == BELIEF_KIND_CONTROL {
            let offset = index * CONTROL_DIMENSIONS;
            let signal = particle.beliefs.control[offset]
                .max(particle.beliefs.control[offset + PHYSICAL])
                .max(particle.beliefs.control[offset + ADMINISTRATIVE]);
            evidence = evidence.max(particle.beliefs.confidence[index].clamp(0.0, 1.0) * signal);
        }
    }
    for state in [&particle.presence_beliefs, &particle.node_presence_beliefs] {
        for (index, key) in state.keys.iter().enumerate() {
            if observer_matches_organization(particle, key.observer, organization)
                && key.locality as usize == locality
                && state.evidence_count.get(index).copied().unwrap_or(0) > 0
                && belief_target_matches(key.target as usize)
            {
                evidence = evidence.max(
                    state.confidence[index].clamp(0.0, 1.0) * state.estimate[index].clamp(0.0, 1.0),
                );
            }
        }
    }
    // `topology` is part of the signature so this helper can later include
    // formation/locality observer rows without changing the action API.
    let _ = topology;
    evidence
}

fn apply_human_target_losses(
    particle: &mut ParticleState,
    target: HumanTarget,
    losses: f64,
) -> f64 {
    let losses = losses.max(0.0).min(target.personnel);
    if target.pooled {
        let available = particle.manpower.pool[target.index].max(0.0);
        let realized = losses.min(available);
        let remaining = available - realized;
        particle.manpower.pool[target.index] = remaining;
        let reserve = particle.manpower.supply_reserve[target.index].max(0.0);
        if available > 0.0 && reserve > 0.0 && realized > 0.0 {
            let lost_supply = reserve * (realized / available);
            particle.manpower.supply_reserve[target.index] = (reserve - lost_supply).max(0.0);
            particle.logistics.cumulative_lost += lost_supply;
        }
        realized
    } else {
        let available = particle.security_posts.personnel[target.index].max(0.0);
        let realized = losses.min(available);
        particle.security_posts.personnel[target.index] = available - realized;
        realized
    }
}

fn local_execution_knowledge(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
    target: usize,
) -> f64 {
    let embedded = crate::organizations::local_embeddedness(
        particle,
        topology,
        config,
        organization,
        locality,
    );
    let information = local_information(particle, topology, organization, locality, target);
    let persistent = if organization == crate::INSURGENT {
        let count = particle.locality.population.len().max(1);
        let index = organization * count + locality;
        if particle
            .footholds
            .renewal_count
            .get(index)
            .copied()
            .unwrap_or(0)
            > 0
        {
            particle
                .footholds
                .strength
                .get(index)
                .copied()
                .unwrap_or(0.0)
        } else {
            0.0
        }
    } else {
        0.0
    };
    let local_access = 1.0
        - (1.0 - embedded.clamp(0.0, 1.0))
            * (1.0 - information.clamp(0.0, 1.0))
            * (1.0 - persistent.clamp(0.0, 1.0));
    let general = particle
        .organizations
        .local_knowledge
        .get(organization)
        .copied()
        .unwrap_or(0.0)
        .clamp(0.0, 1.0);
    (general * local_access.clamp(0.0, 1.0))
        .sqrt()
        .clamp(0.0, 1.0)
}

fn nonfielded_human_targets(
    particle: &ParticleState,
    organization: usize,
    locality: usize,
) -> Vec<HumanTarget> {
    let mut targets = Vec::new();
    // Python sorts manpower-pool keys before appending fixed-post targets.
    // Native initialization currently has no pooled rows, but sorting the
    // numeric identity here keeps the serialization contract deterministic for
    // later empirical/SMC configurations as well.
    let mut pools = (0..particle.manpower.pool.len())
        .filter(|&index| {
            let target = particle.manpower.organization[index] as usize;
            particle.manpower.locality[index] as usize == locality
                && target != organization
                && particle.manpower.pool[index] > 0.0
                && particle.organizations.active.get(target).copied() == Some(1)
                && organizations_hostile(particle, organization, target)
        })
        .collect::<Vec<_>>();
    pools.sort_by_key(|&index| {
        (
            particle.manpower.organization[index] as usize,
            particle.manpower.locality[index] as usize,
        )
    });
    for index in pools {
        let target = particle.manpower.organization[index] as usize;
        targets.push(HumanTarget {
            pooled: true,
            index,
            organization: target,
            personnel: particle.manpower.pool[index].max(0.0),
            available_fraction: 1.0,
        });
    }
    for index in 0..particle.security_posts.organization.len() {
        let target = particle.security_posts.organization[index] as usize;
        if crate::trace_env!("PINELAND_ACTION_TRACE")
            && particle.security_posts.locality[index] as usize == locality
        {
            eprintln!(
                "ACTION human_post index={} target={} formation={} personnel={:.17} active={} hostile={}",
                index,
                target,
                particle.security_posts.formation[index],
                particle.security_posts.personnel[index],
                particle.organizations.active.get(target).copied().unwrap_or(0),
                organizations_hostile(particle, organization, target),
            );
        }
        if particle.security_posts.locality[index] as usize != locality
            || particle.security_posts.formation[index] != u32::MAX
            || particle.security_posts.personnel[index] <= 0.0
            || particle.organizations.active.get(target).copied() != Some(1)
            || !organizations_hostile(particle, organization, target)
        {
            continue;
        }
        targets.push(HumanTarget {
            pooled: false,
            index,
            organization: target,
            personnel: particle.security_posts.personnel[index].max(0.0),
            available_fraction: particle.security_posts.available_fraction[index].clamp(0.0, 1.0),
        });
    }
    targets
}

pub(crate) fn local_fighter_equivalents(
    particle: &ParticleState,
    organization: usize,
    locality: usize,
    config: &SimulationConfig,
) -> (f64, f64) {
    let supply_per_fighter = (config.logistics.formation_supply_days
        * config.logistics.initial_supply_fraction)
        .max(1e-12);
    let mut pooled = 0.0;
    let mut reserve = 0.0;
    for index in 0..particle.manpower.pool.len() {
        if particle
            .manpower
            .organization
            .get(index)
            .copied()
            .unwrap_or(u32::MAX) as usize
            == organization
            && particle
                .manpower
                .locality
                .get(index)
                .copied()
                .unwrap_or(u32::MAX) as usize
                == locality
        {
            pooled += particle.manpower.pool[index].max(0.0);
            reserve += particle.manpower.supply_reserve[index].max(0.0);
        }
    }
    let unfielded = pooled.min(reserve / supply_per_fighter);
    // Python's local_fighter_equivalents intentionally uses personnel, not
    // effective/readiness-adjusted personnel, and only excludes moving or
    // outside-Pineland formations.
    let fielded_values = (0..particle.formations.personnel.len())
        .filter(|&formation| {
            particle.formations.organization[formation] as usize == organization
                && particle.formations.locality[formation] as usize == locality
                && particle.formations.outside_pineland[formation] == 0
                && particle.formations.moving[formation] == 0
        })
        .map(|formation| particle.formations.personnel[formation].max(0.0))
        .collect::<Vec<_>>();
    let fielded = python_sum(&fielded_values);
    (unfielded, fielded)
}

pub(crate) fn committed_fighter_equivalents(
    particle: &ParticleState,
    organization: usize,
    locality: usize,
    config: &SimulationConfig,
) -> f64 {
    let (unfielded, fielded) = local_fighter_equivalents(particle, organization, locality, config);
    let total = unfielded + fielded;
    if total <= 0.0 {
        return 0.0;
    }
    let minimum = config
        .organization_ecology
        .minimum_formation_personnel
        .max(1e-9);
    total * (total / (total + minimum))
}

/// Insurgent operational tempo multiplier (multichannel_v6). Insurgents press
/// harder when the balance of fielded strength moves their way and once the
/// government's external air support has actually stopped (as the Taliban
/// offensive did in 2021); they husband forces when losing. Bounded to
/// [0.5, 2.5]; exactly 1 for non-insurgents, v5, or zero sensitivity.
pub fn insurgent_tempo(particle: &ParticleState, config: &SimulationConfig, organization: usize) -> f64 {
    let sensitivity = config.combat.insurgent_tempo_sensitivity;
    if sensitivity == 0.0
        || config.combat.organized_action_architecture != "multichannel_v6"
        || particle.organizations.kind.get(organization).copied() != Some(3)
    {
        return 1.0;
    }
    let momentum = crate::defection::national_momentum(particle);
    let air = &config.partner_force_support;
    let air_gone = air.enabled
        && air.air.enabled
        && crate::partner_channel_withdrawn(particle, config, crate::SupportChannel::Air);
    (1.0 + sensitivity * (2.0 * (momentum - 0.5) + if air_gone { 0.3 } else { 0.0 }))
        .clamp(0.5, 2.5)
}

pub fn action_attempt_hazard(
    particle: &ParticleState,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
) -> f64 {
    if organization >= particle.organizations.active.len()
        || locality >= particle.locality.population.len()
        || particle.organizations.active[organization] == 0
        || !action_organization(particle.organizations.kind[organization])
    {
        return 0.0;
    }
    let committed = committed_fighter_equivalents(particle, organization, locality, config);
    let minimum = config
        .organization_ecology
        .minimum_formation_personnel
        .max(1e-9);
    (config.organized_action_rate.max(0.0) * committed / minimum
        * insurgent_tempo(particle, config, organization))
    .max(0.0)
}

pub fn action_attempt_probability(
    particle: &ParticleState,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
    interval_days: f64,
) -> f64 {
    let hazard =
        action_attempt_hazard(particle, config, organization, locality) * interval_days.max(0.0);
    // `expm1` is evaluated at the negative hazard: 1 - exp(-h) is
    // numerically stable for both very small and very large exposures.
    clamp01(-(-hazard).exp_m1())
}

fn local_supply_available(particle: &ParticleState, organization: usize, locality: usize) -> f64 {
    let formations = (0..particle.formations.personnel.len())
        .filter(|&formation| {
            particle.formations.organization[formation] as usize == organization
                && particle.formations.locality[formation] as usize == locality
                && particle.formations.outside_pineland[formation] == 0
                && particle.formations.moving[formation] == 0
        })
        .map(|formation| particle.formations.supply_stock[formation].max(0.0))
        .sum::<f64>();
    let sources = (0..particle.logistics.source_stock.len())
        .filter(|&source| {
            particle.logistics.organization[source] as usize == organization
                && particle.logistics.locality[source] as usize == locality
        })
        .map(|source| particle.logistics.source_stock[source].max(0.0))
        .sum::<f64>();
    let reserves = (0..particle.manpower.pool.len())
        .filter(|&index| {
            particle.manpower.organization[index] as usize == organization
                && particle.manpower.locality[index] as usize == locality
        })
        .map(|index| particle.manpower.supply_reserve[index].max(0.0))
        .sum::<f64>();
    formations + sources + reserves
}

fn consume_local_supply(
    particle: &mut ParticleState,
    organization: usize,
    locality: usize,
    demand: f64,
) -> (f64, f64) {
    let mut remaining = demand.max(0.0);
    let demanded = remaining;
    let mut consumed = 0.0;

    // Formation IDs are lexical in the Python implementation and native
    // initialization uses the same lexical row order, so ascending indices
    // are the canonical consumption order.
    for formation in 0..particle.formations.personnel.len() {
        if remaining <= 0.0
            || particle.formations.organization[formation] as usize != organization
            || particle.formations.locality[formation] as usize != locality
            || particle.formations.outside_pineland[formation] != 0
            || particle.formations.moving[formation] != 0
        {
            continue;
        }
        let take = particle.formations.supply_stock[formation]
            .max(0.0)
            .min(remaining);
        if crate::trace_env!("PINELAND_LOGISTICS_FORMATION_TRACE") && formation == 7 {
            eprintln!(
                "ACTION_SUPPLY_CONSUME time=unknown formation=7 demand={:.17} remaining={:.17} take={:.17} before={:.17} bits={}",
                demanded,
                remaining,
                take,
                particle.formations.supply_stock[formation],
                particle.formations.supply_stock[formation].to_bits()
            );
        }
        particle.formations.supply_stock[formation] -= take;
        if crate::trace_env!("PINELAND_LOGISTICS_FORMATION_TRACE") && formation == 7 {
            eprintln!(
                "ACTION_SUPPLY_CONSUMED formation=7 after={:.17} bits={}",
                particle.formations.supply_stock[formation],
                particle.formations.supply_stock[formation].to_bits()
            );
        }
        particle.formations.sustainment[formation] = particle.formations.supply_fraction(formation);
        consumed += take;
        remaining -= take;
    }
    for source in 0..particle.logistics.source_stock.len() {
        if remaining <= 0.0
            || particle.logistics.organization[source] as usize != organization
            || particle.logistics.locality[source] as usize != locality
        {
            continue;
        }
        let take = particle.logistics.source_stock[source]
            .max(0.0)
            .min(remaining);
        particle.logistics.source_stock[source] -= take;
        consumed += take;
        remaining -= take;
    }
    for index in 0..particle.manpower.pool.len() {
        if remaining <= 0.0
            || particle.manpower.organization[index] as usize != organization
            || particle.manpower.locality[index] as usize != locality
        {
            continue;
        }
        let take = particle.manpower.supply_reserve[index]
            .max(0.0)
            .min(remaining);
        particle.manpower.supply_reserve[index] -= take;
        consumed += take;
        remaining -= take;
    }
    particle.logistics.cumulative_consumed += consumed;
    (consumed, (demanded - consumed).max(0.0))
}

fn control_weights(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
    unfielded: f64,
    fielded: f64,
    time: f64,
) -> [f64; 6] {
    let total = unfielded + fielded;
    if total <= 0.0 {
        return [1.0, 0.0, 0.0, 0.0, 0.0, 0.0];
    }
    let insurgent = is_insurgent(particle, organization);
    let target = if insurgent {
        crate::GOVERNMENT
    } else {
        crate::INSURGENT
    };
    let physical = belief_control(particle, organization, target, locality, PHYSICAL);
    let social = belief_control(particle, organization, target, locality, SOCIAL);
    let perceived_presence = if operational_reach_enabled(config) {
        reachable_presence(particle, topology, config, organization, locality, time)
    } else {
        opponent_presence_belief(particle, organization, !insurgent, locality).max(
            evidenced_hostile_physical(particle, organization, !insurgent, locality).unwrap_or(0.0),
        )
    };
    let risk = particle.organizations.phenotype[organization * 8 + 4].clamp(0.0, 1.0);
    let governance = particle.organizations.phenotype[organization * 8 + 2].clamp(0.0, 1.0);
    let fielded_share = (fielded / total).clamp(0.0, 1.0);
    let (human_target_belief, asset_weight, coercion_weight) = if insurgent {
        // Python's action-choice contract lets persistent local foothold
        // memory supplement current embeddedness.  This affects only the
        // channel weights; it does not create fighters or alter the
        // execution-capacity calculation.
        let embedded = crate::organizations::local_embeddedness(
            particle,
            topology,
            config,
            organization,
            locality,
        )
        .max(crate::organizations::local_foothold_strength(
            particle,
            topology,
            organization,
            locality,
        ));
        (
            reachable_target_belief(
                particle,
                topology,
                config,
                organization,
                locality,
                NONFIELDED_HUMAN_TARGET,
            ),
            risk * reachable_target_belief(
                particle,
                topology,
                config,
                organization,
                locality,
                ASSET_VIOLENCE,
            ),
            governance * embedded,
        )
    } else {
        (((physical + social) / 2.0).clamp(0.0, 1.0), 0.0, 0.0)
    };
    let access_weight = if config.access_restriction.enabled {
        (0.35 + 0.65 * governance) * fielded_share * (0.5 + 0.5 * risk)
    } else {
        0.0
    };
    [
        1.0,
        risk * fielded_share * perceived_presence,
        risk * human_target_belief,
        asset_weight,
        coercion_weight,
        access_weight,
    ]
}

fn access_destination(
    particle: &ParticleState,
    topology: &StaticTopology,
    organization: usize,
    locality: usize,
    rng: &mut PyRandomCompat,
) -> Option<usize> {
    let target = if particle.organizations.kind[organization] as usize == crate::INSURGENT {
        crate::GOVERNMENT
    } else {
        crate::INSURGENT
    };
    let mut candidates = topology
        .locality_edges
        .neighbors(locality)
        .collect::<Vec<_>>();
    // Python's access-restriction branch sorts locality IDs before drawing.
    // Do not reuse the insertion-ordered mobility adjacency here.
    candidates.sort_by_key(|(destination, _)| *destination);
    if candidates.is_empty() {
        return None;
    }
    let weights = candidates
        .iter()
        .map(|(destination, cost)| {
            let destination = *destination as usize;
            let strategic = (belief_control(particle, organization, target, destination, PHYSICAL)
                + belief_control(particle, organization, target, destination, EXPECTED)
                + belief_control(particle, organization, target, destination, FISCAL))
                / 3.0;
            (strategic - *cost).clamp(-8.0, 8.0).exp()
        })
        .collect::<Vec<_>>();
    let selected = rng
        .choices_indices(candidates.len(), Some(&weights), 1)
        .ok()?[0];
    Some(candidates[selected].0 as usize)
}

/// Execute one scheduled organized-action event for the supplied actor and
/// locality. The caller owns the process RNG stream and records it after the
/// call. The function intentionally has no all-locality loop: a single
/// scheduler payload is one opportunity.
pub fn opportunities(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    _time: f64,
    organization: usize,
    locality: usize,
    interval_days: f64,
) {
    let trace = crate::trace_env!("PINELAND_ACTION_TRACE");
    if trace && organization == crate::INSURGENT && locality == 32 {
        eprintln!(
            "ACTION relation_debug {:?}",
            particle
                .relations
                .organization_a
                .iter()
                .zip(&particle.relations.organization_b)
                .zip(&particle.relations.status)
                .filter(|((a, b), _)| {
                    (**a as usize == organization && **b as usize == crate::POLICE)
                        || (**b as usize == organization && **a as usize == crate::POLICE)
                })
                .map(|((a, b), status)| (*a, *b, *status))
                .collect::<Vec<_>>()
        );
    }
    if !config.include_insurgency
        || organization >= particle.organizations.active.len()
        || locality >= topology.locality_count()
        || particle.organizations.active[organization] == 0
        || !action_organization(particle.organizations.kind[organization])
    {
        return;
    }
    let (unfielded, fielded) = local_fighter_equivalents(particle, organization, locality, config);
    let total = unfielded + fielded;
    if total <= 0.0 {
        return;
    }
    let probability =
        action_attempt_probability(particle, config, organization, locality, interval_days);
    let attempt_draw = rng.random();
    let funnel = crate::trace_env!("PINELAND_FUNNEL");
    if funnel {
        eprintln!(
            "FUNNEL t={:.3} org={} loc={} stage=opportunity unfielded={:.3} fielded={:.3} p={:.6} attempted={}",
            _time, organization, locality, unfielded, fielded, probability, (attempt_draw < probability) as u8
        );
    }
    if trace {
        eprintln!(
            "ACTION before time={:.17} org={} loc={} interval={:.17} total={:.17} committed={:.17} probability={:.17} draw={:.17}",
            _time,
            organization,
            locality,
            interval_days,
            total,
            committed_fighter_equivalents(particle, organization, locality, config),
            probability,
            attempt_draw
        );
    }
    if attempt_draw >= probability {
        return;
    }

    let mut weights = control_weights(
        particle,
        topology,
        config,
        organization,
        locality,
        unfielded,
        fielded,
        _time,
    );
    if topology.locality_edges.neighbors(locality).next().is_none() {
        weights[ACCESS_RESTRICTION] = 0.0;
    }
    let channel = match rng.choices_indices(6, Some(&weights), 1) {
        Ok(values) => values[0],
        Err(_) => WAIT,
    };
    if trace {
        eprintln!(
            "ACTION choice org={} loc={} weights={:?} channel={}",
            organization, locality, weights, channel
        );
    }
    if funnel {
        eprintln!(
            "FUNNEL t={:.3} org={} loc={} stage=channel channel={} w={:.4},{:.4},{:.4},{:.4},{:.4},{:.4}",
            _time, organization, locality, channel, weights[0], weights[1], weights[2], weights[3], weights[4], weights[5]
        );
    }
    if channel == WAIT {
        return;
    }

    particle.counters.organized_actions = particle.counters.organized_actions.saturating_add(1);

    let committed = committed_fighter_equivalents(particle, organization, locality, config);
    if channel == ACCESS_RESTRICTION {
        let Some(destination) = access_destination(particle, topology, organization, locality, rng)
        else {
            return;
        };
        let minimum = config
            .organization_ecology
            .minimum_formation_personnel
            .max(1e-12);
        let capacity = (committed / (committed + minimum)).clamp(0.0, 1.0);
        let demand = committed
            * config.logistics.presence_consumption_per_person_day
            * interval_days.max(1e-9);
        let available = local_supply_available(particle, organization, locality);
        let (consumed, unmet) = consume_local_supply(particle, organization, locality, demand);
        let supply_fraction = if demand > 0.0 {
            (consumed / demand).clamp(0.0, 1.0)
        } else {
            1.0
        };
        let effort = capacity * supply_fraction;
        if trace {
            eprintln!(
                "ACTION access org={} loc={} destination={} committed={:.17} capacity={:.17} demand={:.17} available={:.17} consumed={:.17} unmet={:.17} effort={:.17}",
                organization, locality, destination, committed, capacity, demand, available, consumed, unmet, effort
            );
        }
        if effort > 0.0 {
            let _level = crate::access::build(
                particle,
                organization,
                locality,
                destination,
                effort,
                _time,
                config,
            );
        }
        return;
    }

    if channel == ARMED_CONFRONTATION {
        let mut pairs = Vec::new();
        let local_formations = (0..particle.formations.personnel.len())
            .filter(|&formation| particle.formations.locality[formation] as usize == locality)
            .collect::<Vec<_>>();
        let own = local_formations
            .iter()
            .copied()
            .filter(|&formation| {
                particle.formations.organization[formation] as usize == organization
                    && particle.formations.personnel[formation] > 0.0
                    && particle.formations.moving[formation] == 0
                    && particle.formations.outside_pineland[formation] == 0
                    && particle.formations.operational_status[formation] == 1
            })
            .collect::<Vec<_>>();
        let opponents = local_formations
            .iter()
            .copied()
            .filter(|&formation| {
                let target_organization = particle.formations.organization[formation] as usize;
                particle.formations.personnel[formation] > 0.0
                    && particle.formations.moving[formation] == 0
                    && particle.formations.outside_pineland[formation] == 0
                    && particle
                        .organizations
                        .active
                        .get(target_organization)
                        .copied()
                        == Some(1)
                    && organizations_hostile(particle, organization, target_organization)
            })
            .collect::<Vec<_>>();
        for actor in own.iter().copied() {
            let actor_microzone = crate::combat::formation_microzone(particle, topology, actor);
            for opponent in opponents.iter().copied() {
                let opponent_microzone =
                    crate::combat::formation_microzone(particle, topology, opponent);
                if actor_microzone == opponent_microzone {
                    pairs.push((actor, opponent));
                }
            }
        }
        if pairs.is_empty() && !own.is_empty() && !opponents.is_empty() {
            *particle
                .counters
                .event_counts
                .entry("armed_contact_fallbacks".to_string())
                .or_insert(0) += 1;
            for actor in own.iter().copied() {
                for opponent in opponents.iter().copied() {
                    pairs.push((actor, opponent));
                }
            }
        }
        if trace {
            eprintln!(
                "ACTION armed_confrontation org={} loc={} own={} opponents={} matched_pairs={}",
                organization,
                locality,
                own.len(),
                opponents.len(),
                pairs.len()
            );
        }
        if funnel {
            eprintln!(
                "FUNNEL t={:.3} org={} loc={} stage=armed own={} opponents={} pairs={} local_formations={}",
                _time, organization, locality, own.len(), opponents.len(), pairs.len(), local_formations.len()
            );
        }
        if pairs.is_empty() && !own.is_empty() && operational_reach_enabled(config) {
            armed_strike(
                particle,
                topology,
                config,
                rng,
                _time,
                organization,
                locality,
                &own,
                funnel,
            );
            return;
        }
        if pairs.is_empty() {
            return;
        }
        let selected = match rng.choice_index(pairs.len()) {
            Ok(index) => index,
            Err(_) => return,
        };
        let (actor, opponent) = pairs[selected];
        let opponent_microzone = crate::combat::formation_microzone(particle, topology, opponent);
        particle.formations.microzone[actor] = opponent_microzone as u32;
        let opponent_organization = particle.formations.organization[opponent] as usize;
        let defender_aware =
            particle
                .presence_beliefs
                .keys
                .iter()
                .enumerate()
                .any(|(index, key)| {
                    key.observer as usize == opponent_organization
                        && key.locality as usize == locality
                        && particle
                            .presence_beliefs
                            .evidence_count
                            .get(index)
                            .copied()
                            .unwrap_or(0)
                            > 0
                        && particle
                            .presence_beliefs
                            .estimate
                            .get(index)
                            .copied()
                            .unwrap_or(0.0)
                            >= 0.5
                });
        crate::combat::resolve_organized_engagement(
            particle,
            topology,
            config,
            rng,
            _time,
            actor,
            opponent,
            organization,
            defender_aware,
        );
        return;
    }

    if channel == NONFIELDED_HUMAN_TARGET {
        if trace {
            eprintln!(
                "ACTION human_enter org={} source={}",
                organization, locality,
            );
        }
        let Some(target_locality) = operational_target(
            particle,
            topology,
            config,
            organization,
            locality,
            NONFIELDED_HUMAN_TARGET,
            rng,
        ) else {
            return;
        };
        let targets = nonfielded_human_targets(particle, organization, target_locality);
        if trace {
            eprintln!(
                "ACTION human_lookup org={} source={} destination={} targets={}",
                organization,
                locality,
                target_locality,
                targets.len(),
            );
        }
        if targets.is_empty() {
            return;
        }
        let target_weights = targets
            .iter()
            .map(|target| (target.personnel * target.available_fraction.clamp(0.0, 1.0)).max(1e-9))
            .collect::<Vec<_>>();
        let selected = match rng.choices_indices(targets.len(), Some(&target_weights), 1) {
            Ok(values) => values[0],
            Err(_) => return,
        };
        let target = targets[selected];
        let exposed = (target.personnel * target.available_fraction.clamp(0.0, 1.0)).max(0.0);
        let resistance = exposed / (committed + exposed).max(1e-12);
        let demand = committed
            * config.combat.supply_per_person_hour
            * config.combat.interval_hours.max(0.0);
        let available = local_supply_available(particle, organization, locality);
        let material_fraction = if demand > 0.0 {
            (available / demand).clamp(0.0, 1.0)
        } else {
            1.0
        };
        let total = local_fighter_equivalents(particle, organization, locality, config);
        let scale = config
            .organization_ecology
            .minimum_formation_personnel
            .max(1e-9);
        let capacity = ((total.0 + total.1) / (total.0 + total.1 + scale)).clamp(0.0, 1.0);
        let knowledge = local_execution_knowledge(
            particle,
            topology,
            config,
            organization,
            target_locality,
            target.organization,
        );
        let vulnerability = (1.0 - resistance).clamp(0.0, 1.0);
        let probability = if capacity <= 0.0
            || knowledge <= 0.0
            || vulnerability <= 0.0
            || material_fraction <= 0.0
        {
            0.0
        } else {
            (capacity * knowledge * vulnerability * material_fraction)
                .powf(0.25)
                .clamp(0.0, 1.0)
        };
        let (consumed, unmet) = consume_local_supply(particle, organization, locality, demand);
        let execution_draw = rng.random();
        if trace {
            eprintln!(
                "ACTION human org={} source={} destination={} target_org={} target_index={} pooled={} exposed={:.17} demand={:.17} available={:.17} consumed={:.17} unmet={:.17} probability={:.17} draw={:.17}",
                organization,
                locality,
                target_locality,
                target.organization,
                target.index,
                target.pooled,
                exposed,
                demand,
                available,
                consumed,
                unmet,
                probability,
                execution_draw,
            );
        }
        if execution_draw < probability {
            let loss_fraction = config
                .combat
                .max_loss_fraction
                .min(config.combat.base_attrition_rate * (1.0 + probability));
            let losses = target.personnel.min(exposed * loss_fraction);
            let realized = apply_human_target_losses(particle, target, losses);
            if realized > 0.0 {
                let intensity = (realized / exposed.max(1.0)).min(1.0);
                particle.locality.violence[target_locality] =
                    clamp01(particle.locality.violence[target_locality] * 0.85 + 0.25 * intensity);
                crate::combat::update_relations(
                    particle,
                    organization,
                    target.organization,
                    intensity,
                    _time,
                    config,
                );
                crate::organizations::record_foothold_action(
                    particle,
                    topology,
                    organization,
                    locality,
                );
            }
        }
        return;
    }

    if channel == ASSET_VIOLENCE {
        let Some(target_locality) = operational_target(
            particle,
            topology,
            config,
            organization,
            locality,
            ASSET_VIOLENCE,
            rng,
        ) else {
            return;
        };
        let target_indices = (0..particle.political.institution_locality.len())
            .filter(|&index| {
                particle.political.institution_locality[index] as usize == target_locality
                    && particle.political.institution_capacity[index] > 0.0
                    && particle.political.institution_reach[index] > 0.0
            })
            .collect::<Vec<_>>();
        if target_indices.is_empty() {
            return;
        }
        let target_weights = target_indices
            .iter()
            .map(|&index| {
                (particle.political.institution_capacity[index]
                    * particle.political.institution_reach[index])
                    .max(1e-9)
            })
            .collect::<Vec<_>>();
        let selected = match rng.choices_indices(target_indices.len(), Some(&target_weights), 1) {
            Ok(values) => values[0],
            Err(_) => return,
        };
        let target = target_indices[selected];
        let hardness = (particle.political.institution_capacity[target]
            + particle.political.institution_integrity[target]
            + particle.political.institution_reach[target])
            / 3.0;
        let demand = committed
            * config.combat.supply_per_person_hour
            * config.combat.interval_hours.max(0.0);
        let available = local_supply_available(particle, organization, locality);
        let material_fraction = if demand > 0.0 {
            (available / demand).clamp(0.0, 1.0)
        } else {
            1.0
        };
        // Match Python's execution_probability: capacity_saturation is based
        // on the full local equipped stock, while `committed` is only the
        // action's demand/consumption unit.
        let total_fighters = local_fighter_equivalents(particle, organization, locality, config);
        let total_fighters = total_fighters.0 + total_fighters.1;
        let capacity = (total_fighters
            / (total_fighters
                + config
                    .organization_ecology
                    .minimum_formation_personnel
                    .max(1e-12)))
        .clamp(0.0, 1.0);
        let knowledge = local_execution_knowledge(
            particle,
            topology,
            config,
            organization,
            target_locality,
            crate::GOVERNMENT,
        );
        let vulnerability = (1.0 - hardness).clamp(0.0, 1.0);
        let probability = if capacity <= 0.0
            || knowledge <= 0.0
            || vulnerability <= 0.0
            || material_fraction <= 0.0
        {
            0.0
        } else {
            (capacity * knowledge * vulnerability * material_fraction)
                .powf(0.25)
                .clamp(0.0, 1.0)
        };
        let (consumed, unmet) = consume_local_supply(particle, organization, locality, demand);
        let execution_draw = rng.random();
        if trace {
            eprintln!(
                "ACTION asset org={} source={} destination={} target={} demand={:.17} available={:.17} consumed={:.17} unmet={:.17} probability={:.17} draw={:.17}",
                organization,
                locality,
                target_locality,
                target,
                demand,
                available,
                consumed,
                unmet,
                probability,
                execution_draw,
            );
        }
        if execution_draw < probability {
            let damage = (config.combat.base_attrition_rate * probability).clamp(0.0, 1.0);
            particle.political.institution_capacity[target] =
                clamp01(particle.political.institution_capacity[target] * (1.0 - damage));
            particle.political.institution_integrity[target] =
                clamp01(particle.political.institution_integrity[target] * (1.0 - damage));
            particle.political.institution_reach[target] =
                clamp01(particle.political.institution_reach[target] * (1.0 - damage));
            particle.locality.violence[target_locality] =
                clamp01(particle.locality.violence[target_locality] * 0.85 + 0.25 * damage);
        }
        return;
    }

    if channel == COERCION {
        // Python realizes the compliance Bernoulli even though the current
        // coercion contract records the outcome without mutating latent
        // state.  Preserve that draw so the shared action stream continues
        // at the same point for the next organized-action event.
        let _compliance_draw = rng.random();
        return;
    }

    // The remaining channels have no native state mutation in this slice, but
    // keep their constants explicit until the process-specific transitions
    // are ported and certified.
    let _ = (
        channel,
        committed,
        ARMED_CONFRONTATION,
        COERCION,
        ADMINISTRATIVE,
    );
}

/// Operational-reach armed confrontation (`multichannel_v6` only).
///
/// A formation with no co-located opponent strikes into an adjacent locality
/// where its organization holds evidence of hostile presence. The strike pays a
/// round-trip movement cost from the formation's own supply stock, fights in
/// the target locality, and returns the formation to its origin. A strike that
/// finds no opponent ("dry hole") still pays its cost.
#[allow(clippy::too_many_arguments)]
fn armed_strike(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
    organization: usize,
    locality: usize,
    own: &[usize],
    funnel: bool,
) {
    let Some((target, edge_cost)) =
        armed_strike_target(particle, topology, config, organization, locality, time, rng)
    else {
        bump_event(particle, "armed_strike_no_target");
        return;
    };
    if funnel {
        eprintln!(
            "FUNNEL t={:.3} org={} loc={} stage=strike_intel target={} {}",
            time,
            organization,
            locality,
            target,
            strike_intel_trace(particle, topology, config, organization, target, time)
        );
    }
    let actor = match rng.choice_index(own.len()) {
        Ok(index) => own[index],
        Err(_) => return,
    };
    let distance_km = 2.0 * (18.0 + 22.0 * edge_cost.max(0.0));
    let burden = if organization == crate::MILITARY {
        config.combat.government_supply_burden_multiplier
    } else {
        1.0
    };
    // A strike commits a detachment, not the whole formation.
    let base_fraction = config.combat.strike_fraction.clamp(0.0, 1.0);
    // A planned assault on a post (no reported enemy formation there) masses
    // force for roughly 3:1 over the garrison instead of a raiding detachment.
    let target_side_insurgent = !is_insurgent(particle, organization);
    let planned_post = hostile_post(particle, organization, target).filter(|_| {
        evidenced_presence(
            particle,
            organization,
            target_side_insurgent,
            target,
            time,
            config.combat.strike_report_decay_days,
        )
        .unwrap_or(0.0)
            < 0.05
    });
    let fraction = match planned_post {
        Some(post) => (3.0 * particle.security_posts.personnel[post]
            / particle.formations.personnel[actor].max(1.0e-9))
        .clamp(base_fraction, 1.0),
        None => base_fraction,
    };
    let moving = particle.formations.personnel[actor].max(0.0)
        * particle.formations.availability[actor].clamp(0.0, 1.0)
        * fraction;
    let cost = moving * distance_km * config.logistics.movement_consumption_per_person_km * burden;
    if cost > particle.formations.supply_stock[actor] + 1.0e-12 {
        bump_event(particle, "armed_strike_unaffordable");
        if funnel {
            eprintln!(
                "FUNNEL t={:.3} org={} loc={} stage=strike outcome=unaffordable target={} cost={:.3} stock={:.3}",
                time, organization, locality, target, cost, particle.formations.supply_stock[actor]
            );
        }
        return;
    }
    particle.formations.supply_stock[actor] -= cost;
    let opponents = (0..particle.formations.personnel.len())
        .filter(|&formation| {
            let target_organization = particle.formations.organization[formation] as usize;
            particle.formations.locality[formation] as usize == target
                && particle.formations.personnel[formation] > 0.0
                && particle.formations.moving[formation] == 0
                && particle.formations.outside_pineland[formation] == 0
                && particle
                    .organizations
                    .active
                    .get(target_organization)
                    .copied()
                    == Some(1)
                && organizations_hostile(particle, organization, target_organization)
        })
        .collect::<Vec<_>>();
    if opponents.is_empty() {
        if let Some(post) = hostile_post(particle, organization, target) {
            let garrison = particle.security_posts.personnel[post];
            let advantage = assault_post(particle, config, rng, actor, post, fraction, target);
            if funnel {
                eprintln!(
                    "FUNNEL t={:.3} org={} loc={} stage=strike outcome=post_assault target={} staffed={} fraction={:.3} garrison={:.1} after={:.1} advantage={:.3}",
                    time, organization, locality, target, particle.security_posts.staffed[post],
                    fraction, garrison, particle.security_posts.personnel[post], advantage
                );
            }
            return;
        }
        bump_event(particle, "armed_strike_dry_hole");
        downgrade_presence_belief(
            particle,
            config,
            organization,
            !is_insurgent(particle, organization),
            target,
            time,
        );
        let lead = sweep_exploitation_lead(particle, config, rng, organization, target, time);
        if lead.is_some() {
            bump_event(particle, "armed_strike_sweep_leads");
        }
        if funnel {
            let mut present = 0;
            let mut in_transit = 0;
            let mut not_operational = 0;
            let mut outside = 0;
            let mut inactive = 0;
            for formation in 0..particle.formations.personnel.len() {
                let target_organization = particle.formations.organization[formation] as usize;
                if particle.formations.locality[formation] as usize == target
                    && particle.formations.personnel[formation] > 0.0
                    && organizations_hostile(particle, organization, target_organization)
                {
                    present += 1;
                    if particle.formations.moving[formation] != 0 {
                        in_transit += 1;
                    }
                    if particle.formations.operational_status[formation] != 1 {
                        not_operational += 1;
                        let f = &particle.formations;
                        eprintln!(
                            "FUNNEL nonop formation={} org={} personnel={:.1} cohesion={:.3} readiness={:.3} eff_readiness={:.3} stock={:.1} cap={:.1} avail={:.3} active={}",
                            formation, target_organization, f.personnel[formation], f.cohesion[formation],
                            f.readiness[formation], f.effective_readiness(formation), f.supply_stock[formation],
                            f.supply_capacity[formation], f.availability[formation], f.active[formation]
                        );
                    }
                    if particle.formations.outside_pineland[formation] != 0 {
                        outside += 1;
                    }
                    if particle.organizations.active.get(target_organization).copied() != Some(1) {
                        inactive += 1;
                        eprintln!(
                            "FUNNEL inactive_org={} actor_org={} active={:?} kind={:?}",
                            target_organization,
                            organization,
                            particle.organizations.active.get(target_organization),
                            particle.organizations.kind.get(target_organization)
                        );
                    }
                }
            }
            eprintln!(
                "FUNNEL t={:.3} org={} loc={} stage=strike outcome=dry_hole target={} hostile_present={} in_transit={} not_operational={} outside={} inactive={} lead={}",
                time, organization, locality, target, present, in_transit, not_operational, outside, inactive,
                lead.map_or(-1, |value| value as i64)
            );
        }
        return;
    }
    let opponent = match rng.choice_index(opponents.len()) {
        Ok(index) => opponents[index],
        Err(_) => return,
    };
    let opponent_organization = particle.formations.organization[opponent] as usize;
    let defender_aware = particle
        .presence_beliefs
        .keys
        .iter()
        .enumerate()
        .any(|(index, key)| {
            key.observer as usize == opponent_organization
                && key.locality as usize == target
                && particle
                    .presence_beliefs
                    .evidence_count
                    .get(index)
                    .copied()
                    .unwrap_or(0)
                    > 0
                && particle
                    .presence_beliefs
                    .estimate
                    .get(index)
                    .copied()
                    .unwrap_or(0.0)
                    >= 0.5
        });
    let origin_locality = particle.formations.locality[actor];
    let origin_microzone = particle.formations.microzone[actor];
    let opponent_microzone = crate::combat::formation_microzone(particle, topology, opponent);
    particle.formations.locality[actor] = target as u32;
    particle.formations.microzone[actor] = opponent_microzone as u32;
    let contacts_before = particle.counters.contacts;
    // Resolve at detachment strength: scale the actor down, then restore the
    // uncommitted remainder and apply only `fraction` of the cohesion and
    // readiness damage to the parent formation.
    let full_personnel = particle.formations.personnel[actor];
    let detachment = full_personnel * fraction;
    let reserve = full_personnel - detachment;
    let cohesion_before = particle.formations.cohesion[actor];
    let readiness_before = particle.formations.readiness[actor];
    let availability_before = particle.formations.availability[actor];
    let experience_before = particle.formations.experience[actor];
    let status_before = particle.formations.operational_status[actor];
    particle.formations.personnel[actor] = detachment;
    crate::combat::RAIDING_FORMATION.with(|cell| cell.set(actor));
    crate::combat::resolve_organized_engagement(
        particle,
        topology,
        config,
        rng,
        time,
        actor,
        opponent,
        organization,
        defender_aware,
    );
    crate::combat::RAIDING_FORMATION.with(|cell| cell.set(usize::MAX));
    // Only the committed detachment fought: blend every state change back
    // into the parent formation in proportion to `fraction`, then re-judge
    // combat effectiveness on the blended state.
    particle.formations.personnel[actor] += reserve;
    let f = &mut particle.formations;
    let blend = |before: f64, after: f64| before + fraction * (after - before);
    f.cohesion[actor] = blend(cohesion_before, f.cohesion[actor]);
    f.readiness[actor] = blend(readiness_before, f.readiness[actor]);
    f.availability[actor] = blend(availability_before, f.availability[actor]);
    f.experience[actor] = blend(experience_before, f.experience[actor]);
    f.operational_status[actor] = status_before;
    if f.personnel[actor] <= 0.0
        || f.cohesion[actor] <= config.combat.ineffective_cohesion
        || f.combat_readiness(actor) <= config.combat.ineffective_readiness
    {
        f.operational_status[actor] = 0;
        f.availability[actor] = f.availability[actor].min(0.08);
    }
    particle.formations.locality[actor] = origin_locality;
    particle.formations.microzone[actor] = origin_microzone;
    bump_event(particle, "armed_strikes");
    if funnel {
        eprintln!(
            "FUNNEL t={:.3} org={} loc={} stage=strike outcome=engaged target={} resolved={}",
            time,
            organization,
            locality,
            target,
            particle.counters.contacts - contacts_before
        );
    }
}

/// A detachment assaults a fixed post. Attrition uses the engagement form
/// (`base_attrition_rate * exp(+-0.45 * advantage + noise)`, capped); the post
/// is lightly armed but fights from cover (x1.25). A decisive advantage (>2:1) can overrun the post
/// outright; a post reduced below 10 personnel is abandoned. Overrun posts stay
/// unstaffed until the state re-deploys police there.
fn assault_post(
    particle: &mut ParticleState,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    actor: usize,
    post: usize,
    fraction: f64,
    locality: usize,
) -> f64 {
    let f = &particle.formations;
    let detachment = f.personnel[actor].max(0.0) * fraction;
    let experience = if config.state_regeneration.enabled {
        0.75 + 0.50 * f.experience[actor].clamp(0.0, 1.0)
    } else {
        1.0
    };
    let attack = (detachment * f.combat_readiness(actor)).max(1.0e-9).powf(0.72)
        * f.quality[actor]
        * experience
        * f.cohesion[actor].max(0.05);
    let posts = &particle.security_posts;
    let defense = (posts.personnel[post] * posts.available_fraction[post].max(0.3))
        .max(1.0e-9)
        .powf(0.72)
        // Lightly armed constabulary: weaker per head than an armed formation
        // even when professional, partly offset by fighting from cover.
        * (0.25 + 0.35 * clamp01(posts.professionalism[post]))
        * 1.25;
    let advantage = attack.max(1.0e-9).ln() - defense.max(1.0e-9).ln();
    if crate::trace_env!("PINELAND_FUNNEL") {
        let f = &particle.formations;
        let posts = &particle.security_posts;
        eprintln!(
            "ASSAULT detach={:.1} cr={:.3} ready={:.3} supply={:.3} fatigue_r={:.3} q={:.3} coh={:.3} exp={:.3} attack={:.2} garrison={:.1} avail={:.2} prof={:.3} defense={:.2}",
            detachment, f.combat_readiness(actor), f.readiness[actor], f.supply_fraction(actor),
            f.fatigue_adjusted_readiness(actor), f.quality[actor], f.cohesion[actor], experience, attack,
            posts.personnel[post], posts.available_fraction[post], posts.professionalism[post], defense
        );
    }
    let sigma = config.combat.stochastic_sigma;
    let frac_post = (config.combat.base_attrition_rate
        * python_exp(0.45 * advantage + rng.normalvariate(0.0, sigma)))
    .min(config.combat.max_loss_fraction);
    let frac_attacker = (config.combat.base_attrition_rate
        * python_exp(-0.45 * advantage + rng.normalvariate(0.0, sigma)))
    .min(config.combat.max_loss_fraction);
    let overrun = advantage > 2.0f64.ln() && rng.random() < 0.5;

    let attacker_loss = detachment * frac_attacker;
    particle.formations.personnel[actor] -= attacker_loss;
    particle.formations.cumulative_losses[actor] += attacker_loss;
    let posts = &mut particle.security_posts;
    let post_loss = posts.personnel[post] * if overrun { 0.5 } else { frac_post };
    posts.personnel[post] -= post_loss;
    if overrun || posts.personnel[post] < 10.0 {
        // Survivors of an overrun post disperse; the state must re-deploy.
        posts.personnel[post] = 0.0;
        posts.staffed[post] = 0;
        posts.presence[post] = 0.0;
        bump_event(particle, "posts_overrun");
    } else {
        posts.presence[post] = clamp01(posts.personnel[post] / 250.0);
    }
    let intensity = (frac_post + frac_attacker) / (2.0 * config.combat.base_attrition_rate).max(0.001);
    particle.locality.violence[locality] =
        clamp01(particle.locality.violence[locality] * 0.85 + 0.25 * intensity.min(1.0));
    particle.counters.contacts += 1;
    bump_event(particle, "post_assaults");
    advantage
}

pub fn apply_nonviolent_coercion(particle: &mut ParticleState, locality: usize, amount: f64) {
    if locality >= particle.locality.population.len() {
        return;
    }
    let offset = locality * pineland_core::state::CONTROL_DIMENSIONS;
    particle.locality.insurgent_control[offset + 5] =
        clamp01(particle.locality.insurgent_control[offset + 5] + amount);
    particle.locality.government_control[offset + 5] =
        clamp01(particle.locality.government_control[offset + 5] - amount * 0.4);
}

// Retained as a typed helper for callers and the action tests.
pub fn schedule_typed_contact(
    particle: &mut ParticleState,
    time: f64,
    locality: usize,
    first: usize,
    second: usize,
    microzone: usize,
) {
    let _ = particle.scheduler.schedule(
        time,
        100,
        EventPayload::Contact {
            first: (first as u32).into(),
            second: (second as u32).into(),
            locality: (locality as u32).into(),
            microzone: (microzone as u32).into(),
        },
    );
}

#[cfg(test)]
mod tests {
    use super::{armed_strike, assault_post, operational_reach_enabled};
    use pineland_core::config::SimulationConfig;
    use pineland_core::rng::{PyRandomCompat, RngStreams};
    use pineland_core::state::{ParticleState, PresenceKey, PresenceState};
    use pineland_core::topology::StaticTopology;

    #[test]
    fn operational_reach_is_the_default_architecture() {
        let mut config = SimulationConfig::default();
        assert_eq!(config.combat.organized_action_architecture, "multichannel_v6");
        assert!(operational_reach_enabled(&config));
        config.combat.organized_action_architecture = "multichannel_v5".to_string();
        assert!(!operational_reach_enabled(&config));
    }

    #[test]
    fn multichannel_v6_neighbor_strike_resolves_and_applies_losses() {
        let (before, after, contacts, strikes) = run_neighbor_strike(1.0);
        assert_eq!(contacts, 1);
        assert_eq!(strikes, Some(1));
        assert!(after[0] < before[0]);
        assert!(after[1] < before[1]);
    }

    #[test]
    fn multichannel_v6_strike_commits_only_the_detachment() {
        let fraction = 0.1;
        let (before, after, contacts, _) = run_neighbor_strike(fraction);
        assert_eq!(contacts, 1);
        // max_loss_fraction caps a single engagement at 12% of the committed
        // detachment, so the parent formation keeps at least the reserve.
        let floor = before[0] - 0.12 * fraction * before[0];
        assert!(after[0] >= floor - 1.0e-9, "{} < {}", after[0], floor);
        assert!(after[0] <= before[0]);
        assert!(after[1] < before[1]);
    }

    fn run_neighbor_strike(fraction: f64) -> ([f64; 2], [f64; 2], u64, Option<u64>) {
        let topology = StaticTopology::new(2);
        let mut config = SimulationConfig {
            locality_count: 2,
            agent_count: 100,
            ..SimulationConfig::default()
        };
        config.combat.organized_action_architecture = "multichannel_v6".to_string();
        config.combat.stochastic_sigma = 0.0;
        config.combat.strike_fraction = fraction;
        let mut particle = ParticleState::new(
            2,
            topology.microzones.len(),
            7,
            2,
            2,
            RngStreams::new(1847, "v6-neighbor-strike-test"),
        );
        particle.organizations.kind[crate::MILITARY] = 1;
        particle.organizations.kind[crate::INSURGENT] = 3;
        particle
            .relations
            .organization_a
            .push(crate::MILITARY as u32);
        particle
            .relations
            .organization_b
            .push(crate::INSURGENT as u32);
        particle.relations.status.push(4);
        particle.relations.rivalry_memory.push(0.0);
        particle.relations.hostility_memory.push(1.0);
        particle.relations.cooperation_memory.push(0.0);
        particle.relations.updated_at.push(0.0);
        particle.relations.last_interaction_at.push(0.0);
        particle.relations.has_last_interaction.push(0);

        particle.formations.organization = vec![crate::MILITARY as u32, crate::INSURGENT as u32];
        particle.formations.locality = vec![0, 1];
        particle.formations.microzone = vec![topology.primary_zone[0], topology.primary_zone[1]];
        particle.formations.personnel = vec![500.0, 500.0];
        particle.formations.supply_stock = vec![1.0e9, 1.0e9];
        particle.formations.supply_capacity = vec![1.0e9, 1.0e9];

        particle.presence_beliefs = PresenceState::with_keys(vec![PresenceKey {
            observer: crate::MILITARY as u32,
            target: crate::INSURGENT as u32,
            locality: 1,
            microzone: u32::MAX,
            target_formation: u32::MAX,
        }]);
        particle.presence_beliefs.estimate[0] = 1.0;
        particle.presence_beliefs.confidence[0] = 1.0;
        particle.presence_beliefs.evidence_count[0] = 1;

        let personnel_before = [
            particle.formations.personnel[0],
            particle.formations.personnel[1],
        ];
        let mut rng = PyRandomCompat::from_seed(2026);
        armed_strike(
            &mut particle,
            &topology,
            &config,
            &mut rng,
            12.0,
            crate::MILITARY,
            0,
            &[0],
            false,
        );

        assert_eq!(particle.formations.locality, vec![0, 1]);
        (
            personnel_before,
            [
                particle.formations.personnel[0],
                particle.formations.personnel[1],
            ],
            particle.counters.contacts as u64,
            particle.counters.event_counts.get("armed_strikes").map(|v| *v as u64),
        )
    }

    #[test]
    fn massed_assault_damages_a_small_post() {
        let config = SimulationConfig::default();
        let mut particle = ParticleState::new(1, 1, 7, 1, 1, RngStreams::new(7, "post-assault-test"));
        particle.organizations.kind[crate::INSURGENT] = 3;
        particle.formations.organization = vec![crate::INSURGENT as u32];
        particle.formations.personnel = vec![900.0];
        particle.formations.supply_stock = vec![27_000.0];
        particle.formations.supply_capacity = vec![27_000.0];
        particle.security_posts = pineland_core::state::SecurityPostState::new(1);
        particle.security_posts.organization[0] = crate::POLICE as u32;
        particle.security_posts.personnel[0] = 40.0;
        particle.security_posts.presence[0] = 0.16;
        particle.security_posts.available_fraction[0] = 0.65;
        particle.security_posts.professionalism[0] = 0.5;
        particle.security_posts.staffed[0] = 1;
        let mut rng = PyRandomCompat::from_seed(11);
        let advantage = assault_post(&mut particle, &config, &mut rng, 0, 0, 1.0, 0);
        assert!(advantage > 0.0, "advantage {advantage}");
        assert!(particle.security_posts.personnel[0] < 40.0);
        assert_eq!(particle.counters.contacts, 1);
        assert!(particle.formations.personnel[0] < 900.0);
    }
}
