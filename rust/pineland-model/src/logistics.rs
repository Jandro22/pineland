//! Conserved supply production, consumption, resupply, and readiness.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::PyRandomCompat;
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

pub fn update(
    particle: &mut ParticleState,
    _topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
) {
    let dt = config.intervals.logistics.max(0.01);
    for organization in 0..particle.logistics.source_stock.len() {
        let production = particle.logistics.source_production[organization] * dt;
        particle.logistics.source_stock[organization] =
            (particle.logistics.source_stock[organization] + production).min(
                particle.logistics.source_capacity[organization]
                    * config.logistics.formation_supply_days.max(1.0),
            );
        particle.logistics.cumulative_produced += production;
    }
    for formation in 0..particle.formations.personnel.len() {
        if particle.formations.active[formation] == 0 {
            continue;
        }
        let personnel = particle.formations.personnel[formation].max(0.0);
        let presence_cost = personnel * config.logistics.presence_consumption_per_person_day * dt;
        let patrol_cost =
            personnel * config.logistics.patrol_consumption_per_person_hour * dt * 24.0;
        let cost = presence_cost + patrol_cost;
        let organization = particle.formations.organization[formation] as usize;
        let source_available = particle
            .logistics
            .source_stock
            .get(organization)
            .copied()
            .unwrap_or(0.0);
        let current = particle.formations.supply_stock[formation];
        let trigger = particle.formations.supply_capacity[formation]
            * config.logistics.resupply_trigger_fraction;
        if current < trigger && source_available > 0.0 {
            let requested = (particle.formations.supply_capacity[formation]
                * config.logistics.resupply_target_fraction
                - current)
                .max(0.0);
            let loss =
                requested * config.logistics.shipment_loss_per_travel_hour * (1.0 + rng.random());
            let delivered = (requested - loss).max(0.0).min(source_available);
            particle.logistics.source_stock[organization] -= delivered;
            particle.formations.supply_stock[formation] =
                (current + delivered).min(particle.formations.supply_capacity[formation]);
            particle.logistics.cumulative_shipped += requested;
            particle.logistics.cumulative_delivered += delivered;
            particle.logistics.cumulative_lost += (requested - delivered).max(0.0);
        }
        let consumed = cost.min(particle.formations.supply_stock[formation]);
        particle.formations.supply_stock[formation] -= consumed;
        particle.logistics.cumulative_consumed += consumed;
        if consumed + 1e-12 < cost {
            particle.formations.readiness[formation] = clamp01(
                particle.formations.readiness[formation]
                    - config.logistics.readiness_degradation_rate * dt * 0.1,
            );
        } else {
            particle.formations.readiness[formation] = clamp01(
                particle.formations.readiness[formation]
                    + config.logistics.readiness_recovery_remote * dt,
            );
        }
        particle.formations.availability[formation] = clamp01(
            particle.formations.availability[formation]
                + config.logistics.availability_recovery_rate
                    * dt
                    * (1.0 - particle.formations.availability[formation]),
        );
        particle.formations.fatigue[formation] =
            clamp01(particle.formations.fatigue[formation] * (1.0 - 0.02 * dt));
    }
    let _ = time;
}

pub fn supply_ratio(particle: &ParticleState, formation: usize) -> f64 {
    if particle
        .formations
        .supply_capacity
        .get(formation)
        .copied()
        .unwrap_or(0.0)
        <= 0.0
    {
        0.0
    } else {
        particle.formations.supply_stock[formation] / particle.formations.supply_capacity[formation]
    }
}
