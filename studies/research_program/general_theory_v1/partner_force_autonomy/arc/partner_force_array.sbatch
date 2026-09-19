#!/usr/bin/env bash
#SBATCH --job-name=pf-autonomy
#SBATCH --array=0-719%8
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=01:00:00

set -euo pipefail

# The script intentionally does not hard-code an ARC account or partition.
# Supply site/account-specific options at submission time. Command-line sbatch
# options override the defaults above (e.g. --array=0-95%8 for one holdout).

REPO_ROOT="${PINELAND_REPO_ROOT:-${SLURM_SUBMIT_DIR:-$(pwd)}}"
cd "$REPO_ROOT"

BINARY="${PF_BINARY:-rust/target/release/examples/partner_force_autonomy_stage3}"
FREEZE="${PF_FREEZE:-studies/research_program/general_theory_v1/partner_force_autonomy/contracts/partner_force_autonomy_preregistration_freeze_v1.json}"
MODE="${PF_MODE:-discovery}"
OUTPUT_DIR="${PF_OUTPUT_DIR:-studies/research_program/general_theory_v1/partner_force_autonomy/outputs/arc_stage3_shards}"

if [[ ! -x "$BINARY" ]]; then
  echo "Missing executable $BINARY" >&2
  echo "Build first with: cargo build --release --manifest-path rust/Cargo.toml -p pineland-model --example partner_force_autonomy_stage3" >&2
  exit 2
fi

if [[ "$MODE" == "discovery" ]]; then
  DESIGN="${PF_DESIGN:-studies/research_program/general_theory_v1/partner_force_autonomy/configs/stage3_discovery_cells_v1.csv}"
  CELL_COUNT="${PF_CELL_COUNT:-60}"
  SEED_COUNT="${PF_SEED_COUNT:-12}"
  SEED_BASE="${PF_SEED_BASE:-2026120000}"
  RUN_ARGS=(--design "$DESIGN")
elif [[ "$MODE" == "holdout" ]]; then
  : "${PF_HOLDOUT_CONTRACT:?PF_HOLDOUT_CONTRACT is required when PF_MODE=holdout}"
  read -r CELL_COUNT SEED_COUNT SEED_BASE < <(
    python - "$PF_HOLDOUT_CONTRACT" <<'PY'
import json, sys
d=json.load(open(sys.argv[1], encoding='utf-8'))
print(int(d['cells_count']), int(d['default_seed_count']), int(d['seed_base']))
PY
  )
  RUN_ARGS=(--holdout-contract "$PF_HOLDOUT_CONTRACT")
else
  echo "PF_MODE must be discovery or holdout, got '$MODE'" >&2
  exit 2
fi

TASK_ID="${SLURM_ARRAY_TASK_ID:?This script must run as a Slurm array task}"
TOTAL_TASKS=$((CELL_COUNT * SEED_COUNT))
if (( TASK_ID < 0 || TASK_ID >= TOTAL_TASKS )); then
  echo "SLURM_ARRAY_TASK_ID=$TASK_ID outside valid range 0..$((TOTAL_TASKS-1))" >&2
  exit 2
fi

CELL_INDEX=$((TASK_ID / SEED_COUNT))
SEED_INDEX=$((TASK_ID % SEED_COUNT))
SEED=$((SEED_BASE + SEED_INDEX))

mkdir -p "$OUTPUT_DIR"
SHARD="$OUTPUT_DIR/task_${TASK_ID}_cell_${CELL_INDEX}_seed_${SEED}.csv"
TRAJECTORY_SHARD="$OUTPUT_DIR/task_${TASK_ID}_cell_${CELL_INDEX}_seed_${SEED}.trajectory.csv"
META="$OUTPUT_DIR/task_${TASK_ID}_cell_${CELL_INDEX}_seed_${SEED}.json"
TMP="${SHARD}.tmp-${SLURM_JOB_ID:-$$}"
TRAJECTORY_TMP="${TRAJECTORY_SHARD}.tmp-${SLURM_JOB_ID:-$$}"
trap 'rm -f "$TMP" "$TRAJECTORY_TMP"' EXIT

START_EPOCH=$(date +%s)
srun "$BINARY" \
  "${RUN_ARGS[@]}" \
  --freeze "$FREEZE" \
  --cell-index "$CELL_INDEX" \
  --seed "$SEED" \
  --execute \
  --output "$TMP" \
  --trajectory-output "$TRAJECTORY_TMP"
END_EPOCH=$(date +%s)

mv "$TMP" "$SHARD"
mv "$TRAJECTORY_TMP" "$TRAJECTORY_SHARD"
trap - EXIT

SHA256=$(sha256sum "$SHARD" | awk '{print $1}')
TRAJECTORY_SHA256=$(sha256sum "$TRAJECTORY_SHARD" | awk '{print $1}')
GIT_COMMIT=$(git rev-parse HEAD)
HOST=$(hostname)
python - "$META" "$MODE" "$TASK_ID" "$CELL_INDEX" "$SEED" "$SHARD" "$SHA256" "$TRAJECTORY_SHARD" "$TRAJECTORY_SHA256" "$GIT_COMMIT" "$HOST" "$START_EPOCH" "$END_EPOCH" <<'PY'
import json, sys
(
    meta, mode, task_id, cell_index, seed, shard, sha256,
    trajectory_shard, trajectory_sha256, git_commit, host, start_epoch, end_epoch,
) = sys.argv[1:]
payload = {
    'schema_version': 'pineland.partner_force_arc_task.v1',
    'mode': mode,
    'slurm_job_id': __import__('os').environ.get('SLURM_JOB_ID'),
    'slurm_array_job_id': __import__('os').environ.get('SLURM_ARRAY_JOB_ID'),
    'slurm_array_task_id': int(task_id),
    'cell_index': int(cell_index),
    'seed': int(seed),
    'git_commit': git_commit,
    'hostname': host,
    'elapsed_seconds': int(end_epoch) - int(start_epoch),
    'output_csv': shard,
    'output_sha256': sha256,
    'trajectory_csv': trajectory_shard,
    'trajectory_sha256': trajectory_sha256,
}
with open(meta, 'w', encoding='utf-8') as f:
    json.dump(payload, f, indent=2, sort_keys=True)
    f.write('\n')
PY

echo "Completed task=$TASK_ID cell=$CELL_INDEX seed=$SEED shard=$SHARD trajectory=$TRAJECTORY_SHARD"
