//! Native particle filtering over autonomous Rust engines.
//!
//! A filter boundary is the only point at which particles interact.  Each
//! trajectory propagates independently, then canonical log-weight
//! normalization and systematic resampling are performed in logical particle
//! order.  Worker identity is never part of a seed or a lineage.

use crate::guided::GuidedProposal;
use crate::likelihood::{Observation, ObservationLikelihood};
use crate::mcse::{McseMonitor, McseStatus};
use crate::parallel::for_each_mut;
use crate::resampling::{normalize_log_weights, systematic_resample};
use pineland_core::config::SimulationConfig;
use pineland_core::json::JsonValue;
use pineland_core::rng::{seed_from_namespace, PyRandomCompat, RngState};
use pineland_model::{ModelError, SimulationEngine};
use std::fmt;

#[derive(Clone, Debug, PartialEq)]
pub struct FilterUpdate {
    pub time: f64,
    pub log_normalizer: f64,
    pub ess: f64,
    pub resampled: bool,
    pub parent_indices: Vec<usize>,
    pub ancestry: Vec<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub enum FilterError {
    Model(String),
    Weight(String),
    Invalid(String),
}

impl fmt::Display for FilterError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Model(message) => write!(formatter, "model: {message}"),
            Self::Weight(message) => write!(formatter, "weight: {message}"),
            Self::Invalid(message) => formatter.write_str(message),
        }
    }
}

