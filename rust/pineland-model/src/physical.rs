//! Physical presence, microzone control, and response-time fields.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::python_exp;
use pineland_core::state::{clamp01, ParticleState, CONTROL_DIMENSIONS};
use pineland_core::topology::StaticTopology;

const GOVERNMENT_KIND: u8 = 0;
const MILITARY_KIND: u8 = 1;
const POLICE_KIND: u8 = 2;
const INSURGENT_KIND: u8 = 3;

fn organization_matches_side(particle: &ParticleState, organization: usize, actor: u8) -> bool {
    if organization >= particle.organizations.kind.len()
        || particle
            .organizations
            .active
            .get(organization)
            .copied()
            .unwrap_or(0)
            == 0
    {
        return false;
    }
    if actor == 1 {
        return organization == crate::INSURGENT
            && particle.organizations.kind[organization] == INSURGENT_KIND;
    }
    if matches!(
        particle.organizations.kind[organization],
        GOVERNMENT_KIND | MILITARY_KIND | POLICE_KIND
    ) {
        return true;
    }
    // The Python reference also admits a non-security organization to the
    // government side when its explicit relation to government is allied or
    // cooperative.  Relation status codes are stable in the core schema.
    particle
        .relations
        .organization_a
        .iter()
        .zip(&particle.relations.organization_b)
        .zip(&particle.relations.status)
        .any(|((left, right), status)| {
            ((*left as usize == organization && *right as usize == crate::GOVERNMENT)
                || (*left as usize == crate::GOVERNMENT && *right as usize == organization))
                && matches!(*status, 0 | 1)
        })
}

fn dijkstra_local(topology: &StaticTopology, locality: usize, source: usize) -> Vec<f64> {
    let mut distances = vec![f64::INFINITY; topology.microzone_count()];
    if source >= distances.len() || topology.microzone_to_locality[source] as usize != locality {
        return distances;
    }
    let zones = topology
        .zones_for_locality(locality.into())
        .collect::<Vec<_>>();
    let mut settled = vec![false; topology.microzone_count()];
    distances[source] = 0.0;
    loop {
        // Python's heap is ordered by (distance, zone_id).  Native zone IDs
        // are in the same frozen lexical order as the Python registry, so the
        // explicit numeric tie break preserves the path chosen at ties.
        let next = zones
            .iter()
            .copied()
            .filter(|zone| !settled[*zone] && distances[*zone].is_finite())
            .min_by(|left, right| {
                distances[*left]
                    .total_cmp(&distances[*right])
                    .then_with(|| left.cmp(right))
            });
        let Some(zone) = next else { break };
        settled[zone] = true;
        let base = distances[zone];
        for (neighbor, travel_time) in topology.physical_edges.neighbors(zone) {
            let neighbor = neighbor as usize;
            if neighbor >= settled.len()
                || settled[neighbor]
                || topology.microzone_to_locality[neighbor] as usize != locality
            {
                continue;
            }
            let candidate = base + travel_time;
            if candidate < distances[neighbor] {
                distances[neighbor] = candidate;
            }
        }
    }
    distances
}

