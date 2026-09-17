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

Synthetic report generation uses deterministic per-unit, per-channel,
per-purpose random substreams. Reporting selection, measurement noise, false-
report status/value, geolocation, geolocation target, and delay therefore do
not share one sequential RNG stream. This is essential for matched degradation
sweeps: changing the geolocation-error rate cannot silently change a retained
report's measurement noise or delay, and lowering reporting probability yields
a true subset of the denser condition with common report realizations held
fixed. Earlier September 17 degradation contrasts generated with the sequential
observation RNG are retained as development history but are superseded for
failure-envelope claims.

Spatially fallible reports are scored with a finite mixture over the reported
locality and its neighbors when the estimator admits geolocation error. A
misspecification experiment can instead force the estimator to pretend that
reported coordinates are exact.

The likelihood can also include an explicit state-independent contamination
component for false reports. The robust observation model mixes the usual
state-dependent Gaussian likelihood with a broad Uniform-plus-Gaussian report
component. This lets an observation be treated as possible junk rather than
forcing some particle state to explain every extreme report.

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

The observation-design diagnostic also reports an explicit null-space basis.
For the current eight-channel mixed-proxy design, the 18-dimensional snapshot
matrix has rank 8 and nullity 10. Six directions are completely unobserved:
government formal, legal, fiscal, and expected control plus insurgent formal
and legal control. Public-alignment reporting identifies only one linear
combination of government social, insurgent social, and insurgent expected
control, leaving two tradeoff directions. The taxation, organizational-
presence, and logistics channels identify only three combinations of five
fiscal/foothold/embeddedness/fighter/supply variables, leaving two additional
tradeoffs. Conversely, the direct anchors plus mixed proxies make government
and insurgent physical and administrative control structurally identifiable in
the declared one-snapshot measurement system. This is structural measurement
identifiability, not proof of practical finite-sample recoverability.

Rank-nullity also puts a hard lower bound on any attempt to identify the full
18-coordinate snapshot state from this reporting menu. The current design has
rank 8, so no inference algorithm can recover ten missing independent
measurement dimensions from those eight scalar equations without importing
restrictions from dynamics or priors. Achieving full snapshot rank would
require at least ten additional independent scalar measurement equations. The
Research-v1 objective is therefore not to add synthetic channels until every
coordinate becomes identifiable; it is to state clearly which coordinate or
linear-combination claims the actual observation contract licenses.

### Measurement-aligned estimands

Exactly four named coordinates are individually identifiable from the current
one-snapshot mixed-proxy design without extra prior/dynamic restrictions:
government physical control, government administrative control, insurgent
physical control, and insurgent administrative control. Other coordinates may
still be estimable in the dynamic model, but any such estimate necessarily
combines observation information with model-imposed restrictions and must be
labeled accordingly.

Research-v1 now evaluates the observable subspace directly as a companion to
coordinate-level recovery. For every declared report channel, the benchmark
projects each coherent Pineland world into the channel's latent expected value
(`estimand::<channel>`). A channel-aligned importance reconstruction then uses
only reports from that channel and declared spatial neighborhood to estimate
that scalar. This asks whether the information that the measurement design
actually contains is recoverable without pretending that a rank-deficient
decomposition into underlying coordinates is unique.

