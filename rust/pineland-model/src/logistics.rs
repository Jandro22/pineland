//! Conserved supply production, consumption, resupply, and readiness.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{python_sum, PyRandomCompat};
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

pub fn update(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    elapsed_days: f64,
    time: f64,
) {
    let dt = elapsed_days.max(0.0);
    let _expired = crate::access::decay(particle, time, dt, config);
    reconcile_source_production(particle, topology, config);
    // The Python oracle reconciles carrying capacity to current personnel at
    // the start of every logistics event.  Combat, recruitment, and peace
    // transitions can change personnel without changing the materiel already
    // carried; preserve that stock while shrinking/growing the doctrinal
    // capacity to the current force size.
    for formation in 0..particle.formations.personnel.len() {
        let doctrinal_capacity = (particle.formations.personnel[formation]
            * config.logistics.formation_supply_days)
            .max(0.0);
        particle.formations.supply_capacity[formation] =
            doctrinal_capacity.max(particle.formations.supply_stock[formation]);
        particle.formations.sustainment[formation] = supply_ratio(particle, formation);
    }
    for source in 0..particle.logistics.source_stock.len() {
        let production = particle.logistics.source_production[source] * dt;
        let available_capacity = (particle.logistics.source_capacity[source]
            - particle.logistics.source_stock[source])
            .max(0.0);
        let produced = production.min(available_capacity);
        particle.logistics.source_stock[source] += produced;
        particle.logistics.cumulative_produced += produced;
    }
    for formation in 0..particle.formations.personnel.len() {
        if particle.formations.active[formation] == 0 || particle.formations.moving[formation] != 0
        {
            continue;
        }
        let personnel = particle.formations.personnel[formation].max(0.0);
        let demand = personnel
            * particle.formations.availability[formation]
            * config.logistics.presence_consumption_per_person_day
            * dt;
        let consumed = demand.min(particle.formations.supply_stock[formation]);
        let shortfall = (demand - consumed).max(0.0);
        particle.formations.supply_stock[formation] -= consumed;
        particle.formations.sustainment[formation] = supply_ratio(particle, formation);
        particle.logistics.cumulative_consumed += consumed;
        let fulfillment = if demand > 0.0 { consumed / demand } else { 1.0 };
        if shortfall > 0.0 {
            particle.formations.readiness[formation] = clamp01(
                particle.formations.readiness[formation]
                    - config.logistics.readiness_degradation_rate * (1.0 - fulfillment) * dt,
            );
            particle.formations.availability[formation] = clamp01(
                particle.formations.availability[formation]
                    - 0.5 * config.logistics.readiness_degradation_rate * (1.0 - fulfillment) * dt,
            );
            particle.formations.fatigue[formation] =
                clamp01(particle.formations.fatigue[formation] + 0.04 * (1.0 - fulfillment) * dt);
        } else {
            let organization = particle.formations.organization[formation];
            let locality = particle.formations.locality[formation];
            let near_source = particle
                .logistics
                .organization
                .iter()
                .zip(particle.logistics.locality.iter())
                .any(|(&source_organization, &source_locality)| {
                    source_organization == organization && source_locality == locality
                });
            let recovery = if near_source {
                config.logistics.readiness_recovery_near_source
            } else {
                config.logistics.readiness_recovery_remote
            };
            particle.formations.readiness[formation] =
                clamp01(particle.formations.readiness[formation] + recovery * dt);
            particle.formations.availability[formation] = clamp01(
                particle.formations.availability[formation]
                    + config.logistics.availability_recovery_rate * dt,
            );
            particle.formations.fatigue[formation] =
                clamp01(particle.formations.fatigue[formation] - recovery * dt);
            particle.formations.cohesion[formation] =
                clamp01(particle.formations.cohesion[formation] + 0.35 * recovery * dt);
        }
        particle.formations.sustainment[formation] = supply_ratio(particle, formation);
    }
    // Shipment and movement-order state is added below as the portable state
    // boundary grows; do not synthesize a different demand model here.
    let _ = rng;
    let _ = time;
}

