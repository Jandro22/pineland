#!/usr/bin/env bash
# Build the Stage-4 harness on an ARC login node (portable x86-64-v3) and run the model tests.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "${ROOT}"
module reset
module load Rust/1.93.1-GCCcore-14.3.0
unset RUSTFLAGS
export RUSTFLAGS="-C target-cpu=x86-64-v3"
cargo test --release --manifest-path rust/Cargo.toml -p pineland-core -p pineland-model --lib
cargo build --release --manifest-path rust/Cargo.toml --example partner_force_autonomy_stage3
BIN=rust/target/release/examples/partner_force_autonomy_stage3
sha256sum "${BIN}"
echo "Built ${ROOT}/${BIN}"
