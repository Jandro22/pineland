# Structural falsification protocol v1

Status: **PROSPECTIVE POST-STAGE-4 SIDECAR, FROZEN BEFORE OUTCOME OBSERVATION**

Date: 2026-09-21

## Purpose

Stage 4 repeatedly produced logistics as the modal post-relief bottleneck. This
sidecar addresses one narrow architectural objection: **is logistics forced to
be terminal by the formal coordinate or runtime architecture, or can successful
relief end with command or force generation as the limiting indigenous service
when the structural ordering is changed?**

The experiment is not a new estimate of how often real or synthetic forces end
in each bottleneck. It is an adversarial possibility test. The intended claim is
limited to whether alternative terminal constraints are dynamically reachable.

## Scientific status

- Stage-4 outcomes are known before this sidecar was designed.
- Stage-5 production is ongoing and no Stage-5 outcome is used in this design.
- No sidecar outcome may be used to alter the four cells, eight seeds, treatment
  doses, measurement windows, or interpretation rules below.
- The result is post-Stage-4 structural falsification, not preregistered Stage-4
  evidence.

## Common environment

- agents: 1,000
- localities: 72
- common supported prehistory: day 0 through day 120
- pre-relief diagnostic window: day 60 through day 120
- post-relief diagnostic horizon: +30 days under continued treatment
- seeds: 2026235000 through 2026235007, shared across all four cells
- formal services: force generation, logistics, command
- formal bottleneck: service with minimum indigenous service coverage among
  active-demand channels, using the existing Lean-aligned runtime adapter

## Cells

The first two cells make logistics deliberately abundant and use the same 1.0x
targeted substitution doses as Stage 4. The final two cells place logistics just
below a designated secondary constraint and use the Stage-4 high developmental
dose so that indigenous logistics itself can plausibly be relieved.

| Cell | Intended path | Indigenous multipliers (FG, logistics, command) | Treatment |
|---|---|---|---|
| structural_001 | force generation -> command | (0.10, 4.00, 0.35) | Stage-4 1.0x force-generation substitution: +0.035 training-rate boost |
| structural_002 | command -> force generation | (0.35, 4.00, 0.15) | Stage-4 1.0x command substitution: +0.55 reliability, 0.55 latency reduction, 0.5h floor |
| structural_003 | logistics -> command | (4.00, 0.25, 0.35) | Stage-4 high logistics development: +0.08 indigenous logistics capacity per 30d |
| structural_004 | logistics -> force generation | (0.35, 0.25, 4.00) | Stage-4 high logistics development: +0.08 indigenous logistics capacity per 30d |

The deliberately high non-target multiplier of 4.0 is an adversarial structural
perturbation. It is not intended as a plausible historical calibration. Its role
is to prevent logistics from becoming terminal merely because all other service
capacities remain near the Stage-4 baseline.

## Estimands

For every cell and seed:

1. reconstruct the pre-relief formal bottleneck over day 60 to day 120;
2. record the +30d `SUPPORT_ON` formal bottleneck;
3. classify whether the intended initial service actually matched the observed
   pre-relief bottleneck;
4. among observed-matched worlds, report the complete distribution of +30d
   bottlenecks;
5. report +30d supported composite-capability change and +30d indigenous
   feasibility where available.

No seed is excluded for failing to match the nominal initial bottleneck. Such a
seed remains in the output and is simply excluded from the target-matched path
fraction.

## Falsification interpretation

The strongest artifact claim would be that the architecture **cannot** produce
a non-logistics post-relief bottleneck. That claim is rejected if at least one
observed-target-matched treated world terminates at +30d with command as the
formal bottleneck and at least one observed-target-matched treated world
terminates with force generation as the formal bottleneck.

Stronger evidence is reported descriptively as the fraction of matched worlds in
each designated path that end at the intended alternate constraint. There is no
minimum fraction required for the narrow architecture-possibility claim.

If no command or force-generation terminal world appears, the manuscript must
retain or strengthen the concern that Stage-4 logistics persistence may be an
architectural attractor. The design must not be tuned and rerun to force a
preferred outcome.

## Scope

Passing this sidecar would establish only that logistics is **not hard-coded as
the unique dynamically reachable terminal constraint**. It would not establish
that the Stage-4 logistics-sink frequency generalizes outside Pineland, nor that
the engineered alternative structures are empirically common.

