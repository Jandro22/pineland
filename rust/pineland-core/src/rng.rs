//! CPython `random.Random` compatibility and deterministic process streams.
//!
//! Python's default `random.Random` is MT19937 with a 53-bit composition for
//! `random()`.  Pineland v1 keeps that algorithm, including the seeding and
//! helper-method consumption rules, so a native trajectory can be certified
//! against the frozen Python reference.

use crate::sha256;
use std::collections::BTreeMap;
use std::f64::consts::PI;
use std::fmt;

// CPython's ``math.exp`` on Windows is backed by the Universal CRT.  Rust's
// intrinsic f64::exp can differ from that implementation by one ulp for some
// arguments, which is enough to change a canonical static-world digest even
// though the MT stream itself is unchanged. Keep the platform oracle explicit
// for the exact-parity build and use the native intrinsic elsewhere.
#[cfg(windows)]
#[link(name = "ucrt")]
unsafe extern "C" {
    fn exp(value: f64) -> f64;
}

fn python_exp(value: f64) -> f64 {
    #[cfg(windows)]
    {
        // SAFETY: the Universal CRT exp function is pure for finite inputs and
        // has the same f64 ABI used by CPython's math module.
        unsafe { exp(value) }
    }
    #[cfg(not(windows))]
    {
        value.exp()
    }
}

const N: usize = 624;
const M: usize = 397;
const MATRIX_A: u32 = 0x9908_B0DF;
const UPPER_MASK: u32 = 0x8000_0000;
const LOWER_MASK: u32 = 0x7fff_ffff;

#[derive(Clone, Debug, PartialEq)]
pub struct RngState {
    pub words: [u32; N],
    pub index: u32,
    pub gauss_next: Option<f64>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct PyRandomCompat {
    state: [u32; N],
    index: usize,
    gauss_next: Option<f64>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RngError {
    InvalidStateIndex(u32),
    EmptyPopulation,
    InvalidRange,
    InvalidSampleSize,
    InvalidDistributionParameter,
}

impl fmt::Display for RngError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidStateIndex(index) => write!(formatter, "invalid MT state index {index}"),
            Self::EmptyPopulation => formatter.write_str("cannot draw from an empty population"),
            Self::InvalidRange => formatter.write_str("range must have a positive width"),
            Self::InvalidSampleSize => formatter.write_str("sample size is outside the population"),
            Self::InvalidDistributionParameter => {
                formatter.write_str("distribution parameters must be positive")
            }
        }
    }
}

impl std::error::Error for RngError {}

impl PyRandomCompat {
    /// Construct the same stream as `random.Random(seed)` for a non-negative
    /// Python integer that fits in 64 bits.
    pub fn from_seed(seed: u64) -> Self {
        let key = if seed == 0 {
            vec![0]
        } else {
            let mut value = seed;
            let mut key = Vec::with_capacity(2);
            while value != 0 {
                key.push(value as u32);
                value >>= 32;
            }
            key
        };
        Self::from_key(&key)
    }

    pub fn from_signed_seed(seed: i64) -> Self {
        Self::from_seed(seed.unsigned_abs())
    }

    pub fn from_key(key: &[u32]) -> Self {
        assert!(!key.is_empty(), "MT19937 key cannot be empty");
        let mut state = [0u32; N];
        state[0] = 19_650_218;
        for index in 1..N {
            state[index] = 1_812_433_253u32
                .wrapping_mul(state[index - 1] ^ (state[index - 1] >> 30))
                .wrapping_add(index as u32);
        }
        let mut i = 1usize;
        let mut j = 0usize;
        let rounds = N.max(key.len());
        for _ in 0..rounds {
            state[i] = (state[i] ^ (state[i - 1] ^ (state[i - 1] >> 30)).wrapping_mul(1_664_525))
                .wrapping_add(key[j])
                .wrapping_add(j as u32);
            i += 1;
            j += 1;
            if i >= N {
                state[0] = state[N - 1];
                i = 1;
            }
            if j >= key.len() {
                j = 0;
            }
        }
        for _ in 0..N - 1 {
            state[i] = (state[i]
                ^ (state[i - 1] ^ (state[i - 1] >> 30)).wrapping_mul(1_566_083_941))
            .wrapping_sub(i as u32);
            i += 1;
            if i >= N {
                state[0] = state[N - 1];
                i = 1;
            }
        }
        state[0] = UPPER_MASK;
        Self {
            state,
            index: N,
            gauss_next: None,
        }
    }

