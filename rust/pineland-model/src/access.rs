//! Persistent actor-owned access restrictions on locality corridors.
//!
//! The Python reference stores these rows in a sparse insertion-ordered map.
//! Native keeps the same logical key and update rules in parallel vectors so
//! the state can be checkpointed and gathered without object conversion.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::python_exp;
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

pub fn organizations_hostile(particle: &ParticleState, first: usize, second: usize) -> bool {
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

pub fn edge_restriction_level(
    particle: &ParticleState,
    first: usize,
    second: usize,
    moving_organization: Option<usize>,
) -> f64 {
    let (first, second) = if first <= second {
        (first as u32, second as u32)
    } else {
        (second as u32, first as u32)
    };
    let mut complement = 1.0;
    let mut found = false;
    for index in 0..particle.access_restrictions.owner.len() {
        if particle.access_restrictions.first_locality[index] != first
            || particle.access_restrictions.second_locality[index] != second
            || particle.access_restrictions.level[index] <= 0.0
        {
            continue;
        }
        let owner = particle.access_restrictions.owner[index] as usize;
        let applies = match moving_organization {
            None => true,
            Some(moving) => owner != moving && organizations_hostile(particle, owner, moving),
        };
        if applies {
            found = true;
            complement *= 1.0 - clamp01(particle.access_restrictions.level[index]);
        }
    }
    if found {
        clamp01(1.0 - complement)
    } else {
        0.0
    }
}

pub fn locality_access_pressure(
    particle: &ParticleState,
    topology: &StaticTopology,
    locality: usize,
) -> f64 {
    let neighbors = topology
        .locality_edges
        .neighbors(locality)
        .collect::<Vec<_>>();
    if neighbors.is_empty() {
        return 0.0;
    }
    let mut total = 0.0;
    for (neighbor, _) in neighbors.iter().copied() {
        total += edge_restriction_level(particle, locality, neighbor as usize, None);
    }
    total / neighbors.len() as f64
}

pub fn route_restriction_level(
    particle: &ParticleState,
    route: &[usize],
    moving_organization: Option<usize>,
) -> f64 {
    route
        .windows(2)
        .map(|pair| edge_restriction_level(particle, pair[0], pair[1], moving_organization))
        .fold(0.0, f64::max)
}

pub fn build(
    particle: &mut ParticleState,
    owner: usize,
    first: usize,
    second: usize,
    effort: f64,
    time: f64,
    config: &SimulationConfig,
) -> f64 {
    let (first, second) = if first <= second {
        (first as u32, second as u32)
    } else {
        (second as u32, first as u32)
    };
    let index = particle
        .access_restrictions
        .find(owner, first as usize, second as usize)
        .unwrap_or_else(|| {
            let index = particle.access_restrictions.owner.len();
            particle.access_restrictions.owner.push(owner as u32);
            particle.access_restrictions.first_locality.push(first);
            particle.access_restrictions.second_locality.push(second);
            particle.access_restrictions.level.push(0.0);
            particle.access_restrictions.cumulative_effort.push(0.0);
            particle.access_restrictions.updated_at.push(time);
            index
        });
    let increment = clamp01(config.access_restriction.build_rate * clamp01(effort));
    let old = particle.access_restrictions.level[index];
    particle.access_restrictions.level[index] = clamp01(1.0 - (1.0 - old) * (1.0 - increment));
    particle.access_restrictions.cumulative_effort[index] += effort.max(0.0);
    particle.access_restrictions.updated_at[index] = time;
    particle.access_restrictions.level[index]
}

pub fn decay(
    particle: &mut ParticleState,
    time: f64,
    elapsed_days: f64,
    config: &SimulationConfig,
) -> usize {
    if elapsed_days <= 0.0 {
        return 0;
    }
    let factor = python_exp(-config.access_restriction.decay_per_day * elapsed_days);
    let mut removed = 0;
    let mut index = 0;
    while index < particle.access_restrictions.owner.len() {
        particle.access_restrictions.level[index] *= factor;
        particle.access_restrictions.updated_at[index] = time;
        if particle.access_restrictions.level[index] <= 1.0e-9 {
            particle.access_restrictions.owner.remove(index);
            particle.access_restrictions.first_locality.remove(index);
            particle.access_restrictions.second_locality.remove(index);
            particle.access_restrictions.level.remove(index);
            particle.access_restrictions.cumulative_effort.remove(index);
            particle.access_restrictions.updated_at.remove(index);
            removed += 1;
        } else {
            index += 1;
        }
    }
    removed
}
