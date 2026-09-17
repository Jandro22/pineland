# Research-v1 recovery certification snapshot - 2026-09-17

**Status:** content-addressed synthetic development evidence; not a preregistered
confirmatory batch and not empirical latent-state validation.

This note records the 8-world x 32-particle repeated dynamic recovery block run
under execution fingerprint
`73213a0f5842b9359a255eef472648724dbb0bff1c7c3916574e01e00fd2d664`.
All runs use 14 simulated days and a seven-day observation interval. Historical
case data are not loaded.

## Main results

| Condition | Coordinate MSE gain vs prior | Measurement-estimand gain | Coordinate world wins | Coordinate 90% coverage |
| --- | ---: | ---: | ---: | ---: |
| Mixed proxy, clean | +10.39% | +10.92% | 8/8 | 92.4% |
| Direct oracle | +12.30% | +12.30% | 8/8 | 91.8% |
| 10% false reports, strict likelihood | -5.00% | -1.34% | 5/8 | 92.1% |
| 10% false reports, contamination-aware likelihood | +2.42% | +4.70% | 6/8 | 92.4% |

Positive gain means lower trajectory MSE than the matched no-assimilation prior.
The clean mixed-proxy and direct-oracle paired MSE-difference diagnostic intervals
are entirely on the improvement side. Both 10%-false-report intervals cross zero.
These are development diagnostics, not preregistered confidence intervals.

## Measurement-space result

The clean mixed-proxy measurement-aligned estimands improve pooled MSE by about
10.92%, with all 8/8 worlds improving. All eight declared report-channel
estimands have positive average gain in this batch:

| Estimand | MSE gain vs matched prior | World wins | 90% coverage |
| --- | ---: | ---: | ---: |
| administrative function | +22.18% | 8/8 | 87.1% |
| organizational presence | +13.36% | 8/8 | 90.8% |
| security presence | +10.15% | 5/8 | 87.1% |
| insurgent physical anchor | +9.54% | 7/8 | 92.3% |
| government administrative anchor | +8.74% | 7/8 | 83.8% |
| taxation/coercion | +3.32% | 4/8 | 94.9% |
| logistics readiness | +3.19% | 6/8 | 96.0% |
| public alignment | +1.22% | 6/8 | 87.1% |

This is important because the 18-coordinate mixed-proxy snapshot design has
rank 8 and nullity 10. Recovery of the measured latent combinations is therefore
a different scientific claim from uniquely decomposing them into 18 named
coordinates.

## Coordinate-level heterogeneity

Aggregate gain does not license every latent coordinate. In the clean mixed-proxy
batch, examples include:

- government administrative: +26.79% MSE gain, 8/8 worlds, 83.5% coverage;
- insurgent fighter capacity: +16.82%, 8/8 worlds, 96.0% coverage;
- insurgent embeddedness: +14.23%, 8/8 worlds, 92.3% coverage;
- insurgent physical: +11.07%, 7/8 worlds, 92.6% coverage;
- government physical: +4.67%, 6/8 worlds, 87.1% coverage.

The six coordinates with no mixed-proxy snapshot loading show zero incremental
information by construction. Several model-assisted coordinates improve, but
those gains cannot be relabeled as direct observation identification. Point-error
improvement, interval calibration, and across-world stability are separate axes.

## False-report failure and robust likelihood

Under 10% fabricated reports, the strict clean-data likelihood changes average
coordinate information gain from +10.39% to -5.00%. The fixed 10% contamination
mixture changes the contaminated condition to +2.42%. In measurement space the
corresponding values are -1.34% and +4.70%.

The robust likelihood therefore reverses the average direction of the failure and
substantially preserves particle support, but the eight-world paired diagnostic
interval still crosses zero. The appropriate claim is **promising robustness
mechanism**, not established rescue.

## Oracle comparison

The direct-oracle profile gives each latent coordinate its own synthetic
measurement channel and improves aggregate MSE by about 12.30% with 8/8 worlds
improving. Previously invisible mixed-proxy coordinates become positively
recoverable under direct measurement. This supports an observation-design
interpretation of mixed-proxy limitations.

