# v0.10 Research Validation Release

This release changes the research question from “can the mechanisms run?” to
“which mechanisms are empirically supported, sensitive, and distinguishable?”
It provides falsification infrastructure, not an assertion that the default
Pineland priors are calibrated to a real conflict.

## Parameter provenance

`pineland-sim parameter-registry` writes one record for every scalar
configuration value. Each record contains a mathematical symbol, code path,
units, subsystem, current prior, sampling range when applicable, assumption
type, empirical source and source-case placeholders, confidence, calibration
status, sensitivity rank, and identifiability status.

The default registry is intentionally candid. Live assumption/status labels
distinguish experimental treatments, empirical estimands, literature priors,
structural/scaling coefficients, engineering priors, numerical safeguards, and
fixed structural assumptions. A value must not be relabeled `calibrated`
merely because it generated a desirable trajectory; calibration requires a
declared empirical source/population, training target, fitting procedure, and
unchanged validation/holdout use.

## Target contracts

An empirical target is a JSON contract, not a hard-coded historical claim. It
names its source, population/case, split, metric values, weights, and
tolerances. Five target families are supported:

- Conflict events: frequency, spatial concentration, temporal burstiness.
- Control: government and insurgent control plus persistence.
- Organizations: active organization count and fragmentation.
- Population: external migration share.
- Peace: agreement, implementation, and recurrence.

The example contracts in `scenarios/targets/` are schema examples only and are
explicitly not empirical data.

## Global sensitivity and interactions

`pineland-sim sensitivity` creates a deterministic Latin-hypercube design over
the declared scientifically interpretable prior ranges. It runs each sampled
configuration, then reports rank-correlation main-effect screens, pairwise
interaction screens, outcome variance, raw draws, seeds, and outcomes. The
screens are prioritization diagnostics, not Sobol variance decompositions;
they identify where a more expensive uncertainty analysis should concentrate.

Example:

```powershell
pineland-sim sensitivity --config scenarios/baseline.json --samples 64 --repetitions 3 `
  --outcomes government_control implementation recurrence --output outputs/sensitivity.json
```

## Practical identifiability and holdout validation

`pineland-sim validate` selects the lowest-error configuration against a
training contract, then scores that unchanged configuration against a holdout
contract. It also finds a practical-equivalence set: sampled parameter sets
whose training error is close to the best. A parameter is classified as:

- **Well constrained:** equivalent fits cover under 25% of its declared prior range.
- **Weakly constrained:** equivalent fits cover 25–60%.
- **Non-identifiable:** equivalent fits cover at least 60%.

These are practical classifications conditional on the target family, prior
ranges, sample design, and stochastic replication count. They are not claims
of formal posterior identifiability.

```powershell
pineland-sim validate --config scenarios/baseline.json `
  --training scenarios/targets/example-training.json `
  --holdout scenarios/targets/example-holdout.json --samples 64 `
  --output outputs/validation.json
```

## Agreement-ceiling stress test

`pineland-sim bargaining-stress` constructs common-opportunity negotiation
environments from hard commitment problems through credible guaranteed windows.
It freezes unrelated organization ecology and foreign stochasticity, holds
mutual bargaining surplus fixed, and varies agreement hazard and credibility
inputs. It should be used to verify that agreement probability does not remain
near one across all plausible bargaining regimes.

## Model ladder

`pineland-sim model-ladder` evaluates the same target contract across:

| Model | Purpose |
|---|---|
| M0 random/null | Minimal independent event baseline |
| M1 self-exciting proxy | Simple event-clustering comparator |
| M2 reduced Pineland | ABM with organizational ecology, foreign affairs, and peace disabled |
| M3 full Pineland | Complete lifecycle model |

Scores are normalized target errors, so lower is better. Each model is scored
only on the target dimensions it claims to represent; unavailable dimensions
are marked not applicable. The simple proxy only claims event-clustering
outputs; it is not judged as though it explained control, migration,
organization ecology, or peace. The full model earns its
complexity only if it improves relevant held-out patterns or provides additional
validated outcomes that simpler models cannot represent.