    pub fn from_state(state: RngState) -> Result<Self, RngError> {
        if state.index > N as u32 {
            return Err(RngError::InvalidStateIndex(state.index));
        }
        Ok(Self {
            state: state.words,
            index: state.index as usize,
            gauss_next: state.gauss_next,
        })
    }

    pub fn state(&self) -> RngState {
        RngState {
            words: self.state,
            index: self.index as u32,
            gauss_next: self.gauss_next,
        }
    }

    pub fn raw_state(&self) -> &[u32; N] {
        &self.state
    }

    pub fn raw_index(&self) -> usize {
        self.index
    }

    fn twist(&mut self) {
        for index in 0..N {
            let value =
                (self.state[index] & UPPER_MASK) | (self.state[(index + 1) % N] & LOWER_MASK);
            let mut next = self.state[(index + M) % N] ^ (value >> 1);
            if value & 1 != 0 {
                next ^= MATRIX_A;
            }
            self.state[index] = next;
        }
        self.index = 0;
    }

    pub fn uint32(&mut self) -> u32 {
        if self.index >= N {
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

    pub fn getrandbits(&mut self, bits: usize) -> u64 {
        assert!(
            bits <= 64,
            "native getrandbits currently supports at most 64 bits"
        );
        if bits == 0 {
            return 0;
        }
        if bits <= 32 {
            return (self.uint32() >> (32 - bits)) as u64;
        }
        // CPython's `_random_Random_getrandbits_impl` stores 32-bit words in
        // little-endian order in the returned Python integer.  That detail is
        // observable by randbelow for ranges wider than 2**32.
        let low = self.uint32() as u64;
        let high = self.uint32() as u64;
        let high_bits = bits - 32;
        let high = if high_bits == 32 {
            high
        } else {
            high >> (32 - high_bits)
        };
        low | (high << 32)
    }

    /// Exact equivalent of CPython's `random_random` implementation.
    pub fn random(&mut self) -> f64 {
        let first = (self.uint32() >> 5) as f64;
        let second = (self.uint32() >> 6) as f64;
        (first * 67_108_864.0 + second) * (1.0 / 9_007_199_254_740_992.0)
    }

    pub fn uniform(&mut self, lower: f64, upper: f64) -> f64 {
        lower + (upper - lower) * self.random()
    }

    pub fn randbelow(&mut self, stop: usize) -> Result<usize, RngError> {
        if stop == 0 {
            return Err(RngError::InvalidRange);
        }
        let bits = (usize::BITS - stop.leading_zeros()) as usize;
        loop {
            let candidate = self.getrandbits(bits) as usize;
            if candidate < stop {
                return Ok(candidate);
            }
        }
    }

    pub fn randrange(&mut self, stop: usize) -> Result<usize, RngError> {
        self.randbelow(stop)
    }

    pub fn randrange_between(
        &mut self,
        start: isize,
        stop: isize,
        step: isize,
    ) -> Result<isize, RngError> {
        if step == 0 {
            return Err(RngError::InvalidRange);
        }
        let width = if step > 0 {
            if stop <= start {
                0
            } else {
                ((stop - start - 1) / step) + 1
            }
        } else if stop >= start {
            0
        } else {
            ((start - stop - 1) / (-step)) + 1
        };
        if width <= 0 {
            return Err(RngError::InvalidRange);
        }
        Ok(start + self.randbelow(width as usize)? as isize * step)
    }

    pub fn choice_index(&mut self, length: usize) -> Result<usize, RngError> {
        self.randbelow(length)
    }

    /// Equivalent to `random.choices(population, weights=weights, k=1)`
    /// repeated `k` times.  CPython consumes one `random()` draw even when the
    /// population has one item; callers rely on that stream behavior.
    pub fn choices_indices(
        &mut self,
        length: usize,
        weights: Option<&[f64]>,
        k: usize,
    ) -> Result<Vec<usize>, RngError> {
        if length == 0 {
            return Err(RngError::EmptyPopulation);
        }
        let mut result = Vec::with_capacity(k);
        match weights {
            None => {
                for _ in 0..k {
                    result.push((self.random() * length as f64) as usize);
                }
            }
            Some(weights) => {
                if weights.len() != length {
                    return Err(RngError::InvalidRange);
                }
                let mut cumulative = Vec::with_capacity(length);
                let mut total = 0.0;
                for weight in weights {
                    if *weight < 0.0 || !weight.is_finite() {
                        return Err(RngError::InvalidRange);
                    }
                    total += *weight;
                    cumulative.push(total);
                }
                if total <= 0.0 || !total.is_finite() {
                    return Err(RngError::InvalidRange);
                }
                for _ in 0..k {
                    let target = self.random() * total;
                    let index = cumulative.partition_point(|value| *value <= target);
                    result.push(index.min(length - 1));
                }
            }
        }
        Ok(result)
    }

    pub fn sample_indices(
        &mut self,
        length: usize,
        sample_size: usize,
    ) -> Result<Vec<usize>, RngError> {
        if sample_size > length {
            return Err(RngError::InvalidSampleSize);
        }
        if sample_size == 0 {
            return Ok(Vec::new());
        }
        // This mirrors Lib/random.py's setsize calculation and the two
        // algorithms used by CPython's Random.sample.
        let mut setsize = 21usize;
        if sample_size > 5 {
            let exponent = ((sample_size * 3) as f64).log(4.0).ceil() as u32;
            setsize += 4usize.saturating_pow(exponent);
        }
        let mut result = Vec::with_capacity(sample_size);
        if length <= setsize {
            let mut pool: Vec<usize> = (0..length).collect();
            for index in 0..sample_size {
                let selected = self.randbelow(length - index)?;
                result.push(pool[selected]);
                pool[selected] = pool[length - index - 1];
            }
        } else {
            let mut selected = std::collections::BTreeSet::new();
            while result.len() < sample_size {
                let candidate = self.randbelow(length)?;
                if selected.insert(candidate) {
                    result.push(candidate);
                }
            }
        }
        Ok(result)
    }

    pub fn gauss(&mut self, mean: f64, standard_deviation: f64) -> f64 {
        if let Some(value) = self.gauss_next.take() {
            return mean + value * standard_deviation;
        }
        let x2pi = self.random() * (2.0 * PI);
        let g2rad = (-2.0 * (1.0 - self.random()).ln()).sqrt();
        let z = x2pi.cos() * g2rad;
        self.gauss_next = Some(x2pi.sin() * g2rad);
        mean + z * standard_deviation
    }

    pub fn normalvariate(&mut self, mean: f64, standard_deviation: f64) -> f64 {
        // Pineland's initialization uses normalvariate only in the generator;
        // retaining the CPython algorithm here makes the native API useful for
        // both initialization and event processes.  Unlike gauss(), this does
        // not use the cached spare value.
        let nv_magicconst = 4.0 * python_exp(-0.5) / 2.0f64.sqrt();
        loop {
            let u1 = self.random();
            let u2 = 1.0 - self.random();
            let z = nv_magicconst * (u1 - 0.5) / u2;
            let zz = z * z / 4.0;
            if zz <= -u2.ln() {
                return mean + z * standard_deviation;
            }
        }
    }

    /// Exact equivalent of CPython's `Random.lognormvariate` helper.
    pub fn lognormvariate(&mut self, mean: f64, standard_deviation: f64) -> f64 {
        python_exp(self.normalvariate(mean, standard_deviation))
    }

    /// The exp implementation used by the Python-compatible distribution
    /// helpers. Exposed for topology generation so static-world transforms do
    /// not silently use a different platform math routine.
    pub fn python_exp(value: f64) -> f64 {
        python_exp(value)
    }

    /// Exact equivalent of CPython's `Random.expovariate` helper.
    pub fn expovariate(&mut self, lambd: f64) -> Result<f64, RngError> {
        if lambd == 0.0 || !lambd.is_finite() {
            return Err(RngError::InvalidDistributionParameter);
        }
        Ok(-(1.0 - self.random()).ln() / lambd)
    }

    /// Exact equivalent of CPython's `Random.gammavariate` helper for the
    /// parameter ranges used by Pineland's generator and certification suite.
    pub fn gammavariate(&mut self, alpha: f64, beta: f64) -> Result<f64, RngError> {
        if alpha <= 0.0 || beta <= 0.0 || !alpha.is_finite() || !beta.is_finite() {
            return Err(RngError::InvalidDistributionParameter);
        }

        if alpha > 1.0 {
            // R.C.H. Cheng, "The generation of Gamma variables with
            // non-integral shape parameters", Applied Statistics (1977).
            let ainv = (2.0 * alpha - 1.0).sqrt();
            let bbb = alpha - 4.0f64.ln();
            let ccc = alpha + ainv;
            let sg_magicconst = 1.0 + 4.5f64.ln();
            loop {
                let u1 = self.random();
                if !(1e-7 < u1 && u1 < 0.9999999) {
                    continue;
                }
                let u2 = 1.0 - self.random();
                let v = (u1 / (1.0 - u1)).ln() / ainv;
                let x = alpha * v.exp();
                let z = u1 * u1 * u2;
                let r = bbb + ccc * v - x;
                if r + sg_magicconst - 4.5 * z >= 0.0 || r >= z.ln() {
                    return Ok(x * beta);
                }
            }
        } else if alpha == 1.0 {
            Ok(-(1.0 - self.random()).ln() * beta)
        } else {
            // Algorithm GS of Kennedy & Gentle for 0 < alpha < 1.
            loop {
                let u = self.random();
                let b = (std::f64::consts::E + alpha) / std::f64::consts::E;
                let p = b * u;
                let x = if p <= 1.0 {
                    p.powf(1.0 / alpha)
                } else {
                    -((b - p) / alpha).ln()
                };
                let u1 = self.random();
                let accepted = if p > 1.0 {
                    u1 <= x.powf(alpha - 1.0)
                } else {
                    u1 <= (-x).exp()
                };
                if accepted {
                    return Ok(x * beta);
                }
            }
        }
    }

    /// Exact equivalent of CPython's `Random.betavariate` helper.
    pub fn betavariate(&mut self, alpha: f64, beta: f64) -> Result<f64, RngError> {
        let y = self.gammavariate(alpha, 1.0)?;
        if y != 0.0 {
            Ok(y / (y + self.gammavariate(beta, 1.0)?))
        } else {
            Ok(0.0)
        }
    }

    /// Fisher-Yates shuffle over an index/value slice.  The caller supplies
    /// the values because the native core does not prescribe a Python object
    /// population type.
    pub fn shuffle_indices(&mut self, values: &mut [usize]) -> Result<(), RngError> {
        for index in (1..values.len()).rev() {
            let selected = self.randbelow(index + 1)?;
            values.swap(index, selected);
        }
        Ok(())
    }

    pub fn clear_gauss_cache(&mut self) {
        self.gauss_next = None;
    }
}

/// Derive the same per-process seed used by the Python implementation:
/// `int.from_bytes(sha256(f"{seed}:{namespace}:{stream}")[:8], "big")`.
pub fn seed_from_namespace(seed: u64, namespace: &str, stream: &str) -> u64 {
    let token = format!("{seed}:{namespace}:{stream}");
    let digest = sha256::digest(token.as_bytes());
    u64::from_be_bytes(digest[..8].try_into().expect("SHA-256 prefix length"))
}

/// Match CPython 3.12+'s compensated floating-point `sum` path.
///
/// Pineland's Python generator uses the built-in `sum` for normalized locality
/// and microzone weights.  A plain Rust iterator sum is a left-fold and can
/// land one ulp away from CPython's compensated result, even when every RNG
/// draw is identical.  The two-term Neumaier accumulator is the algorithm used
/// by the CPython float fast path for finite inputs.
pub fn python_sum(values: &[f64]) -> f64 {
    let mut hi = 0.0;
    let mut lo = 0.0;
    for value in values {
        let next = hi + *value;
        if hi.abs() >= value.abs() {
            lo += (hi - next) + *value;
        } else {
            lo += (*value - next) + hi;
        }
        hi = next;
    }
    hi + lo
}

const DEFAULT_STREAMS: &[&str] = &[
    "world-generation",
    "geography-generation",
    "force-generation",
    "social-network",
    "physical-world",
    "logistics-world",
    "information-world",
    "organization-ecology",
    "political-order",
    "foreign-affairs",
    "relationships",
    "patrol",
    "contact",
    "organized-action",
    "command",
    "force-movement",
    "logistics",
    "information",
    "beliefs",
    "physical",
    "social-influence",
    "mobility",
    "recruitment",
    "organization-ecology-events",
    "governance",
    "economy",
    "political",
    "foreign",
    "peace",
    "recording",
    "checkpoint",
    "forecast",
    "filter",
];

#[derive(Clone, Debug, PartialEq)]
pub struct RngStreams {
    pub root_seed: u64,
    pub namespace: String,
    pub streams: BTreeMap<String, PyRandomCompat>,
}

impl RngStreams {
    pub fn new(root_seed: u64, namespace: impl Into<String>) -> Self {
        let namespace = namespace.into();
        let mut streams = BTreeMap::new();
        for stream in DEFAULT_STREAMS {
            streams.insert(
                (*stream).to_string(),
                PyRandomCompat::from_seed(seed_from_namespace(root_seed, &namespace, stream)),
            );
        }
        Self {
            root_seed,
            namespace,
            streams,
        }
    }

    pub fn get_mut(&mut self, stream: &str) -> &mut PyRandomCompat {
        self.streams.entry(stream.to_string()).or_insert_with(|| {
            PyRandomCompat::from_seed(seed_from_namespace(self.root_seed, &self.namespace, stream))
        })
    }

    pub fn get(&self, stream: &str) -> Option<&PyRandomCompat> {
        self.streams.get(stream)
    }

    /// Create deterministic, branch-scoped future streams without consulting
    /// a worker, thread, or MPI rank.  A forecast branch is a new stochastic
    /// continuation of the current state.  Include the complete current
    /// stream state in the branch namespace; deriving only from root_seed
    /// would silently rewind a checkpointed particle when it is forecast.
    pub fn fork(&self, identity: &str) -> Self {
        let state_tag = sha256::digest_hex(&self.state_digest_material());
        let namespace = format!("{}:branch:{identity}:state:{state_tag}", self.namespace);
        let root_seed = seed_from_namespace(self.root_seed, &namespace, "root");
        let mut streams = BTreeMap::new();
        for name in self.streams.keys() {
            streams.insert(
                name.clone(),
                PyRandomCompat::from_seed(seed_from_namespace(root_seed, &namespace, name)),
            );
        }
        Self {
            root_seed,
            namespace,
            streams,
        }
    }

    pub fn state_digest_material(&self) -> Vec<u8> {
        let mut material = Vec::new();
        for (name, generator) in &self.streams {
            material.extend_from_slice(name.as_bytes());
            material.push(0);
            for word in generator.raw_state() {
                material.extend_from_slice(&word.to_le_bytes());
            }
            material.extend_from_slice(&(generator.raw_index() as u32).to_le_bytes());
            match generator.state().gauss_next {
                Some(value) => {
                    material.push(1);
                    material.extend_from_slice(&value.to_bits().to_le_bytes());
                }
                None => material.push(0),
            }
        }
        material
    }
}

#[cfg(test)]
mod tests {
    use super::{seed_from_namespace, PyRandomCompat};
    use crate::sha256;

    #[test]
    fn random_matches_cpython_examples() {
        let expected = [
            0.8444218515250481,
            0.7579544029403025,
            0.420571580830845,
            0.25891675029296335,
            0.5112747213686085,
        ];
        let mut rng = PyRandomCompat::from_seed(0);
        for value in expected {
            assert_eq!(rng.random(), value);
        }
    }

    #[test]
    fn namespace_seed_matches_sha256_contract() {
        assert_eq!(
            seed_from_namespace(20260902, "baseline", "world-generation"),
            2_120_240_968_955_313_812
        );
    }

    #[test]
    fn helper_consumption_matches_cpython_examples() {
        let mut rng = PyRandomCompat::from_seed(0);
        let values: Vec<usize> = (0..8).map(|_| rng.randrange(17).unwrap()).collect();
        assert_eq!(values, vec![12, 13, 1, 8, 16, 15, 12, 9]);
        let mut rng = PyRandomCompat::from_seed(0);
        assert_eq!(
            rng.sample_indices(20, 8).unwrap(),
            vec![12, 13, 1, 8, 15, 6, 19, 4]
        );
    }

    #[test]
    fn wide_getrandbits_matches_cpython_word_order() {
        let expected = [
            (33, 3_626_764_237u64),
            (34, 7_921_731_533u64),
            (63, 3_553_260_803_050_964_941u64),
            (64, 7_106_521_602_475_165_645u64),
        ];
        for (bits, expected_value) in expected {
            let mut rng = PyRandomCompat::from_seed(0);
            assert_eq!(rng.getrandbits(bits), expected_value);
        }
    }

    #[test]
    fn state_round_trip_preserves_gaussian_cache() {
        let mut original = PyRandomCompat::from_seed(123);
        let first = original.gauss(0.0, 1.0);
        let state = original.state();
        let mut restored = PyRandomCompat::from_state(state).unwrap();
        assert_eq!(original.gauss(0.0, 1.0), restored.gauss(0.0, 1.0));
        assert_eq!(first, 0.40422843322466656);
    }

    #[test]
    fn normalvariate_matches_cpython_vectors() {
        let expected = [
            -0.17833617865111337,
            0.09299998647415351,
            0.7187758465584564,
            -0.4191801769882989,
            -0.11981835108531083,
        ];
        let mut rng = PyRandomCompat::from_seed(123);
        for value in expected {
            assert_eq!(rng.normalvariate(0.0, 1.0), value);
        }
    }

    #[test]
    fn long_random_stream_matches_cpython_reference_prefix() {
        // This is intentionally long enough to cross multiple MT twists and
        // is kept in the permanent certification suite as a cheap regression
        // guard for state indexing and 53-bit composition.
        let mut rng = PyRandomCompat::from_seed(20260902);
        let mut digest_input = Vec::with_capacity(100_000 * 8);
        for _ in 0..100_000 {
            digest_input.extend_from_slice(&rng.random().to_bits().to_le_bytes());
        }
        assert_eq!(
            sha256::digest_hex(&digest_input),
            "1dba454a29de2459eb7f04dbad9f25204f7bc89376131c94c8e82b8ae83c7efc"
        );
    }

    #[test]
    fn branch_forks_are_stable_and_distinct() {
        let streams = super::RngStreams::new(7, "forecast");
        let left = streams.fork("left");
        let left_again = streams.fork("left");
        let right = streams.fork("right");
        assert_eq!(left, left_again);
        assert_ne!(left, right);
        assert_ne!(left.state_digest_material(), right.state_digest_material());
    }
}
