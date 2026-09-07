from array import array
from math import exp

from pineland_sim.native_kernels import available, fuse_control7_batch


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _python_reference(state, time, weight, observed, memory, penalty):
    state = list(state)
    prior_confidence = state[7]
    decay = exp(-max(0.0, time - state[8]) / memory)
    prior = max(0.02, prior_confidence)
    denominator = prior + weight
    scale = denominator / (1.0 + denominator)
    contradiction = state[11]
    confidence = prior_confidence
    for dimension in range(7):
        value = _clamp(observed[dimension])
        old = state[dimension]
        state[dimension] = _clamp(
            (prior * old + weight * value) / denominator
        )
        contradiction = (
            contradiction * decay + weight * abs(value - old)
        )
        confidence = _clamp(scale * exp(-penalty * contradiction))
    state[7] = confidence
    state[8] = time
    if weight >= 0.12:
        state[9] = time
    state[10] += 1.0
    state[11] = contradiction
    return state


def test_native_control_batch_matches_reference_bit_for_bit():
    if not available():
        return
    initial = [
        0.5, 0.4, 0.3, 0.2, 0.1, 0.6, 0.7,
        0.28, 0.0, -1.0e9, 0.0, 0.0,
    ]
    updates = [
        (0.25, 0.31, [0.2, 0.8, 0.4, 0.3, 0.9, 0.1, 0.7]),
        (0.50, 0.18, [0.7, 0.2, 0.5, 0.9, 0.1, 0.8, 0.3]),
    ]
    expected = list(initial)
    for time, weight, observed in updates:
        expected = _python_reference(
            expected, time, weight, observed, 30.0, 0.45
        )
    states = array("d", initial)
    indices = array("I", [0, 0])
    times = array("d", [item[0] for item in updates])
    weights = array("d", [item[1] for item in updates])
    observed = array(
        "d", [value for item in updates for value in item[2]]
    )
    assert fuse_control7_batch(
        states,
        1,
        indices,
        times,
        weights,
        observed,
        contradiction_memory_days=30.0,
        contradiction_penalty=0.45,
    )
    assert list(states) == expected
