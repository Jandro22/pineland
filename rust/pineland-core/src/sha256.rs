//! Small, self-contained SHA-256 implementation for provenance and state hashes.

const INITIAL: [u32; 8] = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
];

const K: [u32; 64] = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

pub fn digest(data: &[u8]) -> [u8; 32] {
    let mut state = INITIAL;
    let bit_length = (data.len() as u128) * 8;

    // Compress every complete block straight from the input, then build only
    // the one or two padded tail blocks.  This avoids copying the (possibly
    // multi-megabyte) state-hash material into a padded buffer.
    let full = data.len() / 64 * 64;
    compress(&mut state, &data[..full]);
    let remainder = &data[full..];
    let mut tail = [0u8; 128];
    tail[..remainder.len()].copy_from_slice(remainder);
    tail[remainder.len()] = 0x80;
    let tail_len = if remainder.len() + 9 <= 64 { 64 } else { 128 };
    tail[tail_len - 8..tail_len].copy_from_slice(&(bit_length as u64).to_be_bytes());
    compress(&mut state, &tail[..tail_len]);

    let mut output = [0u8; 32];
    for (index, word) in state.iter().enumerate() {
        output[index * 4..index * 4 + 4].copy_from_slice(&word.to_be_bytes());
    }
    output
}

/// Compress a whole number of 64-byte blocks into `state`.
fn compress(state: &mut [u32; 8], blocks: &[u8]) {
    debug_assert_eq!(blocks.len() % 64, 0);
    if blocks.is_empty() {
        return;
    }
    #[cfg(target_arch = "x86_64")]
    {
        if shani::available() {
            // SAFETY: the required CPU features were detected at runtime.
            unsafe { shani::compress(state, blocks) };
            return;
        }
    }
    compress_portable(state, blocks);
}

fn compress_portable(state: &mut [u32; 8], blocks: &[u8]) {
    for chunk in blocks.chunks_exact(64) {
        let mut schedule = [0u32; 64];
        for (index, bytes) in chunk.chunks_exact(4).take(16).enumerate() {
            schedule[index] = u32::from_be_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]);
        }
        for index in 16..64 {
            let x = schedule[index - 15];
            let y = schedule[index - 2];
            let sigma0 = x.rotate_right(7) ^ x.rotate_right(18) ^ (x >> 3);
            let sigma1 = y.rotate_right(17) ^ y.rotate_right(19) ^ (y >> 10);
            schedule[index] = schedule[index - 16]
                .wrapping_add(sigma0)
                .wrapping_add(schedule[index - 7])
                .wrapping_add(sigma1);
        }

        let mut working = *state;
        for index in 0..64 {
            let a = working[0];
            let b = working[1];
            let c = working[2];
            let d = working[3];
            let e = working[4];
            let f = working[5];
            let g = working[6];
            let h = working[7];
            let sigma1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let choice = (e & f) ^ ((!e) & g);
            let temporary1 = h
                .wrapping_add(sigma1)
                .wrapping_add(choice)
                .wrapping_add(K[index])
                .wrapping_add(schedule[index]);
            let sigma0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let majority = (a & b) ^ (a & c) ^ (b & c);
            let temporary2 = sigma0.wrapping_add(majority);
            working[7] = g;
            working[6] = f;
            working[5] = e;
            working[4] = d.wrapping_add(temporary1);
            working[3] = c;
            working[2] = b;
            working[1] = a;
            working[0] = temporary1.wrapping_add(temporary2);
        }
        for index in 0..8 {
            state[index] = state[index].wrapping_add(working[index]);
        }
    }
}

/// x86-64 SHA extensions (SHA-NI) block compression.  This is only a faster
/// instruction sequence for the standard SHA-256 compression function; the
/// digest is identical to the portable path (see the tests below).
#[cfg(target_arch = "x86_64")]
mod shani {
    use super::K;
    use std::arch::x86_64::*;

    pub(super) fn available() -> bool {
        static AVAILABLE: std::sync::OnceLock<bool> = std::sync::OnceLock::new();
        *AVAILABLE.get_or_init(|| {
            std::env::var_os("PINELAND_DISABLE_SHANI").is_none()
                && is_x86_feature_detected!("sha")
                && is_x86_feature_detected!("sse2")
                && is_x86_feature_detected!("ssse3")
                && is_x86_feature_detected!("sse4.1")
        })
    }

    #[inline]
    #[target_feature(enable = "sha,sse2,ssse3,sse4.1")]
    unsafe fn schedule(v0: __m128i, v1: __m128i, v2: __m128i, v3: __m128i) -> __m128i {
        let t1 = _mm_sha256msg1_epu32(v0, v1);
        let t2 = _mm_alignr_epi8(v3, v2, 4);
        let t3 = _mm_add_epi32(t1, t2);
        _mm_sha256msg2_epu32(t3, v3)
    }

