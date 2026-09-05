# Nepal 2001-2006 historical benchmark

This study tests Pineland against recorded evidence from the Nepal Maoist insurgency. It is a benchmarking and falsification exercise, not a historical reconstruction and not a claim that any single source is ground truth.

## Frozen historical estimand

The historical scoring unit remains the 75-district week from 2001-11-26 through 2006-11-21. The primary violence observable is any two-sided UCDP state-based Government of Nepal versus CPN-M event in a district-week. Historical train, temporal holdout, geographic holdout, and strict joint holdout definitions remain frozen. No split may be changed in response to model fit.

Calibration is currently **not licensed**. Structural repairs described below were made because of construct-validity defects found during untuned falsification. They are not parameter fitting and do not use study-period outcomes to improve fit.

## Preserved legacy formulation

`config/case_environment.json` and the original results trees are retained as scientific provenance. They preserve the earlier 75-locality formulation and its falsification results. Scripts whose module documentation explicitly says `LEGACY provenance diagnostic` intentionally continue to use those inputs.

The earlier residual diagnosis established that the repaired-but-coarse formulation was nondegenerate yet still had the wrong process shape. Those results must not be silently reinterpreted as results from the newer formulation.

## Post structural repair formulation

New trajectories use formulation tag `post_structural_repair_v1` and:

- `config/case_environment_repaired.json`
- 5 historical development regions as hierarchy metadata
- 14 historical zones as hierarchy metadata
- 75 historical districts as the validation containers
- 300 named settlement/catchment localities, four per district
- district headquarters identified explicitly rather than inferred from list order
- generated tactical microzones below each settlement

The 300 settlement anchors are selected without study-period violence outcomes. Each district contains its declared historical headquarters plus three GeoNames populated-place anchors selected by deterministic farthest-point geographic coverage. GeoNames population is excluded from model weighting. The district's 2001 census population is divided neutrally among its four catchments.

Empirical population generation is stratified: when `agent_count >= locality_count`, every empirical locality receives representative civilians and the sum of person weights in each locality exactly equals that locality's population. This avoids empty localities and preserves locality population rather than relying on multinomial expectation.

## Structural repairs

The current formulation includes the following general repairs:

1. Recruitment is local and access-constrained. Entry into an existing armed organization requires local formation presence, local mobilized membership, or social-network exposure. Mobilized fighter-equivalent manpower is then assigned to an effective local formation, a local manpower pool, or a newly created local formation. It is never assigned to the first formation in an organization by list order. Endogenous proto-organization onset remains the separate route for genuinely new local armed organization formation.
2. Weighted representatives recruit and exit fractionally through bounded subcohorts rather than switching their entire represented population at once.
3. Formation growth is bounded by the declared target token size. Excess local manpower creates additional local formations rather than a mega-formation.
4. Explicitly combat-ineffective formations are excluded from contact scheduling and combat resolution.
5. Formation supply carrying capacity can contract after manpower losses only without destroying existing materiel. Existing overstock remains conserved until consumed or moved.
6. Initial insurgent force dispersion expands geographically from the declared pre-period origin. Equal administrative-capacity values can no longer fall back to locality identifier order.
7. Government formations, police posts, and state logistics hubs use explicit district-headquarters roles in schema-v2 empirical geography.
8. Region, zone, district, settlement, and microzone identities are kept separate. Historical district-week aggregation therefore remains unchanged while physical dynamics operate at finer resolution.

None of these repairs changes `contact_rate` or tunes an empirical event-frequency parameter to Nepal.

## Reproduction

From the repository root:

```powershell
python studies/nepal_2001_2006/scripts/acquire_ucdp.py
python studies/nepal_2001_2006/scripts/build_panel.py
python studies/nepal_2001_2006/scripts/acquire_geography.py
python studies/nepal_2001_2006/scripts/build_geography.py
python studies/nepal_2001_2006/scripts/acquire_census.py
python studies/nepal_2001_2006/scripts/build_population.py
python studies/nepal_2001_2006/scripts/build_case_environment.py
python studies/nepal_2001_2006/scripts/acquire_geonames.py
python studies/nepal_2001_2006/scripts/build_settlement_geography.py
python studies/nepal_2001_2006/scripts/compute_historical_targets.py
python studies/nepal_2001_2006/scripts/run_untuned_benchmark.py --workers 4 --agent-count 750
```

Post-repair trajectory outputs are written under `runs/post_structural_repair/` and `results/post_structural_repair/`. They must not overwrite or be merged with legacy falsification outputs.

## Interpretation boundary

Passing software tests and structural smoke tests does not establish empirical validity. After a structural formulation change, historical performance must be rescored from new trajectories. Until the post-repair ensemble and holdout diagnostics are completed, calibration remains prohibited.
