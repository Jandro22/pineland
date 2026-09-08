//! Deterministic weight normalization and systematic resampling.

use pineland_core::rng::PyRandomCompat;

#[derive(Clone, Debug, PartialEq)]
pub struct EffectiveSampleSize {
    pub normalized_weights: Vec<f64>,
    pub log_normalizer: f64,
    pub ess: f64,
}

pub fn normalize_log_weights(log_weights: &[f64]) -> Result<EffectiveSampleSize, String> {
    if log_weights.is_empty() {
        return Err("cannot normalize an empty particle set".to_string());
    }
    if log_weights.iter().any(|value| value.is_nan()) {
        return Err("particle weights contain NaN".to_string());
    }
    let maximum = log_weights
        .iter()
        .copied()
        .fold(f64::NEG_INFINITY, f64::max);
    if !maximum.is_finite() {
        return Err("all particle weights are non-finite".to_string());
    }
    let mut unnormalized = Vec::with_capacity(log_weights.len());
    let mut total = 0.0;
    for value in log_weights {
        let weight = if value.is_finite() {
            (*value - maximum).exp()
        } else {
            0.0
        };
        unnormalized.push(weight);
        total += weight;
    }
    if total <= 0.0 || !total.is_finite() {
        return Err("particle weights have zero support".to_string());
    }
    let normalized_weights: Vec<f64> = unnormalized.iter().map(|value| *value / total).collect();
    let ess_denominator: f64 = normalized_weights.iter().map(|value| value * value).sum();
    Ok(EffectiveSampleSize {
        normalized_weights,
        log_normalizer: maximum + total.ln(),
        ess: 1.0 / ess_denominator.max(f64::MIN_POSITIVE),
    })
}

pub fn systematic_resample(
    weights: &[f64],
    rng: &mut PyRandomCompat,
) -> Result<Vec<usize>, String> {
    if weights.is_empty() {
        return Err("cannot resample an empty particle set".to_string());
    }
    if weights
        .iter()
        .any(|value| !value.is_finite() || *value < 0.0)
    {
        return Err("weights must be finite and non-negative".to_string());
    }
    let total: f64 = weights.iter().sum();
    if total <= 0.0 || !total.is_finite() {
        return Err("weights have no finite support".to_string());
    }
    let count = weights.len();
    let step = total / count as f64;
    let start = rng.random() * step;
    let mut cumulative = 0.0;
    let mut parent = 0usize;
    let mut result = Vec::with_capacity(count);
    for child in 0..count {
        let target = start + child as f64 * step;
        while parent + 1 < count && target >= cumulative + weights[parent] {
            cumulative += weights[parent];
            parent += 1;
        }
        result.push(parent);
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn normalization_and_ess_are_deterministic() {
        let result = normalize_log_weights(&[0.0, -100.0, 0.0]).unwrap();
        assert!((result.ess - 2.0).abs() < 1e-12);
        assert!((result.normalized_weights[0] - 0.5).abs() < 1e-12);
    }
    #[test]
    fn systematic_resampling_is_in_bounds() {
        let mut rng = PyRandomCompat::from_seed(9);
        let result = systematic_resample(&[0.8, 0.1, 0.1], &mut rng).unwrap();
        assert_eq!(result.len(), 3);
        assert!(result.iter().all(|i| *i < 3));
    }

    #[test]
    fn invalid_weights_are_rejected_before_resampling() {
        assert!(normalize_log_weights(&[0.0, f64::NAN]).is_err());
        let mut rng = PyRandomCompat::from_seed(9);
        assert!(systematic_resample(&[0.5, -0.1], &mut rng).is_err());
        assert!(systematic_resample(&[0.5, f64::NAN], &mut rng).is_err());
    }
}
