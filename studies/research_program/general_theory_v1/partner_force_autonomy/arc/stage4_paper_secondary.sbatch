#!/usr/bin/env bash
# Run the precommitted paper-level Stage-4 analysis after integrated READY.
#SBATCH --job-name=pf-s4-paper
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00

set -euo pipefail

REPO_ROOT="${PINELAND_REPO_ROOT:-/home/alejandrog/pineland-stage4-paper-analysis}"
POST_ROOT="${PF_POSTPROCESS_ROOT:-/home/alejandrog/pineland-stage4-postprocess-fix/studies/research_program/general_theory_v1/partner_force_autonomy/outputs/stage4}"
OUTPUT_DIR="${PF_PAPER_OUTPUT_DIR:-/home/alejandrog/pineland-stage4-paper-results}"
EXPECTED_PRODUCTION_COMMIT="e369c107f4465ce8cd385a366cafca8c28c04b65"
EXPECTED_POSTPROCESS_COMMIT="7697e6eac83248c7bc03830e58d94a2d878c6635"

cd "$REPO_ROOT"
PAPER_COMMIT=$(git rev-parse HEAD)
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing paper analysis from a dirty worktree" >&2
  exit 2
fi

INTEGRATED_READY="$POST_ROOT/READY_STAGE4_INTEGRATED.json"
python3 - "$INTEGRATED_READY" "$EXPECTED_PRODUCTION_COMMIT" "$EXPECTED_POSTPROCESS_COMMIT" <<'PY'
import json, sys
path, production_commit, analysis_commit = sys.argv[1:]
d=json.load(open(path, encoding='utf-8'))
if d.get('status') != 'STAGE4_INTEGRATED_PROGRAM_COMPLETE':
    raise SystemExit('integrated READY is not complete')
if d.get('production_git_commit') != production_commit:
    raise SystemExit('production commit mismatch')
if d.get('analysis_git_commit') != analysis_commit:
    raise SystemExit('postprocess commit mismatch')
if int(d.get('production_worlds', -1)) != 2808:
    raise SystemExit('integrated world count mismatch')
if len(d.get('modules', [])) != 3:
    raise SystemExit('integrated READY must contain three modules')
print('INTEGRATED_READY_VERIFIED')
PY

PHASE="$POST_ROOT/partner_force_stage4_autonomy_phase_map_v1/analysis"
MIGRATION="$POST_ROOT/partner_force_stage4_bottleneck_migration_v1/analysis"
MECHANISM="$POST_ROOT/partner_force_stage4_substitution_development_v1/analysis"
INPUTS=(
  "$PHASE/stage4_world_summary_v1.csv"
  "$PHASE/stage4_paired_trajectory_metrics_v1.csv"
  "$MIGRATION/stage4_world_summary_v1.csv"
  "$MIGRATION/stage4_paired_trajectory_metrics_v1.csv"
  "$MECHANISM/stage4_world_summary_v1.csv"
  "$MECHANISM/stage4_paired_trajectory_metrics_v1.csv"
)
for input in "${INPUTS[@]}"; do
  [[ -s "$input" ]] || { echo "Missing paper-analysis input: $input" >&2; exit 2; }
done

module load Python/3.12.3-GCCcore-13.3.0
module load SciPy-bundle/2024.05-gfbf-2024a
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

python3 studies/research_program/general_theory_v1/partner_force_autonomy/analysis/analyze_stage4_paper_secondary.py \
  --phase-world "${INPUTS[0]}" --phase-paired "${INPUTS[1]}" \
  --migration-world "${INPUTS[2]}" --migration-paired "${INPUTS[3]}" \
  --mechanism-world "${INPUTS[4]}" --mechanism-paired "${INPUTS[5]}" \
  --bootstrap-resamples 10000 --bootstrap-seed 20260920 \
  --output-dir "$OUTPUT_DIR"

python3 - "$OUTPUT_DIR" "$INTEGRATED_READY" "$PAPER_COMMIT" <<'PY'
import hashlib, json, sys
from pathlib import Path
out=Path(sys.argv[1]); integrated=Path(sys.argv[2]); paper_commit=sys.argv[3]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
summary=out/'stage4_paper_secondary_summary_v1.json'
if not summary.exists(): raise SystemExit('paper secondary summary missing')
payload={
 'schema_version':'pineland.partner_force_stage4_paper_ready.v1',
 'status':'STAGE4_PAPER_SECONDARY_COMPLETE',
 'production_git_commit':'e369c107f4465ce8cd385a366cafca8c28c04b65',
 'postprocess_git_commit':'7697e6eac83248c7bc03830e58d94a2d878c6635',
 'paper_analysis_git_commit':paper_commit,
 'integrated_ready_sha256':sha(integrated),
 'summary_sha256':sha(summary),
 'outputs':{p.name:sha(p) for p in sorted(out.glob('*')) if p.is_file() and p.name!='READY_STAGE4_PAPER_SECONDARY.json'},
}
(out/'READY_STAGE4_PAPER_SECONDARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print(json.dumps(payload,indent=2,sort_keys=True))
PY
