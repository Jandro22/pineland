//! Read-only spatial topology shared by every particle.

use crate::config::SimulationConfig;
use crate::ids::{DistrictId, LocalityId, MicrozoneId};
use crate::rng::{python_sum, seed_from_namespace, PyRandomCompat};
use std::collections::HashSet;

#[derive(Clone, Debug, Default, PartialEq)]
pub struct CsrGraph {
    pub offsets: Vec<u32>,
    pub neighbors: Vec<u32>,
    pub weights: Vec<f64>,
}

impl CsrGraph {
    pub fn empty(node_count: usize) -> Self {
        Self {
            offsets: vec![0; node_count + 1],
            neighbors: Vec::new(),
            weights: Vec::new(),
        }
    }

    pub fn from_edges(node_count: usize, edges: &[(u32, u32, f64)], undirected: bool) -> Self {
        let mut rows: Vec<Vec<(u32, f64)>> = (0..node_count).map(|_| Vec::new()).collect();
        for &(from, to, weight) in edges {
            if (from as usize) < node_count && (to as usize) < node_count && weight.is_finite() {
                rows[from as usize].push((to, weight));
                if undirected {
                    rows[to as usize].push((from, weight));
                }
            }
        }
        for row in &mut rows {
            row.sort_by(|a, b| a.0.cmp(&b.0).then_with(|| a.1.total_cmp(&b.1)));
            row.dedup_by(|a, b| a.0 == b.0);
        }
        let mut offsets = Vec::with_capacity(node_count + 1);
        let mut neighbors = Vec::new();
        let mut weights = Vec::new();
        offsets.push(0);
        for row in rows {
            for (neighbor, weight) in row {
                neighbors.push(neighbor);
                weights.push(weight);
            }
            offsets.push(neighbors.len() as u32);
        }
        Self {
            offsets,
            neighbors,
            weights,
        }
    }

    /// Build a graph while preserving the first-seen neighbor order in the
    /// edge list.  Python's locality adjacency is an insertion-ordered dict;
    /// that order is observable by weighted choices in mobility and action
    /// processes, so sorting the rows would change otherwise identical RNG
    /// continuations.  Duplicate edges retain their first position and the
    /// minimum edge weight, matching the Python ``min`` assignment.
    pub fn from_edges_ordered(
        node_count: usize,
        edges: &[(u32, u32, f64)],
        undirected: bool,
    ) -> Self {
        let mut rows: Vec<Vec<(u32, f64)>> = (0..node_count).map(|_| Vec::new()).collect();
        for &(from, to, weight) in edges {
            if (from as usize) >= node_count || (to as usize) >= node_count || !weight.is_finite() {
                continue;
            }
            insert_ordered_edge(&mut rows[from as usize], to, weight);
            if undirected {
                insert_ordered_edge(&mut rows[to as usize], from, weight);
            }
        }
        let mut offsets = Vec::with_capacity(node_count + 1);
        let mut neighbors = Vec::new();
        let mut weights = Vec::new();
        offsets.push(0);
        for row in rows {
            for (neighbor, weight) in row {
                neighbors.push(neighbor);
                weights.push(weight);
            }
            offsets.push(neighbors.len() as u32);
        }
        Self {
            offsets,
            neighbors,
            weights,
        }
    }

    pub fn node_count(&self) -> usize {
        self.offsets.len().saturating_sub(1)
    }

    pub fn neighbors(&self, node: usize) -> impl Iterator<Item = (u32, f64)> + '_ {
        let start = self.offsets.get(node).copied().unwrap_or(0) as usize;
        let end = self.offsets.get(node + 1).copied().unwrap_or(start as u32) as usize;
        self.neighbors[start.min(self.neighbors.len())..end.min(self.neighbors.len())]
            .iter()
            .copied()
            .zip(
                self.weights[start.min(self.weights.len())..end.min(self.weights.len())]
                    .iter()
                    .copied(),
            )
    }
}

