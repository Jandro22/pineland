"""Optional dependency-free native numeric kernels.

The library is never required for correctness. If it is absent or fails its
startup self-check, callers fall back to the Python reference implementation.
"""
from __future__ import annotations

from array import array
import ctypes
from dataclasses import dataclass
import os
from pathlib import Path


_LIBRARY = None
_LOAD_ATTEMPTED = False


@dataclass(slots=True)
class NativeInformationEventResult:
    """Fixed-width rows returned by the optional information event kernel."""

    source_index: array
    kind: array
    target_present: array
    target_actor: array
    target_formation: array
    detection_probability: array
    detected: array
    presence: array
    personnel: array
    attribution_confidence: array
    confidence: array
    quality: array
    control: array
    physical_control: array
    violence: array
    next_sequence: int

    @property
    def row_count(self) -> int:
        return len(self.source_index)


def _library_path() -> Path:
    return Path(__file__).resolve().parent / "_native" / "pineland_kernels.dll"


def _load():
    global _LIBRARY, _LOAD_ATTEMPTED
    if _LOAD_ATTEMPTED:
        return _LIBRARY
    _LOAD_ATTEMPTED = True
    path = _library_path()
    if not path.exists():
        return None
    library = ctypes.CDLL(str(path))
    function = library.pineland_fuse_control7_batch
    function.argtypes = [
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
    ]
    function.restype = ctypes.c_int
    presence = library.pineland_fuse_presence_batch
    presence.argtypes = [
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
    ]
    presence.restype = ctypes.c_int
    zone = library.pineland_fuse_zone_batch
    zone.argtypes = [
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
    ]
    zone.restype = ctypes.c_int
    event = getattr(library, "pineland_information_event_batch", None)
    if event is not None:
        pointer = ctypes.POINTER
        event.argtypes = [
            pointer(ctypes.c_uint32), pointer(ctypes.c_uint32), ctypes.c_size_t,
            pointer(ctypes.c_uint32), pointer(ctypes.c_uint32),
            pointer(ctypes.c_uint32), pointer(ctypes.c_uint32),
            pointer(ctypes.c_uint32), pointer(ctypes.c_uint32),
            pointer(ctypes.c_uint32), pointer(ctypes.c_double),
            pointer(ctypes.c_double), pointer(ctypes.c_double),
            pointer(ctypes.c_double), pointer(ctypes.c_double),
            pointer(ctypes.c_double), ctypes.c_size_t,
            pointer(ctypes.c_uint64), pointer(ctypes.c_uint32),
            pointer(ctypes.c_uint8), pointer(ctypes.c_double),
            pointer(ctypes.c_double), pointer(ctypes.c_uint32),
            pointer(ctypes.c_uint32), ctypes.c_size_t,
            ctypes.c_double, ctypes.c_double, ctypes.c_double,
            ctypes.c_double, ctypes.c_double, ctypes.c_int,
            ctypes.c_uint64, ctypes.c_size_t,
            pointer(ctypes.c_size_t), pointer(ctypes.c_uint64),
            pointer(ctypes.c_uint32), pointer(ctypes.c_uint8),
            pointer(ctypes.c_uint8), pointer(ctypes.c_uint32),
            pointer(ctypes.c_uint32), pointer(ctypes.c_double),
            pointer(ctypes.c_uint8), pointer(ctypes.c_double),
            pointer(ctypes.c_double), pointer(ctypes.c_double),
            pointer(ctypes.c_double), pointer(ctypes.c_double),
            pointer(ctypes.c_double), pointer(ctypes.c_double),
            pointer(ctypes.c_double),
        ]
        event.restype = ctypes.c_int
    _LIBRARY = library
    return library


def available() -> bool:
    return _load() is not None


def control_batch_enabled() -> bool:
    """Return whether native control fusion is enabled.

    Persistent compact rows make the native path safe to use by default when
    the optional library is installed. ``PINELAND_NATIVE_CONTROL_BATCH=0`` is
    retained as a deterministic fallback switch for diagnostics.
    """
    return (
        os.environ.get("PINELAND_NATIVE_CONTROL_BATCH", "1").strip()
        not in {"0", "false", "FALSE", "no", "NO"}
        and available()
    )


def information_batch_enabled() -> bool:
    """Return whether native presence/zone fusion is enabled."""
    return (
        os.environ.get("PINELAND_NATIVE_INFORMATION_BATCH", "1").strip()
        not in {"0", "false", "FALSE", "no", "NO"}
        and available()
    )


def information_event_enabled() -> bool:
    """Return whether the complete numeric information-event ABI is enabled."""
    return (
        os.environ.get("PINELAND_NATIVE_INFORMATION_EVENT", "1").strip()
        not in {"0", "false", "FALSE", "no", "NO"}
        and _load() is not None
        and getattr(_load(), "pineland_information_event_batch", None) is not None
    )


