# Afghanistan 2004-2021 historical benchmark

This is the primary large-case benchmark for Pineland COIN-SIM. It covers the mature Islamic Republic / coalition counterinsurgency period from 2004-01-01 through 2021-08-15. Nepal remains a smaller falsification and development case; Afghanistan is intentionally not tuned to inherit Nepal's historical shape.

## Frozen research design

The primary violence estimand is **province-week**, not district-week. Afghanistan's district system changed repeatedly over the war, so province-week is the stable main scoring surface. District-resolved event measures are retained as secondary diagnostics only when the administrative crosswalk is high-confidence.

The temporal boundary is **2015-01-01**. The geographic holdout is selected without outcome data by hashing the eight OCHA region codes with the literal namespace `afghanistan-geographic-holdout-v1:` and taking the first two lexicographically by SHA-256 digest. This selects `WR` and `CR`; the selection rule, not the resulting conflict history, is the justification.

The resulting four-way split is training before 2015 outside held-out regions; geographic validation before 2015 inside them; temporal validation from 2015 onward outside them; and strict joint holdout from 2015 onward inside them. No fit result may change this split.

## Physical geography

The authoritative analysis geography is the OCHA/AGCHO/NSIA Common Operational Dataset lineage, represented as a harmonized grid rather than a claim that district boundaries were legally unchanged throughout 2004-2021.

Initial physical hierarchy: 8 OCHA humanitarian regions, 34 provinces, 401 harmonized districts, 401 named administrative-center localities supplied by the COD package, and generated tactical microzones.

GADM is retained only as a cross-check because its current Afghanistan level-2 file contains 328 units and is therefore not used as the benchmark district registry.

## Population

Initial population is built from the WorldPop 2004 1-km UN-adjusted population surface and zonally aggregated into the 401 harmonized district polygons. The archived 2016/17 CSO/OCHA district estimates are a cross-check, not the 2004 initialization source.

## Violence and actor strata

The frozen event source is UCDP GED 26.1. The event panel keeps Taliban, Islamic State, Hizb-i Islami, government one-sided violence, and non-state conflict in explicit separate strata. The primary Taliban benchmark never silently re-labels all anti-government violence as Taliban violence.

## Control and presence

Violence is not a territorial-control proxy. The October 2017 SIGAR / Resolute
Support district assessment is an independent target. The completed frozen-v1
run compared it to the old equal-weight geometric effective-control scalar and
failed; that failure is retained. A prospective, unfitted ordinal operator now
maps both actors' seven-dimensional latent vectors to SIGAR category
probabilities. It cannot rescore v1 runs because those runs discarded the
component vectors at the target snapshot.

## External intervention

The coalition intervention, Afghan state, Pakistan border/sanctuary environment, drawdown, and withdrawal are substantive mechanisms rather than noise. Observed major external-policy phase changes may be conditioned as exogenous historical inputs, but tactical violence outcomes may not be used as forcing variables.

## Calibration boundary

Calibration is prohibited until the untuned Afghanistan formulation passes structural and stock-accounting tests, produces nondegenerate contact/control dynamics, is scored on the frozen train and holdout surfaces, is compared with simpler training-only competitors, has independent control/presence validation, and has resolution/recording sensitivities documented.

Any structural repair discovered during Afghanistan construction must be general, tested outside the case where possible, and provenance-recorded before new fit results are inspected.

## Compute-efficient execution order

Long horizons are promoted only after cheaper gates earn them:

```powershell
$env:PYTHONPATH = "src"
python studies/afghanistan_2004_2021/scripts/run_transfer_test.py --stage init
python studies/afghanistan_2004_2021/scripts/run_transfer_test.py --stage smoke
python studies/afghanistan_2004_2021/scripts/run_transfer_test.py --stage year
python studies/afghanistan_2004_2021/scripts/evaluate_transfer_gate.py
python studies/afghanistan_2004_2021/scripts/run_cloud_full.py --workers 3
python studies/afghanistan_2004_2021/scripts/run_competitors.py
python studies/afghanistan_2004_2021/scripts/analyze_transfer_results.py
```

For compute-efficient staged promotion, the same runner accepts a bounded
horizon and separate output directory, for example
`--horizon-days 366 --output-dir runs/transfer_test_v1/year_ensemble`. This is
the preferred next gate before committing to the multi-year full horizon.
Analyze it with matching paths:
`analyze_transfer_results.py --runs-dir runs/transfer_test_v1/year_ensemble
--output-dir results/transfer_test_v1/year_ensemble`.
Then apply the promotion rule with
`evaluate_transfer_results.py`; zero-contact or no-control runs are held for
diagnosis rather than silently promoted.
`diagnose_transfer_opportunity.py` records the expected-contact and zero-event
probability for each initial-strength variant without using those diagnostics
to tune the case.

The one-year gate requires integrity plus actual opposing-force overlap and a
positive contact-hazard draw. A realized engagement is an outcome, not a
promotion prerequisite when the opportunity sample is small. The full runner
writes each initial-strength trajectory atomically and resumes around existing
files.

Long-run execution uses bounded observation retention, deterministic
world-local route caches, one active-shipment index per tick, and a maintained
in-transit stock total. These are execution optimizations excluded from
scientific-state hashes; reproducibility tests require unchanged trajectories.
The three full-horizon initial-strength variants run in separate processes to
minimize wall-clock time without parallelizing the event scheduler itself.

Statistical competitors are fitted on training rows only. Holdout outcomes do
not update the self-exciting history. The final report compares the untuned
strength-mixture predictions with these competitors and independently scores
the dated SIGAR control snapshot.

## Completed first-transfer decision

The three 5,036-day trajectories completed with 24/5, 81/20, and 16/7
latent/recorded contacts for initial Taliban strengths 5,000, 7,500, and
10,000. The frozen scalar control comparison produced MAE 0.226–0.227 and
Pearson correlations from -0.119 to -0.023. The transfer decision is
`HOLD_TRANSFER_AND_DIAGNOSE`; no parameter was fitted and no holdout was
refit. A derived numerical reassessment passes the supply ledgers using
absolute-plus-relative tolerance while preserving every trajectory and score.

The spatial diagnostic shows historical one-week province persistence of
0.639 and neighbor activation of 0.281, versus simulated persistence of
0–0.056 and zero neighbor activation. The implemented control-competitor
runner remains blocked until harmonized pre-target longitudinal control
observations exist; the October 2017 observed mean is not used as a predictor.
