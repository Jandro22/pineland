#!/usr/bin/env bash
# Launch the complete frozen Stage-5 coordinated-development experiment.
set -euo pipefail

REPO_ROOT="${PINELAND_REPO_ROOT:-/home/alejandrog/pineland-stage5-rising-tide}"
cd "$REPO_ROOT"

ACCOUNT="${PF_ACCOUNT:-will_taggart_mcll}"
PARTITION="${PF_PARTITION:-normal_q}"
QOS="${PF_QOS:-owl_normal_base}"
CONSTRAINT="${PF_CONSTRAINT:-avx512}"
BINARY="${PF_BINARY:-/home/alejandrog/pineland-stage5-target/release/examples/partner_force_autonomy_stage3}"
CONTRACT="studies/research_program/general_theory_v1/partner_force_autonomy/contracts/stage5_rising_tide_v1.json"
FREEZE="studies/research_program/general_theory_v1/partner_force_autonomy/contracts/partner_force_stage5_rising_tide_freeze_v1.json"
ARRAY_WRAPPER="studies/research_program/general_theory_v1/partner_force_autonomy/arc/stage5_rising_tide_array.sbatch"
POST_WRAPPER="studies/research_program/general_theory_v1/partner_force_autonomy/arc/stage5_rising_tide_postprocess.sbatch"
OUT="/home/alejandrog/pineland-stage5-production/rising_tide"
LOGROOT="/home/alejandrog/pineland-stage5-production/logs"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing Stage-5 launch from a dirty worktree" >&2
  git status --short >&2
  exit 2
fi
COMMIT=$(git rev-parse HEAD)
[[ -x "$BINARY" ]] || { echo "Missing Stage-5 binary: $BINARY" >&2; exit 2; }
[[ -f "$CONTRACT" ]] || { echo "Missing contract: $CONTRACT" >&2; exit 2; }
[[ -f "$FREEZE" ]] || { echo "Missing freeze: $FREEZE" >&2; exit 2; }

read -r CELLS SEEDS < <(
  python3 - "$CONTRACT" <<'PY'
import json, sys
d=json.load(open(sys.argv[1], encoding='utf-8'))
print(int(d['cells_count']), int(d['default_seed_count']))
PY
)
TOTAL=$((CELLS * SEEDS))
[[ "$TOTAL" -eq 1472 ]] || { echo "Unexpected Stage-5 world count: $TOTAL" >&2; exit 2; }

if [[ -e "$OUT" ]] && [[ -n "$(find "$OUT" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  echo "Refusing to launch into non-empty production directory: $OUT" >&2
  exit 2
fi
mkdir -p "$OUT" "$LOGROOT"

COMMON=(--account="$ACCOUNT" --partition="$PARTITION" --qos="$QOS" --constraint="$CONSTRAINT")

submit_half() {
  local name=$1 offset=$2
  sbatch --parsable "${COMMON[@]}" \
    --job-name="$name" \
    --array="0-735%64" \
    --output="$LOGROOT/${name}_%A_%a.out" \
    --error="$LOGROOT/${name}_%A_%a.err" \
    --export="ALL,PINELAND_REPO_ROOT=$REPO_ROOT,PF_BINARY=$BINARY,PF_STAGE5_CONTRACT=$CONTRACT,PF_STAGE5_FREEZE=$FREEZE,PF_OUTPUT_DIR=$OUT,PF_TASK_OFFSET=$offset" \
    "$ARRAY_WRAPPER"
}

JOB_A=$(submit_half pf-s5-rise-a 0)
JOB_B=$(submit_half pf-s5-rise-b 736)

POST=$(sbatch --parsable "${COMMON[@]}" \
  --job-name=pf-s5-rise-post \
  --dependency="afterok:${JOB_A}:${JOB_B}" \
  --output="$LOGROOT/pf-s5-rise-post_%j.out" \
  --error="$LOGROOT/pf-s5-rise-post_%j.err" \
  --export="ALL,PINELAND_REPO_ROOT=$REPO_ROOT,PF_STAGE5_CONTRACT=$CONTRACT,PF_OUTPUT_DIR=$OUT" \
  "$POST_WRAPPER")

python3 - "$COMMIT" "$JOB_A" "$JOB_B" "$POST" <<'PY'
import json, sys
commit, a, b, post=sys.argv[1:]
print(json.dumps({
  'production_git_commit': commit,
  'expected_worlds': 1472,
  'array_job_ids': [a, b],
  'postprocess_job_id': post,
  'max_aggregate_array_concurrency': 128,
}, indent=2, sort_keys=True))
PY
