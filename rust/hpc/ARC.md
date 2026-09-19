# Pineland on Virginia Tech ARC

Pineland has two separate HPC execution modes and they should not be mixed
casually.

1. Ensemble campaigns run many independent worlds through a Slurm job array.
   Use this for theory sweeps, factorials, seed replication, robustness work,
   and held-out validation.
2. MPI particle filtering distributes one large inference workload across
   ranks through the pineland-hpc crate.

A single "pineland run" trajectory is serial. Do not reserve a many-core node
for it. Scale independent trajectories with arc_campaign.py.

## Account and budget protection

The checked-in ARC resource profiles use the Slurm account
"will_taggart_mcll". Campaign specifications default to a 50,000 SU ceiling.
Before submission, arc_campaign.py computes a conservative upper bound using
the full requested walltime of every Slurm array element. Submission fails if
that bound exceeds the campaign cap unless the overrun is explicitly allowed.

The preemptable profiles use zero SU in the budget model because ARC does not
bill its preemptable partitions. Those jobs may be cancelled and requeued, so
they are intended for short independent trajectories where rerunning one task
is cheap.

## One-time ARC setup

From the repository root on an ARC login node:

~~~bash
bash rust/hpc/arc_build.sh
bash rust/hpc/arc_preflight.sh
~~~

For the MPI-enabled binary:

~~~bash
bash rust/hpc/arc_build.sh --mpi
~~~

The build script pins Rust 1.93.1 and explicitly compiles the portable
x86-64-v3 target required by the repository's certified-build contract. It
refuses to inherit an arbitrary RUSTFLAGS value. MPI builds also pin
foss/2025b rather than depending on whichever compiler/MPI modules happen to
be the defaults.
Preflight checks the live Slurm cluster, account association, base QoS,
software modules, release binary, and performs an "sbatch --test-only"
validation. That scheduler check does not submit a job or consume SUs.

## Build a campaign

Example campaign.json:

~~~json
{
  "campaign_id": "partner-force-pilot-v1",
  "binary": "rust/target/release/pineland",
  "command": "run",
  "configs": [
    {"id": "baseline", "path": "studies/example/baseline.json"},
    {"id": "treatment", "path": "studies/example/treatment.json"}
  ],
  "seeds": [1001, 1002, 1003, 1004],
  "days": 180,
  "extra_args": [],
  "budget_su_cap": 50000
}
~~~

Expand it into a deterministic task manifest:

~~~bash
python3 rust/hpc/arc_campaign.py build \
  --spec campaign.json \
  --repo-root . \
  --manifest-dir campaigns/partner-force-pilot-v1

python3 rust/hpc/arc_campaign.py validate \
  --manifest-dir campaigns/partner-force-pilot-v1
~~~

The task set is the Cartesian product of configs and seeds. Campaign creation
requires the compiled binary and every config to exist. Their SHA256 hashes
are embedded in the task fingerprints and verified again immediately before
execution, so a later config edit or binary rebuild cannot silently mix
scientific conditions inside one campaign. The task file is itself hashed by
the campaign manifest, so manual manifest edits also fail validation. A
fixed-width byte-offset index lets each array worker seek directly to its
task instead of reparsing the entire campaign manifest; full validation and
collection still verify both files end-to-end.

## Dry-run and submit

Always inspect a submission first:

~~~bash
python3 rust/hpc/arc_campaign.py submit \
  --manifest-dir campaigns/partner-force-pilot-v1 \
  --repo-root . \
  --profile tinkercliffs-trajectory-normal \
  --dry-run
~~~

Remove "--dry-run" to submit. Available resource profiles are in
arc_resource_profiles.json. Normal trajectory profiles request one CPU because
a single world is serial. Profiles explicitly request ARC's base QoS so the
budget calculation cannot silently drift to the 2x-billed short QoS. Owl
profiles also request "avx512", which ARC maps to the Zen 4 Genoa CPU nodes.

For very short trajectories, bundle several model tasks into each Slurm array
element so scheduler overhead does not dominate:

~~~bash
python3 rust/hpc/arc_campaign.py submit \
  --manifest-dir campaigns/partner-force-pilot-v1 \
  --repo-root . \
  --profile tinkercliffs-trajectory-normal \
  --tasks-per-array-element 20 \
  --max-concurrent 200 \
  --dry-run
~~~

Bundling does not weaken recovery. Each underlying Pineland task still gets
its own fingerprint, attempt directory, success marker, and artifact hashes.
When run on ARC, submission reads Slurm's live MaxArraySize and rejects a
campaign that would exceed it, reporting the minimum required bundle size.

## Recovery and evidence integrity

Array work is written under:

~~~text
/scratch/$USER/pineland/<campaign>/tasks/<task-id>-<key>/
~~~

Each execution attempt gets a separate directory. A task becomes complete
only after the process exits successfully, all required products exist, their
SHA256 hashes are recorded, and an atomic _SUCCESS.json marker is published.
The required-product list is only a minimum completeness check: after it
passes, every file in the task output tree is hashed, including event and
observation streams and checkpoint shards.
The array worker also pins Rayon/OpenMP/BLAS thread counts to the Slurm CPU
request and appends Slurm logs across requeues instead of truncating them.

On requeue or resubmission:

- a valid completed task is skipped;
- an interrupted or failed attempt remains available for diagnosis and is
  rerun;
- a success marker with a changed fingerprint or artifact hash fails closed
  rather than silently accepting altered evidence.

This is intentionally task-level recovery. The normal run command does not
currently publish a useful mid-trajectory checkpoint, so the ensemble layer
does not claim to resume halfway through a single world. The MPI filter keeps
its existing checkpoint/resume implementation.

## Collect results

After the array finishes:

~~~bash
python3 rust/hpc/arc_campaign.py collect \
  --manifest-dir campaigns/partner-force-pilot-v1 \
  --output campaigns/partner-force-pilot-v1/results_index.json
~~~

Collection fails if any task is absent or any recorded artifact has changed.
Use "--allow-incomplete" only when a deliberately partial analysis is wanted.
The result index points to the successful scratch attempts. Move durable
scientific products to project storage before the ARC scratch-retention window
expires.

## MPI filter path

slurm_mpi.sbatch and rank_topology.sbatch remain the launchers for large
particle-filter jobs. The MPI implementation owns canonical particle
partitioning, rank-independent resampling, state migration, and resumable
checkpoint shards. Do not wrap a single large MPI filter in an ensemble array
unless the study truly requires multiple independent filters.
