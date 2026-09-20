#!/usr/bin/env bash
# Submit the complete integrated Stage-4 production campaign and its dependent
# verification/analysis jobs from one clean frozen commit.
set -euo pipefail

REPO_ROOT="${PINELAND_REPO_ROOT:-/home/alejandrog/pineland-stage4-paper}"
cd "$REPO_ROOT"

ACCOUNT="${PF_ACCOUNT:-will_taggart_mcll}"
PARTITION="${PF_PARTITION:-normal_q}"
QOS="${PF_QOS:-owl_normal_base}"
CONSTRAINT="${PF_CONSTRAINT:-avx512}"
BINARY="${PF_BINARY:-/home/alejandrog/pineland-stage4-target/release/examples/partner_force_autonomy_stage3}"
FREEZE="studies/research_program/general_theory_v1/partner_force_autonomy/contracts/partner_force_stage4_integrated_freeze_v1.json"
ARRAY_WRAPPER="studies/research_program/general_theory_v1/partner_force_autonomy/arc/stage4_array.sbatch"
POST_WRAPPER="studies/research_program/general_theory_v1/partner_force_autonomy/arc/stage4_postprocess.sbatch"
FINAL_WRAPPER="studies/research_program/general_theory_v1/partner_force_autonomy/arc/stage4_finalize.sbatch"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing Stage-4 production launch from a dirty worktree" >&2
  git status --short >&2
  exit 2
fi
COMMIT=$(git rev-parse HEAD)
[[ -x "$BINARY" ]] || { echo "Missing Stage-4 binary: $BINARY" >&2; exit 2; }
[[ -f "$FREEZE" ]] || { echo "Missing Stage-4 freeze: $FREEZE" >&2; exit 2; }

CONTRACT_A="studies/research_program/general_theory_v1/partner_force_autonomy/contracts/stage4_autonomy_phase_map_v1.json"
CONTRACT_B="studies/research_program/general_theory_v1/partner_force_autonomy/contracts/stage4_bottleneck_migration_v1.json"
CONTRACT_C="studies/research_program/general_theory_v1/partner_force_autonomy/contracts/stage4_substitution_development_v1.json"
OUT_A="/home/alejandrog/pineland-stage4-production/phase_map"
OUT_B="/home/alejandrog/pineland-stage4-production/bottleneck_migration"
OUT_C="/home/alejandrog/pineland-stage4-production/substitution_development"

for out in "$OUT_A" "$OUT_B" "$OUT_C"; do
  if [[ -e "$out" ]] && [[ -n "$(find "$out" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    echo "Refusing to launch into non-empty production directory: $out" >&2
    exit 2
  fi
  mkdir -p "$out"
done

COMMON=(--account="$ACCOUNT" --partition="$PARTITION" --qos="$QOS" --constraint="$CONSTRAINT")
LOGROOT="/home/alejandrog/pineland-stage4-production/logs"
mkdir -p "$LOGROOT"

submit_array() {
  local name=$1 array_spec=$2 contract=$3 out=$4
  sbatch --parsable "${COMMON[@]}" \
    --job-name="$name" \
    --array="$array_spec" \
    --output="$LOGROOT/${name}_%A_%a.out" \
    --error="$LOGROOT/${name}_%A_%a.err" \
    --export="ALL,PINELAND_REPO_ROOT=$REPO_ROOT,PF_BINARY=$BINARY,PF_STAGE4_CONTRACT=$contract,PF_FREEZE=$FREEZE,PF_OUTPUT_DIR=$out,PF_ALLOW_UNFROZEN=0" \
    "$ARRAY_WRAPPER"
}

submit_post() {
  local name=$1 dependency=$2 contract=$3 out=$4
  sbatch --parsable "${COMMON[@]}" \
    --job-name="$name" \
    --dependency="afterok:${dependency}" \
    --output="$LOGROOT/${name}_%j.out" \
    --error="$LOGROOT/${name}_%j.err" \
    --export="ALL,PINELAND_REPO_ROOT=$REPO_ROOT,PF_STAGE4_CONTRACT=$contract,PF_OUTPUT_DIR=$out" \
    "$POST_WRAPPER"
}

JOB_A1=$(submit_array pf-s4-phase-a 0-839%48 "$CONTRACT_A" "$OUT_A")
JOB_A2=$(submit_array pf-s4-phase-b 840-1679%48 "$CONTRACT_A" "$OUT_A")
JOB_B=$(submit_array pf-s4-migrate 0-623%52 "$CONTRACT_B" "$OUT_B")
JOB_C=$(submit_array pf-s4-mechanism 0-503%48 "$CONTRACT_C" "$OUT_C")

POST_A=$(submit_post pf-s4-phase-post "${JOB_A1}:${JOB_A2}" "$CONTRACT_A" "$OUT_A")
POST_B=$(submit_post pf-s4-migrate-post "$JOB_B" "$CONTRACT_B" "$OUT_B")
POST_C=$(submit_post pf-s4-mechanism-post "$JOB_C" "$CONTRACT_C" "$OUT_C")

FINAL=$(sbatch --parsable "${COMMON[@]}" \
  --job-name=pf-s4-final \
  --dependency="afterok:${POST_A}:${POST_B}:${POST_C}" \
  --output="$LOGROOT/pf-s4-final_%j.out" \
  --error="$LOGROOT/pf-s4-final_%j.err" \
  --export="ALL,PINELAND_REPO_ROOT=$REPO_ROOT" \
  "$FINAL_WRAPPER")

python3 - "$COMMIT" "$JOB_A1" "$JOB_A2" "$JOB_B" "$JOB_C" "$POST_A" "$POST_B" "$POST_C" "$FINAL" <<'PY'
import json, sys
commit, a1, a2, b, c, pa, pb, pc, final=sys.argv[1:]
print(json.dumps({
  'production_git_commit':commit,
  'phase_map_array_job_ids':[a1,a2],
  'bottleneck_migration_array_job_id':b,
  'substitution_development_array_job_id':c,
  'phase_map_postprocess_job_id':pa,
  'bottleneck_migration_postprocess_job_id':pb,
  'substitution_development_postprocess_job_id':pc,
  'program_finalize_job_id':final,
}, indent=2, sort_keys=True))
PY
