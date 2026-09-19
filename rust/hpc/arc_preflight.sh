#!/usr/bin/env bash
set -euo pipefail

ACCOUNT="${PINELAND_ARC_ACCOUNT:-will_taggart_mcll}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BINARY="${ROOT}/rust/target/release/pineland"

echo "Pineland ARC preflight"
echo "  host:    $(hostname)"
echo "  account: ${ACCOUNT}"
echo "  repo:    ${ROOT}"

for command_name in sbatch srun squeue sacctmgr sinfo python3 module; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "ERROR: ${command_name} is not available" >&2
    exit 2
  fi
done

if ! sacctmgr -n -P show assoc where "user=${USER}" "account=${ACCOUNT}" format=User,Account,Cluster |
  grep -F "|${ACCOUNT}|" >/dev/null; then
  echo "ERROR: Slurm does not show ${USER} associated with ${ACCOUNT}" >&2
  exit 2
fi

if [[ ! -x "${BINARY}" ]]; then
  echo "ERROR: release binary missing: ${BINARY}" >&2
  echo "Run: bash rust/hpc/arc_build.sh" >&2
  exit 2
fi

if [[ ! -d "/scratch/${USER}" ]]; then
  echo "NOTE: /scratch/${USER} does not exist yet."
  echo "ARC creates it when a job runs; initialize with:"
  echo "  srun --account=${ACCOUNT} ls -ld /scratch/${USER}"
else
  echo "  scratch: /scratch/${USER}"
fi

echo "  binary sha256: $(sha256sum "${BINARY}" | awk '{print $1}')"
echo "  partitions:"
sinfo -s
echo "Preflight checks passed."