def fuse_control7_batch(
    states: array,
    state_count: int,
    state_indices: array,
    times: array,
    weights: array,
    observed: array,
    *,
    contradiction_memory_days: float,
    contradiction_penalty: float,
    state_stride: int = 12,
) -> bool:
    library = _load()
    if library is None:
        return False
    if states.typecode != "d":
        raise TypeError("states must be array('d')")
    if state_indices.typecode != "I":
        raise TypeError("state_indices must be array('I')")
    for payload in (times, weights, observed):
        if payload.typecode != "d":
            raise TypeError("numeric payloads must be array('d')")
    update_count = len(state_indices)
    if len(times) != update_count or len(weights) != update_count:
        raise ValueError("update arrays have inconsistent lengths")
    if len(observed) != update_count * 7:
        raise ValueError("observed must contain seven values per update")
    if state_stride < 12:
        raise ValueError("state_stride must contain at least twelve values per belief")
    if len(states) != state_count * state_stride:
        raise ValueError("states length does not match state_stride")

    state_buffer = (ctypes.c_double * len(states)).from_buffer(states)
    index_buffer = (
        ctypes.c_uint32 * len(state_indices)
    ).from_buffer(state_indices)
    time_buffer = (ctypes.c_double * len(times)).from_buffer(times)
    weight_buffer = (ctypes.c_double * len(weights)).from_buffer(weights)
    observed_buffer = (
        ctypes.c_double * len(observed)
    ).from_buffer(observed)
    result = library.pineland_fuse_control7_batch(
        state_buffer,
        state_count,
        state_stride,
        index_buffer,
        time_buffer,
        weight_buffer,
        observed_buffer,
        update_count,
        float(contradiction_memory_days),
        float(contradiction_penalty),
    )
    if result != 0:
        raise RuntimeError(f"native control fusion failed: {result}")
    return True


def _numeric_buffers(states, state_indices, times, weights):
    state_buffer = (ctypes.c_double * len(states)).from_buffer(states)
    index_buffer = (ctypes.c_uint32 * len(state_indices)).from_buffer(state_indices)
    time_buffer = (ctypes.c_double * len(times)).from_buffer(times)
    weight_buffer = (ctypes.c_double * len(weights)).from_buffer(weights)
    return state_buffer, index_buffer, time_buffer, weight_buffer


def fuse_presence_batch(
    states: array,
    state_count: int,
    state_indices: array,
    times: array,
    weights: array,
    observed_presence: array,
    observed_personnel: array,
    *,
    contradiction_memory_days: float,
    contradiction_penalty: float,
    state_stride: int = 7,
) -> bool:
    library = _load()
    if library is None:
        return False
    if states.typecode != "d" or state_indices.typecode != "I":
        raise TypeError("states/indexes have invalid array types")
    for payload in (times, weights, observed_presence, observed_personnel):
        if payload.typecode != "d":
            raise TypeError("numeric payloads must be array('d')")
    update_count = len(state_indices)
    if any(len(payload) != update_count for payload in (times, weights, observed_presence, observed_personnel)):
        raise ValueError("presence update arrays have inconsistent lengths")
    if state_stride < 7 or len(states) != state_count * state_stride:
        raise ValueError("presence state rows have an invalid stride")
    state_buffer, index_buffer, time_buffer, weight_buffer = _numeric_buffers(
        states, state_indices, times, weights
    )
    presence_buffer = (ctypes.c_double * len(observed_presence)).from_buffer(observed_presence)
    personnel_buffer = (ctypes.c_double * len(observed_personnel)).from_buffer(observed_personnel)
    result = library.pineland_fuse_presence_batch(
        state_buffer, state_count, state_stride, index_buffer, time_buffer,
        weight_buffer, presence_buffer, personnel_buffer, update_count,
        float(contradiction_memory_days), float(contradiction_penalty),
    )
    if result != 0:
        raise RuntimeError(f"native presence fusion failed: {result}")
    return True


