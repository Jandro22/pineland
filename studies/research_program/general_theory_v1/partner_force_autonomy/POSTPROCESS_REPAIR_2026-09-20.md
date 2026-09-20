# Stage 4 postprocessing repair — 2026-09-20

## Scope

This repair is **postprocessing-only**.  It is based on production commit
`e369c107f4465ce8cd385a366cafca8c28c04b65` and does not alter the simulator,
Stage-4 contracts, production seeds, treatment definitions, production binary,
or any production output.

The four simulation arrays (`886147`, `886148`, `886149`, `886150`) continue to
run against the original 55-artifact production freeze.  The initially chained
postprocessing/finalizer jobs (`886151`–`886154`) were cancelled before they ran.

## Defect found by pre-completion smoke test

`analysis/analyze_stage4_integrated.py` completed its numerical calculations but
could not serialize grouped summaries when pandas group keys were NumPy scalar
types (for example `numpy.int64`).  Python's standard `json` encoder rejects
those objects.

The production completeness guard worked correctly and first rejected an
intentionally incomplete two-world analysis against the full 1,680-world
contract.  A scratch contract containing exactly the two selected worlds then
exposed the serialization defect without touching production outputs.

## Repair

The analysis now normalizes NumPy scalar group keys to native Python values
before JSON serialization and maps missing floating group keys to JSON `null`.

A second orchestration omission was found during the same pre-completion audit:
single-world ARC shards deliberately defer the preregistered ensemble
degeneracy safeguard to complete-shard merge, but the Stage-4 postprocess
wrapper had not passed `--enforce-degeneracy-safeguard` to the merger.  The
wrapper now enforces that gate before any module analysis or READY artifact can
be produced.

Module READY artifacts also record both:

- `production_git_commit`: the single commit reported by all production shard
  sidecars;
- `analysis_git_commit`: the postprocessing code commit used for merge/analysis.

The program finalizer requires all three modules to agree on both commits.

## Integrity boundary

The production freeze JSON is intentionally **not regenerated** by this repair.
Its purpose is to document the exact code/artifacts seen by every simulation
world.  Postprocessing runs from a separate worktree and commit after the four
production arrays are complete.