    #[target_feature(enable = "sha,sse2,ssse3,sse4.1")]
    pub(super) unsafe fn compress(state: &mut [u32; 8], blocks: &[u8]) {
        macro_rules! rounds4 {
            ($abef:ident, $cdgh:ident, $rest:expr, $i:expr) => {{
                let kv = _mm_loadu_si128(K.as_ptr().add(4 * $i) as *const __m128i);
                let t1 = _mm_add_epi32($rest, kv);
                $cdgh = _mm_sha256rnds2_epu32($cdgh, $abef, t1);
                let t2 = _mm_shuffle_epi32(t1, 0x0E);
                $abef = _mm_sha256rnds2_epu32($abef, $cdgh, t2);
            }};
        }
        macro_rules! schedule_rounds4 {
            ($abef:ident, $cdgh:ident, $w0:expr, $w1:expr, $w2:expr, $w3:expr, $w4:expr, $i:expr) => {{
                $w4 = schedule($w0, $w1, $w2, $w3);
                rounds4!($abef, $cdgh, $w4, $i);
            }};
        }

        let mask = _mm_set_epi64x(
            0x0C0D_0E0F_0809_0A0Bu64 as i64,
            0x0405_0607_0001_0203u64 as i64,
        );
        let state_ptr = state.as_ptr() as *const __m128i;
        let dcba = _mm_loadu_si128(state_ptr);
        let efgh = _mm_loadu_si128(state_ptr.add(1));
        let cdab = _mm_shuffle_epi32(dcba, 0xB1);
        let efgh = _mm_shuffle_epi32(efgh, 0x1B);
        let mut abef = _mm_alignr_epi8(cdab, efgh, 8);
        let mut cdgh = _mm_blend_epi16(efgh, cdab, 0xF0);

        for block in blocks.chunks_exact(64) {
            let abef_save = abef;
            let cdgh_save = cdgh;
            let data_ptr = block.as_ptr() as *const __m128i;
            let mut w0 = _mm_shuffle_epi8(_mm_loadu_si128(data_ptr), mask);
            let mut w1 = _mm_shuffle_epi8(_mm_loadu_si128(data_ptr.add(1)), mask);
            let mut w2 = _mm_shuffle_epi8(_mm_loadu_si128(data_ptr.add(2)), mask);
            let mut w3 = _mm_shuffle_epi8(_mm_loadu_si128(data_ptr.add(3)), mask);
            let mut w4;

            rounds4!(abef, cdgh, w0, 0);
            rounds4!(abef, cdgh, w1, 1);
            rounds4!(abef, cdgh, w2, 2);
            rounds4!(abef, cdgh, w3, 3);
            schedule_rounds4!(abef, cdgh, w0, w1, w2, w3, w4, 4);
            schedule_rounds4!(abef, cdgh, w1, w2, w3, w4, w0, 5);
            schedule_rounds4!(abef, cdgh, w2, w3, w4, w0, w1, 6);
            schedule_rounds4!(abef, cdgh, w3, w4, w0, w1, w2, 7);
            schedule_rounds4!(abef, cdgh, w4, w0, w1, w2, w3, 8);
            schedule_rounds4!(abef, cdgh, w0, w1, w2, w3, w4, 9);
            schedule_rounds4!(abef, cdgh, w1, w2, w3, w4, w0, 10);
            schedule_rounds4!(abef, cdgh, w2, w3, w4, w0, w1, 11);
            schedule_rounds4!(abef, cdgh, w3, w4, w0, w1, w2, 12);
            schedule_rounds4!(abef, cdgh, w4, w0, w1, w2, w3, 13);
            schedule_rounds4!(abef, cdgh, w0, w1, w2, w3, w4, 14);
            schedule_rounds4!(abef, cdgh, w1, w2, w3, w4, w0, 15);

            abef = _mm_add_epi32(abef, abef_save);
            cdgh = _mm_add_epi32(cdgh, cdgh_save);
        }

        let feba = _mm_shuffle_epi32(abef, 0x1B);
        let dchg = _mm_shuffle_epi32(cdgh, 0xB1);
        let dcba = _mm_blend_epi16(feba, dchg, 0xF0);
        let hgef = _mm_alignr_epi8(dchg, feba, 8);
        let state_ptr = state.as_mut_ptr() as *mut __m128i;
        _mm_storeu_si128(state_ptr, dcba);
        _mm_storeu_si128(state_ptr.add(1), hgef);
    }
}

pub fn hex(data: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut result = String::with_capacity(data.len() * 2);
    for byte in data {
        result.push(DIGITS[(byte >> 4) as usize] as char);
        result.push(DIGITS[(byte & 0x0f) as usize] as char);
    }
    result
}

pub fn digest_hex(data: &[u8]) -> String {
    hex(&digest(data))
}

#[cfg(test)]
mod tests {
    use super::{compress_portable, digest, digest_hex, INITIAL};

    /// Reference digest: the original padded-buffer portable implementation.
    fn reference_digest(data: &[u8]) -> [u8; 32] {
        let mut state = INITIAL;
        let bit_length = (data.len() as u128) * 8;
        let mut padded = data.to_vec();
        padded.push(0x80);
        while padded.len() % 64 != 56 {
            padded.push(0);
        }
        padded.extend_from_slice(&(bit_length as u64).to_be_bytes());
        compress_portable(&mut state, &padded);
        let mut output = [0u8; 32];
        for (index, word) in state.iter().enumerate() {
            output[index * 4..index * 4 + 4].copy_from_slice(&word.to_be_bytes());
        }
        output
    }

    #[test]
    fn accelerated_matches_reference_for_all_tail_lengths() {
        let mut data = Vec::new();
        let mut x = 0x9e37_79b9_7f4a_7c15u64;
        for _ in 0..5000 {
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            data.push(x as u8);
        }
        for length in (0..300).chain([1023, 1024, 1025, 4095, 4096, 4097, 5000]) {
            assert_eq!(
                digest(&data[..length]),
                reference_digest(&data[..length]),
                "length {length}"
            );
        }
    }

    #[test]
    fn known_vectors() {
        assert_eq!(
            digest_hex(b""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
        assert_eq!(
            digest_hex(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }
}