fn response_distances(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    locality: usize,
    actor: u8,
    time: f64,
) -> Vec<f64> {
    let mut source_delays = Vec::<(usize, f64)>::new();
    let response_decay = config.physical.response_decay_hours;

    for post in 0..particle.security_posts.locality.len() {
        if particle.security_posts.locality[post] as usize != locality
            || particle
                .security_posts
                .staffed
                .get(post)
                .copied()
                .unwrap_or(1)
                == 0
            || !organization_matches_side(
                particle,
                particle.security_posts.organization[post] as usize,
                actor,
            )
        {
            continue;
        }
        let mut available = particle.security_posts.available_fraction[post];
        let formation = particle.security_posts.formation[post];
        if formation != u32::MAX {
            let formation = formation as usize;
            if formation >= particle.formations.personnel.len()
                || particle.formations.moving[formation] != 0
                || particle.formations.outside_pineland[formation] != 0
                || particle.formations.operational_status[formation] == 0
                || particle.formations.locality[formation] as usize != locality
            {
                available = 0.0;
            } else {
                available *= particle.formations.availability[formation]
                    * particle.formations.effective_readiness(formation);
            }
        }
        if available > 0.0 {
            source_delays.push((
                particle.security_posts.microzone[post] as usize,
                (1.0 - available) * response_decay,
            ));
        }
    }

    for patrol in 0..particle.patrols.formation.len() {
        let formation = particle.patrols.formation[patrol] as usize;
        if formation >= particle.formations.personnel.len()
            || particle.patrols.active.get(patrol).copied().unwrap_or(0) == 0
            || particle.patrols.next_available[patrol] > time
            || particle.formations.moving[formation] != 0
            || particle.formations.outside_pineland[formation] != 0
            || particle.formations.operational_status[formation] == 0
            || !organization_matches_side(
                particle,
                particle.formations.organization[formation] as usize,
                actor,
            )
        {
            continue;
        }
        let effective_fraction = particle.patrols.response_fraction[patrol]
            * particle.formations.availability[formation]
            * particle.formations.effective_readiness(formation);
        if effective_fraction > 0.0 {
            source_delays.push((
                particle.patrols.route_target[patrol] as usize,
                (1.0 - effective_fraction) * response_decay,
            ));
        }
    }

    for formation in 0..particle.formations.personnel.len() {
        if particle.formations.locality[formation] as usize != locality
            || particle.formations.active[formation] == 0
            || particle.formations.moving[formation] != 0
            || particle.formations.outside_pineland[formation] != 0
            || particle.formations.operational_status[formation] == 0
            || particle.formations.personnel[formation] <= 0.0
            || !organization_matches_side(
                particle,
                particle.formations.organization[formation] as usize,
                actor,
            )
        {
            continue;
        }
        let effective_fraction = 0.30
            * particle.formations.availability[formation]
            * particle.formations.effective_readiness(formation);
        if effective_fraction > 0.0 {
            source_delays.push((
                particle.formations.microzone[formation] as usize,
                (1.0 - effective_fraction) * response_decay,
            ));
        }
    }

    let mut distances = vec![f64::INFINITY; topology.microzone_count()];
    let mut paths = Vec::with_capacity(source_delays.len());
    for (source, _) in &source_delays {
        paths.push(dijkstra_local(topology, locality, *source));
    }
    for target in topology.zones_for_locality(locality.into()) {
        let mut best = f64::INFINITY;
        for ((_, delay), path) in source_delays.iter().zip(&paths) {
            let candidate = *delay + path[target];
            if candidate < best {
                best = candidate;
            }
        }
        distances[target] = best;
    }
    distances
}