fn insert_ordered_edge(row: &mut Vec<(u32, f64)>, neighbor: u32, weight: f64) {
    if let Some((_, existing)) = row.iter_mut().find(|(candidate, _)| *candidate == neighbor) {
        *existing = existing.min(weight);
    } else {
        row.push((neighbor, weight));
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct StaticTopology {
    pub localities: Vec<LocalityId>,
    pub microzones: Vec<MicrozoneId>,
    pub districts: Vec<DistrictId>,
    pub locality_names: Vec<String>,
    pub district_names: Vec<String>,
    pub microzone_names: Vec<String>,
    pub locality_to_district: Vec<u32>,
    pub primary_zone: Vec<u32>,
    pub microzone_to_locality: Vec<u32>,
    pub locality_zone_offsets: Vec<u32>,
    pub zone_population_share: Vec<f64>,
    pub zone_infrastructure: Vec<f64>,
    pub zone_terrain_friction: Vec<f64>,
    pub zone_observability: Vec<f64>,
    /// Administrative police-post zone.  This is the minimum local
    /// graph-travel-time zone, which is distinct from the population-modal
    /// zone used by formation posts and patrols.
    pub locality_central_zone: Vec<u32>,
    pub locality_post_zone: Vec<u32>,
    pub x_km: Vec<f64>,
    pub y_km: Vec<f64>,
    /// Exogenous locality adjacency used by the Python geography generator.
    /// Keep this separate from the derived microzone physical graph: the
    /// social bridge generator consumes locality edges, including their
    /// minimum-cost weights, not arbitrary cross-locality microzone links.
    pub locality_edges: CsrGraph,
    pub physical_edges: CsrGraph,
    pub road_edges: CsrGraph,
    pub physical_distances: Vec<f64>,
    /// Initialization metadata generated from the same Pineland registry and
    /// streams as the Python oracle.  These are static case inputs, not
    /// particle-local mutable state.
    pub locality_kind: Vec<u8>,
    pub district_language_patterns: Vec<String>,
    pub locality_population: Vec<f64>,
    pub locality_economic_output: Vec<f64>,
    pub locality_infrastructure: Vec<f64>,
    pub locality_administrative_capacity: Vec<f64>,
    pub locality_terrain_friction: Vec<f64>,
    pub locality_observability: Vec<f64>,
    pub district_population: Vec<f64>,
    pub district_connectivity: Vec<f64>,
    pub district_urbanization: Vec<f64>,
}

#[derive(Clone, Debug)]
struct LocalitySeed {
    id: String,
    district: usize,
    name: String,
    kind: u8,
    population: f64,
    economic_output: f64,
    infrastructure: f64,
    administrative_capacity: f64,
    terrain_friction: f64,
    observability: f64,
    x_km: f64,
    y_km: f64,
}

// This is the frozen synthetic Pineland registry used by the Python
// generator.  Keep the order and literal values stable: world-generation RNG
// consumption is part of the scientific continuation contract.
type DistrictRegistryRow = (
    &'static str,
    &'static str,
    f64,
    f64,
    &'static str,
    f64,
    f64,
    f64,
);

const DISTRICTS: [DistrictRegistryRow; 17] = [
    (
        "D01",
        "Stonebridge Federal",
        1_450_000.0,
        0.82,
        "FS",
        0.0,
        0.0,
        0.95,
    ),
    ("D02", "Northpass", 310_000.0, 0.34, "AR", -72.0, 64.0, 0.35),
    ("D03", "Highpine", 370_000.0, 0.29, "AR", -45.0, 86.0, 0.25),
    (
        "D04", "Ironwood", 460_000.0, 0.42, "AR/FS", -54.0, 32.0, 0.55,
    ),
    (
        "D05",
        "Westreach",
        390_000.0,
        0.31,
        "AR/VE",
        -82.0,
        4.0,
        0.35,
    ),
    (
        "D06", "Redvale", 540_000.0, 0.48, "VE/FS", -38.0, -12.0, 0.65,
    ),
    ("D07", "Mossfield", 420_000.0, 0.36, "VE", -8.0, -34.0, 0.50),
    ("D08", "Cedar", 470_000.0, 0.45, "FS/VE", 12.0, -8.0, 0.75),
    ("D09", "Bracken", 580_000.0, 0.57, "FS", -8.0, 28.0, 0.80),
    (
        "D10",
        "Greenridge",
        440_000.0,
        0.39,
        "FS/TA",
        22.0,
        36.0,
        0.55,
    ),
    ("D11", "Kestrel", 720_000.0, 0.64, "TA/FS", 58.0, 34.0, 0.85),
    ("D12", "Eastmere", 490_000.0, 0.41, "TA", 78.0, 12.0, 0.50),
    ("D13", "Flint", 330_000.0, 0.28, "TA", 92.0, -18.0, 0.25),
    (
        "D14", "Juniper", 510_000.0, 0.52, "VE/TA/FS", 50.0, -28.0, 0.80,
    ),
    (
        "D15",
        "Lakemarch",
        630_000.0,
        0.61,
        "VE/FS",
        14.0,
        -58.0,
        0.85,
    ),
    (
        "D16", "Dovetail", 340_000.0, 0.30, "AR/TA", -52.0, -66.0, 0.30,
    ),
    ("D17", "Alder", 350_000.0, 0.38, "FS/AR", 18.0, 68.0, 0.70),
];

#[derive(Clone, Debug)]
pub struct PinelandTopologyGeneration {
    pub topology: StaticTopology,
    /// `world-generation` after district allocation, locality weights, and
    /// locality attributes.  Person/party generation continues this stream.
    pub world_rng: PyRandomCompat,
    /// `geography-generation` after coordinate jitter. Retaining this stream
    /// makes the topology construction boundary auditable rather than
    /// silently dropping a consumed initialization stream.
    pub geography_rng: PyRandomCompat,
    /// `physical-world-generation` after microzone and edge construction.
    /// Zone-belief noise is generated by the Python physical layer from this
    /// exact continuation point, so it cannot be safely recreated by
    /// reseeding after topology construction.
    pub physical_rng: PyRandomCompat,
}

impl StaticTopology {
    pub fn new(locality_count: usize) -> Self {
        Self::synthetic(locality_count.max(1), 3)
    }

    pub fn synthetic(locality_count: usize, microzones_per_locality: usize) -> Self {
        let locality_count = locality_count.max(1);
        let zones_per_locality = microzones_per_locality.max(1);
        let district_count = 17usize.min(locality_count).max(1);
        let districts: Vec<DistrictId> = (0..district_count)
            .map(|index| DistrictId(index as u32))
            .collect();
        let district_names: Vec<String> = districts
            .iter()
            .map(|id| format!("D{:02}", id.get() + 1))
            .collect();
        let localities: Vec<LocalityId> = (0..locality_count)
            .map(|index| LocalityId(index as u32))
            .collect();
        let locality_names = localities
            .iter()
            .map(|id| format!("L{:03}", id.get() + 1))
            .collect();
        let mut locality_to_district = Vec::with_capacity(locality_count);
        let mut x_km = Vec::with_capacity(locality_count);
        let mut y_km = Vec::with_capacity(locality_count);
        for index in 0..locality_count {
            locality_to_district.push((index * district_count / locality_count) as u32);
            let angle = (index as f64) * std::f64::consts::TAU / locality_count as f64;
            let radius = 25.0 + 3.0 * ((index * 17 % 11) as f64);
            x_km.push(radius * angle.cos());
            y_km.push(radius * angle.sin());
        }

        let mut microzones = Vec::with_capacity(locality_count * zones_per_locality);
        let mut microzone_names = Vec::with_capacity(microzones.capacity());
        let mut microzone_to_locality = Vec::with_capacity(microzones.capacity());
        let mut primary_zone = Vec::with_capacity(locality_count);
        let mut locality_zone_offsets = Vec::with_capacity(locality_count + 1);
        locality_zone_offsets.push(0);
        for locality in 0..locality_count {
            primary_zone.push((locality * zones_per_locality) as u32);
            for zone in 0..zones_per_locality {
                let id = microzones.len() as u32;
                microzones.push(MicrozoneId(id));
                microzone_names.push(format!("L{:03}-Z{:02}", locality + 1, zone + 1));
                microzone_to_locality.push(locality as u32);
            }
            locality_zone_offsets.push(microzones.len() as u32);
        }

        let mut physical_edges = Vec::new();
        let mut road_edges = Vec::new();
        let zone_count = microzones.len();
        for locality in 0..locality_count {
            let start = locality * zones_per_locality;
            for zone in 0..zones_per_locality.saturating_sub(1) {
                let from = (start + zone) as u32;
                let to = (start + zone + 1) as u32;
                physical_edges.push((from, to, 1.0 + zone as f64 * 0.1));
                road_edges.push((from, to, 1.0));
            }
        }
        // A stable ring plus second-neighbor links keeps every locality
        // reachable while retaining a sparse, geography-like graph.
        for locality in 0..locality_count {
            let next = (locality + 1) % locality_count;
            let next2 = (locality + 2) % locality_count;
            let from = primary_zone[locality];
            let to = primary_zone[next];
            let to2 = primary_zone[next2];
            let distance = euclidean(x_km[locality], y_km[locality], x_km[next], y_km[next]);
            let distance2 = euclidean(x_km[locality], y_km[locality], x_km[next2], y_km[next2]);
            physical_edges.push((from, to, distance.max(1.0)));
            road_edges.push((from, to, (distance / 55.0).max(0.1)));
            if next2 != locality {
                physical_edges.push((from, to2, distance2.max(1.0)));
                road_edges.push((from, to2, (distance2 / 55.0).max(0.1)));
            }
        }
        let physical_graph = CsrGraph::from_edges(zone_count, &physical_edges, true);
        let road_graph = CsrGraph::from_edges(zone_count, &road_edges, true);
        let locality_edge_rows = (0..locality_count)
            .map(|locality| {
                let next = (locality + 1) % locality_count;
                let distance = euclidean(x_km[locality], y_km[locality], x_km[next], y_km[next]);
                (locality as u32, next as u32, distance.max(1.0))
            })
            .collect::<Vec<_>>();
        let locality_graph =
            CsrGraph::from_edges_ordered(locality_count, &locality_edge_rows, true);
        let mut physical_distances = vec![f64::INFINITY; locality_count * locality_count];
        for source in 0..locality_count {
            physical_distances[source * locality_count + source] = 0.0;
            for target in 0..locality_count {
                if source != target {
                    physical_distances[source * locality_count + target] =
                        euclidean(x_km[source], y_km[source], x_km[target], y_km[target]);
                }
            }
        }
        Self {
            localities,
            microzones,
            districts,
            locality_names,
            district_names,
            microzone_names,
            locality_to_district,
            primary_zone: primary_zone.clone(),
            microzone_to_locality,
            locality_zone_offsets,
            zone_population_share: vec![
                1.0 / zones_per_locality as f64;
                locality_count * zones_per_locality
            ],
            zone_infrastructure: vec![0.5; locality_count * zones_per_locality],
            zone_terrain_friction: vec![1.0; locality_count * zones_per_locality],
            zone_observability: vec![0.5; locality_count * zones_per_locality],
            locality_central_zone: primary_zone.clone(),
            locality_post_zone: primary_zone.clone(),
            x_km,
            y_km,
            locality_edges: locality_graph,
            physical_edges: physical_graph,
            road_edges: road_graph,
            physical_distances,
            locality_kind: vec![1; locality_count],
            district_language_patterns: vec!["FS".to_string(); district_count],
            locality_population: vec![0.0; locality_count],
            locality_economic_output: vec![0.0; locality_count],
            locality_infrastructure: vec![0.5; locality_count],
            locality_administrative_capacity: vec![0.5; locality_count],
            locality_terrain_friction: vec![1.0; locality_count],
            locality_observability: vec![0.5; locality_count],
            district_population: vec![0.0; district_count],
            district_connectivity: vec![0.5; district_count],
            district_urbanization: vec![0.35; district_count],
        }
    }

    /// Generate the synthetic Pineland topology with the Python generator's
    /// exact registry, stream partition, locality ordering, and physical
    /// microzone construction.  The returned world RNG is intentionally
    /// retained so person generation can continue at the exact boundary
    /// rather than silently reseeding after geography.
    pub fn pineland(
        config: &SimulationConfig,
        initialization_seed: u64,
    ) -> PinelandTopologyGeneration {
        if config.locality_count < DISTRICTS.len() {
            return PinelandTopologyGeneration {
                topology: Self::synthetic(
                    config.locality_count,
                    config.physical.town_microzones.clamp(1, 8),
                ),
                world_rng: PyRandomCompat::from_seed(seed_from_namespace(
                    initialization_seed,
                    &config.random_stream_namespace,
                    "world-generation",
                )),
                geography_rng: PyRandomCompat::from_seed(seed_from_namespace(
                    initialization_seed,
                    &config.random_stream_namespace,
                    "geography-generation",
                )),
                physical_rng: PyRandomCompat::from_seed(seed_from_namespace(
                    initialization_seed,
                    &config.random_stream_namespace,
                    "physical-world-generation",
                )),
            };
        }

        let mut world_rng = PyRandomCompat::from_seed(seed_from_namespace(
            initialization_seed,
            &config.random_stream_namespace,
            "world-generation",
        ));
        let mut geography_rng = PyRandomCompat::from_seed(seed_from_namespace(
            initialization_seed,
            &config.random_stream_namespace,
            "geography-generation",
        ));
        let total_population: f64 = DISTRICTS.iter().map(|row| row.2).sum();
        let mut extra = [0usize; 17];
        for _ in 0..config.locality_count - DISTRICTS.len() {
            let draw = world_rng.random() * total_population;
            let mut cumulative = 0.0;
            for (index, row) in DISTRICTS.iter().enumerate() {
                cumulative += row.2;
                if draw <= cumulative {
                    extra[index] += 1;
                    break;
                }
            }
        }

        let mut locality_seeds = Vec::with_capacity(config.locality_count);
        for (district_index, row) in DISTRICTS.iter().enumerate() {
            let (
                district_id,
                district_name,
                population,
                urban,
                _language,
                center_x,
                center_y,
                connectivity,
            ) = *row;
            let count = 1 + extra[district_index];
            let mut weights = (0..count)
                // CPython calls normalvariate(0, 0.8) directly.  Scaling a
                // unit draw afterwards is mathematically equivalent but can
                // differ by one ulp and therefore changes the normalized
                // locality shares in an exact-parity certificate.
                .map(|_| PyRandomCompat::python_exp(world_rng.normalvariate(0.0, 0.8)).max(0.1))
                .collect::<Vec<_>>();
            weights[0] *= if urban > 0.55 { 2.5 } else { 1.4 };
            let denominator = python_sum(&weights);
            for (index, weight) in weights.iter().enumerate() {
                let share = *weight / denominator;
                let kind = if index == 0 && urban >= 0.55 {
                    0 // city
                } else if index == 0 || share > 0.18 {
                    1 // town
                } else {
                    2 // village-cluster
                };
                let capacity = clamp(
                    0.25 + 0.55 * connectivity + world_rng.uniform(-0.12, 0.12),
                    0.08,
                    0.95,
                );
                let terrain_friction =
                    clamp(2.0 - connectivity + world_rng.uniform(-0.2, 0.2), 0.6, 2.4);
                let locality_id = format!("{district_id}-L{:02}", index + 1);
                let (x_km, y_km) = if index == 0 {
                    (center_x, center_y)
                } else {
                    let angle = 2.0 * std::f64::consts::PI * (index - 1) as f64
                        / (count.saturating_sub(1).max(1) as f64);
                    let radius = geography_rng
                        .uniform(10.0, 10.0f64.max(config.geography.coordinate_jitter_km));
                    (
                        center_x + radius * angle.cos(),
                        center_y + radius * angle.sin(),
                    )
                };
                let locality_population = python_round(population * share);
                let economic_output = population * share * world_rng.uniform(0.7, 1.3);
                let infrastructure =
                    clamp(connectivity + world_rng.uniform(-0.15, 0.15), 0.08, 0.98);
                let observability =
                    clamp(0.35 + urban * 0.5 + world_rng.uniform(-0.1, 0.1), 0.1, 0.95);
                // The Python Locality constructor draws governance leakage
                // during world generation.  The dense native state does not
                // yet expose that field, but the draw is still part of the
                // frozen world-generation stream and must be consumed here.
                let _governance_leakage = world_rng.uniform(0.05, 0.28);
                locality_seeds.push(LocalitySeed {
                    id: locality_id,
                    district: district_index,
                    name: if index == 0 {
                        district_name.to_string()
                    } else {
                        format!("{district_name} {} {index}", kind_name(kind))
                    },
                    kind,
                    population: locality_population,
                    economic_output,
                    infrastructure,
                    administrative_capacity: capacity,
                    terrain_friction,
                    observability,
                    x_km,
                    y_km,
                });
            }
        }
        // Registry order is also lexical order for D01..D17 and L01.., but
        // retain an explicit sort so future registry edits cannot change the
        // numeric ID contract accidentally.
        locality_seeds.sort_by(|a, b| a.id.cmp(&b.id));

        let locality_count = locality_seeds.len();
        let district_count = DISTRICTS.len();
        let localities: Vec<LocalityId> = (0..locality_count)
            .map(|index| LocalityId(index as u32))
            .collect();
        let districts: Vec<DistrictId> = (0..district_count)
            .map(|index| DistrictId(index as u32))
            .collect();
        let locality_names = locality_seeds
            .iter()
            .map(|seed| seed.name.clone())
            .collect();
        let district_names = DISTRICTS.iter().map(|row| row.1.to_string()).collect();
        let locality_to_district = locality_seeds
            .iter()
            .map(|seed| seed.district as u32)
            .collect::<Vec<_>>();
        let x_km = locality_seeds
            .iter()
            .map(|seed| seed.x_km)
            .collect::<Vec<_>>();
        let y_km = locality_seeds
            .iter()
            .map(|seed| seed.y_km)
            .collect::<Vec<_>>();

        let mut microzones = Vec::new();
        let mut microzone_names = Vec::new();
        let mut microzone_to_locality = Vec::new();
        let mut primary_zone = Vec::with_capacity(locality_count);
        let mut locality_zone_offsets = vec![0u32];
        let mut population_share = Vec::new();
        let mut zone_infrastructure = Vec::new();
        let mut zone_terrain = Vec::new();
        let mut zone_observability = Vec::new();
        let mut physical_edge_rows: Vec<(u32, u32, f64)> = Vec::new();
        let mut road_edge_rows: Vec<(u32, u32, f64)> = Vec::new();
        let mut physical_rng = PyRandomCompat::from_seed(seed_from_namespace(
            initialization_seed,
            &config.random_stream_namespace,
            "physical-world-generation",
        ));
        for (locality_index, seed) in locality_seeds.iter().enumerate() {
            let zone_count = match seed.kind {
                0 => config.physical.city_microzones,
                1 => config.physical.town_microzones,
                _ => config.physical.village_microzones,
            };
            let raw_shares = (0..zone_count)
                // Preserve the Python call boundary for the same reason as
                // the locality weights above: normalvariate(0, 0.45) must be
                // evaluated before the exponential, not reconstructed by a
                // post-hoc multiplication of a unit normal.
                .map(|_| PyRandomCompat::python_exp(physical_rng.normalvariate(0.0, 0.45)))
                .collect::<Vec<_>>();
            let denominator = python_sum(&raw_shares);
            let start = microzones.len();
            primary_zone.push(start as u32);
            for (zone_index, raw_share) in raw_shares.iter().enumerate() {
                microzones.push(MicrozoneId(microzones.len() as u32));
                microzone_names.push(format!("{}-Z{:02}", seed.id, zone_index + 1));
                microzone_to_locality.push(locality_index as u32);
                population_share.push(*raw_share / denominator);
                zone_infrastructure.push(clamp(
                    seed.infrastructure + physical_rng.uniform(-0.18, 0.18),
                    0.05,
                    1.0,
                ));
                zone_terrain
                    .push((seed.terrain_friction * physical_rng.uniform(0.75, 1.25)).max(0.35));
                zone_observability.push(clamp(
                    seed.observability + physical_rng.uniform(-0.2, 0.2),
                    0.05,
                    1.0,
                ));
            }
            let zone_ids: Vec<usize> = (start..microzones.len()).collect();
            for index in 0..zone_ids.len().saturating_sub(1) {
                let first = zone_ids[index];
                let second = zone_ids[index + 1];
                let distance = physical_rng.uniform(0.25, 1.4);
                let road = clamp(
                    seed.infrastructure * physical_rng.uniform(0.75, 1.2),
                    0.1,
                    1.0,
                );
                let travel = distance * ((zone_terrain[first] + zone_terrain[second]) / 2.0)
                    / road.max(0.1)
                    / 20.0;
                physical_edge_rows.push((first as u32, second as u32, travel));
                road_edge_rows.push((first as u32, second as u32, travel));
            }
            if zone_ids.len() > 2 {
                let first = *zone_ids.last().expect("zone exists");
                let second = zone_ids[0];
                let distance = physical_rng.uniform(0.4, 1.8);
                let road = clamp(
                    seed.infrastructure * physical_rng.uniform(0.7, 1.15),
                    0.1,
                    1.0,
                );
                let travel = distance * ((zone_terrain[first] + zone_terrain[second]) / 2.0)
                    / road.max(0.1)
                    / 20.0;
                physical_edge_rows.push((first as u32, second as u32, travel));
                road_edge_rows.push((first as u32, second as u32, travel));
            }
            for first_index in 0..zone_ids.len() {
                for second_index in first_index + 2..zone_ids.len() {
                    let first = zone_ids[first_index];
                    let second = zone_ids[second_index];
                    if physical_edge_rows.iter().any(|(a, b, _)| {
                        (*a as usize == first && *b as usize == second)
                            || (*a as usize == second && *b as usize == first)
                    }) {
                        continue;
                    }
                    if physical_rng.random() >= config.physical.extra_edge_probability {
                        continue;
                    }
                    let distance = physical_rng.uniform(0.5, 2.2);
                    let road = clamp(
                        seed.infrastructure * physical_rng.uniform(0.65, 1.2),
                        0.1,
                        1.0,
                    );
                    let travel = distance * ((zone_terrain[first] + zone_terrain[second]) / 2.0)
                        / road.max(0.1)
                        / 20.0;
                    physical_edge_rows.push((first as u32, second as u32, travel));
                    road_edge_rows.push((first as u32, second as u32, travel));
                }
            }
            locality_zone_offsets.push(microzones.len() as u32);
        }

        let mut adjacency_edges: Vec<(usize, usize, f64)> = Vec::new();
        let mut seen_locality_edges = HashSet::new();
        let mut connect = |left: usize, right: usize| {
            if left == right {
                return;
            }
            let key = if left < right {
                (left, right)
            } else {
                (right, left)
            };
            if !seen_locality_edges.insert(key) {
                return;
            }
            let distance = euclidean(x_km[left], y_km[left], x_km[right], y_km[right]).max(0.5);
            let terrain = (locality_seeds[left].terrain_friction
                + locality_seeds[right].terrain_friction)
                / 2.0;
            adjacency_edges.push((left, right, terrain * (0.65 + distance / 55.0)));
        };
        let mut locality_ids: Vec<usize> = (0..locality_count).collect();
        if config.geography.national_backbone == "spatial_mst" {
            let root = locality_ids
                .iter()
                .copied()
                .min_by(|left, right| {
                    let a = x_km[*left] * x_km[*left] + y_km[*left] * y_km[*left];
                    let b = x_km[*right] * x_km[*right] + y_km[*right] * y_km[*right];
                    a.total_cmp(&b).then_with(|| left.cmp(right))
                })
                .expect("locality exists");
            let mut connected = vec![root];
            locality_ids.retain(|id| *id != root);
            while !locality_ids.is_empty() {
                let candidate = locality_ids
                    .iter()
                    .flat_map(|right| connected.iter().map(move |left| (*left, *right)))
                    .min_by(|(left_a, right_a), (left_b, right_b)| {
                        euclidean(x_km[*left_a], y_km[*left_a], x_km[*right_a], y_km[*right_a])
                            .total_cmp(&euclidean(
                                x_km[*left_b],
                                y_km[*left_b],
                                x_km[*right_b],
                                y_km[*right_b],
                            ))
                            .then_with(|| left_a.cmp(left_b))
                            .then_with(|| right_a.cmp(right_b))
                    })
                    .expect("remaining locality has an MST edge");
                connect(candidate.0, candidate.1);
                connected.push(candidate.1);
                locality_ids.retain(|id| *id != candidate.1);
            }
        }
        let k = config.geography.nearest_neighbors;
        for left in 0..locality_count {
            let mut nearest = (0..locality_count)
                .filter(|right| *right != left)
                .collect::<Vec<_>>();
            nearest.sort_by(|a, b| {
                euclidean(x_km[left], y_km[left], x_km[*a], y_km[*a])
                    .total_cmp(&euclidean(x_km[left], y_km[left], x_km[*b], y_km[*b]))
                    .then_with(|| a.cmp(b))
            });
            for right in nearest.into_iter().take(k) {
                connect(left, right);
            }
        }
        if config.geography.district_hub_links {
            for district in 0..district_count {
                let members = locality_seeds
                    .iter()
                    .enumerate()
                    .filter(|(_, seed)| seed.district == district)
                    .map(|(index, _)| index)
                    .collect::<Vec<_>>();
                if let Some(&hub) = members.first() {
                    for locality in members.into_iter().skip(1) {
                        connect(hub, locality);
                    }
                }
            }
        }
        let mut central_zone = Vec::with_capacity(locality_count);
        let mut post_zone = Vec::with_capacity(locality_count);
        for locality in 0..locality_count {
            let start = locality_zone_offsets[locality] as usize;
            let end = locality_zone_offsets[locality + 1] as usize;
            let local_zone_cost = |zone: usize| {
                python_sum(
                    &physical_edge_rows
                        .iter()
                        .filter_map(|(left, right, cost)| {
                            let left = *left as usize;
                            let right = *right as usize;
                            if left == zone || right == zone {
                                Some(*cost)
                            } else {
                                None
                            }
                        })
                        .collect::<Vec<_>>(),
                )
            };
            let central = (start..end)
                .min_by(|left, right| {
                    local_zone_cost(*left)
                        .total_cmp(&local_zone_cost(*right))
                        .then_with(|| left.cmp(right))
                })
                .expect("locality has a physical zone");
            central_zone.push(central as u32);
            let best = (start..end)
                .max_by(|a, b| {
                    population_share[*a]
                        .total_cmp(&population_share[*b])
                        .then_with(|| b.cmp(a))
                })
                .expect("locality has a physical zone");
            post_zone.push(best as u32);
            primary_zone[locality] = best as u32;
        }
        let locality_edge_rows = adjacency_edges
            .iter()
            .map(|(left, right, cost)| (*left as u32, *right as u32, *cost))
            .collect::<Vec<_>>();
        let locality_graph =
            CsrGraph::from_edges_ordered(locality_count, &locality_edge_rows, true);
        // Python's physical world contains only within-locality microzone
        // edges.  National adjacency is a separate locality graph used by
        // movement/propagation; adding those links to the physical graph
        // would create patrol candidates that do not exist in the oracle.
        let zone_count = microzones.len();
        let physical_graph = CsrGraph::from_edges(zone_count, &physical_edge_rows, true);
        let road_graph = CsrGraph::from_edges(zone_count, &road_edge_rows, true);
        let mut physical_distances = vec![f64::INFINITY; locality_count * locality_count];
        for source in 0..locality_count {
            physical_distances[source * locality_count + source] = 0.0;
            for target in 0..locality_count {
                if source != target {
                    physical_distances[source * locality_count + target] =
                        euclidean(x_km[source], y_km[source], x_km[target], y_km[target]);
                }
            }
        }
        let topology = StaticTopology {
            localities,
            microzones,
            districts,
            locality_names,
            district_names,
            microzone_names,
            locality_to_district,
            primary_zone,
            microzone_to_locality,
            locality_zone_offsets,
            zone_population_share: population_share,
            zone_infrastructure,
            zone_terrain_friction: zone_terrain,
            zone_observability,
            locality_central_zone: central_zone,
            locality_post_zone: post_zone,
            x_km,
            y_km,
            locality_edges: locality_graph,
            physical_edges: physical_graph,
            road_edges: road_graph,
            physical_distances,
            locality_kind: locality_seeds.iter().map(|seed| seed.kind).collect(),
            district_language_patterns: DISTRICTS.iter().map(|row| row.4.to_string()).collect(),
            locality_population: locality_seeds.iter().map(|seed| seed.population).collect(),
            locality_economic_output: locality_seeds
                .iter()
                .map(|seed| seed.economic_output)
                .collect(),
            locality_infrastructure: locality_seeds
                .iter()
                .map(|seed| seed.infrastructure)
                .collect(),
            locality_administrative_capacity: locality_seeds
                .iter()
                .map(|seed| seed.administrative_capacity)
                .collect(),
            locality_terrain_friction: locality_seeds
                .iter()
                .map(|seed| seed.terrain_friction)
                .collect(),
            locality_observability: locality_seeds
                .iter()
                .map(|seed| seed.observability)
                .collect(),
            district_population: DISTRICTS.iter().map(|row| row.2).collect(),
            district_connectivity: DISTRICTS.iter().map(|row| row.7).collect(),
            district_urbanization: DISTRICTS.iter().map(|row| row.3).collect(),
        };
        PinelandTopologyGeneration {
            topology,
            world_rng,
            geography_rng,
            physical_rng,
        }
    }

    pub fn locality_count(&self) -> usize {
        self.localities.len()
    }
    pub fn microzone_count(&self) -> usize {
        self.microzones.len()
    }
    pub fn district_count(&self) -> usize {
        self.districts.len()
    }

    pub fn distance(&self, source_microzone: MicrozoneId, target_microzone: MicrozoneId) -> f64 {
        let source = self
            .microzone_to_locality
            .get(source_microzone.get() as usize)
            .copied();
        let target = self
            .microzone_to_locality
            .get(target_microzone.get() as usize)
            .copied();
        match (source, target) {
            (Some(source), Some(target)) => {
                self.physical_distances[source as usize * self.locality_count() + target as usize]
            }
            _ => f64::INFINITY,
        }
    }

    pub fn locality_distance(&self, source: LocalityId, target: LocalityId) -> f64 {
        self.physical_distances
            .get(source.get() as usize * self.locality_count() + target.get() as usize)
            .copied()
            .unwrap_or(f64::INFINITY)
    }

    pub fn zones_for_locality(&self, locality: LocalityId) -> std::ops::Range<usize> {
        let index = locality.get() as usize;
        let start = self.locality_zone_offsets.get(index).copied().unwrap_or(0) as usize;
        let end = self
            .locality_zone_offsets
            .get(index + 1)
            .copied()
            .unwrap_or(start as u32) as usize;
        start..end
    }
}

fn euclidean(x1: f64, y1: f64, x2: f64, y2: f64) -> f64 {
    ((x1 - x2).powi(2) + (y1 - y2).powi(2)).sqrt()
}

fn clamp(value: f64, lower: f64, upper: f64) -> f64 {
    value.max(lower).min(upper)
}

fn kind_name(kind: u8) -> &'static str {
    match kind {
        0 => "City",
        1 => "Town",
        _ => "Village-Cluster",
    }
}

/// Python's round(float) uses ties-to-even before converting to int.
fn python_round(value: f64) -> f64 {
    let floor = value.floor();
    let fraction = value - floor;
    if fraction < 0.5 {
        floor
    } else if fraction > 0.5 {
        floor + 1.0
    } else if (floor as i64) % 2 == 0 {
        floor
    } else {
        floor + 1.0
    }
}
