"""Optional dependency-free native numeric kernels.

The library is never required for correctness. If it is absent or fails its
startup self-check, callers fall back to the Python reference implementation.
"""
from __future__ import annotations

from array import array
import ctypes
import os
from pathlib import Path


_LIBRARY = None
_LOAD_ATTEMPTED = False


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
    _LIBRARY = library
    return library


def available() -> bool:
    return _load() is not None


def control_batch_enabled() -> bool:
    """Return whether the experimental control-fusion batch is requested."""
    return (
        os.environ.get("PINELAND_NATIVE_CONTROL_BATCH", "").strip()
        in {"1", "true", "TRUE", "yes", "YES"}
        and available()
    )


def information_batch_enabled() -> bool:
    """Return whether native presence/zone fusion is requested."""
    return (
        os.environ.get("PINELAND_NATIVE_INFORMATION_BATCH", "").strip()
        in {"1", "true", "TRUE", "yes", "YES"}
        and available()
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
