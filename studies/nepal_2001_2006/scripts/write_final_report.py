"""Write the reproducible Nepal benchmark audit and scientific assessment."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def f(value, digits=3):
    return f"{float(value):.{digits}f}"


def main() -> None:
    hist = load(STUDY / "results" / "historical" / "historical_descriptive_statistics.json")
    model = load(STUDY / "results" / "benchmark" / "untuned_benchmark.json")
    uncertainty = pd.DataFrame(model["uncertainty"])
    competitors = pd.read_csv(STUDY / "results" / "competitors" / "competitor_scores.csv")
    crosscheck = load(STUDY / "results" / "historical" / "insec_ucdp_crosscheck.json")
    funnel_path = STUDY / "results" / "contact_forensic" / "contact_funnel_summary.json"
    funnel = load(funnel_path) if funnel_path.exists() else None
    audit_path = STUDY / "results" / "contact_forensic" / "formation_presence_audit.json"
    formation_audit = load(audit_path) if audit_path.exists() else None
    resolution_path = STUDY / "results" / "contact_forensic" / "resolution_ladder.json"
    resolution = load(resolution_path) if resolution_path.exists() else None
    microworld_path = STUDY / "results" / "contact_forensic" / "controlled_contact_microworld.json"
    microworld = load(microworld_path) if microworld_path.exists() else None
    evidence_plan_path = STUDY / "config" / "control_presence_evidence_plan.json"
    evidence_plan = load(evidence_plan_path) if evidence_plan_path.exists() else None
    chain_path = STUDY / "results" / "contact_forensic" / "supply_contact_chain_diagnosis.json"
    supply_chain = load(chain_path) if chain_path.exists() else None
    logistics_validation_path = STUDY / "results" / "contact_forensic" / "independent_logistics_validation.json"
    logistics_validation = load(logistics_validation_path) if logistics_validation_path.exists() else None
    branch_path = STUDY / "results" / "contact_forensic" / "logistics_contact_branch_comparison.json"
    branch_comparison = load(branch_path) if branch_path.exists() else None
    recovery_path = STUDY / "results" / "contact_forensic" / "synthetic_contact_rate_recovery.json"
    recovery = load(recovery_path) if recovery_path.exists() else None
    double_counting_path = STUDY / "results" / "contact_forensic" / "supply_double_counting_audit.json"
    double_counting = load(double_counting_path) if double_counting_path.exists() else None
    repair_comparison_path = STUDY / "results" / "contact_forensic" / "pre_post_repair_comparison.json"
    repair_comparison = load(repair_comparison_path) if repair_comparison_path.exists() else None
    classification_path = STUDY / "results" / "contact_forensic" / "final_classification.json"
    classification = load(classification_path) if classification_path.exists() else None
    source_manifest = load(STUDY / "data" / "manifests" / "sources.json")
    run_manifest = load(STUDY / "runs" / "untuned_realized" / "manifest_agents_750.json")
    ablation_manifest_path = STUDY / "runs" / "ablations_repaired" / "manifest.json"
    ablation_text = "Ablations were not yet completed at report generation."
    if ablation_manifest_path.exists():
        ablation = load(ablation_manifest_path)
        rows = []
        for item in ablation["results"]:
            payload = load(STUDY / "runs" / "ablations_repaired" / item["file"])
            total = sum(part["recorded_contacts"] for part in payload["by_split"].values())
            rows.append(f"| {item['variant']} | {item['seed']} | {total} | {f(payload['summary'].get('mean_insurgent_effective_control', 0), 5)} | {f(payload['summary'].get('mean_government_effective_control', 0), 5)} |")
        ablation_text = "| Variant | Seed | Recorded contacts | Mean insurgent control | Mean government control |\n|---|---:|---:|---:|---:|\n" + "\n".join(rows)
        if ablation.get("failures"):
            ablation_text += "\n\nAblation failures (retained, not hidden): " + "; ".join(
                f"{item.get('variant')} seed {item.get('seed')}: {item.get('error')}"
                for item in ablation["failures"]
            )

    htrain = hist["splits"]["training"]["strata"]["all"]
    htemp = hist["splits"]["temporal_validation"]["strata"]["all"]
    # Mean model values are ensemble means; the UCDP values are the frozen
    # recorded target, not a fitted reference curve.
    rows = []
    for split, label in (("training", "Training"), ("temporal_validation", "Temporal"),
                         ("geographic_validation", "Geographic"), ("strict_joint_holdout", "Joint")):
        u = uncertainty[uncertainty.split == split].iloc[0]
        h_all = hist["splits"][split]["strata"]["two_sided_state_based"]
        h = h_all["incidence_and_concentration"]
        rows.append(f"| {label} | {h_all['event_count']} | {f(h['mean_events_per_district_week'])} | {f(u['recorded_contact_count_mean'])} | {f(u['recorded_contact_count_p05'])}–{f(u['recorded_contact_count_p95'])} | {f(u['population_adjusted_normalized_hhi_mean'])} |")
    comparison = "| Split | UCDP events | UCDP mean / district-week | Pineland recorded contacts (mean) | Pineland 5–95% contacts | Pineland HHI (mean) |\n|---|---:|---:|---:|---:|---:|\n" + "\n".join(rows)
    diagnostic_rows = []
    for split, label in (("training", "Training"), ("temporal_validation", "Temporal"),
                         ("geographic_validation", "Geographic"), ("strict_joint_holdout", "Joint")):
        u = uncertainty[uncertainty.split == split].iloc[0]
        h = hist["splits"][split]["strata"]["two_sided_state_based"]
        incidence = h["incidence_and_concentration"]
        temporal = h["temporal_and_persistence"]
        diagnostic_rows.append(
            f"| {label} | {f(temporal['weekly_fano_including_zeros'])} | {f(u['weekly_fano_including_zeros_mean'])} | "
            f"{f(incidence['district_count_gini'])} | {f(u['district_count_gini_mean'])} | "
            f"{f(incidence['morans_i_events_per_100k'])} | {f(u['morans_i_events_per_100k_mean'])} |"
        )
    diagnostics = ("| Split | UCDP Fano | Pineland Fano | UCDP district Gini | Pineland Gini | "
                   "UCDP Moran’s I | Pineland Moran’s I |\n|---|---:|---:|---:|---:|---:|---:|\n" +
                   "\n".join(diagnostic_rows))
    if funnel:
        funnel_lines = []
        for gate in (
            "opposing_armed_organizations", "opposing_formation_candidate_pairs",
            "same_locality_candidate_pairs", "microzone_eligible_candidate_pairs",
            "proximity_qualified_pairs", "true_target_presence_cases",
            "detected_opponent_sides", "readiness_available_pairs",
            "supply_eligible_pairs", "command_eligible_pairs",
            "engagement_hazard_draws", "engagement_hazard_passes",
            "realized_latent_contacts", "recorded_contacts",
        ):
            total = funnel["overall"]["totals"].get(gate, 0)
            rate = funnel["overall"]["conditional_pass_rates"].get(gate)
            funnel_lines.append(f"| {gate} | {total} | {'—' if rate is None else f(rate)} |")
        funnel_table = ("| Gate | Count | Conditional pass rate |\n|---|---:|---:|\n" +
                        "\n".join(funnel_lines))
        funnel_reasons = ", ".join(
            f"{reason}={count}" for reason, count in funnel["overall"]["failure_reasons"].items()
        )
        micro_text = ""
        if microworld:
            micro_text = (
                "The data-free controlled micro-world used {trials} trials. For contact rates "
                "0.05/0.15/0.30/0.60, observed frequencies were "
                "0.063/0.133/0.281/0.422 versus mean coded hazards "
                "0.049/0.139/0.259/0.451; forced detection, proximity, and readiness failures "
                "were independently reproduced. This validates the gate implementation without "
                "using Nepal data.\n\n"
            ).format(trials=microworld.get("trials", 0))
        funnel_section = f"""## Contact-generation forensic

