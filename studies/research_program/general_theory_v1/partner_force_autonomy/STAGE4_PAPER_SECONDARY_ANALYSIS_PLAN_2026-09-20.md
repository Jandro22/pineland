# Stage 4 paper-level secondary analysis plan — frozen before production completion

Status: **PRECOMMITTED BEFORE STAGE-4 PRODUCTION COMPLETION**

Production commit: `e369c107f4465ce8cd385a366cafca8c28c04b65`

Postprocessing repair base: `dfd90826b8c5c9cb40b064e467e16fda7319c426`

This plan adds paper-level inference and presentation to the already frozen
module analysis.  It does not change any production treatment, seed, simulator
rule, primary outcome, or production/postprocessing gate.  It was specified
without inspecting incomplete Stage-4 substantive outcome surfaces.

## 1. Primary paper question

The primary question is:

> Under what structural conditions does operationally effective external
> assistance increase indigenous autonomy, and under what conditions does it
> decrease indigenous autonomy?

The primary paired estimands are fixed as:

- **early operational effect**: `SUPPORT_ON - SUPPORT_OFF` composite capability
  at +30 days;
- **terminal autonomy effect**: `SUPPORT_ON - SUPPORT_OFF` in
  `min(q_indigenous, 1.0)` at +360 days.

For a world, with epsilon `1e-6`:

- **effective autonomy building**: early capability effect > epsilon and
  terminal autonomy effect > epsilon;
- **effective autonomy trap**: early capability effect > epsilon and terminal
  autonomy effect < -epsilon;
- effective neutral/mixed: early capability effect > epsilon and terminal
  autonomy effect is within the epsilon band;
- not initially effective: early capability effect <= epsilon.

This definition deliberately uses *early* operational effectiveness rather than
requiring continued capability superiority at day 360.  The substantive theory
is about assistance that works operationally and nevertheless changes the
partner's subsequent autonomous production trajectory.

## 2. Phase-map inference

Module A is analyzed on its exact preregistered grid:

```text
starting structure × indigenous capacity level × support intensity
```

For every cell (12 seeds), report:

- mean and median +30d capability effect;
- mean and median +360d terminal-autonomy effect;
- deterministic percentile-bootstrap 95% CIs for both means;
- effective-seed fraction;
- effective-autonomy-trap fraction;
- effective-autonomy-building fraction;
- trap/build fractions conditional on early effectiveness;
- Wilson 95% intervals for the seed-level fractions;
- 10th/90th percentiles of both continuous effects.

The cell's descriptive regime is determined only from the two cell means.  A
separate **robust** label requires the corresponding 95% bootstrap CIs to
exclude zero and the medians to have the same signs.  Statistical uncertainty
therefore cannot silently change the descriptive phase map.

### Phase boundaries

No global monotonic boundary is assumed.

At fixed structure/capacity, scan adjacent support intensities and report every
observed interval whose mean terminal-autonomy effect changes sign.  At fixed
structure/intensity, do the same across adjacent capacity levels.  Preserve
multiple crossings if they exist.

For each sign-changing adjacent pair, a straight-line zero crossing may be
reported as a **descriptive interpolation only**.  The primary boundary is the
observed bracketing interval, not the interpolated point.

The paper's strongest conditional statement should be based on regions in which
the assistance is also positively effective at +30d.  Transitions outside that
region remain descriptive phase-map information rather than autonomy-trap
evidence.

## 3. Mechanism: indigenous supply versus induced demand

At +360d, reconstruct cumulative indigenous service coverage separately for
force generation, logistics, and command:

```text
coverage = cumulative indigenous service / cumulative service demand
```

when cumulative demand is positive.  Report both raw coverage and coverage
capped at 1.0.  The paired change in capped coverage is the scale-free mechanism
measure: negative values mean continued assistance left indigenous supply
covering a smaller share of accumulated demand than under withdrawal.

For Module C, compare substitution, development, and hybrid treatments only at
matched target × severity × intensity.  Repeated seed indices are used as
common-random-number matched contrasts, but are **not** described as exact
cloned counterfactuals across treatment cells.

Primary mode contrasts:

- development minus substitution;
- hybrid minus substitution.

For each contrast report matched-seed effects on:

- +30d capability;
- +360d indigenous autonomy;
- +360d relevant indigenous cumulative service;
- +360d relevant cumulative demand;
- +360d capped indigenous coverage;
- +360d donor cost.

Use deterministic bootstrap 95% CIs over the 12 matched seed indices.

## 4. Bottleneck migration

The baseline bottleneck is the **observed pre-withdrawal structural bottleneck**
recorded in the primary rows.  The post-split bottleneck is the evolving
trajectory `interval_formal_bottleneck`.

A persistent migration remains the preregistered event: the first post-split
checkpoint at which a new bottleneck differs from baseline for two consecutive
checkpoints.

For treated worlds, classify support as observed-bottleneck-matched when the
preregistered support target equals the observed baseline bottleneck.  Report:

- persistent-migration probability and Wilson CI;
- time to persistent migration among migrating worlds;
- bottleneck-path entropy;
- +30d capability and +360d autonomy effects;
- results by intensity and starting structure.

Because the formal bottleneck is based on the minimum service ratio, report the
sign and magnitude of +360d effects under the preregistered arithmetic,
geometric, and harmonic smooth feasibility aggregators as robustness checks.
Do not claim that a result is production-function-general if its substantive
direction exists only under the hard-minimum measure.

## 5. Heavy tails and uncertainty

Stage 3 showed material heavy-tail behavior.  Therefore:

- means are never reported without medians;
- cell summaries include 10th/90th percentiles;
- directional seed fractions are reported alongside continuous effects;
- bootstrap CIs are deterministic from a frozen base seed;
- no cell is discarded because it is an outlier;
- no post hoc winsorization is permitted in the primary paper analysis.

Base bootstrap seed: `20260920`.

Default bootstrap resamples: `10000`.

## 6. Evidentiary boundaries

The Stage-4 results identify mechanisms and conditional relationships **inside
the synthetic Pineland model**.  The paper may argue that these mechanisms are
theoretically general, but it must not present the estimated numerical phase
boundary as an empirical threshold for a historical partner force without
separate external measurement/calibration.

The production outcomes are fixed by the original production commit; the
postprocessing repair is separately identified; and this paper-level plan is a
third provenance layer.  Any additional outcome-driven exploratory analysis
must be labeled exploratory rather than silently folded into this plan.

