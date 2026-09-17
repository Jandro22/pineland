# Pineland Research-v1: the hidden-war program

## North star

Pineland is a computational research platform for estimating hidden political
and organizational conditions in irregular warfare from incomplete
observations. Its first scientific question is not whether a highly detailed
simulation can resemble one historical war. It is whether a declared inference
system can recover a known latent conflict state after the observation process
has hidden, delayed, corrupted, or spatially displaced the evidence.

The estimator never receives the truth projection. Truth is retained only by
the experiment harness for scoring.

## Evidence hierarchy

1. **Synthetic recovery.** Run Pineland as the known world, create imperfect
   reports from that world, reconstruct the hidden state, and measure error and
   uncertainty calibration.
2. **Synthetic misspecification.** Make the estimator wrong on purpose: alter
   reporting rates, spatial error, noise, transition mechanisms, or available
   channels and map the failure envelope.
3. **Afghanistan.** Treat Afghanistan as a development/calibration case with a
   genuinely held-out time/geography target and explicit simple baselines. It
   is not a source of known latent truth.
4. **Nepal.** Freeze mechanisms before transfer. Case-specific initialization
   is allowed; outcome-driven mechanism retuning is not. Failure is retained as
   evidence rather than tuned away.

## Architecture freeze

Research-v1 is an experiment-first branch. Broad mechanics are frozen. Changes
are in scope only when they are one of the following:

- bug or invariant correction;
- observation/measurement model work;
- inference or validation infrastructure;
- experiment orchestration and simple baselines;
- provenance/reproduction support;
- a scientifically necessary correction discovered by a failing experiment.

GUI work, fictional-world enrichment, new political subsystems, and performance
work without an experiment-level bottleneck are out of scope for this branch.
Every core-model change must state which experiment requires it and invalidates
the affected recovery/historical evidence until rerun.

## Primary latent targets

The initial benchmark retains all seven government and insurgent control
dimensions: formal, physical, administrative, legal, fiscal, social, and
expected control. It also exposes locality-level insurgent foothold,
organizational embeddedness, equipped fighter-capacity saturation, and supply
capacity. A target may be removed from the eventual claims if the benchmark
shows that the observation design cannot identify it.

That removal is a finding, not a failed software milestone.

## Observation process

`src/pineland_sim/recovery.py` defines a history-free observation layer with
declared proxy channels. The current channels are synthetic measurement
contracts, not assertions about the properties of any historical dataset. The
process can vary report probability, Gaussian measurement error, reporting
delay, geolocation error, false-report probability, and channel availability.

Spatially fallible reports are scored with a finite mixture over the reported
locality and its neighbors when the estimator admits geolocation error. A
misspecification experiment can instead force the estimator to pretend that
reported coordinates are exact.

## Recovery measures

The benchmark reports point error (bias, MAE, RMSE), 50/90/95 percent interval
coverage, interval width, confidently-wrong rate, spatial correlation,
change-detection rate, and detection lag. Undetected changes remain in the
denominator; they are never silently removed because no lag could be computed.

Posterior cross-variable correlation is reported only as a collinearity
warning. Small or resampled particle ensembles can create duplicate support and
spuriously extreme correlations. A substantive non-identifiability claim
therefore requires repeated worlds, adequate particle support, deliberate
observation-channel ablations, and stability across seeds.

## Development profiles

The 8-particle/14-day configuration is a software smoke test only. It is not a
calibration experiment. Development runs should use larger ensembles and
multiple worlds. Confirmatory particle counts, world counts, uncertainty gates,
and misspecification severity levels must be frozen before the confirmatory
batch is executed; they must not be chosen to make a pilot pass.

Current runnable example:

```text
python studies/research_program/scripts/run_research_v1_synthetic_recovery.py \
  --agents 120 --particles 32 --days 28 --scenario nominal
```

The misspecification battery is selected with repeated `--scenario` arguments
or `--scenario all`.

The repository-level reproduction entry point does not require package
installation:

```text
python pineland.py reproduce paper1 --profile smoke
```

The smoke profile is deliberately too small for scientific claims. The
development profile adds the current misspecification battery and a matched
no-assimilation ensemble so posterior improvement can be measured against the
same latent prior rather than only against a direct-report heuristic. The
development profile also compares localization radii 0, 1, and 2 on the same
hidden world, reports, and prior ensemble. Radius is therefore treated as an
estimator-design choice to diagnose spatial dimensionality, not tuned against a
historical case.

Three additional synthetic diagnostics isolate failure modes before expensive
dynamic batches are attempted:

```text
python studies/research_program/scripts/run_research_v1_weight_collapse_diagnostic.py
python studies/research_program/scripts/run_research_v1_channel_ablation.py
python studies/research_program/scripts/run_research_v1_repeated_snapshot_recovery.py
```

The repeated-snapshot benchmark treats the synthetic world as the scientific
unit and measures paired prior-versus-posterior error across multiple known
truths. A single world's RMSE change is therefore a pilot diagnostic, not a
general recoverability claim.

## Claim firewall

The synthetic benchmark may support statements such as "under this declared
observation and transition process, physical control is recoverable with this
error and coverage." It cannot support "Pineland reconstructed the true Taliban
strength in a historical district," because that historical latent truth is
not observed. Historical cases answer predictive/transfer questions against
observable held-out evidence under a separately frozen contract.
