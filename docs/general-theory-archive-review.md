# General Theory v1 archive review

This is a **review inventory**, not an archival action. It records what can be
simplified later without moving or deleting files during active research.

Inventory date: 2026-09-19.

## Current tracked footprint

At the time of review, `studies/research_program/general_theory_v1/` contains
340 tracked files.

| Type | Files | Approximate size |
|---|---:|---:|
| JSON | 234 | 5.97 MB |
| Python | 71 | 0.54 MB |
| Rust | 20 | 0.43 MB |
| Markdown | 7 | 0.11 MB |
| CSV | 2 | 0.01 MB |
| Other metadata/build files | 6 | negligible |

This is not large in Git-storage terms. The organizational problem is mainly
**cognitive surface area**, especially versioned scientific artifacts, rather
than repository size.

## Active untracked work observed

The primary research checkout contained 23 untracked General Theory files at
review time.

### Generated evidence: keep local / external by default

Five files are CSV experiment panels in the `graph_markov_dev_20260917/` and
`localflow_samepool_battery_20260917/` directories.

Disposition: **retain as generated scientific evidence; do not commit merely
for completeness.** If a paper claim depends on them, retain their hashes and
compact summaries and move the large panels to the eventual research archive.

### Compact protocols: retain and consider tracking

- `localflow_component_ablation_protocol_v1.json`
- `localflow_samepool_comparator_protocol_v1.json`

Disposition: **retain.** These look like prospective scientific design/protocol
artifacts and are candidates for tracking once the active research owner
confirms their freeze status.

### Compact diagnostics/theory evidence: retain

- `probabilistic_causal_cone_20260917.json`
- `ring1_failure_predictors_20260917.json`

Disposition: **retain.** These are compact scientific evidence/diagnostics, not
cleanup debris.

### Equivalence and correction artifacts: preserve through freeze

Fourteen JSON files record equivalence results, corrected equivalence results,
or restricted screens across graph-Markov, local-flow, same-pool, and ring-1
experiments.

Disposition: **preserve both original and corrected forms during active
research.** After the theory program is frozen, the current/corrected artifacts
can remain prominent while superseded originals move to an explicit provenance
archive. Do not delete originals merely because a corrected artifact exists.

## No immediate deletion candidates

None of the 23 active untracked files reviewed here is classified as safely
disposable. That is intentional: active scientific evidence is not a hygiene
problem.

Disposable caches, build products, and smoke outputs remain governed by
`scripts/cleanup_generated_artifacts.py`.

## First post-freeze archive candidates

A filename-family review found two tracked JSON families with at least three
explicit numbered versions:

- `theory_status_vN.json` — 8 retained versions;
- `falsification_ledger_vN.json` — 4 retained versions.

These are **not deletion candidates**. Once the General Theory program reaches
a stable freeze, the latest canonical version can remain on the active path and
older versions can be moved to an archive area with a manifest recording:

- original path;
- archive date;
- final canonical successor;
- last commit where the archived version was current;
- reason for retention.

Other superseded version families should be reviewed by scientific meaning, not
by filename age alone.

## Proposed frozen layout

After Paper 1 / General Theory freeze, a cleaner structure could be:

    general_theory_v1/
      README.md
      contracts/
      analysis/
      protocols/
      findings/
      validation/
      archive/
        superseded_contracts/
        superseded_status/
        development_diagnostics/

Generated panels should remain outside that Git archive and be represented by
manifests/hashes.

## Decision rule

Do not move a file solely because it is old. Archive only when all are true:

1. a current successor is known;
2. no active runner imports the old path;
3. no frozen study expects the old path;
4. its scientific provenance remains recoverable;
5. the move actually makes the active tree easier to understand.

The broader rules are in [docs/archive-policy.md](archive-policy.md).
