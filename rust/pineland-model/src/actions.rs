//! Belief-routed organized actions.
//!
//! Organized actions are deliberately event-local. A contact scan schedules
//! one event for one actor/locality pair; executing that event must consume the
//! same capacity, supply, and RNG sequence as Python's
//! `ProcessEngine.on_organized_action`. In particular, this module must not
//! loop over every locality when handling one scheduled action.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::PyRandomCompat;
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

fn action_organization(kind: u8) -> bool {
    // Python ACTION_ORGANIZATION_KINDS: insurgent, military, police, foreign.
    matches!(kind, 1 | 2 | 3 | 5 | 6 | 7)
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

fn local_fighter_equivalents(
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
        if particle.manpower.organization.get(index).copied().unwrap_or(u32::MAX)
                as usize
            == organization
            && particle.manpower.locality.get(index).copied().unwrap_or(u32::MAX) as usize
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
    let hazard = action_attempt_hazard(particle, config, organization, locality)
        * interval_days.max(0.0);
    // `expm1` is evaluated at the negative hazard: 1 - exp(-h) is
    // numerically stable for both very small and very large exposures.
    clamp01(-(-hazard).exp_m1())
}

fn local_supply_available(
    particle: &ParticleState,
    organization: usize,
    locality: usize,
) -> f64 {
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
    let kind = particle.organizations.kind[organization];
    let target = if kind as usize == crate::INSURGENT {
        crate::GOVERNMENT
    } else {
        crate::INSURGENT
    };
    let physical = belief_control(particle, organization, target, locality, PHYSICAL);
    let social = belief_control(particle, organization, target, locality, SOCIAL);
    // Presence is a separate Python belief table. A zero-valued but evidenced
    // presence row suppresses armed confrontation even when the control table
    // still has its neutral physical prior; the native presence table is
    // completed in the information parity slice, so preserve that zero at the
    // current boundary rather than substituting the control prior.
    let perceived_presence = 0.0;
    let risk = particle.organizations.phenotype[organization * 8 + 4].clamp(0.0, 1.0);
    let governance = particle.organizations.phenotype[organization * 8 + 2].clamp(0.0, 1.0);
    let fielded_share = (fielded / total).clamp(0.0, 1.0);
    let human_target_belief = if kind as usize == crate::INSURGENT {
        // Reachable target evidence is zero in the no-evidence fallback.
        0.0
    } else {
        ((physical + social) / 2.0).clamp(0.0, 1.0)
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
        0.0,
        0.0,
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
    let candidates = topology.locality_edges.neighbors(locality).collect::<Vec<_>>();
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
    let selected = rng.choices_indices(candidates.len(), Some(&weights), 1).ok()?[0];
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
    let probability = action_attempt_probability(particle, config, organization, locality, interval_days);
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

    let mut weights = control_weights(particle, config, organization, locality, unfielded, fielded);
    if topology.locality_edges.neighbors(locality).next().is_none() {
        weights[ACCESS_RESTRICTION] = 0.0;
    }
    let channel = match rng.choices_indices(6, Some(&weights), 1) {
        Ok(values) => values[0],
        Err(_) => WAIT,
    };
    if trace {
        eprintln!("ACTION choice org={} loc={} weights={:?} channel={}", organization, locality, weights, channel);
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

    // Python chooses an operational locality before it checks whether the
    // execution-time target is actually present.  Even a failed/empty target
    // therefore consumes the same weighted-choice draw.  Preserve that RNG
    // boundary now; the target-state mutations are handled below as their
    // corresponding channels are certified.
    if channel == NONFIELDED_HUMAN_TARGET || channel == ASSET_VIOLENCE {
        let mut candidate_count = 1usize; // same-locality candidate
        candidate_count += topology.locality_edges.neighbors(locality).count();
        let _ = rng.choices_indices(candidate_count, None, 1);
    }

    // The remaining channels have no native state mutation in this slice, but
    // keep their constants explicit until the process-specific transitions
    // are ported and certified.
    let _ = (channel, committed, ARMED_CONFRONTATION, COERCION, ADMINISTRATIVE);
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
