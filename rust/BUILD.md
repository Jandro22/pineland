# Certified native builds

The native runtime has two supported build classes:

1. A portable Linux binary for a certified ensemble, built for the declared
   x86-64-v3 target (or the exact portable target supported by the installed
   compiler).
2. An explicitly named Owl/Genoa binary built for the verified Zen 4 target.

Do not use `RUSTFLAGS="-C target-cpu=native"` for either certified build.  Do
not mix the resulting binaries in one ensemble.  Record each binary SHA256 in
the provenance manifest.

```bash
rustc --version
rustc --print target-list | grep x86_64
rustc --print target-cpus | grep -E 'x86-64-v3|znver4'
cargo test --workspace --manifest-path rust/Cargo.toml
cargo build --release --locked --manifest-path rust/Cargo.toml -p pineland-cli
sha256sum rust/target/release/pineland
```

On an MPI-equipped ARC image, build the live hybrid launcher with:

```bash
module reset
module load foss/2025b
module load Rust/1.93.1-GCCcore-14.3.0
cargo build --release --locked --manifest-path rust/Cargo.toml -p pineland-cli --features mpi
sha256sum rust/target/release/pineland
```

The ordinary Windows build intentionally omits this feature because rsmpi
requires a system MPI implementation.  The MPI CLI path gathers weights in
logical order, performs root-canonical resampling, exchanges versioned parent
frames with `MPI_Alltoallv`, and writes one checkpoint shard per rank.  A
completed MPI checkpoint can be resumed with `filter --mpi --checkpoint`; the
state is repartitioned by logical particle ID so the restart may use a
different rank count.  The MPI path expects the unguided filter continuation.

Independent trajectory ensembles use the ARC Slurm-array layer documented in
rust/hpc/ARC.md. The normal run command is serial, so its production ensemble
profile requests one CPU per executing array element rather than reserving
idle many-core nodes.

The default release profile is deliberately conservative: `opt-level=3`,
`lto=fat`, `codegen-units=1`, `panic=abort`, no debug symbols, and no relaxed
floating-point arithmetic.  Rayon is enabled by default; the dependency-free
fallback remains available with `--no-default-features` for constrained hosts.