{funnel_table}

Failure reasons: {funnel_reasons}. The repaired aggregate trace has no universal
zero-count gate (`first_zero_gate` is null). Here `recorded_contacts`
counts recording-layer passes on scheduled contact attempts; it is not a claim
that those attempts were realized engagements. Traces are broken down
by seed, district, week, and selected formation in
`results/contact_forensic/contact_funnel_records.csv` and
`contact_funnel_summary.json`.

{micro_text}The funnel diagnosis is therefore separated from the hazard-unit test. After the
general repair, supply eligibility is no longer a hard contact gate; the remaining
pre-realization losses are primarily readiness/availability and organization survival.
"""
    else:
        funnel_section = "## Contact-generation forensic\n\nFunnel artifacts were not yet present at report generation.\n"

    if formation_audit:
        audit_rows = []
        for item in formation_audit["rows"]:
            audit_rows.append(
                f"| {item['seed']} | {item['phase']} | {item['formation_count']} | "
                f"{item['insurgent_physical_formations']} | {item['government_physical_formations']} | "
                f"{f(item['effective_readiness_mean'], 6)} | {f(item['available_personnel_total'], 2)} | "
                f"{f(item['supply_fraction_mean'], 8)} |"
            )
        formation_section = (
            "## Formation and presence audit\n\n"
            "The audit separates physical formation presence from organization status, readiness, "
            "available personnel, and supply. Initial states contain one insurgent formation and "
            "17 government formations in every seed; by the horizon, insurgent status is collapsed "
            "in five of eight baseline seeds and mean readiness/supply are near zero in all seeds.\n\n"
            "| Seed | Phase | Formations | Effective insurgent formations | Effective government formations | Mean effective readiness | Available personnel | Mean supply fraction |\n"
            "|---:|---|---:|---:|---:|---:|---:|---:|\n" + "\n".join(audit_rows) + "\n"
        )
    else:
        formation_section = "## Formation and presence audit\n\nAudit artifact was not yet present at report generation.\n"

    if resolution:
        resolution_rows = []
        for item in resolution["rows"]:
            resolution_rows.append(
                f"| {item['agent_count']} | {item['seed']} | {item['scheduler_executions']} | "
                f"{item['readiness_available_pairs']} | {item['supply_eligible_pairs']} | "
                f"{item['engagement_hazard_passes']} | {item['realized_latent_contacts']} | "
                f"{item['final_insurgent_physical_formations']} |"
            )
        resolution_section = (
            "## Resolution ladder\n\n"
            "The archived pre-repair resolution ladder used matched seeds at 750, 1,500, "
            "3,000, and 7,500 represented agents with frozen case/split hashes and no "
            "calibration; it produced zero hazard passes. It is retained as pre-repair "
            "provenance only; the separate post-repair eight-seed baseline is authoritative "
            "for the general repair.\n\n"
            "| Agents | Seed | Scheduler executions | Ready/available pairs | Supply-eligible pairs | Hazard passes | Realized contacts | Final insurgent formations |\n"
            "|---:|---:|---:|---:|---:|---:|---:|---:|\n" + "\n".join(resolution_rows) + "\n"
        )
    else:
        resolution_section = "## Resolution ladder\n\nResolution artifact was not yet present at report generation.\n"

    if evidence_plan:
        evidence_section = (
            "## Control/presence evidence plan\n\n"
            "No structured district-week control panel was silently fabricated. The preregistered "
            "evidence plan (`config/control_presence_evidence_plan.json`) records the OHCHR and "
            "INSEC source candidates, admissible observables, coding fields, uncertainty policy, "
            "and the rule that unresolved narrative claims remain null. The plan is therefore an "
            "active parallel workstream, not a calibration input in this benchmark.\n"
        )
    else:
        evidence_section = "## Control/presence evidence plan\n\nNo evidence plan was present at report generation.\n"

    if supply_chain:
        supply_section = (
            "## Supply-to-contact causal-chain reconstruction\n\n"
            f"The exact chain is `generate_logistics_world` → `update_logistics` → "
            f"`ArmedFormation.supply_fraction` → `effective_readiness` → "
            f"`available_personnel` → `ProcessEngine.on_contact` → `resolve_engagement`. "
            f"Initial nominal demand is {f(supply_chain['initial_demand_units_per_day'], 2)} units/day. "
            f"Under the pre-repair hub-locality source basis, production was "
            f"{f(supply_chain['source_production_units_per_day_under_old_hub_locality_basis'], 2)} "
            f"units/day ({f(supply_chain['production_to_initial_demand_under_old_basis'], 3)} of demand). "
            f"Sizing each source to its full container catchment raises production to "
            f"{f(supply_chain['source_production_units_per_day_after_catchment_fix'], 2)} "
            f"units/day ({f(supply_chain['production_to_initial_demand_after_catchment_fix'], 3)} of demand). "
            "The diagnosis records stock, capacity, demand, consumption, deliveries, departures, "
            "routes, travel times, readiness, availability, supply ratios, and contact denials "
            "for every formation at each logistics update in "
            "`results/contact_forensic/supply_contact_chain_diagnosis.json`.\n\n"
            "The documented units are abstract person-sustainment units, units/person-day, "
            "units/day, represented armed personnel, and dimensionless readiness/availability "
            "ratios; no civilian-agent count is substituted for represented military state.\n"
        )
    else:
        supply_section = "## Supply-to-contact causal-chain reconstruction\n\nChain artifact was not present at report generation.\n"

    if logistics_validation:
        checks = logistics_validation["checks"]
        validation_section = (
            "## Independent logistics validation\n\n"
            f"Propagation increased receiver stock with conservation residual "
            f"{checks['supply_propagation']['conservation_residual']:.3g}; depletion matched the "
            f"availability-adjusted equation ({checks['depletion']['matches_until_stockout']}); "
            f"route time/cost was monotone ({checks['distance']['distance_monotone']}); degraded "
            f"supply lowered effective readiness/strength ({checks['operational_degradation']['degradation_is_monotone']}); "
            f"and 400/800-agent represented-state scaling was invariant "
            f"({checks['scale']['represented_state_invariant']}).\n"
        )
    else:
        validation_section = "## Independent logistics validation\n\nValidation artifact was not present at report generation.\n"

    if double_counting:
        dc = double_counting["checks"]
        double_counting_section = (
            "## Supply double-counting audit\n\n"
            f"The default no-gate hazard has no second direct supply multiplier "
            f"({dc['default_has_no_direct_contact_supply_multiplier']}); its residual against "
            f"the activity-only equation is {double_counting['max_hazard_residual']:.3g}. "
            f"Sustained-presence and combat-expenditure flows remain distinct "
            f"({dc['presence_and_combat_flows_are_distinct']['distinct']}).\n"
        )
    else:
        double_counting_section = "## Supply double-counting audit\n\nAudit artifact was not present at report generation.\n"

    if branch_comparison:
        branch_rows = []
        for rule in ("hard_gate", "no_gate", "continuous", "ammunition_floor", "initiation_asymmetry"):
            cells = [r for r in branch_comparison["rows"] if r["rule"] == rule and
                     r["scenario"] == "mutual_encounter" and r["supply"] in (0.0, 0.5, 1.0)]
            values = "; ".join(f"S={r['supply']}: p={f(r['contact_probability'], 3)}" for r in cells)
            branch_rows.append(f"| {rule} | {values} |")
        branch_section = (
            "## Contact-supply policy branches\n\n"
            "The data-free branch battery evaluates the same supply ladder, detection, seeds, "
            "and contact rate across five general formulations.\n\n"
            "| Rule | Mutual-encounter contact probability at selected supply levels |\n|---|---|\n" +
            "\n".join(branch_rows) + "\n\n"
            "The hard gate and ammunition-floor branch make zero-supply encounters impossible. "
            "The no-gate branch permits involuntary contact while supply continues to reduce "
            "effective readiness/capability; the continuous branch provides a smooth attenuator; "
            "initiation asymmetry gates only an explicitly identified initiator. The no-gate "
            "default is selected on theoretical coherence, not Nepal fit.\n"
        )
    else:
        branch_section = "## Contact-supply policy branches\n\nBranch artifact was not present at report generation.\n"

    if recovery:
        full_rows = [r for r in recovery["rows"] if r["supply"] == 1.0]
        max_error = max(r["absolute_error"] for r in full_rows) if full_rows else 0.0
        recovery_section = (
            "## Synthetic contact-rate recovery\n\n"
            f"Across {sum(r['n'] for r in recovery['rows'])} data-free trials, the full-supply "
            f"cells recover contact_rate with maximum absolute error {f(max_error, 3)} when "
            "activity and detection are observed. Lower-supply cells remain interpretable but "
            "less precise because the hazard is smaller. Nepal calibration remains blocked by "
            "joint confounding with movement, detection, readiness, supply, and the recording "
            "operator; see `synthetic_contact_rate_recovery.json`.\n"
        )
    else:
        recovery_section = "## Synthetic contact-rate recovery\n\nRecovery artifact was not present at report generation.\n"

    if repair_comparison:
        pre = repair_comparison["pre_repair"]["funnel"]
        post = repair_comparison["post_repair"]["funnel"]
        repair_section = (
            "## Pre/post repair comparison\n\n"
            f"The frozen comparison changes only the general source-catchment basis and the "
            f"contact-supply policy; historical inputs and calibration remain unchanged. "
            f"Supply-eligible pairs rise from {pre['supply_eligible_pairs']} to "
            f"{post['supply_eligible_pairs']}; hazard passes from {pre['engagement_hazard_passes']} "
            f"to {post['engagement_hazard_passes']}; latent realized contacts from "
            f"{pre['realized_latent_contacts']} to {post['realized_latent_contacts']}. "
            f"Recorded realized contacts remain {repair_comparison['post_repair']['model']['total_recorded_contacts']}; both "
            "post-repair latent engagements are unrecorded.\n"
        )
    else:
        repair_section = "## Pre/post repair comparison\n\nComparison artifact was not present at report generation.\n"

    holdout = competitors[competitors.split.isin(["temporal_validation", "geographic_validation", "strict_joint_holdout"])].copy()
    ranking = (holdout.groupby("model").mean(numeric_only=True)["mean_poisson_log_score"]
               .sort_values(ascending=False).to_string())
    report = f"""# Nepal 2001–2006 Pineland historical benchmark