impl std::error::Error for FilterError {}
impl From<ModelError> for FilterError {
    fn from(error: ModelError) -> Self {
        Self::Model(error.to_string())
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct NativeParticleFilter {
    pub config: SimulationConfig,
    pub particles: Vec<SimulationEngine>,
    pub log_weights: Vec<f64>,
    pub rng: PyRandomCompat,
    pub ess_fraction: f64,
    pub boundary: u64,
    pub threads: usize,
    pub guided: Option<GuidedProposal>,
    pub mcse: McseMonitor,
}

impl NativeParticleFilter {
    pub fn new(config: SimulationConfig, count: usize) -> Result<Self, FilterError> {
        if count == 0 {
            return Err(FilterError::Invalid(
                "particle count must be positive".to_string(),
            ));
        }
        let mut particles = Vec::with_capacity(count);
        for index in 0..count {
            let mut particle_config = config.clone();
            particle_config.seed = seed_from_namespace(
                config.seed,
                &config.random_stream_namespace,
                &format!("particle-{index}"),
            );
            let mut particle = SimulationEngine::new(particle_config)?;
            particle.particle.logical_id = index as u64;
            particle.particle.lineage = format!("root.{index}");
            particle.particle.ancestry = vec![index as u64];
            particles.push(particle);
        }
        Ok(Self::empty(config, particles))
    }

    pub fn from_engines(
        config: SimulationConfig,
        particles: Vec<SimulationEngine>,
    ) -> Result<Self, FilterError> {
        if particles.is_empty() {
            return Err(FilterError::Invalid(
                "particle count must be positive".to_string(),
            ));
        }
        let expected = filter_config_hash(&config);
        if particles
            .iter()
            .any(|particle| filter_config_hash(&particle.config) != expected)
        {
            return Err(FilterError::Invalid(
                "particle configurations do not match filter configuration".to_string(),
            ));
        }
        Ok(Self::empty(config, particles))
    }

    fn empty(config: SimulationConfig, particles: Vec<SimulationEngine>) -> Self {
        let count = particles.len();
        Self {
            rng: PyRandomCompat::from_seed(seed_from_namespace(
                config.seed,
                &config.random_stream_namespace,
                "filter",
            )),
            config,
            particles,
            log_weights: vec![0.0; count],
            ess_fraction: 0.5,
            boundary: 0,
            threads: 1,
            guided: None,
            mcse: McseMonitor::new(0.01, 32),
        }
    }

    pub fn set_threads(&mut self, threads: usize) {
        self.threads = threads.max(1);
    }
    pub fn particle_count(&self) -> usize {
        self.particles.len()
    }

    pub fn normalized_weights(&self) -> Result<Vec<f64>, FilterError> {
        Ok(normalize_log_weights(&self.log_weights)
            .map_err(FilterError::Weight)?
            .normalized_weights)
    }

    pub fn log_likelihoods(&self, observation: &Observation) -> Vec<f64> {
        self.particles
            .iter()
            .map(|particle| observation_log_likelihood(particle, observation))
            .collect()
    }

    pub fn update_observation(
        &mut self,
        time: f64,
        observation: &Observation,
    ) -> Result<FilterUpdate, FilterError> {
        if !time.is_finite() {
            return Err(FilterError::Invalid(
                "filter boundary time must be finite".to_string(),
            ));
        }
        // The observation belongs to the state at its timestamp.  Propagate
        // every trajectory first, then evaluate the likelihood on that
        // boundary state before normalizing/resampling.
        self.advance_particles(time)?;
        let likelihoods = self.log_likelihoods(observation);
        self.update_propagated(time, Some(&likelihoods))
    }

    /// Apply a guided proposal's importance correction before propagation.
    /// The correction includes the prior weight, target likelihood, and
    /// proposal likelihood, so it is safe to checkpoint and restore.
    pub fn apply_guided_proposal(
        &mut self,
        observed_signal: f64,
        predicted_signals: &[f64],
        log_likelihood: &[f64],
    ) -> Result<(), FilterError> {
        if predicted_signals.len() != self.particles.len()
            || log_likelihood.len() != self.particles.len()
        {
            return Err(FilterError::Invalid(
                "guided proposal vectors do not equal particle count".to_string(),
            ));
        }
        let Some(guided) = &self.guided else {
            for (weight, likelihood) in self.log_weights.iter_mut().zip(log_likelihood) {
                *weight += if likelihood.is_finite() {
                    *likelihood
                } else {
                    f64::NEG_INFINITY
                };
            }
            return Ok(());
        };
        for index in 0..self.particles.len() {
            let correction = guided.weight(
                self.log_weights[index],
                log_likelihood[index],
                observed_signal,
                predicted_signals[index],
            );
            self.log_weights[index] = correction.correction;
        }
        Ok(())
    }

    pub fn update(
        &mut self,
        time: f64,
        log_likelihood: Option<&[f64]>,
    ) -> Result<FilterUpdate, FilterError> {
        self.validate_update_inputs(time, log_likelihood)?;
        self.advance_particles(time)?;
        self.update_propagated(time, log_likelihood)
    }

    fn validate_update_inputs(
        &self,
        time: f64,
        log_likelihood: Option<&[f64]>,
    ) -> Result<(), FilterError> {
        if !time.is_finite() {
            return Err(FilterError::Invalid(
                "filter boundary time must be finite".to_string(),
            ));
        }
        if let Some(values) = log_likelihood {
            if values.len() != self.particles.len() {
                return Err(FilterError::Invalid(
                    "likelihood length does not equal particle count".to_string(),
                ));
            }
        }
        Ok(())
    }

    fn advance_particles(&mut self, time: f64) -> Result<(), FilterError> {
        for_each_mut(&mut self.particles, self.threads, |particle| {
            particle.advance_until(time).map_err(FilterError::from)
        })
    }

    fn update_propagated(
        &mut self,
        time: f64,
        log_likelihood: Option<&[f64]>,
    ) -> Result<FilterUpdate, FilterError> {
        self.validate_update_inputs(time, log_likelihood)?;
        if let Some(values) = log_likelihood {
            for (index, value) in values.iter().enumerate() {
                if !value.is_finite() {
                    self.log_weights[index] = f64::NEG_INFINITY;
                } else {
                    self.log_weights[index] += *value;
                }
            }
        }

        let target_boundary = self.boundary.saturating_add(1);
        let normalized = normalize_log_weights(&self.log_weights).map_err(FilterError::Weight)?;

        // Track a stable, scientific summary statistic for MCSE stopping.  It
        // is evaluated before resampling so its weighting is the posterior
        // weighting at this boundary rather than the uniform bootstrap weight.
        let weighted_control = self
            .particles
            .iter()
            .zip(normalized.normalized_weights.iter().copied())
            .map(|(particle, weight)| {
                let total = particle
                    .particle
                    .locality
                    .insurgent_control
                    .iter()
                    .sum::<f64>();
                let count = particle.particle.locality.population.len().max(1) as f64;
                weight * total / count
            })
            .sum::<f64>();
        self.mcse.push(weighted_control);

        let threshold = self.particles.len() as f64 * self.ess_fraction;
        let (resampled, parents) = if normalized.ess < threshold {
            let parents = systematic_resample(&normalized.normalized_weights, &mut self.rng)
                .map_err(FilterError::Weight)?;
            let old = self.particles.clone();
            let mut next = Vec::with_capacity(old.len());
            for (child, parent) in parents.iter().enumerate() {
                let mut engine = old[*parent].clone();
                let lineage = format!("{}.{}", old[*parent].particle.lineage, child);
                engine.particle = old[*parent].particle.clone_for_child(child as u64, lineage);
                // Resampled siblings must not share future stochastic
                // trajectories.  The identity is canonical and independent
                // of the Rayon worker or MPI rank that executes the child.
                engine.particle.rng = old[*parent].particle.rng.fork(&format!(
                    "filter-boundary-{target_boundary}:child-{child}:parent-{parent}"
                ));
                engine.particle.weights_log = -(old.len() as f64).ln();
                engine.particle.filter_boundary = target_boundary;
                next.push(engine);
            }
            self.particles = next;
            self.log_weights = vec![0.0; self.particles.len()];
            (true, parents)
        } else {
            for (index, particle) in self.particles.iter_mut().enumerate() {
                particle.particle.filter_boundary = target_boundary;
                particle.particle.weights_log = self.log_weights[index];
            }
            (false, (0..self.particles.len()).collect())
        };
        self.boundary = target_boundary;
        let ancestry = self
            .particles
            .iter()
            .map(|particle| particle.particle.lineage.clone())
            .collect();
        Ok(FilterUpdate {
            time,
            log_normalizer: normalized.log_normalizer,
            ess: normalized.ess,
            resampled,
            parent_indices: parents,
            ancestry,
        })
    }

    pub fn mcse_status(&self) -> McseStatus {
        self.mcse.status()
    }
    pub fn mcse_converged(&self) -> bool {
        self.mcse.status().converged
    }

    /// Filter-only continuation state not duplicated in particle checkpoint
    /// shards.  It is JSON so the state is inspectable and schema-versioned.
    pub fn continuation_json(&self) -> JsonValue {
        let mut value = JsonValue::object();
        value.insert(
            "schema",
            JsonValue::string("pineland-filter-continuation-v1"),
        );
        value.insert("boundary", JsonValue::integer(self.boundary));
        value.insert(
            "configuration_hash",
            JsonValue::string(self.config.canonical_hash()),
        );
        value.insert(
            "particle_count",
            JsonValue::integer(self.particles.len() as u64),
        );
        value.insert("ess_fraction", JsonValue::number(self.ess_fraction));
        value.insert("threads", JsonValue::integer(self.threads as u64));
        value.insert("guided", guided_to_json(self.guided.as_ref()));
        value.insert("log_weights", f64_array(&self.log_weights));
        value.insert("filter_rng", rng_to_json(&self.rng));

        let status = self.mcse.status();
        let mut mcse = JsonValue::object();
        mcse.insert("target", JsonValue::number(self.mcse.target));
        mcse.insert(
            "minimum_samples",
            JsonValue::integer(self.mcse.minimum_samples as u64),
        );
        mcse.insert("samples", f64_array(&self.mcse.samples));
        mcse.insert("count", JsonValue::integer(status.count as u64));
        mcse.insert("mcse", finite_or_null(status.mcse));
        value.insert("mcse", mcse);
        value
    }

    /// Restore a filter from particle engines plus `continuation_json`.
    /// Particle state remains in the versioned binary checkpoint shards.
    pub fn from_continuation(
        config: SimulationConfig,
        particles: Vec<SimulationEngine>,
        value: &JsonValue,
    ) -> Result<Self, FilterError> {
        let mut filter = Self::from_engines(config, particles)?;
        let object = value.as_object().ok_or_else(|| {
            FilterError::Invalid("filter continuation is not an object".to_string())
        })?;
        if object.get("schema").and_then(JsonValue::as_str)
            != Some("pineland-filter-continuation-v1")
        {
            return Err(FilterError::Invalid(
                "unsupported filter continuation schema".to_string(),
            ));
        }
        filter.boundary = required_u64(object, "boundary")?;
        let configuration_hash = object
            .get("configuration_hash")
            .and_then(JsonValue::as_str)
            .ok_or_else(|| {
                FilterError::Invalid(
                    "filter continuation is missing configuration_hash".to_string(),
                )
            })?;
        if configuration_hash != filter.config.canonical_hash() {
            return Err(FilterError::Invalid(
                "filter continuation configuration hash mismatch".to_string(),
            ));
        }
        let particle_count = object
            .get("particle_count")
            .and_then(JsonValue::as_usize)
            .ok_or_else(|| {
                FilterError::Invalid("invalid filter continuation particle_count".to_string())
            })?;
        if particle_count != filter.particles.len() {
            return Err(FilterError::Invalid(
                "filter continuation particle count mismatch".to_string(),
            ));
        }
        filter.ess_fraction = required_f64(object, "ess_fraction")?;
        filter.threads = required_u64(object, "threads")?
            .try_into()
            .map_err(|_| FilterError::Invalid("filter thread count overflows usize".to_string()))?;
        filter.log_weights = object
            .get("log_weights")
            .and_then(JsonValue::as_array)
            .ok_or_else(|| {
                FilterError::Invalid("filter continuation is missing log_weights".to_string())
            })?
            .iter()
            .map(|value| match value {
                JsonValue::Null => Ok(f64::NEG_INFINITY),
                _ => value
                    .as_f64()
                    .ok_or_else(|| FilterError::Invalid("invalid filter log weight".to_string())),
            })
            .collect::<Result<Vec<_>, _>>()?;
        if filter.log_weights.len() != filter.particles.len() {
            return Err(FilterError::Invalid(
                "filter continuation particle count mismatch".to_string(),
            ));
        }
        let filter_rng = object.get("filter_rng").ok_or_else(|| {
            FilterError::Invalid("filter continuation is missing filter_rng".to_string())
        })?;
        filter.rng = rng_from_json(filter_rng)?;
        filter.guided = guided_from_json(object.get("guided").unwrap_or(&JsonValue::Null))?;
        if let Some(mcse) = object.get("mcse").and_then(JsonValue::as_object) {
            let target = mcse
                .get("target")
                .and_then(JsonValue::as_f64)
                .ok_or_else(|| FilterError::Invalid("invalid MCSE target".to_string()))?;
            let minimum_samples = mcse
                .get("minimum_samples")
                .and_then(JsonValue::as_usize)
                .ok_or_else(|| FilterError::Invalid("invalid MCSE minimum_samples".to_string()))?;
            let samples = mcse
                .get("samples")
                .and_then(JsonValue::as_array)
                .ok_or_else(|| FilterError::Invalid("invalid MCSE samples".to_string()))?
                .iter()
                .map(|value| {
                    value
                        .as_f64()
                        .ok_or_else(|| FilterError::Invalid("invalid MCSE sample".to_string()))
                })
                .collect::<Result<Vec<_>, _>>()?;
            filter.mcse = McseMonitor {
                target,
                minimum_samples,
                samples,
            };
        }
        Ok(filter)
    }

    pub fn summary(&self) -> JsonValue {
        let mut object = JsonValue::object();
        object.insert(
            "configuration_hash",
            JsonValue::string(self.config.canonical_hash()),
        );
        object.insert("particles", JsonValue::integer(self.particles.len() as u64));
        object.insert("boundary", JsonValue::integer(self.boundary));
        object.insert("threads", JsonValue::integer(self.threads as u64));
        object.insert("ess_fraction", JsonValue::number(self.ess_fraction));
        let status = self.mcse.status();
        let mut mcse = JsonValue::object();
        mcse.insert("mean", JsonValue::number(status.mean));
        mcse.insert("variance", finite_or_null(status.variance));
        mcse.insert("mcse", finite_or_null(status.mcse));
        mcse.insert("converged", JsonValue::Bool(status.converged));
        mcse.insert("count", JsonValue::integer(status.count as u64));
        object.insert("mcse", mcse);
        let mut hashes = JsonValue::Array(Vec::new());
        if let JsonValue::Array(values) = &mut hashes {
            for particle in &self.particles {
                values.push(JsonValue::string(particle.state_hash()));
            }
        }
        object.insert("state_hashes", hashes);
        object
    }
}

/// Evaluate one observation against one propagated native trajectory.  This
/// is public so the MPI adapter can evaluate rank-local particles without
/// constructing a duplicated global filter on every rank.
pub fn observation_log_likelihood(particle: &SimulationEngine, observation: &Observation) -> f64 {
    let value = match observation {
        Observation::BinaryActivity {
            observed,
            hazard,
            opportunities,
        } => ObservationLikelihood::default().log_binary(*observed, *hazard, *opportunities),
        Observation::GaussianControl {
            actor,
            observed,
            sigma,
        } => {
            let likelihood = ObservationLikelihood {
                gaussian_sigma: *sigma,
                ..Default::default()
            };
            let count = particle.topology.locality_count().max(1) as f64;
            let predicted = (0..particle.topology.locality_count())
                .map(|locality| {
                    particle
                        .particle
                        .locality
                        .effective_control(locality, *actor)
                })
                .sum::<f64>()
                / count;
            likelihood.log_gaussian(*observed, predicted)
        }
        Observation::GaussianInsurgentPersonnel { observed, sigma } => {
            let likelihood = ObservationLikelihood {
                gaussian_sigma: *sigma,
                ..Default::default()
            };
            let predicted = particle
                .particle
                .formations
                .organization
                .iter()
                .enumerate()
                .filter(|(index, organization)| {
                    particle.particle.formations.active[*index] != 0
                        && **organization as usize == pineland_model::INSURGENT
                })
                .map(|(index, _)| particle.particle.formations.personnel[index])
                .sum::<f64>();
            likelihood.log_gaussian(*observed, predicted)
        }
    };
    if value.is_finite() {
        value
    } else {
        f64::NEG_INFINITY
    }
}

fn filter_config_hash(config: &SimulationConfig) -> String {
    let mut normalized = config.clone();
    // Particle trajectories use a namespace-derived seed, but share every
    // other filter configuration field with the filter root.
    normalized.seed = 0;
    normalized.canonical_hash()
}

fn finite_or_null(value: f64) -> JsonValue {
    if value.is_finite() {
        JsonValue::number(value)
    } else {
        JsonValue::Null
    }
}

fn f64_array(values: &[f64]) -> JsonValue {
    let mut result = JsonValue::Array(Vec::with_capacity(values.len()));
    if let JsonValue::Array(items) = &mut result {
        for value in values {
            items.push(finite_or_null(*value));
        }
    }
    result
}

fn guided_to_json(guided: Option<&GuidedProposal>) -> JsonValue {
    let Some(guided) = guided else {
        return JsonValue::Null;
    };
    let mut value = JsonValue::object();
    value.insert("strength", JsonValue::number(guided.strength));
    value.insert("floor", JsonValue::number(guided.floor));
    value
}

fn guided_from_json(value: &JsonValue) -> Result<Option<GuidedProposal>, FilterError> {
    let Some(object) = value.as_object() else {
        return Ok(None);
    };
    Ok(Some(GuidedProposal {
        strength: required_f64(object, "strength")?,
        floor: required_f64(object, "floor")?,
    }))
}

fn required_u64(
    object: &std::collections::BTreeMap<String, JsonValue>,
    key: &str,
) -> Result<u64, FilterError> {
    object
        .get(key)
        .and_then(JsonValue::as_u64)
        .ok_or_else(|| FilterError::Invalid(format!("invalid filter continuation field {key}")))
}

fn required_f64(
    object: &std::collections::BTreeMap<String, JsonValue>,
    key: &str,
) -> Result<f64, FilterError> {
    object
        .get(key)
        .and_then(JsonValue::as_f64)
        .filter(|value| value.is_finite())
        .ok_or_else(|| FilterError::Invalid(format!("invalid filter continuation field {key}")))
}

fn rng_to_json(rng: &PyRandomCompat) -> JsonValue {
    let state = rng.state();
    let mut value = JsonValue::object();
    value.insert("index", JsonValue::integer(state.index));
    let mut words = JsonValue::Array(Vec::with_capacity(state.words.len()));
    if let JsonValue::Array(items) = &mut words {
        for word in state.words {
            items.push(JsonValue::integer(word));
        }
    }
    value.insert("words", words);
    value.insert(
        "gauss_next",
        state.gauss_next.map_or(JsonValue::Null, JsonValue::number),
    );
    value
}

fn rng_from_json(value: &JsonValue) -> Result<PyRandomCompat, FilterError> {
    let object = value
        .as_object()
        .ok_or_else(|| FilterError::Invalid("filter RNG state is not an object".to_string()))?;
    let index = required_u64(object, "index")?
        .try_into()
        .map_err(|_| FilterError::Invalid("filter RNG index overflows u32".to_string()))?;
    let words = object
        .get("words")
        .and_then(JsonValue::as_array)
        .ok_or_else(|| FilterError::Invalid("filter RNG words are missing".to_string()))?;
    if words.len() != 624 {
        return Err(FilterError::Invalid(
            "filter RNG must contain 624 words".to_string(),
        ));
    }
    let mut state_words = [0u32; 624];
    for (slot, value) in state_words.iter_mut().zip(words) {
        *slot = value
            .as_u64()
            .ok_or_else(|| FilterError::Invalid("invalid filter RNG word".to_string()))?
            .try_into()
            .map_err(|_| FilterError::Invalid("filter RNG word overflows u32".to_string()))?;
    }
    let gauss_next = match object.get("gauss_next") {
        Some(JsonValue::Null) | None => None,
        Some(value) => Some(
            value
                .as_f64()
                .filter(|value| value.is_finite())
                .ok_or_else(|| FilterError::Invalid("invalid cached gaussian".to_string()))?,
        ),
    };
    PyRandomCompat::from_state(RngState {
        words: state_words,
        index,
        gauss_next,
    })
    .map_err(|error| FilterError::Invalid(error.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn filter_runs_and_keeps_logical_particles() {
        let config = SimulationConfig {
            agent_count: 100,
            locality_count: 5,
            ..Default::default()
        };
        let mut filter = NativeParticleFilter::new(config, 4).unwrap();
        let update = filter
            .update(0.25, Some(&[0.0, -100.0, -100.0, -100.0]))
            .unwrap();
        assert!(update.resampled);
        assert_eq!(update.parent_indices.len(), 4);
        assert_eq!(filter.particle_count(), 4);
        assert!(filter
            .particles
            .iter()
            .all(|particle| particle.particle.filter_boundary == 1));
        assert!(filter
            .particles
            .windows(2)
            .all(|pair| pair[0].particle.rng != pair[1].particle.rng));
    }

    #[test]
    fn thread_count_is_scientifically_invariant() {
        let config = SimulationConfig {
            agent_count: 100,
            locality_count: 5,
            ..Default::default()
        };
        let mut one = NativeParticleFilter::new(config.clone(), 8).unwrap();
        let mut many = NativeParticleFilter::new(config, 8).unwrap();
        many.set_threads(4);
        let likelihoods = [0.0, -0.3, -0.7, -1.2, -0.1, -0.8, -0.4, -1.0];
        let first = one.update(1.0, Some(&likelihoods)).unwrap();
        let second = many.update(1.0, Some(&likelihoods)).unwrap();
        assert_eq!(first.parent_indices, second.parent_indices);
        assert_eq!(
            one.particles
                .iter()
                .map(|p| p.state_hash())
                .collect::<Vec<_>>(),
            many.particles
                .iter()
                .map(|p| p.state_hash())
                .collect::<Vec<_>>()
        );
        assert_eq!(first.ancestry, second.ancestry);
    }

    #[test]
    fn filter_continuation_restores_rng_weights_and_mcse() {
        let config = SimulationConfig {
            agent_count: 80,
            locality_count: 4,
            ..Default::default()
        };
        let mut filter = NativeParticleFilter::new(config.clone(), 4).unwrap();
        filter.set_threads(2);
        filter.update(0.5, Some(&[0.0, -0.1, -0.2, -0.3])).unwrap();
        let continuation = filter.continuation_json();
        let restored = NativeParticleFilter::from_continuation(
            config,
            filter.particles.clone(),
            &continuation,
        )
        .unwrap();
        assert_eq!(filter.boundary, restored.boundary);
        assert_eq!(filter.log_weights, restored.log_weights);
        assert_eq!(filter.rng, restored.rng);
        assert_eq!(filter.mcse, restored.mcse);
        assert_eq!(filter.summary(), restored.summary());
    }

    #[test]
    fn observation_and_guided_boundaries_stay_native() {
        let config = SimulationConfig {
            agent_count: 60,
            locality_count: 3,
            ..Default::default()
        };
        let mut filter = NativeParticleFilter::new(config, 3).unwrap();
        filter.guided = Some(GuidedProposal::default());
        let observation = Observation::GaussianControl {
            actor: 0,
            observed: 0.5,
            sigma: 0.2,
        };
        let likelihoods = filter.log_likelihoods(&observation);
        let predicted = vec![0.5; 3];
        filter
            .apply_guided_proposal(0.5, &predicted, &likelihoods)
            .unwrap();
        assert!(filter.log_weights.iter().all(|value| value.is_finite()));
        let update = filter
            .update_observation(
                0.5,
                &Observation::BinaryActivity {
                    observed: true,
                    hazard: 0.2,
                    opportunities: 1.0,
                },
            )
            .unwrap();
        assert_eq!(update.parent_indices.len(), 3);
    }
}
