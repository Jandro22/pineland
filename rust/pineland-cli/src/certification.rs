//! Cross-language certification probes.
//!
//! These commands are deliberately separate from the simulation hot path.  A
//! Python harness invokes `certify-rng`, computes the same vectors with the
//! frozen CPython `random.Random` implementation, and compares both the
//! output digest and the exported MT state.  Keeping the probe in the native
//! binary makes the certificate exercise the exact release artifact that is
//! intended to run the model.

use super::Arguments;
use pineland_core::json::{self, JsonValue};
use pineland_core::rng::{PyRandomCompat, RngState};
use pineland_core::sha256;
use std::fs;
use std::path::PathBuf;

const DRAW_COUNT: usize = 100_000;
const SAMPLE_ROUNDS: usize = 5_000;
const SHUFFLE_ROUNDS: usize = 1_000;
const SAMPLE_LENGTH: usize = 1_000;
const SAMPLE_SIZE: usize = 25;
const SHUFFLE_LENGTH: usize = 128;

/// The R2 seed list is part of the certification contract.  It spans small
/// seeds, boundary values, and the high unsigned 64-bit range without relying
/// on a platform-specific integer representation.
pub(crate) const CERTIFICATION_SEEDS: [u64; 20] = [
    0,
    1,
    2,
    3,
    7,
    17,
    42,
    99,
    123,
    314_159,
    8_675_309,
    20_260_902,
    20_011_126,
    2_147_483_647,
    4_294_967_295,
    4_294_967_296,
    281_474_976_723_001,
    9_223_372_036_854_775_807,
    18_446_744_073_709_551_615,
    16_021_456_112_345_678_901,
];

pub(crate) fn certify_rng(arguments: &Arguments) -> Result<(), String> {
    if let Some(path) = arguments.value("state-file") {
        return continue_from_state(arguments, PathBuf::from(path));
    }

    let draws = arguments.usize("draws", DRAW_COUNT)?;
    if draws == 0 {
        return Err("--draws must be positive".to_string());
    }
    let sample_rounds = arguments.usize("sample-rounds", SAMPLE_ROUNDS)?;
    let shuffle_rounds = arguments.usize("shuffle-rounds", SHUFFLE_ROUNDS)?;
    if let Some(seed) = arguments.value("seed") {
        let seed = seed
            .parse::<u64>()
            .map_err(|_| "--seed must be an unsigned integer".to_string())?;
        let mut result = JsonValue::object();
        result.insert("schema", JsonValue::string("pineland-rng-certification-v1"));
        result.insert("draws", JsonValue::integer(draws as u64));
        result.insert(
            "operations",
            seed_vector(seed, draws, sample_rounds, shuffle_rounds)?,
        );
        println!("{}", result.to_pretty());
        return Ok(());
    }
    let mut result = JsonValue::object();
    result.insert("schema", JsonValue::string("pineland-rng-certification-v1"));
    result.insert("draws", JsonValue::integer(draws as u64));
    result.insert("sample_rounds", JsonValue::integer(sample_rounds as u64));
    result.insert("shuffle_rounds", JsonValue::integer(shuffle_rounds as u64));
    let mut seeds = JsonValue::Array(Vec::with_capacity(CERTIFICATION_SEEDS.len()));
    if let JsonValue::Array(values) = &mut seeds {
        values.extend(
            CERTIFICATION_SEEDS
                .iter()
                .map(|seed| JsonValue::integer(*seed)),
        );
    }
    result.insert("seeds", seeds);

    let mut vectors = JsonValue::Array(Vec::with_capacity(CERTIFICATION_SEEDS.len()));
    if let JsonValue::Array(values) = &mut vectors {
        for seed in CERTIFICATION_SEEDS {
            values.push(seed_vector(seed, draws, sample_rounds, shuffle_rounds)?);
        }
    }
    result.insert("vectors", vectors);
    println!("{}", result.to_pretty());
    Ok(())
}

