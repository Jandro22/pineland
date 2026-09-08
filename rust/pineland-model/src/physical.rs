//! Physical presence, microzone control, and response-time fields.

use pineland_core::config::SimulationConfig;
use pineland_core::state::{clamp01, ParticleState, CONTROL_DIMENSIONS};
use pineland_core::topology::StaticTopology;

pub fn refresh(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    time: f64,
) {
    let zone_count = topology.microzone_count();
    for zone in 0..zone_count {
        let gov_age = (time - particle.zones.government_presence_updated_at[zone]).max(0.0);
        let ins_age = (time - particle.zones.insurgent_presence_updated_at[zone]).max(0.0);
        let memory = config.physical.presence_memory_days.max(f64::MIN_POSITIVE);
        particle.zones.government_presence[zone] *= (-gov_age / memory).exp();
        particle.zones.insurgent_presence[zone] *= (-ins_age / memory).exp();
        // The decay is accounted only for the elapsed interval since the
        // previous refresh.  Leaving the old timestamp in place would apply
        // the entire age again at every tick and make presence disappear
        // quadratically fast in event time.
        particle.zones.government_presence_updated_at[zone] = time;
        particle.zones.insurgent_presence_updated_at[zone] = time;
        let locality = topology.microzone_to_locality[zone] as usize;
        let base = particle.locality.government_control[locality * CONTROL_DIMENSIONS + 1];
        let government = clamp01(
            base * 0.25
                + particle.zones.government_presence[zone]
                    * config.physical.formation_presence_gain,
        );
        let insurgent = clamp01(
            particle.zones.insurgent_presence[zone] * config.physical.formation_presence_gain
                + particle.zones.insurgent_control[zone] * 0.25,
        );
        particle.zones.government_control[zone] = government;
        particle.zones.insurgent_control[zone] = insurgent;
    }
    // Fixed posts contribute persistent, separately auditable presence after
    // mobile presence memory has decayed.  Their state is SoA and therefore
    // remains cheap to update at every physical refresh boundary.
    for post in 0..particle.security_posts.locality.len() {
        if particle.security_posts.staffed[post] == 0 {
            continue;
        }
        let zone = particle.security_posts.microzone[post] as usize;
        if zone >= zone_count {
            continue;
        }
        let gain =
            config.physical.fixed_post_presence_gain * particle.security_posts.reliability[post];
        particle.zones.government_presence[zone] = clamp01(
            particle.zones.government_presence[zone]
                + particle.security_posts.presence[post] * gain,
        );
        particle.zones.government_presence_updated_at[zone] = time;
        particle.security_posts.updated_at[post] = time;
    }
    for locality in 0..topology.locality_count() {
        let mut gov = 0.0;
        let mut ins = 0.0;
        let mut denominator = 0.0;
        for zone in topology.zones_for_locality(locality.into()) {
            let weight = particle.zones.population_share[zone].max(0.0);
            gov += weight * particle.zones.government_control[zone];
            ins += weight * particle.zones.insurgent_control[zone];
            denominator += weight;
        }
        let offset = locality * CONTROL_DIMENSIONS;
        let gov = if denominator > 0.0 {
            gov / denominator
        } else {
            0.0
        };
        let ins = if denominator > 0.0 {
            ins / denominator
        } else {
            0.0
        };
        particle.locality.government_control[offset + 1] = gov;
        particle.locality.insurgent_control[offset + 1] = ins;
        particle.locality.government_control[offset + 6] = clamp01(
            (particle.locality.government_control[offset]
                + gov
                + particle.locality.government_control[offset + 2])
                / 3.0,
        );
        particle.locality.insurgent_control[offset + 6] =
            clamp01((ins + particle.locality.insurgent_governance[locality]) / 2.0);
        particle.locality.violence[locality] = clamp01(particle.locality.violence[locality]);
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
