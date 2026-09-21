#!/usr/bin/env bash
# One Stage-5 rising-tide world per Slurm array task.
#SBATCH --job-name=pf-s5-rise
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=01:00:00

set -euo pipefail

REPO_ROOT="${PINELAND_REPO_ROOT:-${SLURM_SUBMIT_DIR:-$(pwd)}}"
cd "$REPO_ROOT"

BINARY="${PF_BINARY:-rust/target/release/examples/partner_force_autonomy_stage3}"
CONTRACT="${PF_STAGE5_CONTRACT:?PF_STAGE5_CONTRACT is required}"
FREEZE="${PF_STAGE5_FREEZE:?PF_STAGE5_FREEZE is required}"
OUTPUT_DIR="${PF_OUTPUT_DIR:?PF_OUTPUT_DIR is required}"

[[ -x "$BINARY" ]] || { echo "Missing executable $BINARY" >&2; exit 2; }
[[ -f "$CONTRACT" ]] || { echo "Missing Stage-5 contract $CONTRACT" >&2; exit 2; }
[[ -f "$FREEZE" ]] || { echo "Missing Stage-5 freeze $FREEZE" >&2; exit 2; }

read -r EXPERIMENT_ID CELL_COUNT SEED_COUNT SEED_BASE < <(
  python3 - "$CONTRACT" <<'PY'
import json, sys
d=json.load(open(sys.argv[1], encoding='utf-8'))
print(d['experiment_id'], int(d['cells_count']), int(d['default_seed_count']), int(d['seed_base']))
PY
)

SLURM_TASK_ID="${SLURM_ARRAY_TASK_ID:?This script must run as a Slurm array task}"
TASK_OFFSET="${PF_TASK_OFFSET:-0}"
[[ "$TASK_OFFSET" =~ ^[0-9]+$ ]] || { echo "invalid PF_TASK_OFFSET=$TASK_OFFSET" >&2; exit 2; }
TASK_ID=$((SLURM_TASK_ID + TASK_OFFSET))
TOTAL_TASKS=$((CELL_COUNT * SEED_COUNT))
if (( TASK_ID < 0 || TASK_ID >= TOTAL_TASKS )); then
  echo "logical task $TASK_ID outside 0..$((TOTAL_TASKS-1))" >&2
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
  --stage4-contract "$CONTRACT" \
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
CONTRACT_SHA256=$(sha256sum "$CONTRACT" | awk '{print $1}')
FREEZE_SHA256=$(sha256sum "$FREEZE" | awk '{print $1}')
GIT_COMMIT=$(git rev-parse HEAD)
HOST=$(hostname)
python3 - "$META" "$EXPERIMENT_ID" "$TASK_ID" "$SLURM_TASK_ID" "$TASK_OFFSET" "$CELL_INDEX" "$SEED" "$SHARD" "$SHA256" "$TRAJECTORY_SHARD" "$TRAJECTORY_SHA256" "$GIT_COMMIT" "$HOST" "$START_EPOCH" "$END_EPOCH" "$CONTRACT" "$CONTRACT_SHA256" "$FREEZE" "$FREEZE_SHA256" <<'PY'
import json, os, sys
(
    meta, experiment_id, logical_task_id, slurm_task_id, task_offset, cell_index, seed,
    shard, sha256, trajectory_shard, trajectory_sha256, git_commit, host,
    start_epoch, end_epoch, contract, contract_sha256, freeze, freeze_sha256,
) = sys.argv[1:]
payload = {
    'schema_version': 'pineland.partner_force_arc_task.stage5.v1',
    'experiment_id': experiment_id,
    'slurm_job_id': os.environ.get('SLURM_JOB_ID'),
    'slurm_array_job_id': os.environ.get('SLURM_ARRAY_JOB_ID'),
    'slurm_array_task_id': int(slurm_task_id),
    'logical_task_id': int(logical_task_id),
    'task_offset': int(task_offset),
    'cell_index': int(cell_index),
    'seed': int(seed),
    'git_commit': git_commit,
    'hostname': host,
    'elapsed_seconds': int(end_epoch) - int(start_epoch),
    'stage5_contract': contract,
    'stage5_contract_sha256': contract_sha256,
    'freeze': freeze,
    'freeze_sha256': freeze_sha256,
    'output_csv': shard,
    'output_sha256': sha256,
    'trajectory_csv': trajectory_shard,
    'trajectory_sha256': trajectory_sha256,
}
with open(meta, 'w', encoding='utf-8') as f:
    json.dump(payload, f, indent=2, sort_keys=True)
    f.write('\n')
PY

echo "Completed Stage-5 experiment=$EXPERIMENT_ID logical_task=$TASK_ID cell=$CELL_INDEX seed=$SEED"