fn seed_vector(
    seed: u64,
    draws: usize,
    sample_rounds: usize,
    shuffle_rounds: usize,
) -> Result<JsonValue, String> {
    let mut operations = JsonValue::object();
    operations.insert("random", float_vector(seed, draws, |rng| rng.random()));
    operations.insert(
        "uniform",
        float_vector(seed, draws, |rng| rng.uniform(-17.25, 83.5)),
    );
    operations.insert(
        "randrange",
        integer_vector(seed, draws, |rng| {
            rng.randrange(17).map(|value| value as u64)
        })?,
    );
    operations.insert(
        "choice",
        integer_vector(seed, draws, |rng| {
            rng.choice_index(97).map(|value| value as u64)
        })?,
    );
    operations.insert(
        "choices_equal",
        integer_vector(seed, draws, |rng| {
            rng.choices_indices(97, None, 1)
                .map(|values| values[0] as u64)
        })?,
    );
    let weights = (0..97)
        .map(|index| 0.25 + (index as f64) * 0.125)
        .collect::<Vec<_>>();
    operations.insert(
        "choices_weighted",
        integer_vector(seed, draws, |rng| {
            rng.choices_indices(97, Some(&weights), 1)
                .map(|values| values[0] as u64)
        })?,
    );
    operations.insert("sample", sample_vector(seed, sample_rounds)?);
    operations.insert("shuffle", shuffle_vector(seed, shuffle_rounds)?);
    operations.insert(
        "gauss",
        float_vector(seed, draws, |rng| rng.gauss(1.25, 0.75)),
    );
    operations.insert(
        "normalvariate",
        float_vector(seed, draws, |rng| rng.normalvariate(-2.0, 1.75)),
    );
    operations.insert(
        "lognormvariate",
        float_vector(seed, draws, |rng| rng.lognormvariate(0.0, 0.55)),
    );
    operations.insert(
        "lognormvariate_045",
        float_vector(seed, draws, |rng| rng.lognormvariate(0.0, 0.45)),
    );
    operations.insert(
        "lognormvariate_080",
        float_vector(seed, draws, |rng| rng.lognormvariate(0.0, 0.8)),
    );
    operations.insert(
        "expovariate",
        float_vector(seed, draws, |rng| {
            rng.expovariate(1.0 / 3.75)
                .expect("certification rate is valid")
        }),
    );
    operations.insert(
        "betavariate",
        float_vector_result(seed, draws, |rng| {
            rng.betavariate(2.0, 9.0).map_err(|error| error.to_string())
        })?,
    );

    let mut vector = JsonValue::object();
    vector.insert("seed", JsonValue::integer(seed));
    vector.insert("operations", operations);
    Ok(vector)
}

fn float_vector<F>(seed: u64, count: usize, mut draw: F) -> JsonValue
where
    F: FnMut(&mut PyRandomCompat) -> f64,
{
    let mut rng = PyRandomCompat::from_seed(seed);
    let mut bytes = Vec::with_capacity(count * 8);
    for _ in 0..count {
        bytes.extend_from_slice(&draw(&mut rng).to_bits().to_le_bytes());
    }
    operation_digest(&bytes, &rng)
}

fn float_vector_result<F>(seed: u64, count: usize, mut draw: F) -> Result<JsonValue, String>
where
    F: FnMut(&mut PyRandomCompat) -> Result<f64, String>,
{
    let mut rng = PyRandomCompat::from_seed(seed);
    let mut bytes = Vec::with_capacity(count * 8);
    for _ in 0..count {
        bytes.extend_from_slice(
            &draw(&mut rng)
                .map_err(|error| error.to_string())?
                .to_bits()
                .to_le_bytes(),
        );
    }
    Ok(operation_digest(&bytes, &rng))
}

fn integer_vector<F>(seed: u64, count: usize, mut draw: F) -> Result<JsonValue, String>
where
    F: FnMut(&mut PyRandomCompat) -> Result<u64, pineland_core::rng::RngError>,
{
    let mut rng = PyRandomCompat::from_seed(seed);
    let mut bytes = Vec::with_capacity(count * 8);
    for _ in 0..count {
        bytes.extend_from_slice(
            &draw(&mut rng)
                .map_err(|error| error.to_string())?
                .to_le_bytes(),
        );
    }
    Ok(operation_digest(&bytes, &rng))
}

fn sample_vector(seed: u64, rounds: usize) -> Result<JsonValue, String> {
    let mut rng = PyRandomCompat::from_seed(seed);
    let mut bytes = Vec::with_capacity(rounds * SAMPLE_SIZE * 8);
    for _ in 0..rounds {
        for value in rng
            .sample_indices(SAMPLE_LENGTH, SAMPLE_SIZE)
            .map_err(|error| error.to_string())?
        {
            bytes.extend_from_slice(&(value as u64).to_le_bytes());
        }
    }
    Ok(operation_digest(&bytes, &rng))
}

fn shuffle_vector(seed: u64, rounds: usize) -> Result<JsonValue, String> {
    let mut rng = PyRandomCompat::from_seed(seed);
    let mut bytes = Vec::with_capacity(rounds * SHUFFLE_LENGTH * 4);
    for _ in 0..rounds {
        let mut values = (0..SHUFFLE_LENGTH).collect::<Vec<_>>();
        rng.shuffle_indices(&mut values)
            .map_err(|error| error.to_string())?;
        for value in values {
            bytes.extend_from_slice(&(value as u32).to_le_bytes());
        }
    }
    Ok(operation_digest(&bytes, &rng))
}

fn operation_digest(bytes: &[u8], rng: &PyRandomCompat) -> JsonValue {
    let mut value = JsonValue::object();
    value.insert("digest", JsonValue::string(sha256::digest_hex(bytes)));
    value.insert("state_digest", JsonValue::string(state_digest(rng)));
    value
}

