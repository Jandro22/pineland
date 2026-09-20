# Stage 4 integrated ARC run ledger — 2026-09-20

This ledger records the immutable simulation provenance, scheduler layout,
pre-production gates, and postprocessing-only repairs for the integrated Stage-4
partner-force experiment.  It is descriptive provenance; scientific results are
not recorded here while production is incomplete.

## Immutable production layer

- Branch: `stage4/integrated-paper-v1`
- Production Git commit:
  `e369c107f4465ce8cd385a366cafca8c28c04b65`
- ARC worktree: `/home/alejandrog/pineland-stage4-paper`
- Production worktree verified clean after launch.
- Production freeze:
  `contracts/partner_force_stage4_integrated_freeze_v1.json`
- Frozen artifacts: **55**
- Every tested frozen canary reported all 55 artifacts matching the manifest.
- Production release binary:
  `/home/alejandrog/pineland-stage4-target/release/examples/partner_force_autonomy_stage3`

No production treatment, seed, simulator rule, contract, or binary was changed
after the production arrays were submitted.

## Canonical engineering calibration

- Job: `886011`
- Worlds: 36
- Completed: 36/36
- Failed: 0
- Seed namespace: `2026290000` series, disjoint from production.
- Combined primary/trajectory file-set SHA-256:
  `09ef281ab97c9923d29b44240c143d2d947cce58581698cb76cff8e924afbacc`
- Decision: retain the originally specified developmental rate scale unchanged.

The pre-canonical engineering jobs `885968` and `886005` exposed and repaired a
development-only command-overlay exact-zero defect before any production seed
was run.  Canonical job `886011` reran the full 36-world calibration under one
corrected runtime.

## Pre-production gates

All of the following passed before production launch:

- Python compilation;
- Rust formatting;
- workspace Clippy with warnings denied;
- full Rust workspace test suite;
- Stage-4 treatment-invariant tests;
- partner-force formal adapter tests;
- safeguards/assays suite (7/7);
- local 12-world treatment-relevance test;
- Owl release-mode 12-world treatment-relevance/preflight battery;
- all 234 Stage-4 configuration cells mapped to valid `SimulationConfig`s;
- Bash syntax for launch/array/postprocessing scripts;
- independent verification of every freeze hash.

The Owl release preflight job `886145` passed combat, air, logistics,
force-generation, and command liveness, exact negative controls, treated-branch
divergence, and encounter realism.

Frozen full-horizon canaries `886068`, `886072`, and `886135` each completed
with exit `0:0`, 10 primary branch rows, and 120 trajectory rows.

## Production scheduler layout

Owl reports `MaxArraySize = 1001`; therefore the 1,680-world Phase Map cannot be
represented by one array or by a second array whose local indices exceed 1000.
The generic Stage-4 wrapper consequently separates Slurm-local task ID from the
logical experiment task ID and records both in every sidecar.

| Module | Slurm job | Slurm IDs | Offset | Logical IDs | Throttle |
|---|---:|---|---:|---|---:|
| Phase Map A | `886147` | 0–839 | 0 | 0–839 | 48 |
| Phase Map B | `886148` | 0–839 | 840 | 840–1679 | 48 |
| Bottleneck Migration | `886149` | 0–623 | 0 | 0–623 | 52 |
| Substitution/Development | `886150` | 0–503 | 0 | 0–503 | 48 |

Aggregate intended active concurrency: **196 one-core worlds**.

The merger requires

```text
slurm_array_task_id + task_offset = logical_task_id
```

for Stage-4 metadata.  A representative Phase Map B task was observed mapping
Slurm task 0 to logical task 840 / cell 70 / seed `2026200000` as intended.

Production output directories:

- `/home/alejandrog/pineland-stage4-production/phase_map`
- `/home/alejandrog/pineland-stage4-production/bottleneck_migration`
- `/home/alejandrog/pineland-stage4-production/substitution_development`

## Cross-chunk and integrity canaries

A cross-chunk merger canary used logical Phase Map tasks 0 and 840 and passed:

- 2 task sidecars verified;
- 20 primary branch rows;
- 240 trajectory rows;
- source array IDs `886147` and `886148`;
- one production commit, `e369c107...`.

Repeated live integrity sweeps independently recomputed primary/trajectory
SHA-256s, row counts, logical-ID mappings, filenames, and production commit for
all completed sidecars available at the time.  Sweeps at 302, 835, and 1,023+
completed worlds found zero integrity errors and zero duplicate logical IDs.

## Postprocessing-only repair layer

Production remains immutable.  Downstream analysis is isolated in:

- branch: `stage4/postprocess-fix-v1`
- ARC worktree: `/home/alejandrog/pineland-stage4-postprocess-fix`
- final postprocessing repair commit:
  `dfd90826b8c5c9cb40b064e467e16fda7319c426`

Two pre-completion smoke tests found postprocessing defects before the module
jobs ran:

1. grouped pandas/NumPy scalar keys were not JSON serializable;
2. the wrapper did not request the merge-time ensemble degeneracy safeguard,
   even though single-world shards explicitly defer that gate to merge.

The fixes are strictly postprocessing-only.  Module READY files now record both
`production_git_commit` and `analysis_git_commit`; the finalizer requires all
modules to agree on both.

The original downstream jobs `886151`–`886154` and intermediate repaired jobs
`886884`–`886887` were cancelled before execution.  They produced no accepted
module READY artifacts.

### Postprocessing validation

A contiguous two-world wrapper canary passed end-to-end.

A larger 144-world Phase Map canary (12 complete cells × 12 seeds) then passed
with the ensemble safeguard enabled.  The safeguard evaluated 120 treated
worlds at +180d and reported:

- near-zero worlds: 22;
- near-zero fraction: 0.1833333333;
- mean `R_180`: 0.9843915361;
- variance: 0.00535134827;
- status: **PASS**.

The canary completed analysis and emitted a READY artifact carrying production
commit `e369c107...` and analysis commit `dfd90826...`.  Canary READY/output
artifacts were removed from the repair worktree before final jobs were queued.

### Final dependency chain

Final postprocessing jobs are queued from the clean `dfd90826...` worktree and
remain dependency-blocked until their production arrays succeed:

- Phase Map postprocess: `887341`, after `886147` + `886148`;
- Migration postprocess: `887342`, after `886149`;
- Mechanism postprocess: `887343`, after `886150`;
- integrated finalizer: `887344`, after all three postprocessors.

The module postprocessors require exact task coverage, cryptographic shard
verification, one production commit, the ensemble degeneracy gate, complete
analysis, and an independently hashed READY artifact.  The finalizer requires
2,808 expected worlds and one shared production commit plus one shared analysis
commit across all three modules.

## Precommitted paper-analysis layer

To avoid outcome-driven threshold selection, paper-level secondary analysis was
specified before production completion in a third branch:

- branch: `stage4/paper-analysis-plan-v1`
- initial precommit: `8f00818a0a2ed675cfd84bb6bea2088834abd85c`
- plan: `STAGE4_PAPER_SECONDARY_ANALYSIS_PLAN_2026-09-20.md`
- script: `analysis/analyze_stage4_paper_secondary.py`

This layer fixes the early-effect (+30d) versus terminal-autonomy (+360d)
definition of the autonomy trap, non-monotonic phase-boundary reporting,
bootstrap/Wilson uncertainty rules, substitution-development matched-seed
contrasts, cumulative indigenous-coverage mechanism metrics, and bottleneck
migration robustness checks.  The implementation passed synthetic Stage-4-shaped
tests before any complete production surface was inspected.

