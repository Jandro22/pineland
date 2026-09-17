use pineland_core::config::SimulationConfig;
use pineland_model::SimulationEngine;
use std::error::Error;

fn main() -> Result<(), Box<dyn Error>> {
    let mut c = SimulationConfig::load("tmp/parity300.json")?;
    c.seed = 16021456112345678901;
    c.horizon_days = 90.0;
    let mut e = SimulationEngine::new(c)?;
    e.advance_until(90.0)?;
    println!(
        "idx,org,locality,origin,dest,execute,arrives,travel,distance,cost,seq,status,purpose"
    );
    let p = &e.particle;
    for i in 0..p.formations.personnel.len() {
        println!(
            "{},{},{},{},{},{:.17},{:.17},{:.17},{:.17},{:.17},{},{},{}",
            i,
            p.formations.organization[i],
            p.formations.locality[i],
            p.formations.movement_origin[i],
            p.formations.movement_destination[i],
            p.formations.movement_execute_at[i],
            p.formations.movement_arrives_at[i],
            p.formations.movement_travel_hours[i],
            p.formations.movement_distance_km[i],
            p.formations.movement_supply_cost[i],
            p.formations.movement_order_sequence[i],
            p.formations.movement_status[i],
            p.formations.movement_purpose[i]
        );
    }
    Ok(())
}