## Executive assessment

The benchmark is reproducible and the frozen data/split firewall is intact, but Pineland does **not** survive this first historical confrontation as a validated event-generating model. The repaired untuned ensemble produces **two latent realized engagements in one seed, but zero recorded realized contacts**, so it still cannot reproduce the positive UCDP recorded lethal-event target in training or either geographic/temporal holdout. Concentration and transfer statistics remain degenerate zeros for the recorded realized stream, not evidence of realistic dispersion. This is a falsification result, not a tuning invitation.

Calibration is intentionally **not licensed**. The two permitted parameters (`contact_rate`, `combat.base_attrition_rate`) cannot be identified honestly from this comparison because Pineland’s reported severity is unitless and no defensible bridge to UCDP fatalities exists. Fitting that bridge would confound event semantics, combat intensity, and recording.

## Frozen design and provenance

- Case: Nepal Maoist insurgency, 26 November 2001–21 November 2006.
- Unit: 75 historical districts × split-specific 7-day windows.
- Training: 59 non-Eastern districts through 31 December 2004.
- Holdouts: the same 59 districts after 1 January 2005; 16 Eastern districts early; and 16 Eastern districts late.
- Comparison boundary: synthetic **recorded** history versus historical **recorded** history.
- Split hash: `{run_manifest['split_sha256']}`.
- Case-environment hash: `{run_manifest['case_sha256']}`.
- Untuned ensemble: {len(run_manifest['seeds'])} fixed seeds, 750 represented agents per trajectory, four isolated workers, {f(run_manifest['wall_seconds_this_invocation'], 1)} seconds wall time.
- Compile check: `python -m compileall -q src studies tests` completed in 0.18 seconds in the current environment (well below the 20-second target).

