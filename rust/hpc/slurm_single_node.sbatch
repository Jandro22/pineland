#!/usr/bin/env bash
#SBATCH --job-name=pineland-native
#SBATCH --partition=normal_q
#SBATCH --constraint=avx512
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=96
#SBATCH --time=24:00:00
#SBATCH --output=pineland-%j.out

set -euo pipefail
module reset

export RAYON_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
run_root="/scratch/${USER}/pineland/${SLURM_JOB_ID}"
mkdir -p "${run_root}"

# Keep source and binaries in the project/home area; put checkpoints and
# intermediate trajectory products on scratch.
srun ./pineland run experiment.json --output "${run_root}/run"
