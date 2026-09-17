# Current science status

Generated after the canonical fixed-work run on the live model. No historical outcome was read or fitted, and no PDF was regenerated.

## Phase A

- Exact scheduler-oracle battery: passed. The v9 battery reports 60 boundary comparisons, zero world-state mismatches, zero execution-state mismatches, and a passing resampling-lineage check.
- Packed-state authority inventory: passed.
- Independent kernel oracles: passed.
- Profile and migration validation: passed; migrated execution preserved exactness in the bounded validation.
- Production packed filtering: exercised in the benchmark path.
- Fixed workload: 32 particles × 8 weekly boundaries × 3 branch-equivalents = 768 PWB per measured repetition; synthetic all-inactive observations; five measured repetitions after one warmup; 16 workers.
- Performance: median 5.583900 PWB/s, range 5.452355–5.928904, coefficient of variation 0.032946. E1 (≥4 PWB/s) passed; E2 (≥10 PWB/s) remains unmet. No extrapolation is used.

The authoritative records are:

- `studies/research_program/phase_a_exactness_battery_v9.json`
- `studies/research_program/phase_a_execution_profile_v7.json`
- `studies/research_program/phase_a_fixed_work_benchmark_v5.json`
- `studies/research_program/phase_a_fixed_work_benchmark_failure_v4.json`
- `studies/research_program/phase_a_migration_decision_v3.json`
- `studies/research_program/phase_a_certificate_v11.json`

The certificate is `phase_a_passed` because exactness, authority, kernel oracles, profile-driven migration, E1, packed filtering, and synthetic inference all pass. E2 remains an explicit unmet target and is not silently converted into a gate.

The tested cross-particle packed alternative is retained only as a negative A6 probe: it was exact in the smoke oracle but measured 0.686005 PWB/s on the complete fixed workload, so it was not promoted.

## Phase B

Synthetic-only Rao–Blackwellized, guided-proposal, MCSE, and combined validation passed after rebinding to exactness battery v9:

`studies/research_program/phase_b_inference_validation_v6.json`

This is not evidence of historical validity.

## Phases C–F

The method contract, historical status, theory contract, and robustness status are all preserved as fail-closed artifacts:

- Phase C: historical authorization remains false because the frozen core boundary is not clean against the live model hash.
- Phase D: Nepal/Afghanistan confrontation not authorized and not run under this contract; stale-core logs remain unpromoted.
- Phase E: equations and falsifiable predictions are specified, but no historical transfer claim is promoted.
- Phase F: synthetic design constraints are recorded; historical robustness and cross-case transfer remain unexecuted.

No result here licenses parameter tuning against Nepal or Afghanistan.