Primary event source: [UCDP GED 26.1](https://ucdp.uu.se/downloads/ged/ged261-csv.zip), archived with SHA-256 `8c941d84954e555ee2e54f40fa04d9203bf1e2f962203d0a9930966c4947c667`. The panel retains two unmapped national-level events rather than imputing districts. The secondary spatial check is INSEC’s [complete victim report](https://www.insec.org.np/victim/reports/total.pdf), whose linked page states that materials may be used for non-profit purposes with due acknowledgement; its cumulative period and unit are not interchangeable with the UCDP district-week target.

## Historical target behavior

    The corrected primary UCDP target contains {hist['splits']['training']['strata']['two_sided_state_based']['event_count']} two-sided state-based events in training, {hist['splits']['temporal_validation']['strata']['two_sided_state_based']['event_count']} in temporal validation, {hist['splits']['geographic_validation']['strata']['two_sided_state_based']['event_count']} in geographic validation, and {hist['splits']['strict_joint_holdout']['strata']['two_sided_state_based']['event_count']} in the joint holdout. One-sided violence is retained as an observational diagnostic only. The INSEC cumulative spatial cross-check covers {crosscheck['districts_compared']} districts (Mustang is explicitly not listed), with Spearman ρ = {f(crosscheck['spearman_rank_correlation'], 3)} and top-10 overlap {crosscheck['top_10_overlap_count']}/10. This supports a useful spatial consistency check, not a ground-truth claim.

## Untuned model versus target

{comparison}

{funnel_section}

### Temporal and spatial diagnostics

{diagnostics}

The Pineland columns are degenerate because no realized **recorded** contacts occur;
they are reported as zeros rather than replaced with a null-model value. Two latent
engagements occur after the general repair, but both fail the recording layer.

Pineland’s severity is not compared to UCDP fatality intervals. It remains a unitless reported engagement severity until a separately identified measurement bridge exists.

The historical targets are now separated by construct. The primary UCDP target
is two-sided Government of Nepal–CPN-M state-based violence, while state- and
Maoist-perpetrated one-sided violence remains observational because Pineland
has no validated civilian/coercive violence analogue. The primary incidence
comparison is therefore construct-aligned, but still not a licensed
one-to-one fatality or violence-rate calibration target.

The model’s **realized recorded** contact count across the ensemble is {model['total_recorded_contacts']} (realized latent contacts: {model.get('total_realized_latent_contacts', model['total_contact_records'])}; scheduled contact-attempt records: {model.get('total_contact_attempt_records', 'not recorded')}). The two latent engagements occur in seed 20051154, in NP-D32 during weeks 3 and 4, and neither is recorded. Thus the recorded count is zero in every seed, including the temporal and geographic holdouts; that is a measurement-plus-dynamics finding, not missing-data padding.

## Competitors

All competitors were fit once on training rows only; no holdout refitting was performed. The simple district-shrunk negative-binomial rate is the strongest held-out comparator by mean Poisson log score. Hawkes uses only the frozen training event history in holdouts and does not improve the comparison.

```text
{ranking}
```

## Mechanism ablations

{ablation_text}

The ablation results are interpreted as matched-seed changes in the same case input. They are not used to rescue the full model’s fit.

{formation_section}

{resolution_section}

{evidence_section}

{supply_section}

{validation_section}

{double_counting_section}

{branch_section}

{recovery_section}

{repair_section}

## Measurement, control, and remaining limits

- The primary event target is recorded lethal organized violence; UCDP source, date, location precision, actor coding, and fatality intervals remain explicit.
- INSEC supplies cumulative district victim totals only; it cannot identify district-week timing or a Pineland severity-to-fatality map.
- No independent, structured district-week control/presence panel was available in this package. Control vectors remain model state, not empirical observations; the evidence plan above preserves this boundary.
- No displacement stream was ingested; displacement is an unvalidated extension target.
- Geography uses GADM 4.1 level-3 boundaries as a provisional 75-district topology, with a recorded caveat that it is not a Government of Nepal source.
- The benchmark run uses bounded 90-day report retention for long ensembles. Beliefs, latent state transitions, recorded contact target streams, checkpoints, seeds, and hashes are retained; raw old evidence objects are not. A no-pruning sensitivity should precede any claim about long-run information-memory effects.

## Final audit judgments

1. **Does Pineland survive its first historical confrontation?** No. It is internally executable and now produces two latent engagements, but its recorded realized incidence remains zero; spatial concentration and geographic transfer therefore cannot be meaningfully assessed for the recorded event process.
2. **Which mechanisms gained empirical credibility?** The INSEC/UCDP spatial rank agreement supports the case geography as a useful benchmark. Independent logistics tests support propagation, depletion, distance loss, degradation, conservation, and represented-state scaling as implemented mechanisms; they do not validate Nepal’s empirical fit.
3. **Which mechanisms lost credibility or remain unidentified?** The original hard supply contact gate was structurally invalid, and Nepal exposed a source-capacity unit/scaling defect. After those repairs, readiness/availability and organization survival still sparsify engagements, while the severity/reporting bridge remains unidentified.
4. **Did Pineland add information beyond simpler models?** Not in this first benchmark. District-shrunk statistical rates forecast held-out incidence at least as well while being vastly cheaper and easier to identify.
5. **What should come next?** Complete the control/presence evidence plan, establish an identified fatality/engagement measurement bridge, and rerun the same frozen holdouts only after a pre-registered study design; do not calibrate Nepal’s contact_rate or severity from this zero-recorded-contact result.

## Final classification

**MULTIPLE CAUSES** — the primary logistics issue was a general source-capacity unit/scaling defect (hub locality instead of full container catchment), and the original symmetric hard supply contact gate was structurally invalid. Both were repaired without Nepal-specific tuning. The repaired model now produces two latent engagements, but both are unrecorded, so the historical recorded-contact mismatch remains. `contact_rate` and severity calibration are not licensed.

## Artifact index

- Frozen design: `config/study.json`, `config/split_manifest.json`, `config/measurement_model.json`, `config/event_ontology.json`.
- Case inputs: `config/districts.csv`, `config/case_environment.json`.
- Historical panel/targets: `data/processed/district_week_panel.csv`, `results/historical/historical_descriptive_statistics.json`.
- Secondary cross-check: `data/processed/insec_district_totals.csv`, `results/historical/insec_ucdp_crosscheck.json`.
- Untuned ensemble: `runs/untuned_realized/manifest_agents_750.json` and per-seed JSON files.
- Model target metrics: `results/benchmark/untuned_benchmark.json`, `untuned_contact_metrics.csv`, `untuned_contact_uncertainty.csv`.
- Competitors: `results/competitors/manifest.json`, `competitor_scores.csv`.
- Ablations: `runs/ablations_repaired/manifest.json` and per-variant JSON files.
- Calibration gate: `results/calibration/calibration_status.json` (not licensed; no fitted values).
- Contact forensic: `results/contact_forensic/contact_funnel_summary.json`, `contact_funnel_records.csv`, `formation_presence_audit.json`, `controlled_contact_microworld.json`, archived pre-repair `resolution_ladder.json`, `supply_contact_chain_diagnosis.json`, `independent_logistics_validation.json`, `supply_double_counting_audit.json`, `logistics_contact_branch_comparison.json`, `synthetic_contact_rate_recovery.json`, `pre_post_repair_comparison.json`, and `final_classification.json`.
- Control/presence evidence plan: `config/control_presence_evidence_plan.json`.
- Diagnostics: `results/figures/event_incidence_comparison.png`, `insec_ucdp_spatial_crosscheck.png`, and `competitor_holdout_scores.png`.

This report freezes the benchmark’s scientific assessment; it does not freeze Pineland as empirically validated.
"""
    destination = STUDY / "results" / "nepal_benchmark_report.md"
    destination.write_text(report, encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
