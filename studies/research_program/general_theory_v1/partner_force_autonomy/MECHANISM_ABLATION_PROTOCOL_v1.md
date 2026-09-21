# Mechanism ablation protocol v1

Status: **PROSPECTIVE POST-REVIEW SIDECAR, TO BE FROZEN BEFORE PRODUCTION OUTCOMES**

Date: 2026-09-21

## Purpose

The original Stage-4 paper operationalized indigenous coverage as the minimum
active-service ratio `I/D`. A post-completion review correctly noted that a
lower ratio can arise because indigenous service falls, because the supported
force generates a larger service requirement, or both. Frozen Stage-4 telemetry
shows that higher logistics demand is nearly ubiquitous in terminal logistics
penalty worlds, but that decomposition is descriptive rather than a direct
intervention on the mechanism.

This experiment asks a narrow causal question:

> **How much of the terminal indigenous-coverage penalty survives when the
> continued-support branch is prevented from generating more military
> logistics demand than its matched withdrawal branch?**

The ablation acts only in the experiment runner. It does not replace Pineland's
core logistics equations. For each post-withdrawal telemetry interval, the
withdrawal branch is advanced first. The continued-support branch is then
replayed from the same interval-start state under deterministic rescaling of
the four military logistics-consumption coefficients until its realized
military logistics demand matches the withdrawal branch as closely as possible.
The selected replay state is retained and the original coefficients are
restored before the next interval.

## Status and chronology

- Stage-4 and Stage-5 outcomes were known before this experiment was designed.
- The Stage-4 reviewer-driven supply/demand decomposition was known before this
  experiment was designed.
- Engineering calibration used only seed `2026999902` and a logistics-targeted
  scratch cell. That seed is excluded from production.
- Calibration was used only to verify implementation and demand-matching
  accuracy. Its capability and coverage outcomes are not scientific evidence.
- Production seeds are fresh and are not Stage-4, Stage-5, structural-sidecar,
  or clamp-calibration seeds.
- No production outcome may be inspected before the contract and freeze are
  committed.

## Production design

Four Stage-4 Phase-Map conditions are copied exactly from the original frozen
contract. They were selected because the completed Stage-4 cell summary showed
positive mean +30-day capability and negative mean +360-day indigenous
coverage. Selection spans all four nominal starting-structure labels rather
than choosing only the strongest logistics cell.

| Scenario | Original structure | Capacity | Support intensity | Original mean +30d capability | Original mean +360d coverage |
|---|---|---:|---:|---:|---:|
| M1 | logistics_constrained | 0.40 | 1.00 | +0.1958 | -0.1056 |
| M2 | balanced_capacity | 0.40 | 1.00 | +0.0635 | -0.1050 |
| M3 | forcegen_constrained | 0.25 | 2.00 | +0.0127 | -0.1061 |
| M4 | command_constrained | 0.40 | 2.00 | +0.0140 | -0.1339 |

Each scenario has two otherwise identical treatment cells:

1. `normal`: original Stage-4 execution;
2. `demand_clamped`: continued support with interval military logistics demand
   adaptively matched to the paired withdrawal branch.

The experiment therefore contains `4 scenarios x 2 modes x 12 seeds = 96`
worlds. Every world still contains the native `SUPPORT_ON` and `SUPPORT_OFF`
branches after day 120.

Production seeds: `2026240000` through `2026240011`.

Common environment:

- 1,000 agents;
- 72 localities;
- split at day 120;
- outcome horizons +7, +30, +90, +180, +360 days;
- weekly diagnostic trajectory grid plus registered horizons;
- common random numbers within seed/scenario/mode according to the existing
  runner contract.

## Primary estimands

For each scenario and seed define the native branch contrast

`delta_q(mode) = q_indigenous_SUPPORT_ON(360) - q_indigenous_SUPPORT_OFF(360)`

using the same capped coverage coordinate as Stage 4.

The primary ablation estimand is the paired attenuation:

`A_q = delta_q(demand_clamped) - delta_q(normal)`.

Positive `A_q` means removing excess supported-branch logistics demand makes
the terminal coverage penalty less negative.

Secondary estimands:

- paired change in +30d composite-capability effect;
- paired changes in +90d, +180d, and +360d capability effects;
- paired change in terminal indigenous logistics service;
- paired change in terminal logistics demand;
- demand-clamp matching error at every post-split trajectory interval;
- fraction of worlds in which the clamp reverses a negative terminal coverage
  contrast to neutral/positive;
- bottleneck identity under normal and clamped execution.

## Manipulation check

For each demand-clamped world and post-split interval:

`relative_error = |D_on - D_off| / max(|D_off|, 1)`.

Report the median, mean, 95th percentile, and maximum relative error. The
experiment is considered a successful demand-clamp manipulation only if:

- median relative error <= 0.01; and
- at least 95% of post-split intervals have relative error <= 0.05.

If this check fails, coverage attenuation is not interpreted as a clean demand
ablation.

## Hypotheses and interpretation

**M1. Demand contribution.** The mean paired attenuation `A_q` is positive.

**M2. Material contribution.** Report the ratio

`mean(A_q) / abs(mean(delta_q(normal)))`

when the denominator is nonzero. No threshold is required for success; the
effect size is the result.

**M3. Capability tradeoff.** Demand clamping may also change supported
capability. The experiment therefore does not interpret attenuation as a free
policy improvement. The +30d through +360d capability trajectory must be
reported alongside coverage attenuation.

**M4. Migration is not the mediator by assumption.** Bottleneck migration is
reported descriptively but is not required for M1. The experiment is designed
to test requirement expansion, not to rescue the original claim that migration
causes the coverage penalty.

If M1 fails despite a successful manipulation check, the paper must not claim
that induced logistics demand causally explains the Stage-4 terminal coverage
penalty. If M1 succeeds, the result supports requirement expansion as one causal
component but does not imply it is the only component.

## Inference

The unit of analysis is the paired simulation world, not the grid cell. Report
paired means, medians, seed-level distributions, and bootstrap uncertainty as a
descriptive stability measure. Do not use `statistically significant` language
or treat the number of seeds as a population-sampling design.

## Scope

The clamp is an artificial mechanism intervention. It answers whether the
endogenous logistics-requirement pathway matters inside Pineland. It is not a
realistic assistance policy and should not be interpreted as one.