fn state_digest(rng: &PyRandomCompat) -> String {
    let state = rng.state();
    let mut bytes = Vec::with_capacity(624 * 4 + 4 + 9);
    for word in state.words {
        bytes.extend_from_slice(&word.to_le_bytes());
    }
    bytes.extend_from_slice(&state.index.to_le_bytes());
    match state.gauss_next {
        Some(value) => {
            bytes.push(1);
            bytes.extend_from_slice(&value.to_bits().to_le_bytes());
        }
        None => bytes.push(0),
    }
    sha256::digest_hex(&bytes)
}

fn state_to_json(state: &RngState) -> JsonValue {
    let mut value = JsonValue::object();
    let mut words = JsonValue::Array(Vec::with_capacity(state.words.len()));
    if let JsonValue::Array(values) = &mut words {
        values.extend(
            state
                .words
                .iter()
                .map(|word| JsonValue::integer(*word as u64)),
        );
    }
    value.insert("words", words);
    value.insert("index", JsonValue::integer(state.index as u64));
    value.insert(
        "gauss_next",
        state
            .gauss_next
            .map(JsonValue::number)
            .unwrap_or(JsonValue::Null),
    );
    value
}

fn continue_from_state(arguments: &Arguments, path: PathBuf) -> Result<(), String> {
    let text = fs::read_to_string(&path)
        .map_err(|error| format!("cannot read RNG state {}: {error}", path.display()))?;
    let value = json::parse(&text).map_err(|error| error.to_string())?;
    let state = parse_state(&value)?;
    let operation = arguments.string("operation", "random");
    let draws = arguments.usize("draws", 10_000)?;
    if draws == 0 {
        return Err("--draws must be positive".to_string());
    }
    let mut rng = PyRandomCompat::from_state(state).map_err(|error| error.to_string())?;
    let output = match operation.as_str() {
        "random" => float_vector_from_rng(&mut rng, draws, |rng| Ok(rng.random()))?,
        "gauss" => float_vector_from_rng(&mut rng, draws, |rng| Ok(rng.gauss(1.25, 0.75)))?,
        "normalvariate" => {
            float_vector_from_rng(&mut rng, draws, |rng| Ok(rng.normalvariate(-2.0, 1.75)))?
        }
        "expovariate" => float_vector_from_rng(&mut rng, draws, |rng| {
            rng.expovariate(1.0 / 3.75)
                .map_err(|error| error.to_string())
        })?,
        "betavariate" => float_vector_from_rng(&mut rng, draws, |rng| {
            rng.betavariate(2.0, 9.0).map_err(|error| error.to_string())
        })?,
        _ => {
            return Err(format!(
                "unsupported RNG continuation operation '{operation}'"
            ))
        }
    };
    println!("{}", output.to_pretty());
    Ok(())
}

fn float_vector_from_rng<F>(
    rng: &mut PyRandomCompat,
    count: usize,
    mut draw: F,
) -> Result<JsonValue, String>
where
    F: FnMut(&mut PyRandomCompat) -> Result<f64, String>,
{
    let mut bytes = Vec::with_capacity(count * 8);
    for _ in 0..count {
        bytes.extend_from_slice(
            &draw(rng)
                .map_err(|error| error.to_string())?
                .to_bits()
                .to_le_bytes(),
        );
    }
    let mut output = operation_digest(&bytes, rng);
    output.insert("state", state_to_json(&rng.state()));
    Ok(output)
}

fn parse_state(value: &JsonValue) -> Result<RngState, String> {
    let object = value
        .as_object()
        .ok_or_else(|| "RNG state must be a JSON object".to_string())?;
    let words_value = object
        .get("words")
        .and_then(JsonValue::as_array)
        .ok_or_else(|| "RNG state.words must be an array".to_string())?;
    if words_value.len() != 624 {
        return Err(format!(
            "RNG state.words must contain 624 values, got {}",
            words_value.len()
        ));
    }
    let mut words = [0u32; 624];
    for (index, value) in words_value.iter().enumerate() {
        let word = value
            .as_u64()
            .and_then(|value| u32::try_from(value).ok())
            .ok_or_else(|| format!("RNG state.words[{index}] must be a uint32"))?;
        words[index] = word;
    }
    let index = object
        .get("index")
        .and_then(JsonValue::as_u64)
        .and_then(|value| u32::try_from(value).ok())
        .ok_or_else(|| "RNG state.index must be an integer in 0..=624".to_string())?;
    let gauss_next =
        match object.get("gauss_next") {
            None | Some(JsonValue::Null) => None,
            Some(value) => Some(value.as_f64().ok_or_else(|| {
                "RNG state.gauss_next must be null or a finite number".to_string()
            })?),
        };
    Ok(RngState {
        words,
        index,
        gauss_next,
    })
}
