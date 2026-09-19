#!/usr/bin/env bash
#SBATCH --job-name=pineland-filter
#SBATCH --account=will_taggart_mcll
#SBATCH --partition=normal_q
#SBATCH --constraint=avx512
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=2
#SBATCH --cpus-per-task=48
#SBATCH --time=24:00:00
#SBATCH --output=pineland-filter-%j.out

set -euo pipefail
module reset
module load foss/2025b

export RAYON_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
run_root="/scratch/${USER}/pineland/${SLURM_JOB_ID}"
mkdir -p "${run_root}"

# Build the MPI-enabled CLI once in the deployment image.  The MPI feature is
# deliberately optional so Windows/local builds do not need an MPI SDK.
# pineland-hpc owns canonical ownership, reductions, packed parent states, and
# the cross-rank resampling exchange.
srun --mpi=pmix ./pineland filter experiment.json --mpi --output "${run_root}/filter"
