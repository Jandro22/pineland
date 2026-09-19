#!/usr/bin/env bash
# Generic Pineland ensemble worker. Array bounds and resource sizing are
# supplied by arc_campaign.py submit so they remain coupled to the manifest.
#SBATCH --job-name=pineland-array
#SBATCH --requeue
#SBATCH --open-mode=append

set -euo pipefail

: "${PINELAND_MANIFEST_DIR:?set by arc_campaign.py submit}"
: "${PINELAND_REPO_ROOT:?set by arc_campaign.py submit}"
: "${PINELAND_SCRATCH_ROOT:?set by arc_campaign.py submit}"
: "${PINELAND_TASKS_PER_ARRAY:?set by arc_campaign.py submit}"
: "${SLURM_ARRAY_TASK_ID:?this script must run as a Slurm array}"

cd "${PINELAND_REPO_ROOT}"

export RAYON_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"

python3 rust/hpc/arc_campaign.py run-bundle \
  --manifest-dir "${PINELAND_MANIFEST_DIR}" \
  --repo-root "${PINELAND_REPO_ROOT}" \
  --scratch-root "${PINELAND_SCRATCH_ROOT}" \
  --bundle-id "${SLURM_ARRAY_TASK_ID}" \
  --tasks-per-bundle "${PINELAND_TASKS_PER_ARRAY}"
