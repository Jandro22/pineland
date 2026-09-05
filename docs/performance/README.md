# Exact performance candidate

The 750-agent, 300-locality, 180-day Nepal workload took 99.54 seconds on the
frozen implementation and 65.19 seconds on the candidate: 1.53x throughput,
34.5% less elapsed time. Decision-state, trajectory, synthetic-record hashes,
and all event counts match exactly. Historical scoring was not used.

This is one sequential comparison on a laptop running other historical workers;
it is not a measured full-horizon speedup. The 30-day comparison also matches.

Changes:
- Index formations and patrols once per physical refresh, preserving insertion order.
- Advance idempotent patrol memory once per refresh instead of once per actor/locality.
- Reuse command adjacency/routes within report generation; discard at its boundary.
- Index report sources and check locality before actor matching.
- Reuse movement route computations and pending-order membership per command operation.
- Avoid constructing discarded seeded RNGs and foothold calculations.
- Write trajectory JSON in workers, return only completion metadata, recycle workers,
  and stream JSON to reduce copies and peak memory. File bytes are unchanged.

No scientific equations, RNG draws, event ordering, parameters, or retained outputs
were intentionally changed. Caches are operation-scoped, not persistent model state.

Validation: the first optimization pass passed the 512-test existing suite. Final
routing/movement/physical/reproducibility coverage passed 51 focused tests; subsequent
information/output coverage passed 13 tests. The new regression tests cover cache
scope, route-copy isolation, exception cleanup, relocation, and identical JSON bytes.
The original study fixtures were used to test the candidate imports because ignored
case data are not copied by Git worktree creation.

The implementation lives on codex/exact-performance in an isolated checkout.
It has not replaced the live release certificate or the in-flight frozen historical
runs. Its distinct source hash is recorded in assessment.json; do not relabel it
as the frozen source. Benchmark reproduction is provided by
scripts/benchmark_exact_performance.py with explicit source-root and case-file paths.