fn reconcile_source_production(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
) {
    if config.logistics.source_capacity_model != "organization_manpower" {
        return;
    }
    let organization_count = particle.organizations.kind.len();
    for organization in 0..organization_count {
        let source_indices: Vec<usize> = particle
            .logistics
            .organization
            .iter()
            .enumerate()
            .filter_map(|(index, &candidate)| (candidate as usize == organization).then_some(index))
            .collect();
        if source_indices.is_empty() {
            continue;
        }
        let formation_indices: Vec<usize> = particle
            .formations
            .organization
            .iter()
            .enumerate()
            .filter_map(|(index, &candidate)| {
                (candidate as usize == organization && particle.formations.active[index] != 0)
                    .then_some(index)
            })
            .collect();
        // Match Python's per-organization dictionary accumulation exactly;
        // an optimized iterator reduction may reassociate the additions and
        // move a parity value by one ulp.
        let mut personnel = 0.0;
        for &formation in &formation_indices {
            personnel =
                round_binary64(personnel + particle.formations.personnel[formation].max(0.0));
        }
        let requirement = round_binary64(
            round_binary64(personnel * config.logistics.presence_consumption_per_person_day)
                * config.logistics.organization_sustainment_coverage,
        );
        let territorial = particle
            .organizations
            .kind
            .get(organization)
            .is_some_and(|kind| *kind == 1 || *kind == 2);
        let mut weights = Vec::with_capacity(source_indices.len());
        for &source in &source_indices {
            let locality = particle.logistics.locality[source];
            let weight = if territorial {
                let district = topology
                    .locality_to_district
                    .get(locality as usize)
                    .copied()
                    .unwrap_or(u32::MAX);
                particle
                    .locality
                    .district_population
                    .get(district as usize)
                    .copied()
                    .unwrap_or_else(|| {
                        topology
                            .district_population
                            .get(district as usize)
                            .copied()
                            .unwrap_or(0.0)
                    })
            } else {
                python_sum(
                    &formation_indices
                        .iter()
                        .filter(|&&formation| {
                            particle.formations.home_locality[formation] == locality
                        })
                        .map(|&formation| particle.formations.personnel[formation].max(0.0))
                        .collect::<Vec<_>>(),
                )
            };
            weights.push(weight);
        }
        let weight_total = python_sum(&weights);
        if weight_total <= 0.0 {
            weights.fill(1.0);
        }
        let total_weight = python_sum(&weights);
        if std::env::var_os("PINELAND_LOGISTICS_TRACE").is_some() && organization == 1 {
            eprintln!(
                "LOGISTICS_RECON organization={} personnel={:.17} requirement={:.17} weights={:?} total_weight={:.17}",
                organization, personnel, requirement, weights, total_weight
            );
        }
        for (&source, &weight) in source_indices.iter().zip(weights.iter()) {
            // Keep the two Python operations (multiply, then divide) as two
            // observable IEEE-754 boundaries; otherwise an optimized native
            // build may contract/reassociate them and differ by one ulp.
            let numerator = round_binary64(requirement * weight);
            let production = round_binary64(numerator / total_weight);
            particle.logistics.source_production[source] = production;
            particle.logistics.source_capacity[source] = particle.logistics.source_capacity[source]
                .max(particle.logistics.source_stock[source])
                .max(production / config.logistics.source_daily_production_fraction.max(1e-12));
            if std::env::var_os("PINELAND_LOGISTICS_TRACE").is_some() && organization == 1 {
                eprintln!(
                    "LOGISTICS_SOURCE source={} weight={:.17} production={:.17} capacity={:.17}",
                    source, weight, production, particle.logistics.source_capacity[source]
                );
            }
        }
    }
}

/// Force the same binary64 rounding boundary that CPython applies when a
/// float result is stored back into a Python object.  MSVC/LLVM may otherwise
/// retain an intermediate in a wider register across a short reduction,
/// which changes the last bit of parity-critical accumulations.
#[inline(never)]
fn round_binary64(value: f64) -> f64 {
    unsafe { std::ptr::read_volatile(&value) }
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

#[cfg(test)]
mod tests {
    use super::round_binary64;

    #[test]
    fn python_accumulation_rounds_at_each_addition() {
        let value = f64::from_bits(4_651_811_840_107_362_532);
        let mut total = 0.0;
        for _ in 0..9 {
            total = round_binary64(total + value);
        }
        assert_eq!(total.to_bits(), 4_666_063_465_490_677_759);
    }
}
