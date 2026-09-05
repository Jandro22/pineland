"""Assemble the final machine-readable dashboard and decision report."""
from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[3];STUDY=ROOT/"studies/nepal_2001_2006";OUT=STUDY/"results/residual_diagnosis"

def get(x,path):
    for part in path.split("."): x=x.get(part,{}) if isinstance(x,dict) else {}
    return x if isinstance(x,(int,float)) else None
def compact_value(design,target,path):
    """Translate the deliberately small compact battery onto comparable targets."""
    direct=get(design,path+".mean")
    if direct is not None: return direct
    direct=get(design,target+".mean")
    if direct is not None: return direct
    events=get(design,"events.mean"); cells=get(design,"active_cells.mean")
    district_weeks=75*53  # 75 Nepal districts, 365-day compact horizon.
    derived={
      "active_cell_share": cells/district_weeks if cells is not None else None,
      "events_per_district_week": events/district_weeks if events is not None else None,
      "events_per_active_district_week": events/cells if events is not None and cells else None,
      "active_districts_per_week": cells/53 if cells is not None else None,
    }
    return derived.get(target)
def main():
    shape=json.loads((OUT/"historical_shape_validation.json").read_text())
    compact=json.loads((OUT/"compact_mechanism_diagnostics.json").read_text())["designs"]
    competitors=pd.read_csv(OUT/"binary_competitor_scores.csv")
    paths={"active_cell_share":"active_cell_share","events_per_district_week":"mean_events_per_cell",
      "events_per_active_district_week":"events_per_active_cell","active_districts_per_week":"mean_active_districts_per_week",
      "weekly_fano":"weekly_fano","weekly_autocorrelation_lag1":"weekly_autocorrelation_lag_1_to_8.1",
      "district_gini":"district_gini","normalized_hhi":"normalized_hhi","top_decile_share":"top_decile_district_share",
      "morans_i":"morans_i","districts_ever_active":"districts_ever_active","new_activation_rate":"new_district_activation_rate",
      "return_activation_rate":"return_activation_rate","event_distance_median":"consecutive_event_distance.q50"}
    for lag in (1,2,4,8):
        paths[f"reactivation_lag{lag}"]=f"recurrence_probability.{lag}"
        paths[f"adjacent_propagation_lag{lag}"]=f"adjacent_propagation_probability.{lag}"
    classes={"active_cell_share":"LEVEL","events_per_district_week":"LEVEL","events_per_active_district_week":"LEVEL",
      "active_districts_per_week":"LEVEL","weekly_fano":"TEMPORAL PERSISTENCE","weekly_autocorrelation_lag1":"TEMPORAL PERSISTENCE",
      "district_gini":"SPATIAL CONCENTRATION","normalized_hhi":"SPATIAL CONCENTRATION","top_decile_share":"SPATIAL CONCENTRATION",
      "morans_i":"SPATIAL AUTOCORRELATION","districts_ever_active":"SPATIAL CONCENTRATION","new_activation_rate":"DIFFUSION",
      "return_activation_rate":"TEMPORAL PERSISTENCE","event_distance_median":"DIFFUSION"}
    rows=[]
    for split,payload in shape["splits"].items():
        comp=competitors[(competitors.split==split)&~competitors.model.str.contains("pineland")].sort_values("log_score",ascending=False).iloc[0]
        for target,path in paths.items():
            h=get(payload["historical"],path); recorded=[get(r,path) for r in payload["recorded_runs"]];latent=[get(r,path) for r in payload["latent_runs"]]
            recorded=[x for x in recorded if x is not None];latent=[x for x in latent if x is not None]
            mean=float(np.mean(recorded)) if recorded else None;sd=float(np.std(recorded,ddof=1)) if len(recorded)>1 else None
            rows.append({"target":target,"split":split,"historical_value":h,"historical_uncertainty":None,
              "latent_pineland":float(np.mean(latent)) if latent else None,"recorded_pineland":mean,"simulation_sd":sd,
              "best_statistical_competitor":comp.model,"best_competitor_log_score":comp.log_score,
              "no_logistics":compact_value(compact.get("no_logistics",{}),target,path),
              "perfect_information":compact_value(compact.get("perfect_information",{}),target,path),
              "no_adaptive_response":compact_value(compact.get("no_adaptive_response",{}),target,path),
              "network_rewired":compact_value(compact.get("degree_preserving_rewire",{}),target,path),
              "standardized_error":((mean-h)/sd if h is not None and mean is not None and sd and sd>0 else None),
              "discrepancy_class":classes.get(target,"TEMPORAL PERSISTENCE" if "reactivation" in target else "DIFFUSION"),
              "mechanism_interpretation":"Recorded Pineland prediction; latent contrast isolates measurement.","empirical_status":"UNTUNED VALIDATION"})
    frame=pd.DataFrame(rows);frame.to_csv(OUT/"residual_dashboard.csv",index=False)
    (OUT/"residual_dashboard.json").write_text(json.dumps({"schema_version":"1.0.0","rows":rows},indent=2)+"\n")
    train=shape["splits"]["training"]; h=train["historical"]; rm=train["recorded_mean"]
    standardized=shape["count_standardized"]["training"]
    funnel=json.loads((OUT/"residual_funnel.json").read_text()); sensitivity=json.loads((OUT/"sensitivities/summary.json").read_text())["results"]
    control=json.loads((OUT/"sparse_control_presence_diagnostic.json").read_text())
    retention=json.loads((OUT/"retention_equivalence.json").read_text())
    best=competitors[competitors.split=="strict_joint_holdout"].sort_values("log_score",ascending=False).iloc[0]
    latent_share=float(np.mean([x["active_cell_share"] for x in train["latent_runs"]]));recorded_share=rm["active_cell_share"]
    measurement_fraction=(latent_share-recorded_share)/(h["active_cell_share"]-recorded_share)
    report=f"""# Nepal residual diagnosis

## Decision

**GENERAL MECHANISM DEFECT FOUND AND REPAIRED**

The repaired model remains empirically falsified on process shape. The classification records the independently demonstrated retention/identity defect, not a claim that Nepal fit is now adequate.

## Numeric answers

1. **Scale or shape?** Both. Training recorded incidence is {recorded_share:.4f} versus {h['active_cell_share']:.4f}. After equal-count thinning, model Gini {standardized['model_recorded_mean']['district_gini']:.3f} lies against historical 95% interval [{standardized['historical_thinned_summary']['district_gini']['q025']:.3f}, {standardized['historical_thinned_summary']['district_gini']['q975']:.3f}], and Moran's I {standardized['model_recorded_mean']['morans_i']:.3f} against [{standardized['historical_thinned_summary']['morans_i']['q025']:.3f}, {standardized['historical_thinned_summary']['morans_i']['q975']:.3f}]. The volume-only hypothesis is rejected.
2. **Weak persistence:** engagement-conditioned co-presence creates short renewal, but reallocation rapidly removes involved formations and engagement state is absent from destination utility. The compact post-event audit reports the causal departure and renewal probabilities in `compact_mechanism_diagnostics.json`; no hidden local Hawkes state exists.
3. **Weak diffusion:** movement destinations are selected nationally from control beliefs, not by an engagement-to-neighbor impulse. Degree-preserving rewiring barely changes the target, indicating social topology is not carrying the missing armed diffusion.
4. **Concentration:** exact microzone co-presence plus sparse force tokens concentrates opportunities; training Gini is {rm['district_gini']:.3f} versus {h['district_gini']:.3f} and only {rm['districts_ever_active']:.1f} versus {h['districts_ever_active']} districts activate.
5. **Measurement share:** recording probability conditional on latent engagement is {funnel['p_recorded_given_latent']:.3f}. Measurement explains approximately {measurement_fraction:.1%} of the training active-cell gap; latent dynamics explain the balance.
6. **Formation scale:** substantive unidentified knob. Compact recorded active cells average {sensitivity['formation_500']['recorded_active_cells']:.1f}, {sensitivity['baseline']['recorded_active_cells']:.1f}, and {sensitivity['formation_2000']['recorded_active_cells']:.1f} at 500/1,000/2,000 personnel per token.
7. **Logistics reserve:** influential engineering prior: recorded active cells range from {sensitivity['reserve_080']['recorded_active_cells']:.1f} at 0.80 to {sensitivity['reserve_150']['recorded_active_cells']:.1f} at 1.50.
8. **Actor persistence:** no effect within the one-year compact window ({sensitivity['endogenous_survival']['recorded_active_cells']:.1f} versus {sensitivity['baseline']['recorded_active_cells']:.1f}); longer-run conditioning remains a supplied historical fact rather than a model success.
9. **Mechanisms earned?** Logistics and adaptive response materially change incidence/coverage, imperfect information is modest, and degree-preserving network topology has little Nepal-relevant effect. Network topology is not empirically earned here.
10. **Held-out value:** none demonstrated. The best strict-joint competitor is {best.model} with log score {best.log_score:.3f}; full Pineland remains worse in `binary_competitor_scores.csv`. Low Brier from near-zero predictions is not treated as success.
11. **Territorial presence:** only {control['observations_in_period']} sparse district-period observations overlap the run and exploratory accuracy is {control['accuracy']:.1%}. This is insufficient for validation and currently contradicts the frozen ordinal projection.
12. **General defect:** observation and combat report IDs were based on live dictionary length, so pruning reused identities and overwrote evidence/relays. Monotonic counters repair it; bounded and full retention are behaviorally identical: {retention['behaviorally_equivalent']}.
13. **Calibration:** not justified. Shape remains wrong, token scale and reserve are influential, recording is not independently estimated, and statistical competitors dominate.

## Scientific conclusion

Pineland now generates a nondegenerate conflict, but its Nepal process is too sparse, too concentrated, insufficiently spatially autocorrelated, and poorly diffusive. No Nepal-specific rate or diffusion adjustment was made. The falsification is preserved.
"""
    (OUT/"residual_diagnosis_report.md").write_text(report)
    print(OUT/"residual_dashboard.csv")
if __name__=="__main__":main()
