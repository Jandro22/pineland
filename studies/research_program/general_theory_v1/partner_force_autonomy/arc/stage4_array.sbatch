#!/usr/bin/env bash
# Generic one-world-per-task wrapper for the integrated Stage-4 partner-force program.
# The array range/throttle is supplied at sbatch time so scientific design and
# scheduler concurrency remain separate.
#SBATCH --job-name=pf-stage4
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=01:00:00

set -euo pipefail

REPO_ROOT="${PINELAND_REPO_ROOT:-${SLURM_SUBMIT_DIR:-$(pwd)}}"
cd "$REPO_ROOT"

BINARY="${PF_BINARY:-rust/target/release/examples/partner_force_autonomy_stage3}"
CONTRACT="${PF_STAGE4_CONTRACT:?PF_STAGE4_CONTRACT is required}"
FREEZE="${PF_FREEZE:?PF_FREEZE is required for Stage-4 production}"
OUTPUT_DIR="${PF_OUTPUT_DIR:?PF_OUTPUT_DIR is required}"
ALLOW_UNFROZEN="${PF_ALLOW_UNFROZEN:-0}"

if [[ ! -x "$BINARY" ]]; then
  echo "Missing executable $BINARY" >&2
  exit 2
fi
if [[ ! -f "$CONTRACT" ]]; then
  echo "Missing Stage-4 contract $CONTRACT" >&2
  exit 2
fi

read -r EXPERIMENT_ID CELL_COUNT SEED_COUNT SEED_BASE < <(
  python3 - "$CONTRACT" <<'PY'
import json, sys
d=json.load(open(sys.argv[1], encoding='utf-8'))
print(d['experiment_id'], int(d['cells_count']), int(d['default_seed_count']), int(d['seed_base']))
PY
)

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

RUN_ARGS=(
  --stage4-contract "$CONTRACT"
  --freeze "$FREEZE"
  --cell-index "$CELL_INDEX"
  --seed "$SEED"
  --execute
  --output "$TMP"
  --trajectory-output "$TRAJECTORY_TMP"
)
if [[ "$ALLOW_UNFROZEN" == "1" ]]; then
  RUN_ARGS+=(--allow-unfrozen)
fi

START_EPOCH=$(date +%s)
srun "$BINARY" "${RUN_ARGS[@]}"
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
python3 - "$META" "$EXPERIMENT_ID" "$TASK_ID" "$CELL_INDEX" "$SEED" "$SHARD" "$SHA256" "$TRAJECTORY_SHARD" "$TRAJECTORY_SHA256" "$GIT_COMMIT" "$HOST" "$START_EPOCH" "$END_EPOCH" "$CONTRACT" "$CONTRACT_SHA256" "$FREEZE" "$FREEZE_SHA256" <<'PY'
import json, os, sys
(
    meta, experiment_id, task_id, cell_index, seed, shard, sha256,
    trajectory_shard, trajectory_sha256, git_commit, host, start_epoch, end_epoch,
    contract, contract_sha256, freeze, freeze_sha256,
) = sys.argv[1:]
payload = {
    'schema_version': 'pineland.partner_force_arc_task.stage4.v1',
    'experiment_id': experiment_id,
    'slurm_job_id': os.environ.get('SLURM_JOB_ID'),
    'slurm_array_job_id': os.environ.get('SLURM_ARRAY_JOB_ID'),
    'slurm_array_task_id': int(task_id),
    'cell_index': int(cell_index),
    'seed': int(seed),
    'git_commit': git_commit,
    'hostname': host,
    'elapsed_seconds': int(end_epoch) - int(start_epoch),
    'stage4_contract': contract,
    'stage4_contract_sha256': contract_sha256,
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

echo "Completed experiment=$EXPERIMENT_ID task=$TASK_ID cell=$CELL_INDEX seed=$SEED"
