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

// CPython's ``random.Random.random`` is the 53-bit composition of two
// MT19937 outputs below.  Keeping this small implementation beside the event
// kernel makes the native information boundary reproducible without asking
// Python to materialize one object per report.
struct PythonRandom {
    state: [u32; 624],
    index: usize,
}

impl PythonRandom {
    unsafe fn from_ptr(pointer: *const u32) -> Self {
        let mut state = [0u32; 624];
        for index in 0..624 {
            state[index] = *pointer.add(index);
        }
        Self {
            state,
            index: *pointer.add(624) as usize,
        }
    }

    unsafe fn write_ptr(&self, pointer: *mut u32) {
        for index in 0..624 {
            *pointer.add(index) = self.state[index];
        }
        *pointer.add(624) = self.index as u32;
    }

    fn twist(&mut self) {
        for index in 0..624 {
            let value = (self.state[index] & 0x8000_0000)
                | (self.state[(index + 1) % 624] & 0x7fff_ffff);
            let mut next = self.state[(index + 397) % 624] ^ (value >> 1);
            if value & 1 != 0 {
                next ^= 0x9908_b0df;
            }
            self.state[index] = next;
        }
        self.index = 0;
    }

    fn uint32(&mut self) -> u32 {
        if self.index >= 624 {
            self.twist();
        }
        let mut value = self.state[self.index];
        self.index += 1;
        value ^= value >> 11;
        value ^= (value << 7) & 0x9d2c_5680;
        value ^= (value << 15) & 0xefc6_0000;
        value ^= value >> 18;
        value
    }

    fn random(&mut self) -> f64 {
        let first = (self.uint32() >> 5) as f64;
        let second = (self.uint32() >> 6) as f64;
        (first * 67_108_864.0 + second) * (1.0 / 9_007_199_254_740_992.0)
    }

