#!/usr/bin/env bash
# Merge, validate, and analyze one completed Stage-4 module.
#SBATCH --job-name=pf-s4-post
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00

set -euo pipefail

REPO_ROOT="${PINELAND_REPO_ROOT:-${SLURM_SUBMIT_DIR:-$(pwd)}}"
cd "$REPO_ROOT"

CONTRACT="${PF_STAGE4_CONTRACT:?PF_STAGE4_CONTRACT is required}"
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

OUTDIR="studies/research_program/general_theory_v1/partner_force_autonomy/outputs/stage4/${EXPERIMENT_ID}"
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

python3 - "$MERGE_META" "$EXPERIMENT_ID" <<'PY'
import json, sys
p=json.load(open(sys.argv[1], encoding='utf-8'))
experiment=sys.argv[2]
if p['task_metadata_verified'] != p['expected_tasks']:
    raise SystemExit('not all task metadata were verified')
if p['experiment_ids'] != [experiment]:
    raise SystemExit(f"unexpected experiment IDs: {p['experiment_ids']}")
if len(p['git_commits']) != 1:
    raise SystemExit(f"production shards span multiple git commits: {p['git_commits']}")
print('STAGE4_MERGE_INTEGRITY_PASS', experiment, p['expected_tasks'], p['git_commits'][0])
PY

python3 studies/research_program/general_theory_v1/partner_force_autonomy/analysis/analyze_stage4_integrated.py \
  --primary-csv "$PRIMARY" \
  --trajectory-csv "$TRAJECTORY" \
  --contract "$CONTRACT" \
  --output-dir "$OUTDIR/analysis"

python3 - "$OUTDIR" "$EXPERIMENT_ID" "$EXPECTED_TASKS" "$MERGE_META" <<'PY'
import hashlib, json, sys
from pathlib import Path
import subprocess
out=Path(sys.argv[1]); experiment=sys.argv[2]; n=int(sys.argv[3]); merge_meta=Path(sys.argv[4])
def h(p): return hashlib.sha256(p.read_bytes()).hexdigest()
primary=out/'raw_branch_panel.csv'; traj=out/'trajectory_panel.csv'
summary=out/'analysis'/'stage4_analysis_summary_v1.json'
merge=json.loads(merge_meta.read_text(encoding='utf-8'))
commits=merge['git_commits']
if len(commits) != 1:
    raise SystemExit(f'expected one production commit, got {commits}')
analysis_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
payload={
  'schema_version':'pineland.partner_force_stage4_module_ready.v1',
  'status':'MODULE_ANALYSIS_COMPLETE',
  'experiment_id':experiment,
  'expected_worlds':n,
  'production_git_commit':commits[0],
  'analysis_git_commit':analysis_commit,
  'source_array_job_ids':merge.get('source_array_job_ids', []),
  'primary_sha256':h(primary),
  'trajectory_sha256':h(traj),
  'merge_metadata_sha256':h(merge_meta),
  'analysis_summary_sha256':h(summary),
}
(out/'READY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print(json.dumps(payload,indent=2,sort_keys=True))
PY