The oracle and mixed-proxy profiles are different measurement contracts. Their
percentage gains should not be treated as a ranking or as a literal percentage
of oracle information recovered.

## Direct-report reconstruction baseline

A follow-on nominal run also scores the estimator against a deliberately strong
fixed-lag direct-report baseline. For each channel-estimand/locality/state-time
point, that baseline uses the raw delayed report describing the state when one
exists and otherwise falls back to the matched prior mean. It therefore shares
the retrospective benchmark's benefit of assigning delayed reports back to the
state they describe; it is stronger than a naive real-time last-observation
baseline.

Across the same eight nominal mixed-proxy worlds:

- direct-report-or-prior MSE: **0.00923135**;
- dynamic posterior estimand MSE: **0.00491589**;
- pooled MSE reduction versus the direct-report baseline: **46.75%**;
- posterior MSE was lower in **8/8 worlds**;
- per-world relative reduction ranged from about **25.4% to 64.1%**;
- median per-world relative reduction was about **45.8%**.

Raw reports directly covered about **38.5%** of scored
estimand/locality/state-time points; the matched prior supplied the remainder.
The comparison therefore supports model-assisted temporal/cross-state
reconstruction value beyond simply copying the available report stream. It does
not alter the rank deficiency of the observation operator or convert
model-assisted coordinates into observation-identified quantities.


## Simple raw-report baseline

A second content-addressed run under execution fingerprint
`a1f8f57bffe1886fadd05120e3bb01d2278615a461dce5f18c6c3a13cabfd621`
adds a deliberately simple measurement-space comparator: for each
channel/locality/state-time, use the raw report value if a report exists and
otherwise retain the matched prior mean. This is a fair fixed-lag baseline
because the Pineland reconstruction also assigns delayed reports back to the
state time they describe.

Under the nominal mixed-proxy condition, the measurement-space posterior MSE is
`0.004916`, compared with `0.009231` for the raw-report/prior baseline: a
**46.75% MSE reduction**. Pineland beats the simple baseline in **8/8 worlds**.
The paired posterior-minus-baseline MSE diagnostic interval is approximately
`[-0.005289, -0.003342]`, entirely on the improvement side. Raw reports directly
cover about 38.5% of the scored channel/locality/time points, with the prior
providing the fallback elsewhere.

A matched control removes geolocation error entirely and tells both the data
generator and estimator that report locations are exact. Pineland still reduces
MSE by **45.60%** relative to the raw-report/prior baseline in **8/8 worlds**,
with paired diagnostic interval approximately `[-0.004586, -0.003096]`. Its MSE
improvement versus the matched no-assimilation prior rises to about **16.95%**.
The raw-report advantage therefore cannot be explained mainly by Pineland
correcting misplaced reports; substantial value remains from denoising, dynamic
prior integration, and interpolation across missing reports.

A near-noiseless control (`0.01x` the declared channel measurement SD, with exact
geolocation) provides the opposite falsification. The raw-report/prior baseline
MSE falls to `0.003512`, while Pineland's measurement-space posterior MSE is
`0.003697`: Pineland is about **5.24% worse** than simply taking the nearly exact
measurement, and it wins 0/8 worlds. The paired diagnostic interval crosses
zero, while Pineland still improves about 33.0% over the no-assimilation prior.
This is the expected qualitative behavior of a sensible state estimator: noisy
measurements benefit from model-based shrinkage, whereas an almost exact
measurement should be trusted directly. The empirical break-even noise level is
now a development target rather than an assumed property.

## Claim firewall

Use [`paper1-claim-matrix.md`](paper1-claim-matrix.md) to classify results as:

- `OBSERVATION_IDENTIFIED`
- `MEASUREMENT_ESTIMAND`
- `MODEL_ASSISTED`
- `HISTORICAL_OBSERVABLE_ONLY`

The synthetic benchmark can score latent-state recovery because it owns the
ground truth. Afghanistan and Nepal cannot supply known historical latent truth;
they can only confront held-out observable evidence under separately frozen
contracts.
