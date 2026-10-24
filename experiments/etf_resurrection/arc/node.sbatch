#!/usr/bin/env bash
# One array element = one whole node running a bundle of autonomy-trap tasks in parallel.
#SBATCH --job-name=pineland-trap
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --exclusive
#SBATCH --requeue
#SBATCH --open-mode=append
set -euo pipefail
: "${TRAP_HERE:?}" "${TRAP_CAMPAIGN:?}" "${TRAP_BINARY:?}" "${TRAP_SCRATCH:?}" "${TRAP_BUNDLE_SIZE:?}" "${SLURM_ARRAY_TASK_ID:?}"
module reset >/dev/null 2>&1 || true
module load Python/3.12.3-GCCcore-13.3.0 >/dev/null 2>&1 || module load Python >/dev/null 2>&1 || true
export RAYON_NUM_THREADS=1 OMP_NUM_THREADS=1
python3 "${TRAP_HERE}/run_bundle.py" \
  --campaign "${TRAP_CAMPAIGN}" --binary "${TRAP_BINARY}" --scratch "${TRAP_SCRATCH}" \
  --bundle "${SLURM_ARRAY_TASK_ID}" --bundle-size "${TRAP_BUNDLE_SIZE}" \
  --workers "${SLURM_CPUS_ON_NODE:-$(nproc)}"
