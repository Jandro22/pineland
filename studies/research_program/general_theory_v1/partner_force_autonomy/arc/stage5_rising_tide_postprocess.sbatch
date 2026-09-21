#!/usr/bin/env bash
# Merge, validate, and analyze the Stage-5 coordinated-development campaign.
#SBATCH --job-name=pf-s5-post
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00

set -euo pipefail

REPO_ROOT="${PINELAND_REPO_ROOT:-${SLURM_SUBMIT_DIR:-$(pwd)}}"
cd "$REPO_ROOT"

CONTRACT="${PF_STAGE5_CONTRACT:?PF_STAGE5_CONTRACT is required}"
INPUT_DIR="${PF_OUTPUT_DIR:?PF_OUTPUT_DIR is required}"

module load Python/3.12.3-GCCcore-13.3.0
module load SciPy-bundle/2024.05-gfbf-2024a

read -r EXPERIMENT_ID CELL_COUNT SEED_COUNT < <(
  python3 - "$CONTRACT" <<'PY'
import json, sys
d=json.load(open(sys.argv[1], encoding='utf-8'))
print(d['experiment_id'], int(d['cells_count']), int(d['default_seed_count']))
PY
)
EXPECTED_TASKS=$((CELL_COUNT * SEED_COUNT))

OUTDIR="studies/research_program/general_theory_v1/partner_force_autonomy/outputs/stage5/${EXPERIMENT_ID}"
mkdir -p "$OUTDIR"
PRIMARY="$OUTDIR/raw_branch_panel.csv"
TRAJECTORY="$OUTDIR/trajectory_panel.csv"
MERGE_META="$OUTDIR/merge_metadata.json"

python3 studies/research_program/general_theory_v1/partner_force_autonomy/arc/merge_partner_force_shards.py \
  --input-dir "$INPUT_DIR" \
  --output-csv "$PRIMARY" \
  --trajectory-output-csv "$TRAJECTORY" \
  --require-task-metadata \
  --enforce-degeneracy-safeguard \
  --expected-tasks "$EXPECTED_TASKS" \
  --metadata-json "$MERGE_META"

python3 studies/research_program/general_theory_v1/partner_force_autonomy/analysis/analyze_stage4_integrated.py \
  --primary-csv "$PRIMARY" \
  --trajectory-csv "$TRAJECTORY" \
  --contract "$CONTRACT" \
  --output-dir "$OUTDIR/generic_diagnostics"

python3 studies/research_program/general_theory_v1/partner_force_autonomy/analysis/analyze_stage5_rising_tide.py \
  --primary-csv "$PRIMARY" \
  --trajectory-csv "$TRAJECTORY" \
  --contract "$CONTRACT" \
  --output-dir "$OUTDIR/analysis"

python3 - "$OUTDIR" "$EXPERIMENT_ID" "$EXPECTED_TASKS" "$MERGE_META" <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path
out=Path(sys.argv[1]); experiment=sys.argv[2]; expected=int(sys.argv[3]); merge_meta=Path(sys.argv[4])
def h(p): return hashlib.sha256(p.read_bytes()).hexdigest()
merge=json.loads(merge_meta.read_text(encoding='utf-8'))
if merge['task_metadata_verified'] != expected:
    raise SystemExit('not all Stage-5 task metadata were verified')
if merge['experiment_ids'] != [experiment]:
    raise SystemExit(f'unexpected experiment IDs: {merge["experiment_ids"]}')
if len(merge['git_commits']) != 1:
    raise SystemExit(f'production shards span multiple commits: {merge["git_commits"]}')
summary=out/'analysis'/'stage5_analysis_summary_v1.json'
payload={
  'schema_version':'pineland.partner_force_stage5_ready.v1',
  'status':'STAGE5_ANALYSIS_COMPLETE',
  'experiment_id':experiment,
  'expected_worlds':expected,
  'production_git_commit':merge['git_commits'][0],
  'analysis_git_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
  'source_array_job_ids':merge.get('source_array_job_ids', []),
  'primary_sha256':h(out/'raw_branch_panel.csv'),
  'trajectory_sha256':h(out/'trajectory_panel.csv'),
  'merge_metadata_sha256':h(merge_meta),
  'analysis_summary_sha256':h(summary),
}
(out/'READY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print(json.dumps(payload,indent=2,sort_keys=True))
PY