pub fn refresh(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    time: f64,
) {
    // Python closes mobile patrol exposure before applying the physical
    // operator.  This is a separate state transition from the response
    // calculation and is intentionally idempotent at a fixed timestamp.
    crate::patrol::advance_all_presence_memory(particle, topology, config, time);

    let zone_count = topology.microzone_count();
    let memory_days = config.physical.presence_memory_days.max(f64::MIN_POSITIVE);
    for zone in 0..zone_count {
        let government_age = (time - particle.zones.government_presence_updated_at[zone]).max(0.0);
        let insurgent_age = (time - particle.zones.insurgent_presence_updated_at[zone]).max(0.0);
        particle.zones.government_presence[zone] *= python_exp(-government_age / memory_days);
        particle.zones.insurgent_presence[zone] *= python_exp(-insurgent_age / memory_days);
        particle.zones.government_presence_updated_at[zone] = time;
        particle.zones.insurgent_presence_updated_at[zone] = time;
    }

    // The reference computes raw reach independently for both sides and then
    // applies a symmetric contestation transform.  Keeping the raw arrays
    // separate prevents iteration order from changing the result.
    let mut raw_government = vec![0.0; zone_count];
    let mut raw_insurgent = vec![0.0; zone_count];
    for locality in 0..topology.locality_count() {
        let government_response = response_distances(particle, topology, config, locality, 0, time);
        let insurgent_response = response_distances(particle, topology, config, locality, 1, time);
        // The locality zone count is small and fixed in Pineland.  Use a
        // temporary vector rather than a map so the fold order is explicit.
        let zones = topology
            .zones_for_locality(locality.into())
            .collect::<Vec<_>>();
        let mut post_values = vec![[0.0f64; 2]; zone_count];
        for post in 0..particle.security_posts.locality.len() {
            if particle.security_posts.locality[post] as usize != locality
                || particle
                    .security_posts
                    .staffed
                    .get(post)
                    .copied()
                    .unwrap_or(1)
                    == 0
            {
                continue;
            }
            let zone = particle.security_posts.microzone[post] as usize;
            if zone >= zone_count {
                continue;
            }
            let organization = particle.security_posts.organization[post] as usize;
            let actor = if organization_matches_side(particle, organization, 0) {
                Some(0)
            } else if organization_matches_side(particle, organization, 1) {
                Some(1)
            } else {
                None
            };
            let Some(actor) = actor else { continue };
            let mut effective_presence = particle.security_posts.presence[post];
            let formation = particle.security_posts.formation[post];
            if formation != u32::MAX {
                let formation = formation as usize;
                if formation >= particle.formations.personnel.len()
                    || particle.formations.moving[formation] != 0
                    || particle.formations.outside_pineland[formation] != 0
                    || particle.formations.operational_status[formation] == 0
                    || particle.formations.locality[formation] as usize != locality
                {
                    effective_presence = 0.0;
                } else {
                    effective_presence *= particle.formations.availability[formation]
                        * particle.formations.effective_readiness(formation);
                }
            }
            post_values[zone][actor] += effective_presence;
        }
        let mut formation_values = vec![[0.0f64; 2]; zone_count];
        let denominator = 250.0f64.max(particle.locality.population[locality] * 0.002);
        for formation in 0..particle.formations.personnel.len() {
            if particle.formations.locality[formation] as usize != locality
                || particle.formations.active[formation] == 0
                || particle.formations.moving[formation] != 0
                || particle.formations.outside_pineland[formation] != 0
                || particle.formations.operational_status[formation] == 0
                || particle.formations.personnel[formation] <= 0.0
            {
                continue;
            }
            let actor = if organization_matches_side(
                particle,
                particle.formations.organization[formation] as usize,
                0,
            ) {
                Some(0)
            } else if organization_matches_side(
                particle,
                particle.formations.organization[formation] as usize,
                1,
            ) {
                Some(1)
            } else {
                None
            };
            let Some(actor) = actor else { continue };
            let zone = particle.formations.microzone[formation] as usize;
            if zone >= zone_count || topology.microzone_to_locality[zone] as usize != locality {
                continue;
            }
            formation_values[zone][actor] += config.physical.formation_presence_gain
                * particle.formations.effective_strength(formation)
                / denominator;
        }
        for zone in zones {
            let government_presence = 1.0
                - python_exp(
                    -(particle.zones.government_presence[zone]
                        + config.physical.fixed_post_presence_gain * post_values[zone][0]
                        + formation_values[zone][0]),
                );
            let insurgent_presence = 1.0
                - python_exp(
                    -(particle.zones.insurgent_presence[zone]
                        + config.physical.fixed_post_presence_gain * post_values[zone][1]
                        + formation_values[zone][1]),
                );
            let government_response = government_response[zone];
            let insurgent_response = insurgent_response[zone];
            raw_government[zone] = clamp01(
                0.55 * government_presence
                    + 0.45
                        * if government_response.is_infinite() {
                            0.0
                        } else {
                            python_exp(-government_response / config.physical.response_decay_hours)
                        },
            );
            raw_insurgent[zone] = clamp01(
                0.55 * insurgent_presence
                    + 0.45
                        * if insurgent_response.is_infinite() {
                            0.0
                        } else {
                            python_exp(-insurgent_response / config.physical.response_decay_hours)
                        },
            );
        }
    }

    for locality in 0..topology.locality_count() {
        let mut government = 0.0;
        let mut insurgent = 0.0;
        for zone in topology.zones_for_locality(locality.into()) {
            let government_value =
                clamp01(raw_government[zone] * (1.0 - 0.35 * raw_insurgent[zone]));
            let insurgent_value =
                clamp01(raw_insurgent[zone] * (1.0 - 0.35 * raw_government[zone]));
            particle.zones.government_control[zone] = government_value;
            particle.zones.insurgent_control[zone] = insurgent_value;
            government += particle.zones.population_share[zone] * government_value;
            insurgent += particle.zones.population_share[zone] * insurgent_value;
        }
        let offset = locality * CONTROL_DIMENSIONS;
        particle.locality.government_control[offset + 1] = clamp01(government);
        particle.locality.insurgent_control[offset + 1] = clamp01(insurgent);
    }
    if std::env::var_os("PINELAND_PHYS_TRACE").is_some() && time >= 1.0 {
        eprintln!(
            "PHYS locality0 gphys={:.17} iphys={:.17} z0g={:.17} z0i={:.17} memg={:.17} memi={:.17}",
            particle.locality.government_control[1],
            particle.locality.insurgent_control[1],
            particle.zones.government_control[0],
            particle.zones.insurgent_control[0],
            particle.zones.government_presence[0],
            particle.zones.insurgent_presence[0]
        );
        let nonzero = particle
            .zones
            .government_presence
            .iter()
            .enumerate()
            .filter(|(_, value)| **value > 0.0)
            .map(|(zone, value)| format!("{}:{:.17}", zone, value))
            .collect::<Vec<_>>();
        eprintln!("PHYS memories {}", nonzero.join(","));
    }
}

