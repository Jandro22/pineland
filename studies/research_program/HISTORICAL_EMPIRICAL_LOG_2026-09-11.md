# Historical Empirical Transport Log - 2026-09-11

This log begins the post-synthetic empirical phase. The frozen synthetic theory
is not retuned here. Historical work is divided into (1) direct observable
mechanism confrontations, (2) measurement-operator identification, and only
later (3) latent-state historical scoring if an operator is actually identified.

## Empirical firewall inherited from the synthetic phase

- `reduced_theory_specification_v2.json` remains frozen.
- Historical outcomes may test observable implications but may not change
  Pineland parameters/equations/state dimensions.
- Existing `measurement_operator_identifiability_audit_v1.json` remains in
  force: source detection, false-positive rates, spatial error, temporal error,
  and source dependence are not quantitatively identified.
- Therefore the initial historical stage uses direct observables and ordinal/
  directional source semantics rather than pretending to observe latent states.
- Nigeria 2014 remains sealed.

## Exposure disclosure before first historical propagation test

Before freezing `historical_nonlocal_reproduction_contract_v1.json`, the
following were inspected for source engineering only: event-table row counts,
principal actor-label frequency tables, geography centroid completeness, and
source-coverage/status counts. Quiet-period onset sets, spatial pressure scores,
and predictive AUCs were not inspected.

## Historical confrontation 1 - event-only nonlocal propagation analogue

- Contract SHA-256:
  `B45BE4E436FA978EFC25373FBF1709D7682887F8D5A69466DF072655C7328C96`.
- Primary design: after 12 months of local principal-actor inactivity, compare
  a three-month nonlocal event-pressure kernel against distance to the nearest
  recently active unit for predicting activity during the next 90 days.
- Frozen cross-case gate FAILED.
- 90d AUC gains (dynamic pressure minus nearest distance):
  - Afghanistan Taliban: `+0.0115`;
  - Nepal CPN-M: `-0.1260`;
  - Colombia FARC: `+0.0063`;
  - Iraq IS: `+0.0128`;
  - Vietnam opposing-force aggregate: no positive onsets in the frozen quiet
    risk set, therefore no scored AUC.
- Cross-case median gain: `+0.0089`, below the preregistered `+0.02` gate.
- Interpretation: event pressure is not an adequate historical stand-in for
  synthetic recruitment hazard. Nepal is the strongest counterexample.
- Permanent consequence: violence intensity may remain an outcome/process
  observable, but it is not licensed as an estimate of rooted membership or
  recruitment propensity.

## Next frozen confrontation - Vietnam independent enemy presence

- Before result computation, froze
  `vietnam_hes_enemy_presence_holdout_contract_v1.json`.
- Contract SHA-256:
  `B7775912D03FCF4AF61110E2A9892C8594D04143DF203EE8D1DF3D9DD8A324B6`.
- Predictor is independent HES enemy-military-presence distribution, using only
  ordinal category information; outcome is future enemy-initiated ground-event
  activity from the separate MACV/NARA cleaned incident stream.
- Training anchors: 1969-07 through 1970-12. Heldout anchors: calendar 1971.
- No HES score is called Pineland `M_star` or territorial control.

## Historical confrontation 2 - independent HES presence versus future incidents

- Frozen contract SHA-256:
  `B7775912D03FCF4AF61110E2A9892C8594D04143DF203EE8D1DF3D9DD8A324B6`.
- Result: `INDEPENDENT_PRESENCE_SIGNAL_NOT_CONFIRMED_ON_1971_HOLDOUT`.
- Baseline heldout RMSE/Spearman: `0.6287 / 0.9124`.
- Enhanced (adds HES enemy-presence burden) RMSE/Spearman:
  `0.6371 / 0.9109`.
- Relative RMSE change: `-1.33%`; Spearman gain `-0.0015`; frozen training
  coefficient on presence burden was negative. All three promotion gates failed.
- Important descriptive result retained: heldout province-months in the top HES
  enemy-presence-burden quartile had `5.67x` the mean next-3-month enemy event
  count of the bottom quartile. Presence is therefore strongly associated with
  the conflict state but redundant with recent incident history for the tested
  province-level forecasting task.
- Permanent consequence: do not equate construct validity with forecast
  increment. The next test moves to hamlet-level **state transitions** inside
  HES rather than asking a province-level state marker to beat a very strong
  autoregressive incident baseline.

## Historical confrontation 3 - political penetration -> military deterioration

- Frozen hamlet-level HES transition test also failed its strict incremental-
  prediction gate, but produced a strong directional state relationship.
- Heldout 1971 sample: `45,936` eligible hamlet-month anchors.
- Baseline vs enhanced AUC: `0.78949 -> 0.79127` (`+0.00178`).
- Baseline vs enhanced log loss: `0.22194 -> 0.22152` (`+0.00042` gain).
- Training coefficient on prior political penetration: `+0.631`.
- Raw 90-day military-deterioration risk: `6.68%` with zero high-political-
  presence months versus `21.54%` when >=2 of 3 prior months were high; risk
  ratio `3.23`. Fully persistent political exposure had `31.23%` transition
  risk.
- Interpretation: political penetration is a meaningful state marker, but most
  of its predictive information is already contained in current military-state
  depth and geography. Preserve state-measurement interpretation; do not claim
  incremental forecasting breakthrough.

## Direct Vietnam archival linkage breakthrough - TFES, NAPE, VNUS

- Direct NAPE parser certified all `31,473` documented 87-byte records and
  produced a compact police personnel/deployment table.
- Direct TFES parser decoded IBM variable-blocked framing and recovered exactly
  the documented `269,078` logical records: 259,516 608-byte unit records,
  8,437 1024-byte district records, 1,100 1059-byte extended unit records, and
  25 monthly control records. The control sequence independently reconstructs
  the surviving TFES months from 1970-04 through 1972-07 with the documented
  gaps.
- TFES yields unit-level ordered quality evaluations, training dates, assigned
  and present-for-duty strength, and equipment/logistics fields. About `5.43%`
  of active positive-strength records report present strength above assigned;
  these are preserved as archival anomalies, never silently clipped.
- Direct VNUS contains exactly `103,624` documented 80-character records. Five
  malformed source-date rows are preserved and excluded from date-linked tests.
- Identity-only crosswalk audit shows TFES `district + unit type + unit_series`
  is the VNUS unit identity: same-month match rate `98.86%`, versus only `3.20%`
  for the next-best unit-number mapping. Mapping selection used identifiers and
  months only, before any quality/performance relationship was inspected.

