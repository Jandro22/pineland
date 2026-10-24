#!/usr/bin/env bash
#SBATCH --job-name=etf-replay
#SBATCH --partition=normal_q
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:20:00

set -euo pipefail
module load Rust/1.93.1-GCCcore-14.3.0
AUDIT_ROOT="${ETF_AUDIT_ROOT:-/home/alejandrog/pineland-etf-resurrection-audit}"
cd "$AUDIT_ROOT/source-original"
test "$(git rev-parse HEAD)" = e369c107f4465ce8cd385a366cafca8c28c04b65
test -z "$(git status --porcelain --untracked-files=no)"
rustc --version
cargo --version
mkdir -p "$AUDIT_ROOT/rebuilt-replay" "$AUDIT_ROOT/frozen-binary-replay"
cargo build --release --locked -p pineland-model --example partner_force_autonomy_stage3 \
  --manifest-path rust/Cargo.toml --target-dir "$AUDIT_ROOT/original-target"
CONTRACT=studies/research_program/general_theory_v1/partner_force_autonomy/contracts/stage4_autonomy_phase_map_v1.json
FREEZE=studies/research_program/general_theory_v1/partner_force_autonomy/contracts/partner_force_stage4_integrated_freeze_v1.json
STEM=task_0_cell_0_seed_2026200000
for mode in rebuilt-replay frozen-binary-replay; do
  if [[ "$mode" == rebuilt-replay ]]; then
    BINARY="$AUDIT_ROOT/original-target/release/examples/partner_force_autonomy_stage3"
  else
    BINARY=/home/alejandrog/pineland-stage4-target/release/examples/partner_force_autonomy_stage3
  fi
  sha256sum "$BINARY"
  srun "$BINARY" --stage4-contract "$CONTRACT" --freeze "$FREEZE" \
    --cell-index 0 --seed 2026200000 --execute \
    --output "$AUDIT_ROOT/$mode/$STEM.csv" \
    --trajectory-output "$AUDIT_ROOT/$mode/$STEM.trajectory.csv"
  cmp "/home/alejandrog/pineland-stage4-production/phase_map/$STEM.csv" "$AUDIT_ROOT/$mode/$STEM.csv"
  cmp "/home/alejandrog/pineland-stage4-production/phase_map/$STEM.trajectory.csv" "$AUDIT_ROOT/$mode/$STEM.trajectory.csv"
  echo "$mode: both CSVs match exactly"
done