def fuse_zone_batch(
    states: array,
    state_count: int,
    state_indices: array,
    times: array,
    weights: array,
    observed: array,
    *,
    contradiction_memory_days: float,
    contradiction_penalty: float,
    state_stride: int = 6,
) -> bool:
    library = _load()
    if library is None:
        return False
    if states.typecode != "d" or state_indices.typecode != "I":
        raise TypeError("states/indexes have invalid array types")
    for payload in (times, weights, observed):
        if payload.typecode != "d":
            raise TypeError("numeric payloads must be array('d')")
    update_count = len(state_indices)
    if any(len(payload) != update_count for payload in (times, weights, observed)):
        raise ValueError("zone update arrays have inconsistent lengths")
    if state_stride < 6 or len(states) != state_count * state_stride:
        raise ValueError("zone state rows have an invalid stride")
    state_buffer, index_buffer, time_buffer, weight_buffer = _numeric_buffers(
        states, state_indices, times, weights
    )
    observed_buffer = (ctypes.c_double * len(observed)).from_buffer(observed)
    result = library.pineland_fuse_zone_batch(
        state_buffer, state_count, state_stride, index_buffer, time_buffer,
        weight_buffer, observed_buffer, update_count,
        float(contradiction_memory_days), float(contradiction_penalty),
    )
    if result != 0:
        raise RuntimeError(f"native zone fusion failed: {result}")
    return True


def _array_pointer(payload: array, ctype):
    """Return a typed pointer, including a null pointer for empty payloads."""
    if not payload:
        return ctypes.POINTER(ctype)()
    return (ctype * len(payload)).from_buffer(payload)


