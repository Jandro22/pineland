#!/usr/bin/env bash
# One frozen mechanism-ablation world per Slurm array task.
#SBATCH --job-name=pf-mech-ablate
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=04:00:00

set -euo pipefail

REPO_ROOT="${PINELAND_REPO_ROOT:-${SLURM_SUBMIT_DIR:-$(pwd)}}"
cd "$REPO_ROOT"
BINARY="${PF_BINARY:?PF_BINARY is required}"
CONTRACT="${PF_ABLATION_CONTRACT:?PF_ABLATION_CONTRACT is required}"
FREEZE="${PF_ABLATION_FREEZE:?PF_ABLATION_FREEZE is required}"
OUTPUT_DIR="${PF_OUTPUT_DIR:?PF_OUTPUT_DIR is required}"

read -r EXPERIMENT_ID CELL_COUNT SEED_COUNT SEED_BASE < <(
python3 - "$CONTRACT" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
print(d['experiment_id'],d['cells_count'],d['default_seed_count'],d['seed_base'])
PY
)
TASK_ID="${SLURM_ARRAY_TASK_ID:?array task required}"
TOTAL=$((CELL_COUNT * SEED_COUNT))
(( TASK_ID >= 0 && TASK_ID < TOTAL )) || { echo "task outside range" >&2; exit 2; }
CELL_INDEX=$((TASK_ID / SEED_COUNT))
SEED_INDEX=$((TASK_ID % SEED_COUNT))
SEED=$((SEED_BASE + SEED_INDEX))

mkdir -p "$OUTPUT_DIR"
SHARD="$OUTPUT_DIR/task_${TASK_ID}_cell_${CELL_INDEX}_seed_${SEED}.csv"
TRAJ="$OUTPUT_DIR/task_${TASK_ID}_cell_${CELL_INDEX}_seed_${SEED}.trajectory.csv"
META="$OUTPUT_DIR/task_${TASK_ID}_cell_${CELL_INDEX}_seed_${SEED}.json"
TMP="$SHARD.tmp-${SLURM_JOB_ID:-$$}"
TTMP="$TRAJ.tmp-${SLURM_JOB_ID:-$$}"
trap 'rm -f "$TMP" "$TTMP"' EXIT

srun "$BINARY" --stage4-contract "$CONTRACT" --freeze "$FREEZE" \
  --cell-index "$CELL_INDEX" --seed "$SEED" --execute \
  --output "$TMP" --trajectory-output "$TTMP"
mv "$TMP" "$SHARD"
mv "$TTMP" "$TRAJ"
trap - EXIT

python3 - "$META" "$EXPERIMENT_ID" "$TASK_ID" "$CELL_INDEX" "$SEED" "$SHARD" "$TRAJ" "$CONTRACT" "$FREEZE" <<'PY'
import hashlib,json,os,subprocess,sys
meta,exp,task,cell,seed,shard,traj,contract,freeze=sys.argv[1:]
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
payload={
 'schema_version':'pineland.partner_force_arc_task.mechanism_ablation.v1',
 'experiment_id':exp,'logical_task_id':int(task),'cell_index':int(cell),'seed':int(seed),
 'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
 'hostname':os.uname().nodename,'contract':contract,'contract_sha256':sha(contract),
 'freeze':freeze,'freeze_sha256':sha(freeze),'output_csv':shard,'output_sha256':sha(shard),
 'trajectory_csv':traj,'trajectory_sha256':sha(traj),
}
with open(meta,'w',encoding='utf-8') as f: json.dump(payload,f,indent=2,sort_keys=True); f.write('\n')
PY

echo "completed mechanism-ablation task=$TASK_ID cell=$CELL_INDEX seed=$SEED"
