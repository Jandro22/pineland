# Pineland Native v1

This directory is the standalone Rust runtime.  The `pineland` executable owns
configuration validation, world generation, event scheduling, simulation,
filtering, forecast branches, checkpoint/restart, provenance, and benchmark
outputs.  Python is not required by any simulation command.

## Build

The toolchain and dependency graph are pinned by `rust-toolchain.toml` and
`Cargo.lock`:

```powershell
cargo test --workspace --manifest-path rust/Cargo.toml
cargo build --release --locked --manifest-path rust/Cargo.toml -p pineland-cli
```

For a native Parquet row-group writer, enable the optional `pineland-io`
feature when building the analysis-facing library:

```powershell
cargo check --locked --manifest-path rust/Cargo.toml -p pineland-io --features parquet
```

The release profile uses LTO, one code-generation unit, and panic abort.  It
does not enable fast-math or `target-cpu=native`.  For a certified Linux
ensemble, build one explicitly named portable target (for example
`x86-64-v3`) and record the resulting binary hash in the run manifest.  A
Genoa/Zen 4 build is a separate binary and must not be mixed with the portable
ensemble without an equivalence certificate.

## Commands

```text
pineland validate-config [config.json]
pineland generate [config.json] --output DIR
pineland run [config.json] --seed N --days N --output DIR
pineland resume CHECKPOINT_DIR --until N --output DIR
pineland filter [config.json] --particles N --days N --threads N --observations FILE --output DIR
pineland filter --checkpoint CHECKPOINT_DIR --until N --output DIR
pineland filter [config.json] --mpi --particles N --days N --threads N --observations FILE --output DIR
pineland filter --mpi --checkpoint CHECKPOINT_DIR --until N --output DIR
pineland forecast [config.json] --particles N --branches N --until N
pineland inspect-checkpoint CHECKPOINT_DIR
pineland hash-state [CHECKPOINT_DIR]
pineland benchmark [config.json] --particles N --days N --threads N
pineland version
```

Example from the repository root:

```powershell
cargo run --release --locked --manifest-path rust/Cargo.toml -p pineland-cli -- run scenarios/baseline.json --seed 20011126 --days 7 --output outputs/native-baseline
```

Each run writes a summary, JSONL event/observation streams, a versioned
checkpoint directory, and `run_metadata.json`.  Filter runs additionally
write `filter_state.json`, containing normalized continuation state for the
filter RNG, weights, guided proposal, and MCSE monitor.  A filter can be
continued with `--checkpoint` when its sibling `filter_state.json` and
`config.json` are present.

The MPI-enabled filter accepts the same completed checkpoint and continuation
files, repartitions particles canonically for the current world size, and can
therefore restart with a different number of ranks.  MPI restart currently
requires the unguided filter path; guided proposals remain available to the
single-process filter.

`--observations` accepts a JSON array, an object of the form
`{"observations": [...]}`, or one JSON observation object per line.  Each
record has a finite `time` and a `type` of `binary_activity`,
`gaussian_control`, or `gaussian_insurgent_personnel` with the fields needed
by that likelihood.  Records are canonically ordered by time before the
native boundary loop.

## Architecture

The workspace is split into dependency-light crates:

* `pineland-core`: typed IDs, SoA state, static CSR topology, CPython MT19937
  compatibility, deterministic scheduler, JSON, checkpoint codec, and
  provenance.
* `pineland-model`: native typed-event model processes for physical presence,
  patrols, information/beliefs, action/contact/combat, logistics/movement,
  recruitment/footholds/organization ecology, social and mobility dynamics,
  governance/economy/political order, foreign affairs, peace, and recording.
* `pineland-inference`: normalized log weights, ESS, systematic resampling,
  guided proposals, Rao–Blackwellized activity likelihoods, deterministic
  Rayon particle propagation, MCSE, and branch forecasts.
* `pineland-io`: run products, configuration and checkpoint adapters, and the
  deterministic columnar row-group API.  The default writer is JSONL so the
  core remains dependency-light; `--features parquet` adds an atomic native
  Parquet writer with one canonical UTF-8 JSON row per record, without
  changing checkpoint bytes.
* `pineland-hpc`: canonical particle ownership, rank-independent boundary
  reduction, packed parent-state frames, and deterministic all-to-all
  resampling plans for MPI launchers.  The default Windows build includes a
  rank-count harness; the optional `mpi` feature enables the live MPI adapter
  on a host with an MPI implementation.
* `pineland-python`: optional coarse C ABI; it is not on the simulation hot
  path.

State hashes include the complete continuation state: all mutable arrays,
RNG words and Gaussian cache, scheduler heap/sequence, weights, ancestry,
observations, event log, and counters.  Checkpoints are schema-owned binary
  payloads, never Rust memory images; manifests are published only after every
  shard has been written, flushed, checksummed, and decoded successfully.

## Determinism contract

Trajectory-local event order is `(time, priority, sequence)`.  Process RNGs
are namespace-derived CPython-compatible streams.  Particle workers use Rayon
only across independent trajectories; particle IDs, branch IDs, resampling
parents, and RNG streams never depend on worker, rank, or completion order.
The `pineland-hpc` crate performs normalization and resampling after weights
are gathered in logical particle order, which is the required MPI boundary
contract.
