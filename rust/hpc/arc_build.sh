#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

module reset
features=()
if [[ "${1:-}" == "--mpi" ]]; then
  module load foss/2025b
  features=(--features mpi)
fi
module load Rust/1.93.1-GCCcore-14.3.0

if [[ -n "${RUSTFLAGS:-}" ]]; then
  echo "ERROR: RUSTFLAGS is already set; refusing a non-canonical ARC build" >&2
  exit 2
fi
export RUSTFLAGS="-C target-cpu=x86-64-v3"

cargo test --locked --manifest-path rust/Cargo.toml -p pineland-hpc --lib "${features[@]}"
cargo build --release --locked --manifest-path rust/Cargo.toml -p pineland-cli "${features[@]}"
sha256sum rust/target/release/pineland

echo "Built: ${ROOT}/rust/target/release/pineland"
echo "Target: x86-64-v3"
