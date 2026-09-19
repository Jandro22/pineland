#!/usr/bin/env bash
#SBATCH --job-name=pineland-native
#SBATCH --account=will_taggart_mcll
#SBATCH --partition=normal_q
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=04:00:00
#SBATCH --output=pineland-%j.out

set -euo pipefail
module reset

submit_root="${SLURM_SUBMIT_DIR:?SLURM_SUBMIT_DIR is not set}"
pineland_bin="${PINELAND_BIN:-${submit_root}/rust/target/release/pineland}"
pineland_config="${PINELAND_CONFIG:-${submit_root}/experiment.json}"
[[ -x "${pineland_bin}" ]] || { echo "missing executable: ${pineland_bin}" >&2; exit 2; }
[[ -f "${pineland_config}" ]] || { echo "missing config: ${pineland_config}" >&2; exit 2; }

run_root="/scratch/${USER}/pineland/${SLURM_JOB_ID}"
mkdir -p "${run_root}"

# pineland run advances one trajectory and is serial. Use arc_campaign.py for
# ensemble parallelism rather than reserving idle cores here.
srun "${pineland_bin}" run "${pineland_config}" --output "${run_root}/run"
