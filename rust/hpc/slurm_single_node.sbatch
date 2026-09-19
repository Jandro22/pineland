#!/usr/bin/env bash
#SBATCH --job-name=pineland-native
#SBATCH --account=will_taggart_mcll
#SBATCH --partition=normal_q
#SBATCH --constraint=avx512
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=04:00:00
#SBATCH --output=pineland-%j.out

set -euo pipefail
module reset

run_root="/scratch/${USER}/pineland/${SLURM_JOB_ID}"
mkdir -p "${run_root}"

# pineland run advances one trajectory and is serial. Use arc_campaign.py for
# ensemble parallelism rather than reserving idle cores here.
srun ./pineland run experiment.json --output "${run_root}/run"