pub fn record_presence(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    time: f64,
) {
    for formation in 0..particle.formations.personnel.len() {
        if particle.formations.active[formation] == 0 {
            continue;
        }
        let zone = particle.formations.microzone[formation] as usize;
        if zone >= topology.microzone_count() {
            continue;
        }
        let presence = clamp01(
            particle.formations.personnel[formation] / 1000.0
                * particle.formations.availability[formation],
        );
        let insurgent = particle.formations.organization[formation] as usize == crate::INSURGENT;
        let target = if insurgent {
            &mut particle.zones.insurgent_presence
        } else {
            &mut particle.zones.government_presence
        };
        let updated = if insurgent {
            &mut particle.zones.insurgent_presence_updated_at
        } else {
            &mut particle.zones.government_presence_updated_at
        };
        let gain = if insurgent {
            config.physical.formation_presence_gain * 0.85
        } else {
            config.physical.formation_presence_gain
        };
        target[zone] = clamp01(target[zone] + presence * gain);
        updated[zone] = time;
    }
}

pub fn response_time(
    particle: &ParticleState,
    topology: &StaticTopology,
    locality: usize,
    actor: u8,
    target_zone: usize,
    config: &SimulationConfig,
    now: f64,
) -> f64 {
    if target_zone >= topology.microzone_count() {
        return f64::INFINITY;
    }
    let source_zone = topology.primary_zone[locality];
    let distance = topology.distance(source_zone.into(), target_zone.into());
    let source = if actor == 0 {
        particle.zones.government_presence[source_zone as usize]
    } else {
        particle.zones.insurgent_presence[source_zone as usize]
    };
    if source <= 0.0 {
        return f64::INFINITY;
    }
    let age = (now
        - if actor == 0 {
            particle.zones.government_presence_updated_at[source_zone as usize]
        } else {
            particle.zones.insurgent_presence_updated_at[source_zone as usize]
        })
    .max(0.0);
    distance * particle.locality.terrain_friction[locality] / (1.0 + source)
        + age * config.physical.response_decay_hours / 24.0
}
