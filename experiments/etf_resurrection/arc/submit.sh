#!/usr/bin/env bash
# Build the campaign manifest and submit it as a node-parallel Slurm array.
#   bash submit.sh [--dry-run] [--preemptable] [--seeds 64] [--max-nodes 100] [--per-node-rounds 3]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/../../.." && pwd)"
DRY=0; PART=normal_q; QOS=tc_normal_base; SEEDS=64; MAXN=100; ROUNDS=3; CORES=128; WALL=01:30:00
while [[ $# -gt 0 ]]; do case "$1" in
  --dry-run) DRY=1;; --preemptable) PART=preemptable_q; QOS=tc_preemptable_base;;
  --seeds) SEEDS=$2; shift;; --max-nodes) MAXN=$2; shift;; --per-node-rounds) ROUNDS=$2; shift;;
  --walltime) WALL=$2; shift;; *) echo "unknown $1"; exit 2;; esac; shift; done
CAMPAIGN="${ROOT}/campaigns/autonomy_trap_v1"
SCRATCH="/scratch/${USER}/pineland/autonomy_trap_v1"
BIN="${ROOT}/rust/target/release/examples/partner_force_autonomy_stage3"
DESIGN="${ROOT}/studies/research_program/general_theory_v1/partner_force_autonomy/contracts/stage4_autonomy_phase_map_v1.json"
[[ -x "${BIN}" ]] || { echo "build first: bash ${HERE}/build_arc.sh"; exit 1; }
python3 "${HERE}/build_campaign.py" --design "${DESIGN}" --out "${CAMPAIGN}" --seeds "${SEEDS}"
TASKS=$(wc -l < "${CAMPAIGN}/tasks.jsonl")
BUNDLE=$(( CORES * ROUNDS ))
ELEMENTS=$(( (TASKS + BUNDLE - 1) / BUNDLE ))
mkdir -p "${SCRATCH}/logs"
CMD=(sbatch --account=will_taggart_mcll --cluster=tinkercliffs --partition="${PART}" --qos="${QOS}"
     --cpus-per-task="${CORES}" --time="${WALL}" --array="0-$((ELEMENTS-1))%${MAXN}"
     --output="${SCRATCH}/logs/%A_%a.out"
     --export=ALL,TRAP_HERE="${HERE}",TRAP_CAMPAIGN="${CAMPAIGN}",TRAP_BINARY="${BIN}",TRAP_SCRATCH="${SCRATCH}",TRAP_BUNDLE_SIZE="${BUNDLE}"
     "${HERE}/node.sbatch")
HOURS=$(python3 -c "h,m,s='${WALL}'.split(':');print(int(h)+int(m)/60)")
echo "tasks=${TASKS} bundle=${BUNDLE} nodes(array elements)=${ELEMENTS} concurrent<=${MAXN}"
echo "SU upper bound (normal_q, full walltime): $(python3 -c "print(round(${ELEMENTS}*${CORES}*${HOURS}))")"
echo "${CMD[*]}"
if [[ ${DRY} -eq 1 ]]; then sbatch --test-only "${CMD[@]:1}" 2>&1 | tail -2 || true; exit 0; fi
"${CMD[@]}"
echo "collect afterwards: python3 ${HERE}/collect.py --campaign ${CAMPAIGN} --scratch ${SCRATCH}"
