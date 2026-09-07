// Minimal dependency-free native kernels for Pineland.
//
// Build as a cdylib and load through ctypes. The authoritative Python
// reference implementation remains available for exact-equivalence gating.

#[inline]
fn clamp01(value: f64) -> f64 {
    if value < 0.0 {
        0.0
    } else if value > 1.0 {
        1.0
    } else {
        value
    }
}

#[no_mangle]
pub unsafe extern "C" fn pineland_fuse_control7_batch(
    states: *mut f64,
    state_count: usize,
    state_stride: usize,
    state_indices: *const u32,
    times: *const f64,
    weights: *const f64,
    observed: *const f64,
    update_count: usize,
    contradiction_memory_days: f64,
    contradiction_penalty: f64,
) -> i32 {
    if states.is_null()
        || state_indices.is_null()
        || times.is_null()
        || weights.is_null()
        || observed.is_null()
        || state_stride < 12
        || contradiction_memory_days <= 0.0
    {
        return -1;
    }

    for update_index in 0..update_count {
        let state_index = *state_indices.add(update_index) as usize;
        if state_index >= state_count {
            return -2;
        }
        let state = states.add(state_index * state_stride);
        let time = *times.add(update_index);
        let weight = *weights.add(update_index);
        let obs = observed.add(update_index * 7);

        let prior_confidence = *state.add(7);
        let updated_at = *state.add(8);
        let age = if time > updated_at {
            time - updated_at
        } else {
            0.0
        };
        let contradiction_decay =
            (-age / contradiction_memory_days).exp();
        let prior = if prior_confidence > 0.02 {
            prior_confidence
        } else {
            0.02
        };
        let denominator = prior + weight;
        let confidence_scale = denominator / (1.0 + denominator);
        let mut contradiction = *state.add(11);
        let mut confidence = prior_confidence;

        for dimension in 0..7 {
            let observed_value = clamp01(*obs.add(dimension));
            let old = *state.add(dimension);
            let new_value = clamp01(
                (prior * old + weight * observed_value) / denominator
            );
            *state.add(dimension) = new_value;
            contradiction = contradiction * contradiction_decay
                + weight * (observed_value - old).abs();
            confidence = clamp01(
                confidence_scale
                    * (-contradiction_penalty * contradiction).exp()
            );
        }

        *state.add(7) = confidence;
        *state.add(8) = time;
        if weight >= 0.12 {
            *state.add(9) = time;
        }
        *state.add(10) += 1.0;
        *state.add(11) = contradiction;
    }
    0
}

#[no_mangle]
pub unsafe extern "C" fn pineland_fuse_presence_batch(
    states: *mut f64,
    state_count: usize,
    state_stride: usize,
    state_indices: *const u32,
    times: *const f64,
    weights: *const f64,
    observed_presence: *const f64,
    observed_personnel: *const f64,
    update_count: usize,
    contradiction_memory_days: f64,
    contradiction_penalty: f64,
) -> i32 {
    if states.is_null()
        || state_indices.is_null()
        || times.is_null()
        || weights.is_null()
        || observed_presence.is_null()
        || observed_personnel.is_null()
        || state_stride < 7
        || contradiction_memory_days <= 0.0
    {
        return -1;
    }

    for update_index in 0..update_count {
        let state_index = *state_indices.add(update_index) as usize;
        if state_index >= state_count {
            return -2;
        }
        let state = states.add(state_index * state_stride);
        let time = *times.add(update_index);
        let weight = *weights.add(update_index);
        let presence = clamp01(*observed_presence.add(update_index));
        let personnel = if *observed_personnel.add(update_index) < 0.0 {
            0.0
        } else {
            *observed_personnel.add(update_index)
        };
        let prior_confidence = *state.add(1);
        let prior = if prior_confidence > 0.02 {
            prior_confidence
        } else {
            0.02
        };
        let denominator = prior + weight;
        let old_presence = *state;
        let age = if time > *state.add(2) {
            time - *state.add(2)
        } else {
            0.0
        };
        let mut contradiction = *state.add(5)
            * (-age / contradiction_memory_days).exp();
        contradiction += weight * (presence - old_presence).abs();
        *state = clamp01(
            (prior * old_presence + weight * presence) / denominator
        );
        let old_personnel = *state.add(6);
        *state.add(6) = (
            old_personnel * if prior_confidence > 0.02 { prior_confidence } else { 0.02 }
                + personnel * weight
        ) / (if prior_confidence > 0.02 { prior_confidence } else { 0.02 } + weight);
        *state.add(1) = clamp01(
            (prior + weight) / (1.0 + prior + weight)
                * (-contradiction_penalty * contradiction).exp()
        );
        *state.add(2) = time;
        *state.add(4) += 1.0;
        *state.add(5) = contradiction;
        if weight >= 0.12 {
            *state.add(3) = time;
        }
    }
    0
}

#[no_mangle]
pub unsafe extern "C" fn pineland_fuse_zone_batch(
    states: *mut f64,
    state_count: usize,
    state_stride: usize,
    state_indices: *const u32,
    times: *const f64,
    weights: *const f64,
    observed: *const f64,
    update_count: usize,
    contradiction_memory_days: f64,
    contradiction_penalty: f64,
) -> i32 {
    if states.is_null()
        || state_indices.is_null()
        || times.is_null()
        || weights.is_null()
        || observed.is_null()
        || state_stride < 6
        || contradiction_memory_days <= 0.0
    {
        return -1;
    }

    for update_index in 0..update_count {
        let state_index = *state_indices.add(update_index) as usize;
        if state_index >= state_count {
            return -2;
        }
        let state = states.add(state_index * state_stride);
        let time = *times.add(update_index);
        let weight = *weights.add(update_index);
        let observed_value = clamp01(*observed.add(update_index));
        let prior_confidence = *state.add(1);
        let prior = if prior_confidence > 0.02 {
            prior_confidence
        } else {
            0.02
        };
        let denominator = prior + weight;
        let old_value = *state;
        let age = if time > *state.add(2) {
            time - *state.add(2)
        } else {
            0.0
        };
        let mut contradiction = *state.add(5)
            * (-age / contradiction_memory_days).exp();
        contradiction += weight * (observed_value - old_value).abs();
        *state = clamp01(
            (prior * old_value + weight * observed_value) / denominator
        );
        *state.add(1) = clamp01(
            (prior + weight) / (1.0 + prior + weight)
                * (-contradiction_penalty * contradiction).exp()
        );
        *state.add(2) = time;
        *state.add(4) += 1.0;
        *state.add(5) = contradiction;
        if weight >= 0.12 {
            *state.add(3) = time;
        }
    }
    0
}
