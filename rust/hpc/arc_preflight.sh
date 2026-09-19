#!/usr/bin/env bash
set -euo pipefail

ACCOUNT="${PINELAND_ARC_ACCOUNT:-will_taggart_mcll}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BINARY="${ROOT}/rust/target/release/pineland"

echo "Pineland ARC preflight"
echo "  host:    $(hostname)"
echo "  account: ${ACCOUNT}"
echo "  repo:    ${ROOT}"

for command_name in sbatch srun squeue sacctmgr scontrol sinfo python3 module; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "ERROR: ${command_name} is not available" >&2
    exit 2
  fi
done

if ! module spider Rust/1.93.1-GCCcore-14.3.0 >/dev/null 2>&1; then
  echo "ERROR: Rust/1.93.1-GCCcore-14.3.0 is not available on this ARC host" >&2
  exit 2
fi
if ! module spider foss/2025b >/dev/null 2>&1; then
  echo "ERROR: foss/2025b is not available on this ARC host" >&2
  exit 2
fi

cluster="$(
  scontrol show config |
    awk -F= '/^[[:space:]]*ClusterName[[:space:]]*=/ {
      gsub(/[[:space:]]/, "", $2);
      print tolower($2);
      exit
    }'
)"
case "${cluster}" in
  *tinkercliffs*)
    cluster="tinkercliffs"
    base_qos="tc_normal_base"
    preempt_qos="tc_preemptable_base"
    expected_cpu_rate="1.0"
    test_constraint=()
    ;;
  *owl*)
    cluster="owl"
    base_qos="owl_normal_base"
    preempt_qos="owl_preemptable_base"
    expected_cpu_rate="1.5"
    test_constraint=(--constraint=avx512)
    ;;
  *)
    echo "ERROR: unsupported ARC cluster reported by Slurm: ${cluster:-unknown}" >&2
    exit 2
    ;;
esac
echo "  cluster: ${cluster}"

if ! sacctmgr -n -P show assoc where "user=${USER}" "account=${ACCOUNT}" "cluster=${cluster}" format=User,Account,Cluster |
  grep -F "|${ACCOUNT}|" >/dev/null; then
  echo "ERROR: Slurm does not show ${USER} associated with ${ACCOUNT} on ${cluster}" >&2
  exit 2
fi

if ! sacctmgr -n -P show qos "${base_qos}" format=Name,UsageFactor |
  awk -F'|' -v q="${base_qos}" '$1 == q && ($2 + 0) == 1 { found=1 } END { exit !found }'; then
  echo "ERROR: expected base QoS ${base_qos} with UsageFactor=1 was not found" >&2
  exit 2
fi
if ! sacctmgr -n -P show qos "${preempt_qos}" format=Name,UsageFactor |
  awk -F'|' -v q="${preempt_qos}" '$1 == q && ($2 + 0) == 0 { found=1 } END { exit !found }'; then
  echo "ERROR: expected preemptable QoS ${preempt_qos} with UsageFactor=0 was not found" >&2
  exit 2
fi

if ! scontrol show partition normal_q >/dev/null 2>&1; then
  echo "ERROR: normal_q is not available on ${cluster}" >&2
  exit 2
fi
if ! scontrol show partition preemptable_q >/dev/null 2>&1; then
  echo "ERROR: preemptable_q is not available on ${cluster}" >&2
  exit 2
fi
billing_weights="$(
  scontrol show partition normal_q -o |
    sed -n 's/.*TRESBillingWeights=\([^ ]*\).*/\1/p'
)"
if [[ -z "${billing_weights}" ]] ||
  ! printf '%s\n' "${billing_weights}" |
    awk -F'[=,]' -v cpu="${expected_cpu_rate}" '
      ($1 == "CPU") && (($2 + 0) == (cpu + 0)) &&
      ($3 == "Mem") && (($4 + 0) == 0.125) { ok=1 }
      END { exit !ok }
    '; then
  echo "ERROR: ARC billing weights changed from the checked-in profile assumptions" >&2
  echo "  observed: ${billing_weights:-missing}" >&2
  echo "  expected: CPU=${expected_cpu_rate},Mem=0.125G" >&2
  echo "Update arc_resource_profiles.json before submitting Pineland jobs." >&2
  exit 2
fi

# Validate account/partition/QoS combinations with Slurm without creating a
# job or consuming SUs. --test-only performs scheduler validation only.
normal_test=(
  --test-only
  "--account=${ACCOUNT}"
  --partition=normal_q
  "--qos=${base_qos}"
  "${test_constraint[@]}"
  --nodes=1
  --ntasks=1
  --cpus-per-task=1
  --mem=1G
  --time=00:01:00
  --wrap=/bin/true
)
if ! sbatch "${normal_test[@]}" >/dev/null; then
  echo "ERROR: Slurm rejected a test-only Pineland-sized request" >&2
  exit 2
fi

preempt_test=(
  --test-only
  "--account=${ACCOUNT}"
  --partition=preemptable_q
  "--qos=${preempt_qos}"
  "${test_constraint[@]}"
  --nodes=1
  --ntasks=1
  --cpus-per-task=1
  --mem=1G
  --time=00:01:00
  --wrap=/bin/true
)
if ! sbatch "${preempt_test[@]}" >/dev/null; then
  echo "ERROR: Slurm rejected a test-only preemptable request" >&2
  exit 2
fi

if [[ ! -x "${BINARY}" ]]; then
  echo "ERROR: release binary missing: ${BINARY}" >&2
  echo "Run: bash rust/hpc/arc_build.sh" >&2
  exit 2
fi

module reset
module load foss/2025b
module load Rust/1.93.1-GCCcore-14.3.0
if ! "${BINARY}" version >/dev/null; then
  echo "ERROR: release binary cannot execute in the current ARC software environment" >&2
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
echo "  Slurm account/QoS test: passed"
echo "  normal_q billing: ${billing_weights}"
echo "Preflight checks passed."
