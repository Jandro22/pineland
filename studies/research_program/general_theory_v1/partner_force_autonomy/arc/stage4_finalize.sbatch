#!/usr/bin/env bash
# Program-level Stage-4 integrity finalizer. Runs only after all module
# postprocessors succeed.
#SBATCH --job-name=pf-s4-finalize
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:10:00

set -euo pipefail

REPO_ROOT="${PINELAND_REPO_ROOT:-${SLURM_SUBMIT_DIR:-$(pwd)}}"
cd "$REPO_ROOT"

BASE="studies/research_program/general_theory_v1/partner_force_autonomy/outputs/stage4"
python3 - "$BASE" <<'PY'
import hashlib, json, sys
from pathlib import Path

base=Path(sys.argv[1])
experiments=[
  'partner_force_stage4_autonomy_phase_map_v1',
  'partner_force_stage4_bottleneck_migration_v1',
  'partner_force_stage4_substitution_development_v1',
]
records=[]
for experiment in experiments:
    path=base/experiment/'READY.json'
    if not path.exists():
        raise SystemExit(f'missing module READY: {path}')
    record=json.loads(path.read_text(encoding='utf-8'))
    if record.get('status') != 'MODULE_ANALYSIS_COMPLETE':
        raise SystemExit(f'{path} is not complete')
    if record.get('experiment_id') != experiment:
        raise SystemExit(f'{path} experiment mismatch')
    records.append((path,record))

commits={r['production_git_commit'] for _,r in records}
if len(commits) != 1:
    raise SystemExit(f'Stage-4 modules do not share one production commit: {sorted(commits)}')
total=sum(int(r['expected_worlds']) for _,r in records)
if total != 2808:
    raise SystemExit(f'expected 2808 production worlds, module READY total is {total}')

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
payload={
  'schema_version':'pineland.partner_force_stage4_program_ready.v1',
  'status':'STAGE4_INTEGRATED_PROGRAM_COMPLETE',
  'production_git_commit':next(iter(commits)),
  'production_worlds':total,
  'modules':[
    {
      'experiment_id':r['experiment_id'],
      'expected_worlds':r['expected_worlds'],
      'ready_file':str(path),
      'ready_sha256':sha(path),
      'primary_sha256':r['primary_sha256'],
      'trajectory_sha256':r['trajectory_sha256'],
      'analysis_summary_sha256':r['analysis_summary_sha256'],
    }
    for path,r in records
  ],
}
out=base/'READY_STAGE4_INTEGRATED.json'
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print(json.dumps(payload,indent=2,sort_keys=True))
PY