These measurement-aligned quantities do not replace substantive latent
variables. They separate whether the estimator can recover the latent
combination actually measured by a reporting stream from whether the collection
design contains enough independent information to split that combination into
the substantive coordinates a researcher wants to discuss. Strong recovery in
measurement space combined with weak coordinate recovery is therefore evidence
of an observation-design/identification limit rather than a generic estimator
failure.

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
python studies/research_program/scripts/run_research_v1_repeated_dynamic_recovery.py
```

The repeated-snapshot benchmark treats the synthetic world as the scientific
unit and measures paired prior-versus-posterior error across multiple known
truths. A single world's RMSE change is therefore a pilot diagnostic, not a
general recoverability claim.

The repeated-dynamic benchmark carries that same paired design through live
Pineland transitions. It regenerates the synthetic country for every world,
propagates a matched no-assimilation ensemble through the same observation
boundaries, and scores trajectory reconstruction against known latent truth.
Its default estimator is radius-zero component localization. A locality-only
run with the same seeds is the principal estimator ablation.

### State-component localization

The first localized estimator weighted every latent coordinate in a locality
with every report from that locality. Repeated prior-width experiments exposed
a second dimensionality problem: finite ensembles create incidental
cross-variable correlations, so evidence about one construct can move an
unrelated construct even when the observation channel has no loading on it.

`component_localized_importance_reconstruction` therefore adds a second,
declared localization boundary. Each locality-variable marginal uses only
channels whose measurement equation has a non-zero loading on that variable.
Particles remain complete coherent Pineland worlds; only the weights used to
summarize each marginal differ. Mixed-proxy channels can still inform multiple
coordinates, so their intended ambiguity is preserved rather than artificially
diagonalized.

In the September 17 development pilot, this removed the broad-prior failure of
locality-only weighting. Across eight independently generated truths with 64
particles per world and truth SD 0.10, component localization produced direct-
oracle MSE information gains of about 8.3%, 7.8%, and 10.2% at prior SD 0.10,
0.20, and 0.30 respectively. The mixed-proxy design produced gains of about
9.6%, 3.4%, and 1.1% over the same prior widths. These are development results,
not confirmatory thresholds.

The dynamic benchmark exposes this mode with `--state-localization component`.
The repository development reproduction profile uses it explicitly; locality-
only weighting remains available as an ablation and failure-mode comparison.

The first repeated live-dynamics pilot used four independently generated worlds,
16 particles per world, 14 days, and a seven-day observation interval. That
pilot initially reported a 21.3% mixed-proxy MSE gain. Subsequent audit found
that the observation generator used one sequential RNG stream, so changing a
degradation parameter could also change unrelated later noise/delay draws. The
21.3% value is therefore retained in provenance but superseded for comparative
claims.

After introducing purpose-separated paired observation substreams, the matched
nominal rerun gives an 11.3% mixed-proxy trajectory-MSE information gain, with
all four development worlds improving and empirical 90% coverage of about
90.7%. The paired locality-only ablation gives a similar/slightly larger point
gain (12.1%) but only about 87.4% coverage, a 6.3% confidently-wrong rate, and
mean effective support of about 71.8% versus 96.6% for component localization.
Component localization therefore remains the development default because it is
substantially better calibrated and less particle-degenerate, not because it
maximizes this four-world point estimate.

### Variable-level recoverability

The paired nominal development run also makes clear that aggregate error hides
strong heterogeneity. Relative to the matched dynamically propagated prior,
government administrative control improves by about 26.7%, insurgent fighter
capacity by 22.3%, and insurgent embeddedness by 15.0%. Insurgent fiscal,
physical, administrative, expected, and supply-capacity targets show only small
positive gains. The six completely unobserved formal/legal/fiscal/expected
directions identified by the measurement null space show exactly zero
incremental information, while insurgent foothold and social control are
slightly worse than the prior in this small pilot. Paper-level claims must
therefore be target-specific rather than treating "hidden conflict state" as a
single recoverable object.

A paired full-rank direct-oracle diagnostic supports the interpretation that
these zeros belong primarily to the mixed measurement design rather than an
intrinsic inability of the localized estimator to update those coordinates.
Across the same four-world development structure, the direct-oracle profile
reduces aggregate MSE by about 9.7% and improves all four worlds. Variables that
receive no mixed-proxy loading become positively recoverable when directly
measured: government legal about +19.2%, government fiscal +6.0%, government
formal +5.6%, insurgent formal +4.4%, government expected +2.2%, and insurgent
legal +1.3%. The mixed-proxy and direct-oracle profiles have different channel
contracts and are not a performance ranking; the oracle exists to separate
measurement identification from estimator failure.

The paired reporting-density sweep is correspondingly smoother than the old
single-stream assay: mixed-proxy MSE information gain is about 8.0% at 25% of
nominal reporting, 8.0% at 35%, 10.1% at 50%, and 11.3% at nominal reporting in
the current four-world development batch. These values do not license a sharp
reporting threshold; larger frozen batches are required before estimating a
failure boundary.

### False-report robustness

False-report contamination is the clearest adversarial failure found so far.
With the paired generator and a strict Gaussian observation likelihood, the
four-world development gain falls from +11.3% with clean reports to +6.9% at
5% false reports, -2.0% at 10%, and -4.3% at 20%. A fixed 10% contamination-
mixture likelihood costs little on clean data (+10.4%) while producing +8.9%,
+5.7%, and +4.6% gains at 5%, 10%, and 20% false-report rates respectively. At
20% contamination, a correctly specified 20% robust mixture yields +5.8%.
These are development results, but they motivate a robust-likelihood estimator
as a predeclared Paper-1 ablation rather than an after-the-fact rescue.

At 10% false reports the strict estimator particularly damages insurgent
physical state, embeddedness, and fighter capacity. The fixed 10% robust
mixture changes their information gains from about -18.0%, -11.8%, and -5.0%
to +2.4%, +5.2%, and +9.6% respectively. Government administrative recovery is
much less sensitive to contamination, suggesting that vulnerability depends on
the report/latent measurement block rather than being a uniform property of the
estimator.

The four-world values above remain early development diagnostics. A subsequent
content-addressed development replication on execution fingerprint
`73213a0f5842b9359a255eef472648724dbb0bff1c7c3916574e01e00fd2d664`
used eight worlds and 32 particles per world. Under nominal mixed-proxy
observation, coordinate-level MSE improves by about 10.39% with 8/8 worlds
improving, 92.4% empirical coverage for nominal 90% intervals, and a paired
normal diagnostic interval for posterior-minus-prior MSE entirely below zero.
The measurement-aligned estimand space improves by about 10.92%, also with 8/8
worlds improving and its paired diagnostic interval entirely below zero. The
direct-oracle diagnostic improves by about 12.30%, again 8/8 worlds, supporting
the interpretation that mixed-proxy coordinate limitations are substantially a
measurement-design issue.

At 10% fabricated reports, the same 8x32 design gives -5.00% average coordinate
information gain under the strict Gaussian likelihood (5/8 worlds improve) and
+2.42% under the fixed 10% contamination mixture (6/8 improve). Measurement-space
gains are -1.34% and +4.70% respectively. The robust mixture therefore still
reverses the average direction of the contamination failure, but the paired
diagnostic intervals cross zero at eight worlds. It remains a promising
robustness mechanism rather than an established rescue result.

These eight-world runs are content-addressed development evidence, not a
confirmatory batch. The final world count, particle count, severity grid, and
promotion criteria must be frozen independently before any paper-level
failure-envelope claim is made.

## Executable provenance guard

Research-v1 long-running recovery scripts content-address the executable
scientific bundle before simulation begins. The fingerprint includes the live
Pineland model source plus the benchmark runner code (and, for the repeated
dynamic runner, the synthetic-recovery runner it imports). The bundle is hashed
again after the experiment. If executable scientific content changed while the
run was in flight, the runner raises an error and refuses to certify/write that
run as admissible evidence. This is deliberately content-based rather than
commit-based so unrelated Git history movement does not invalidate a stable
experiment, while live scientific edits do.

## Repository and data boundary

The private GitHub repository is the canonical code/protocol/provenance remote.
Large generated runs, processed historical panels, sealed holdouts, and local
research result bundles remain outside Git and are covered by `.gitignore`.
GitHub CI therefore runs a portable regression suite plus the Research-v1 core
tests. Data-bound historical certification remains a local-workspace test and
must not be inferred from a green clean-clone CI run.

## Claim firewall

The operational claim taxonomy is maintained in [`paper1-claim-matrix.md`](paper1-claim-matrix.md).

The synthetic benchmark may support statements such as "under this declared
observation and transition process, physical control is recoverable with this
error and coverage." It cannot support "Pineland reconstructed the true Taliban
strength in a historical district," because that historical latent truth is
not observed. Historical cases answer predictive/transfer questions against
observable held-out evidence under a separately frozen contract.
