#!/usr/bin/env bash
# Sweep the one-node MPI/Rayon topologies required before choosing a default.
# Submit with: sbatch --export=ALL,RANKS_PER_NODE=1,THREADS_PER_RANK=96 ...
# Repeat for (2,48), (4,24), and (8,12).
#SBATCH --job-name=pineland-topology
#SBATCH --partition=normal_q
#SBATCH --constraint=avx512
#SBATCH --nodes=1
#SBATCH --cpus-per-task=96
#SBATCH --time=04:00:00

set -euo pipefail
module reset
module load foss/2023b
export RAYON_NUM_THREADS="${THREADS_PER_RANK:?set THREADS_PER_RANK}"
run_root="/scratch/${USER}/pineland/${SLURM_JOB_ID}/ranks-${RANKS_PER_NODE}-threads-${THREADS_PER_RANK}"
mkdir -p "${run_root}"
srun --ntasks-per-node="${RANKS_PER_NODE:?set RANKS_PER_NODE}" --cpus-per-task="${THREADS_PER_RANK}" --mpi=pmix ./pineland filter experiment.json --mpi --particles 768 --days 7 --threads "${THREADS_PER_RANK}" --output "${run_root}/filter"
