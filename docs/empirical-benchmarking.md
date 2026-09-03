# v0.11 Empirical Benchmarking and Case Library

Version 0.11 creates a boundary between evidence and simulation. It does not
claim that the bundled examples are historical data. They are schema fixtures
that make missingness, uncertainty, and provenance visible before real case
packages are admitted.

## Evidence topology

```text
RawObservation
    -> TransformationRecord (formula, assumptions, source hash)
    -> EmpiricalTarget (value, uncertainty, weight, split)
    -> target contract
    -> calibration / validation / falsification
```

`RawObservation` supports CSV, JSON, and JSONL. It retains source name, URL,
case, timestamp, geography, recorded uncertainty, and arbitrary metadata.
`TransformationRecord` stores the exact input observation IDs, formula,
assumptions, and a stable hash of the source rows. `EmpiricalTarget` carries
measurement uncertainty separately from model error.

## Recorded versus true history

The model's `recorded_synthetic_observations` exporter uses only
`SyntheticRecord.recorded` values. `recorded_vs_true_metrics` reports the
observation operator's distortion alongside hidden event truth. Validation
should compare synthetic recorded data with real recorded data wherever the
historical source is a recording process, not silently compare model truth with
imperfect records.

Run outputs persist both `recorded_empirical_observations.jsonl` and
`recorded_vs_true_metrics.json`, so an empirical comparison can audit exactly
which synthetic records entered a target transformation.

## Case packages

Each `CasePackage` contains observations, targets, transformations,
time-window and geography metadata, and an explicit missing-metric list. Cases
may stress different parts of the model; missing targets are not treated as
zeros. Use `case-catalog` to summarize packages and
`CasePackage.target_contract()` to route a package into the v0.10 workbench.

The bundled `scenarios/cases/illustrative-pineland-case.json` is a fixture only.
Replace it with a documented package before empirical claims are made.

## Fragmentation forensic workflow

`fragmentation-forensic` focuses on birth, split, collapse, succession, combat
attrition, and recruitment instead of sampling all 170 parameters. It reports
the best target error, main-effect ranking, practical identifiability, and a
diagnosis:

- parameter problem when a focused lever can reproduce the target;
- weakly identifiable parameter problem when equivalent fits span the prior;
- structural model problem or measurement mismatch when the focused family
  cannot approach the target.

This turns the illustrative fragmentation error of `1.0` into a falsifiable
forensic exercise rather than a reason to retune blindly.

## Synthetic parameter recovery

`parameter-recovery` draws and hides a known parameter vector, generates a
synthetic target contract, and runs the same sampling/calibration machinery to
recover it. The output reports true and recovered values, normalized errors,
and a recovery status. Failure is informative: it separates structural
identifiability limits from disagreement with external historical evidence.

## Question-specific active sets

The 170-parameter registry remains complete, but `question-registry` returns a
focused set for insurgency onset, fragmentation, recurrence, foreign
dependence, or control. This creates reduced inference designs without
rewriting or deleting the simulator's mechanisms.