    fn uniform(&mut self, lower: f64, upper: f64) -> f64 {
        lower + (upper - lower) * self.random()
    }
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

// Generate one complete numeric information event.  Source selection remains
// in Python because community ``random.choices`` is part of the reference
// stream; the selected source indices, however, cross the boundary only once.
// Every emitted row is fixed-width and no Observation/relay object is made.
#[allow(clippy::too_many_arguments)]
#[no_mangle]
pub unsafe extern "C" fn pineland_information_event_batch(
    mt_state: *mut u32,
    selected_sources: *const u32,
    selected_count: usize,
    source_observer: *const u32,
    source_node: *const u32,
    source: *const u32,
    source_type: *const u32,
    source_locality: *const u32,
    source_microzone: *const u32,
    source_control_target: *const u32,
    source_control: *const f64,
    source_violence: *const f64,
    report_probability: *const f64,
    source_quality_base: *const f64,
    source_trust: *const f64,
    language: *const f64,
    source_count: usize,
    target_offsets: *const u64,
    target_actor: *const u32,
    target_present: *const u8,
    target_personnel: *const f64,
    target_detection_probability: *const f64,
    target_formation: *const u32,
    target_alternate_actor: *const u32,
    target_count: usize,
    time: f64,
    observation_noise: f64,
    positive_report_confidence: f64,
    negative_report_confidence: f64,
    attribution_error_rate: f64,
    record_negative: i32,
    next_sequence: u64,
    output_capacity: usize,
    out_count: *mut usize,
    out_next_sequence: *mut u64,
    out_source_index: *mut u32,
    out_kind: *mut u8,
    out_target_present: *mut u8,
    out_target_actor: *mut u32,
    out_target_formation: *mut u32,
    out_detection_probability: *mut f64,
    out_detected: *mut u8,
    out_presence: *mut f64,
    out_personnel: *mut f64,
    out_attribution_confidence: *mut f64,
    out_confidence: *mut f64,
    out_quality: *mut f64,
    out_control: *mut f64,
    out_physical_control: *mut f64,
    out_violence: *mut f64,
) -> i32 {
    if mt_state.is_null()
        || selected_sources.is_null()
        || source_observer.is_null()
        || source_node.is_null()
        || source.is_null()
        || source_type.is_null()
        || source_locality.is_null()
        || source_microzone.is_null()
        || source_control_target.is_null()
        || source_control.is_null()
        || source_violence.is_null()
        || report_probability.is_null()
        || source_quality_base.is_null()
        || source_trust.is_null()
        || language.is_null()
        || target_offsets.is_null()
        || (target_count > 0
            && (target_actor.is_null()
                || target_present.is_null()
                || target_personnel.is_null()
                || target_detection_probability.is_null()
                || target_formation.is_null()
                || target_alternate_actor.is_null()))
        || out_count.is_null()
        || out_next_sequence.is_null()
        || out_source_index.is_null()
        || out_kind.is_null()
        || out_target_present.is_null()
        || out_target_actor.is_null()
        || out_target_formation.is_null()
        || out_detection_probability.is_null()
        || out_detected.is_null()
        || out_presence.is_null()
        || out_personnel.is_null()
        || out_attribution_confidence.is_null()
        || out_confidence.is_null()
        || out_quality.is_null()
        || out_control.is_null()
        || out_physical_control.is_null()
        || out_violence.is_null()
        || source_count == 0
    {
        return -1;
    }

    let mut rng = PythonRandom::from_ptr(mt_state);
    let mut output_index = 0usize;
    let mut sequence = next_sequence;

    for selected_index in 0..selected_count {
        let source_index = *selected_sources.add(selected_index) as usize;
        if source_index >= source_count {
            return -2;
        }
        if rng.random() >= *report_probability.add(source_index) {
            continue;
        }
        let observer = *source_observer.add(source_index);
        let node = *source_node.add(source_index);
        let source_id = *source.add(source_index);
        let source_type_id = *source_type.add(source_index);
        let locality = *source_locality.add(source_index);
        let microzone = *source_microzone.add(source_index);
        let quality_base = *source_quality_base.add(source_index);
        let trust = *source_trust.add(source_index);
        let language_value = *language.add(source_index);
        let start = *target_offsets.add(source_index) as usize;
        let end = *target_offsets.add(source_index + 1) as usize;
        if start > end || end > target_count {
            return -3;
        }

        for target_index in start..end {
            let present = *target_present.add(target_index) != 0;
            let probability = *target_detection_probability.add(target_index);
            let detected = rng.random() < probability;
            if !detected && record_negative == 0 {
                continue;
            }
            let quality = clamp01(quality_base * (0.85 + 0.3 * rng.random()));
            let personnel = *target_personnel.add(target_index);
            let mut estimate = 0.0;
            if detected {
                estimate = personnel * (0.65 + 0.7 * rng.random());
                if !present {
                    estimate = rng.uniform(20.0, 250.0).max(1.0);
                }
            }
            let attribution_mistake = present
                && detected
                && rng.random() < attribution_error_rate;
            let reported_actor = if attribution_mistake
                && *target_alternate_actor.add(target_index) != 0
            {
                *target_alternate_actor.add(target_index)
            } else {
                *target_actor.add(target_index)
            };
            let formation = *target_formation.add(target_index);
            let reported_formation = if attribution_mistake { 0 } else { formation };
            if output_index >= output_capacity {
                return -4;
            }
            *out_source_index.add(output_index) = source_index as u32;
            *out_kind.add(output_index) = 1;
            *out_target_present.add(output_index) = if present { 1 } else { 0 };
            *out_target_actor.add(output_index) = reported_actor;
            *out_target_formation.add(output_index) = reported_formation;
            *out_detection_probability.add(output_index) = probability;
            *out_detected.add(output_index) = if detected { 1 } else { 0 };
            *out_presence.add(output_index) = if detected { 1.0 } else { 0.0 };
            *out_personnel.add(output_index) = estimate;
            *out_attribution_confidence.add(output_index) =
                if attribution_mistake { 0.25 } else { 0.9 };
            *out_confidence.add(output_index) = if detected {
                positive_report_confidence
            } else {
                negative_report_confidence
            };
            *out_quality.add(output_index) = quality;
            for dimension in 0..7 {
                *out_control.add(output_index * 7 + dimension) = 0.0;
            }
            *out_physical_control.add(output_index) = 0.0;
            *out_violence.add(output_index) = 0.0;
            output_index += 1;
            sequence += 1;
        }

        let control_quality = clamp01(quality_base * (0.85 + 0.3 * rng.random()));
        let noise = observation_noise * (1.35 - 0.55 * control_quality * language_value);
        let mut control_values = [0.0f64; 7];
        for dimension in 0..7 {
            control_values[dimension] = clamp01(
                *source_control.add(source_index * 7 + dimension)
                    + rng.uniform(-noise, noise),
            );
        }
        let violence = clamp01(*source_violence.add(source_index)
            + rng.uniform(-noise, noise));
        let control_confidence = clamp01(0.45 + 0.45 * trust);
        if output_index >= output_capacity {
            return -4;
        }
        *out_source_index.add(output_index) = source_index as u32;
        *out_kind.add(output_index) = 2;
        *out_target_present.add(output_index) = 0;
        *out_target_actor.add(output_index) = *source_control_target.add(source_index);
        *out_target_formation.add(output_index) = 0;
        *out_detection_probability.add(output_index) = 0.0;
        *out_detected.add(output_index) = 0;
        *out_presence.add(output_index) = 0.0;
        *out_personnel.add(output_index) = 0.0;
        *out_attribution_confidence.add(output_index) = 0.0;
        *out_confidence.add(output_index) = control_confidence;
        *out_quality.add(output_index) = control_quality;
        for dimension in 0..7 {
            *out_control.add(output_index * 7 + dimension) = control_values[dimension];
        }
        *out_physical_control.add(output_index) = control_values[1];
        *out_violence.add(output_index) = violence;
        output_index += 1;
        sequence += 1;
        let _ = (observer, node, source_id, source_type_id, locality, microzone);
    }

    rng.write_ptr(mt_state);
    *out_count = output_index;
    *out_next_sequence = sequence;
    let _ = time;
    0
}
