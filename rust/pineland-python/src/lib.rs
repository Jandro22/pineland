//! Optional coarse C ABI surface; Python remains an analysis-layer client.
//!
//! The CLI is authoritative for production work.  These functions are kept
//! deliberately coarse so an embedding application can create an engine,
//! advance it to a boundary, and retrieve a stable hash without calling into
//! individual model processes millions of times.

use pineland_core::config::SimulationConfig;
use pineland_model::SimulationEngine;
use std::ffi::c_char;

/// Opaque engine handle for C/Python callers.
#[repr(C)]
pub struct PinelandEngineHandle {
    engine: SimulationEngine,
}

static VERSION: &[u8] = b"pineland-native-v1\0";

#[no_mangle]
pub extern "C" fn pineland_native_version() -> *const c_char {
    VERSION.as_ptr().cast()
}

#[no_mangle]
pub extern "C" fn pineland_engine_new(seed: u64) -> *mut PinelandEngineHandle {
    let config = SimulationConfig {
        seed,
        ..Default::default()
    };
    let Ok(engine) = SimulationEngine::new(config) else {
        return std::ptr::null_mut();
    };
    Box::into_raw(Box::new(PinelandEngineHandle { engine }))
}

/// Advance to an absolute simulation day.  Returns 0 on success and -1 for a
/// null handle or invalid target.
///
/// # Safety
///
/// `handle` must be null or a valid, uniquely borrowed pointer returned by
/// [`pineland_engine_new`] that has not already been freed.
#[no_mangle]
pub unsafe extern "C" fn pineland_engine_advance(
    handle: *mut PinelandEngineHandle,
    until: f64,
) -> i32 {
    let Some(handle) = handle.as_mut() else {
        return -1;
    };
    handle.engine.advance_until(until).map(|_| 0).unwrap_or(-1)
}

/// Copy the hexadecimal state hash into a caller-owned buffer.  The return
/// value is the required buffer length including the trailing NUL, or zero
/// for a null handle/buffer.  Callers may pass a zero-length buffer to query
/// the required size.
///
/// # Safety
///
/// `handle` must be null or a valid pointer returned by [`pineland_engine_new`]
/// that has not already been freed.  When `output` is non-null, it must point
/// to a writable buffer of at least `output_len` bytes.
#[no_mangle]
pub unsafe extern "C" fn pineland_engine_state_hash(
    handle: *const PinelandEngineHandle,
    output: *mut c_char,
    output_len: usize,
) -> usize {
    let Some(handle) = handle.as_ref() else {
        return 0;
    };
    let hash = handle.engine.state_hash();
    let required = hash.len() + 1;
    if !output.is_null() && output_len >= required {
        std::ptr::copy_nonoverlapping(hash.as_ptr().cast::<c_char>(), output, hash.len());
        *output.add(hash.len()) = 0;
    }
    required
}

///
/// # Safety
///
/// `handle` must be null or a pointer returned by [`pineland_engine_new`] that
/// has not already been freed.  It must not be used again after this call.
#[no_mangle]
pub unsafe extern "C" fn pineland_engine_free(handle: *mut PinelandEngineHandle) {
    if !handle.is_null() {
        drop(Box::from_raw(handle));
    }
}
