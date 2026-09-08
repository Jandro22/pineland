//! Branch-identity based forecast execution.

use pineland_core::json::JsonValue;
use pineland_model::{ModelError, SimulationEngine};

#[derive(Clone, Debug, PartialEq)]
pub struct ForecastBranch {
    pub root_particle: u64,
    pub branch_id: u64,
    pub engine: SimulationEngine,
}
#[derive(Clone, Debug, PartialEq)]
pub struct ForecastResult {
    pub branches: Vec<JsonValue>,
    pub means: JsonValue,
}

impl ForecastBranch {
    pub fn identity(&self) -> String {
        format!("{}.{}", self.root_particle, self.branch_id)
    }
}

pub fn run_branches(
    parents: &[SimulationEngine],
    horizon: f64,
    branches_per_particle: usize,
) -> Result<ForecastResult, ModelError> {
    let mut outputs = Vec::new();
    for parent in parents {
        let root_particle = parent.particle.logical_id;
        for branch_id in 0..branches_per_particle.max(1) {
            let identity = format!("parent-{root_particle}:branch-{branch_id}");
            let mut engine = parent.clone();
            engine.particle.lineage = format!("{}.{}", parent.particle.lineage, branch_id);
            engine.particle.logical_id = parent.particle.logical_id;
            engine.particle.ancestry.push(branch_id as u64);
            engine.particle.rng = parent.particle.rng.fork(&identity);
            engine.advance_until(horizon)?;
            let mut summary = engine.summary();
            summary.insert("root_particle", JsonValue::integer(root_particle));
            summary.insert("branch_id", JsonValue::integer(branch_id as u64));
            summary.insert(
                "branch_identity",
                JsonValue::string(format!("{}.{branch_id}", root_particle)),
            );
            outputs.push(summary);
        }
    }
    let mut means = JsonValue::object();
    let mut gov = 0.0;
    let mut ins = 0.0;
    for item in &outputs {
        gov += item
            .get("government_control")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0);
        ins += item
            .get("insurgent_control")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0);
    }
    if !outputs.is_empty() {
        means.insert(
            "government_control",
            JsonValue::number(gov / outputs.len() as f64),
        );
        means.insert(
            "insurgent_control",
            JsonValue::number(ins / outputs.len() as f64),
        );
    }
    Ok(ForecastResult {
        branches: outputs,
        means,
    })
}

#[cfg(test)]
mod tests {
    use super::run_branches;
    use pineland_core::config::SimulationConfig;
    use pineland_model::SimulationEngine;

    #[test]
    fn forecast_branches_have_stable_identity_and_independent_streams() {
        let config = SimulationConfig {
            agent_count: 100,
            locality_count: 4,
            horizon_days: 1.0,
            ..Default::default()
        };
        let parent = SimulationEngine::new(config).unwrap();
        let result = run_branches(std::slice::from_ref(&parent), 1.0, 3).unwrap();
        assert_eq!(result.branches.len(), 3);
        let hashes = result
            .branches
            .iter()
            .map(|branch| {
                branch
                    .get("state_hash")
                    .and_then(|value| value.as_str())
                    .unwrap()
            })
            .collect::<Vec<_>>();
        assert!(hashes.windows(2).all(|pair| pair[0] != pair[1]));
        let repeat = run_branches(&[parent], 1.0, 3).unwrap();
        assert_eq!(result.branches, repeat.branches);
    }
}
