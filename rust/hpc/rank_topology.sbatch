#!/usr/bin/env bash
# Sweep the one-node MPI/Rayon topologies required before choosing a default.
# Submit with: sbatch --export=ALL,RANKS_PER_NODE=1,THREADS_PER_RANK=96 ...
# Repeat for (2,48), (4,24), and (8,12).
#SBATCH --job-name=pineland-topology
#SBATCH --account=will_taggart_mcll
#SBATCH --partition=normal_q
#SBATCH --constraint=avx512
#SBATCH --nodes=1
#SBATCH --cpus-per-task=96
#SBATCH --time=04:00:00

set -euo pipefail
module reset
module load foss/2025b
submit_root="${SLURM_SUBMIT_DIR:?SLURM_SUBMIT_DIR is not set}"
pineland_bin="${PINELAND_BIN:-${submit_root}/rust/target/release/pineland}"
pineland_config="${PINELAND_CONFIG:-${submit_root}/experiment.json}"
[[ -x "${pineland_bin}" ]] || { echo "missing executable: ${pineland_bin}" >&2; exit 2; }
[[ -f "${pineland_config}" ]] || { echo "missing config: ${pineland_config}" >&2; exit 2; }
export RAYON_NUM_THREADS="${THREADS_PER_RANK:?set THREADS_PER_RANK}"
run_root="/scratch/${USER}/pineland/${SLURM_JOB_ID}/ranks-${RANKS_PER_NODE}-threads-${THREADS_PER_RANK}"
mkdir -p "${run_root}"
srun --ntasks-per-node="${RANKS_PER_NODE:?set RANKS_PER_NODE}" --cpus-per-task="${THREADS_PER_RANK}" --mpi=pmix "${pineland_bin}" filter "${pineland_config}" --mpi --particles 768 --days 7 --threads "${THREADS_PER_RANK}" --output "${run_root}/filter"
