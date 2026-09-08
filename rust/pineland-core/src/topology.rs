//! Read-only spatial topology shared by every particle.

use crate::ids::{DistrictId, LocalityId, MicrozoneId};

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
    pub x_km: Vec<f64>,
    pub y_km: Vec<f64>,
    pub physical_edges: CsrGraph,
    pub road_edges: CsrGraph,
    pub physical_distances: Vec<f64>,
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
            primary_zone,
            microzone_to_locality,
            locality_zone_offsets,
            x_km,
            y_km,
            physical_edges: physical_graph,
            road_edges: road_graph,
            physical_distances,
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
