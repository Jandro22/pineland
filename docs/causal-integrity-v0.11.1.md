# v0.11.1 Causal-integrity release

This release resolves the pre-publication audit of v0.11.0. It is a software
and measurement-integrity release, not a claim that the synthetic priors are
empirically calibrated.

## Repaired causal paths

- Formation location is independent of patrol activity. Government and
  insurgent formations both carry `current_microzone_id`; presence, response,
  and physical-control aggregation run for both sides.
- Background intelligence targets the insurgent side aggregate, so splinters
  are not silently ignored. Microzone detection accepts a formation position
  even when no patrol object exists.
- Recruitment runs only in the explicit recruitment process. Organization
  ecology records eligibility and conditional split draws but does not recruit
  a second time.
- Civilian mobility and expected-control updates consume beliefs/social signals;
  they do not read realized destination control. Initial actor beliefs are
  uninformative priors and are updated by observations.
- Combat capability uses deployable personnel and applies effective readiness
  once. Battlefield momentum is converted to a common government-advantage
  frame before public pooling.
- Language is applied in detection and fusion, not hidden in source quality or
  control-observation confidence. Corroboration counts distinct source IDs and
  contradiction memory decays.
- Fragmentation and post-signature spoilers are distinct quantities. The
  pre-agreement hazard contains one fragmentation penalty.
- Organization identity dispersion is weighted variance around the group's
  weighted mean. Proto/split eligibility and formation manpower use represented
  population semantics.
- Birth-time formation supply is debited from organization resources and entered
  through an explicit cross-stock conversion ledger. Runtime foreign stocks are
  external inflows rather than changes to the generated baseline.
- Patronage stocks decay between political cycles. Synthetic event recording is
  configurable and emits recording/geocoding diagnostics.

## Reproducibility contract

Run from a clean checkout with:

```powershell
python -m pip install -e .
python -m pytest -q
```

All stochastic streams remain named and seed-derived. The full suite and the
adversarial causal tests must be rerun after any change to a model prior or
process schedule. Existing v0.11.0 sensitivity and recovery artifacts are not
silently mixed with v0.11.1 results.

## Interpretation boundary

`WorldState` still distinguishes latent truth, actor belief, and synthetic
recording. `recording_diagnostics.json` reports generated-versus-recorded recall,
source/event-type strata, geocoding-error flags, and distance distributions.
Precision is explicitly `null` until a false-event generator is configured;
recorded events are not treated as ground truth.