def native_information_event_batch(
    rng,
    *,
    selected_sources: array,
    source_observer: array,
    source_node: array,
    source: array,
    source_type: array,
    source_locality: array,
    source_microzone: array,
    source_control_target: array,
    source_control: array,
    source_violence: array,
    report_probability: array,
    source_quality_base: array,
    source_trust: array,
    language: array,
    target_offsets: array,
    target_actor: array,
    target_present: array,
    target_personnel: array,
    target_detection_probability: array,
    target_formation: array,
    target_alternate_actor: array,
    time: float,
    observation_noise: float,
    positive_report_confidence: float,
    negative_report_confidence: float,
    attribution_error_rate: float,
    record_negative: bool = True,
    next_sequence: int = 1,
) -> NativeInformationEventResult | None:
    """Run the optional complete information event over numeric arrays.

    ``selected_sources`` is produced by the Python source-plan iterator so
    CPython's weighted-community selection remains in the exact reference
    order.  The native kernel owns all remaining report/detection/noise draws.
    ``None`` means that the optional DLL is unavailable or the supplied RNG is
    not a CPython-compatible ``random.Random`` instance; callers must use the
    exact Python numeric fallback in that case.
    """
    library = _load()
    function = (
        getattr(library, "pineland_information_event_batch", None)
        if library is not None else None
    )
    if function is None or not information_event_enabled():
        return None
    if not hasattr(rng, "getstate") or not hasattr(rng, "setstate"):
        return None
    if selected_sources.typecode != "I":
        raise TypeError("selected_sources must be array('I')")
    source_count = len(source_observer)
    if source_count < 1:
        return None
    source_arrays = (
        source_observer, source_node, source, source_type, source_locality,
        source_microzone, source_control_target, source_violence,
        report_probability, source_quality_base, source_trust, language,
    )
    for payload in source_arrays:
        if len(payload) != source_count:
            raise ValueError("native information source arrays have inconsistent lengths")
    if source_control.typecode != "d" or len(source_control) != source_count * 7:
        raise ValueError("source_control must contain seven doubles per source")
    target_count = len(target_actor)
    target_arrays = (
        target_actor, target_present, target_personnel,
        target_detection_probability, target_formation, target_alternate_actor,
    )
    if len(target_offsets) != source_count + 1:
        raise ValueError("target_offsets must contain one interval per source")
    if any(len(payload) != target_count for payload in target_arrays):
        raise ValueError("native information target arrays have inconsistent lengths")
    if target_offsets.typecode != "Q" or target_actor.typecode != "I":
        raise TypeError("native information target arrays have invalid types")
    if target_present.typecode != "B" or target_formation.typecode != "I" or target_alternate_actor.typecode != "I":
        raise TypeError("native information target code arrays have invalid types")
    for payload in (target_personnel, target_detection_probability):
        if payload.typecode != "d":
            raise TypeError("native information target values must be array('d')")

    # One control row plus one row per target is a strict upper bound for each
    # selected source.  It avoids a native reallocation or a Python object list.
    output_capacity = sum(
        1 + int(target_offsets[index + 1]) - int(target_offsets[index])
        for index in selected_sources
    )
    if output_capacity < 1:
        return NativeInformationEventResult(
            array("I"), array("B"), array("B"), array("I"), array("I"),
            array("d"), array("B"), array("d"), array("d"), array("d"),
            array("d"), array("d"), array("d"), array("d"), array("d"),
            int(next_sequence),
        )

    state = rng.getstate()
    if not isinstance(state, tuple) or len(state) != 3 or state[0] != 3:
        return None
    mt_state_values = state[1]
    if not isinstance(mt_state_values, tuple) or len(mt_state_values) != 625:
        return None
    try:
        mt_state = array("I", (int(value) for value in mt_state_values))
    except (OverflowError, TypeError, ValueError):
        return None

    out_source_index = array("I", [0]) * output_capacity
    out_kind = array("B", [0]) * output_capacity
    out_target_present = array("B", [0]) * output_capacity
    out_target_actor = array("I", [0]) * output_capacity
    out_target_formation = array("I", [0]) * output_capacity
    out_detection_probability = array("d", [0.0]) * output_capacity
    out_detected = array("B", [0]) * output_capacity
    out_presence = array("d", [0.0]) * output_capacity
    out_personnel = array("d", [0.0]) * output_capacity
    out_attribution_confidence = array("d", [0.0]) * output_capacity
    out_confidence = array("d", [0.0]) * output_capacity
    out_quality = array("d", [0.0]) * output_capacity
    out_control = array("d", [0.0]) * (output_capacity * 7)
    out_physical_control = array("d", [0.0]) * output_capacity
    out_violence = array("d", [0.0]) * output_capacity
    out_count = ctypes.c_size_t()
    out_next_sequence = ctypes.c_uint64()
    status = function(
        _array_pointer(mt_state, ctypes.c_uint32),
        _array_pointer(selected_sources, ctypes.c_uint32), len(selected_sources),
        _array_pointer(source_observer, ctypes.c_uint32),
        _array_pointer(source_node, ctypes.c_uint32),
        _array_pointer(source, ctypes.c_uint32),
        _array_pointer(source_type, ctypes.c_uint32),
        _array_pointer(source_locality, ctypes.c_uint32),
        _array_pointer(source_microzone, ctypes.c_uint32),
        _array_pointer(source_control_target, ctypes.c_uint32),
        _array_pointer(source_control, ctypes.c_double),
        _array_pointer(source_violence, ctypes.c_double),
        _array_pointer(report_probability, ctypes.c_double),
        _array_pointer(source_quality_base, ctypes.c_double),
        _array_pointer(source_trust, ctypes.c_double),
        _array_pointer(language, ctypes.c_double), source_count,
        _array_pointer(target_offsets, ctypes.c_uint64),
        _array_pointer(target_actor, ctypes.c_uint32),
        _array_pointer(target_present, ctypes.c_uint8),
        _array_pointer(target_personnel, ctypes.c_double),
        _array_pointer(target_detection_probability, ctypes.c_double),
        _array_pointer(target_formation, ctypes.c_uint32),
        _array_pointer(target_alternate_actor, ctypes.c_uint32), target_count,
        float(time), float(observation_noise), float(positive_report_confidence),
        float(negative_report_confidence), float(attribution_error_rate),
        1 if record_negative else 0, int(next_sequence), output_capacity,
        ctypes.byref(out_count), ctypes.byref(out_next_sequence),
        _array_pointer(out_source_index, ctypes.c_uint32),
        _array_pointer(out_kind, ctypes.c_uint8),
        _array_pointer(out_target_present, ctypes.c_uint8),
        _array_pointer(out_target_actor, ctypes.c_uint32),
        _array_pointer(out_target_formation, ctypes.c_uint32),
        _array_pointer(out_detection_probability, ctypes.c_double),
        _array_pointer(out_detected, ctypes.c_uint8),
        _array_pointer(out_presence, ctypes.c_double),
        _array_pointer(out_personnel, ctypes.c_double),
        _array_pointer(out_attribution_confidence, ctypes.c_double),
        _array_pointer(out_confidence, ctypes.c_double),
        _array_pointer(out_quality, ctypes.c_double),
        _array_pointer(out_control, ctypes.c_double),
        _array_pointer(out_physical_control, ctypes.c_double),
        _array_pointer(out_violence, ctypes.c_double),
    )
    if status != 0:
        raise RuntimeError(f"native information event failed: {status}")
    count = int(out_count.value)
    if count < 0 or count > output_capacity:
        raise RuntimeError("native information event returned an invalid row count")
    rng.setstate((3, tuple(int(value) for value in mt_state), state[2]))
    return NativeInformationEventResult(
        array("I", out_source_index[:count]),
        array("B", out_kind[:count]),
        array("B", out_target_present[:count]),
        array("I", out_target_actor[:count]),
        array("I", out_target_formation[:count]),
        array("d", out_detection_probability[:count]),
        array("B", out_detected[:count]),
        array("d", out_presence[:count]),
        array("d", out_personnel[:count]),
        array("d", out_attribution_confidence[:count]),
        array("d", out_confidence[:count]),
        array("d", out_quality[:count]),
        array("d", out_control[:count * 7]),
        array("d", out_physical_control[:count]),
        array("d", out_violence[:count]),
        int(out_next_sequence.value),
    )
