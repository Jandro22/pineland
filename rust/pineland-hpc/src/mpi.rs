//! Canonical distributed-filter boundary representation.
use crate::distribution::{DeterministicPartition, ParentTransfer};
use pineland_core::json::JsonValue;
use pineland_core::rng::PyRandomCompat;
use pineland_inference::resampling::{normalize_log_weights, systematic_resample};
#[derive(Clone, Debug, PartialEq)]
pub struct MpiBoundary {
    pub boundary: u64,
    pub partition: DeterministicPartition,
    pub log_weights: Vec<f64>,
    pub parent_indices: Vec<usize>,
    pub transfers: Vec<ParentTransfer>,
}
impl MpiBoundary {
    pub fn new(boundary: u64, partition: DeterministicPartition, log_weights: Vec<f64>) -> Self {
        Self {
            boundary,
            partition,
            log_weights,
            parent_indices: Vec::new(),
            transfers: Vec::new(),
        }
    }
    pub fn with_resample(mut self, parents: Vec<usize>) -> Self {
        self.transfers = self.partition.transfer_plan(&parents);
        self.parent_indices = parents;
        self
    }
    pub fn to_json(&self) -> JsonValue {
        let mut o = JsonValue::object();
        o.insert("boundary", JsonValue::integer(self.boundary));
        o.insert("partition", self.partition.to_json());
        o.insert("transfers", JsonValue::integer(self.transfers.len() as u64));
        let mut parents = JsonValue::Array(Vec::new());
        if let JsonValue::Array(values) = &mut parents {
            for parent in &self.parent_indices {
                values.push(JsonValue::integer(*parent as u64));
            }
        }
        o.insert("parent_indices", parents);
        o
    }
}

/// Canonical rank-independent result for one distributed filtering boundary.
/// Callers gather local weights into logical particle order before invoking
/// this function.  The returned parent mapping is therefore invariant to the
/// number of ranks or the order in which ranks completed propagation.
#[derive(Clone, Debug, PartialEq)]
pub struct CanonicalBoundary {
    pub log_normalizer: f64,
    pub ess: f64,
    pub normalized_weights: Vec<f64>,
    pub parent_indices: Vec<usize>,
    pub resampled: bool,
}

pub fn canonical_boundary(
    log_weights: &[f64],
    ess_fraction: f64,
    rng: &mut PyRandomCompat,
) -> Result<CanonicalBoundary, String> {
    if !ess_fraction.is_finite() || ess_fraction < 0.0 {
        return Err("ESS fraction must be finite and non-negative".to_string());
    }
    let normalized = normalize_log_weights(log_weights).map_err(|error| error.to_string())?;
    let threshold = log_weights.len() as f64 * ess_fraction;
    let (resampled, parent_indices) = if normalized.ess < threshold {
        (
            true,
            systematic_resample(&normalized.normalized_weights, rng)
                .map_err(|error| error.to_string())?,
        )
    } else {
        (false, (0..log_weights.len()).collect())
    };
    Ok(CanonicalBoundary {
        log_normalizer: normalized.log_normalizer,
        ess: normalized.ess,
        normalized_weights: normalized.normalized_weights,
        parent_indices,
        resampled,
    })
}

/// Sum values that have already been placed in canonical logical order.
/// Rank-local reductions must not call this on arbitrary arrival order.
pub fn canonical_reduce(values: &[f64]) -> f64 {
    values.iter().fold(0.0, |acc, value| acc + *value)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn boundary_is_deterministic() {
        let weights = [0.0, -0.2, -1.5, -0.7];
        let mut a = PyRandomCompat::from_seed(8);
        let mut b = PyRandomCompat::from_seed(8);
        let first = canonical_boundary(&weights, 0.5, &mut a).unwrap();
        let second = canonical_boundary(&weights, 0.5, &mut b).unwrap();
        assert_eq!(first, second);
        let partition = DeterministicPartition::new(4, 2);
        let boundary = MpiBoundary::new(3, partition, weights.to_vec())
            .with_resample(first.parent_indices.clone());
        assert_eq!(boundary.parent_indices.len(), 4);
    }
}
