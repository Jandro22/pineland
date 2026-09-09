//! Belief-routed organized actions.
//!
//! Organized actions are deliberately event-local. A contact scan schedules
//! one event for one actor/locality pair; executing that event must consume the
//! same capacity, supply, and RNG sequence as Python's
//! `ProcessEngine.on_organized_action`. In particular, this module must not
//! loop over every locality when handling one scheduled action.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{python_exp, PyRandomCompat};
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

fn opponent_presence_belief(
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
    python_exp(-travel_hours / 24.0)
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
    organization: usize,
    locality: usize,
    channel: usize,
    rng: &mut PyRandomCompat,
) -> Option<usize> {
    let target_side_insurgent = !is_insurgent(particle, organization);
    let mut candidates = Vec::new();
    candidates.push((locality, 1.0));
    for (destination, cost) in topology.locality_edges.neighbors(locality) {
        candidates.push((
            destination as usize,
            locality_reach(
                particle,
                topology,
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
    for (destination, cost) in topology.locality_edges.neighbors(locality) {
        let destination = destination as usize;
        if !has_target_evidence(particle, organization, target_side_insurgent, destination) {
            continue;
        }
        let reach = locality_reach(
            particle,
            topology,
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

fn local_embeddedness(particle: &ParticleState, organization: usize, locality: usize) -> f64 {
    let locality_count = particle.locality.population.len().max(1);
    particle
        .footholds
        .embeddedness
        .get(organization * locality_count + locality)
        .copied()
        .unwrap_or(0.0)
        .clamp(0.0, 1.0)
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
    organization: usize,
    locality: usize,
    target: usize,
) -> f64 {
    let embedded = local_embeddedness(particle, organization, locality);
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
        if std::env::var_os("PINELAND_ACTION_TRACE").is_some()
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
    let fielded = (0..particle.formations.personnel.len())
        .filter(|&formation| {
            particle.formations.organization[formation] as usize == organization
                && particle.formations.locality[formation] as usize == locality
                && particle.formations.outside_pineland[formation] == 0
                && particle.formations.moving[formation] == 0
        })
        .map(|formation| particle.formations.personnel[formation].max(0.0))
        .sum();
    (unfielded, fielded)
}

fn committed_fighter_equivalents(
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
    (config.organized_action_rate.max(0.0) * committed / minimum).max(0.0)
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
        particle.formations.supply_stock[formation] -= take;
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
    let perceived_presence = opponent_presence_belief(particle, organization, !insurgent, locality)
        .max(
            evidenced_hostile_physical(particle, organization, !insurgent, locality).unwrap_or(0.0),
        );
    let risk = particle.organizations.phenotype[organization * 8 + 4].clamp(0.0, 1.0);
    let governance = particle.organizations.phenotype[organization * 8 + 2].clamp(0.0, 1.0);
    let fielded_share = (fielded / total).clamp(0.0, 1.0);
    let (human_target_belief, asset_weight, coercion_weight) = if insurgent {
        (
            reachable_target_belief(
                particle,
                topology,
                organization,
                locality,
                NONFIELDED_HUMAN_TARGET,
            ),
            risk * reachable_target_belief(
                particle,
                topology,
                organization,
                locality,
                ASSET_VIOLENCE,
            ),
            governance * local_embeddedness(particle, organization, locality),
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
    let candidates = topology
        .locality_edges
        .neighbors(locality)
        .collect::<Vec<_>>();
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
    let trace = std::env::var_os("PINELAND_ACTION_TRACE").is_some();
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
    if channel == WAIT {
        return;
    }

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
                    && particle.formations.operational_status[formation] == 1
                    && particle
                        .organizations
                        .active
                        .get(target_organization)
                        .copied()
                        == Some(1)
                    && organizations_hostile(particle, organization, target_organization)
            })
            .collect::<Vec<_>>();
        for actor in own {
            for opponent in opponents.iter().copied() {
                if particle.formations.microzone[actor] == particle.formations.microzone[opponent] {
                    pairs.push((actor, opponent));
                }
            }
        }
        if pairs.is_empty() {
            return;
        }
        let selected = match rng.choice_index(pairs.len()) {
            Ok(index) => index,
            Err(_) => return,
        };
        let (actor, opponent) = pairs[selected];
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
        let capacity = (committed
            / (committed
                + config
                    .organization_ecology
                    .minimum_formation_personnel
                    .max(1e-12)))
        .clamp(0.0, 1.0);
        let knowledge = local_execution_knowledge(
            particle,
            topology,
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
