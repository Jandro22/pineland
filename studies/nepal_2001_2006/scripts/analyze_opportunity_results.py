"""Compute construct-aligned latent/recorded opportunity metrics and write the audit report."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from math import hypot
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies/nepal_2001_2006"
RUNS = STUDY / "runs/opportunity_nested"
OUT = STUDY / "results/opportunity_structure"
SEEDS = (20011126, 20021133, 20031140, 20041147, 20051154, 20061161, 20071168, 20081175)


def concentration(values):
    values = list(values); total = sum(values)
    if not values or total == 0: return {"gini": 0.0, "hhi": 0.0}
    ordered = sorted(values); n = len(ordered)
    gini = sum((2*i-n-1)*x for i, x in enumerate(ordered, 1))/(n*total)
    return {"gini": gini, "hhi": sum((x/total)**2 for x in values)}


def metrics(events, horizon_weeks=261):
    cells = Counter((e["district_id"], int(e["day"]//7)) for e in events)
    districts = Counter(e["district_id"] for e in events)
    weekly = Counter(int(e["day"]//7) for e in events)
    week_values = [weekly[w] for w in range(horizon_weeks)]
    mean = sum(week_values)/len(week_values)
    variance = sum((x-mean)**2 for x in week_values)/len(week_values)
    active_by_district = defaultdict(list)
    for district, week in cells: active_by_district[district].append(week)
    recurrence = sum(any(b-a == 1 for a,b in zip(sorted(ws), sorted(ws)[1:]))
                     for ws in active_by_district.values())
    return {"events": len(events), "active_district_weeks": len(cells),
            "active_week_share": sum(x>0 for x in week_values)/len(week_values),
            "zero_week_share": sum(x==0 for x in week_values)/len(week_values),
            "fano_weekly": variance/mean if mean else 0.0,
            "districts_active": len(districts), "district_recurrence_count": recurrence,
            **concentration(districts.values())}


def main():
    nested = json.loads((OUT/"nested_untuned_summary.json").read_text())
    rows = [json.loads((RUNS/"E_combined"/f"seed_{seed}_agents_750.json").read_text())
            for seed in SEEDS]
    latent_by_run = [[e for e in row["contacts"] if e["realized"]] for row in rows]
    recorded_by_run = [[e for e in events if e["recorded"]] for events in latent_by_run]
    latent = [e for events in latent_by_run for e in events]
    recorded = [e for events in recorded_by_run for e in events]
    historical = []
    with (STUDY/"data/processed/district_week_panel.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            count = int(row["government_maoist_state_based_events"])
            historical.extend({"district_id": row["district_id"], "day": index*7}
                              for index in range(count))
    def ensemble_metrics(groups):
        per_run = [metrics(group) for group in groups]
        return {"pooled_concentration_diagnostic": metrics([e for group in groups for e in group]),
                "mean_events": sum(x["events"] for x in per_run)/len(per_run),
                "mean_active_district_weeks": sum(x["active_district_weeks"] for x in per_run)/len(per_run),
                "mean_active_district_week_share": sum(x["active_district_weeks"] for x in per_run)/(len(per_run)*75*261),
                "mean_zero_week_share": sum(x["zero_week_share"] for x in per_run)/len(per_run),
                "mean_fano_weekly": sum(x["fano_weekly"] for x in per_run)/len(per_run)}
    result = {"latent": ensemble_metrics(latent_by_run), "recorded": ensemble_metrics(recorded_by_run),
              "historical_contract": nested["historical_measurement_contract"],
              "classification": {
                  "event_ceiling": "RESOLVED BY GENERAL OPPORTUNITY/FORMATION REPAIRS",
                  "formation_ontology": "REPAIRED AT TOKEN DECOMPOSITION LEVEL; ECHELON EVIDENCE STILL NEEDED",
                  "actor_persistence": "CONDITIONED FOR KNOWN EXISTENCE; OPERATIONS ENDOGENOUS",
                  "time_units": "RESOLVED AND SYNTHETICALLY VERIFIED",
                  "recording_semantics": "RESOLVED; RECORDED ENGAGEMENT IMPLIES LATENT",
                  "historical_fit": "NOT CALIBRATED; DISTRICT-WEEK VALIDATION REMAINS",
                  "contact_rate_identifiability": "NOT LICENSED",
                  "control_presence": "SPARSE EVIDENCE WORKSTREAM REMAINS OPEN",
              }}
    (OUT/"post_repair_metrics.json").write_text(json.dumps(result, indent=2)+"\n")
    report = f"""# Armed-interaction opportunity report

## Frozen result

No historical outcome parameter was fitted. The defensible common contract is **district-week any state-based government–CPN-M event**; the {nested['historical_measurement_contract']['raw_ged_row_count_diagnostic_only']} UCDP rows remain diagnostic because a formation engagement has no identified one-to-one row mapping.

The prior repaired model generated {nested['variants']['A_prior_repaired']['latent_engagements']} latent engagement across eight trajectories. The theory-preferred combined model generated {nested['variants']['E_combined']['latent_engagements']} latent and {nested['variants']['E_combined']['recorded_engagements']} recorded engagements across the same fixed seeds. Historical data contain {nested['historical_measurement_contract']['active_district_weeks']} active district-weeks ({nested['historical_measurement_contract']['active_share']:.3f} of cells). The combined model averages {nested['variants']['E_combined']['mean_latent_active_district_weeks_per_trajectory']:.1f} **latent** active district-weeks ({nested['variants']['E_combined']['mean_latent_active_district_week_share']:.3f}) and {nested['variants']['E_combined']['mean_recorded_active_district_weeks_per_trajectory']:.1f} **recorded** active district-weeks ({nested['variants']['E_combined']['mean_recorded_active_district_week_share']:.3f}). The earlier 441.9 label referred to latent activity; it is corrected here. The ceiling is gone, but recorded historical incidence remains substantially underproduced.

## Answers

1. **Ceiling:** the old scheduler allowed at most one strongest-pair draw per occupied microzone scan. With one insurgent token its physical ceiling was about one opportunity per day, before survival and co-location. This was structurally incompatible with raw row-count comparison.
2. **Granularity:** raw counts are not commensurate. District-week incidence is frozen as primary; district-day and dyad-location-day episodes are robustness contracts.
3. **Formation ontology:** 17 government/1 insurgent was inherited generator residue, not Nepal evidence. `ArmedFormation` remains an abstract operational presence token, not a claimed battalion.
4. **Decomposition:** organizations now map to multiple independently located tokens by a declared manpower rule. Nepal outcomes never set their count.
5. **Persistence:** observed actor intervals preserve organizational identity while readiness, availability, logistics, movement, losses, and effectiveness remain endogenous.
6. **Initiation:** directional competing hazards use initiator state and realized detection; target readiness affects response rather than targetability. A small declared accidental co-presence component permits involuntary contact.
7. **Time:** `contact_rate` is now per formation-pair day and the hazard includes explicit elapsed days. Synthetic tests recover the same implied daily rate at 0.25, 0.5, 1, 2, and 7 days.
8. **Logistics:** the former population proxy hid side-specific imbalance. Organization-manpower sustainment capacity prevents no-combat collapse without using event outcomes, though the 1.20 reserve remains an engineering prior requiring sensitivity analysis.
9. **Recording:** contact opportunity, latent engagement, recording draw, and recorded engagement are distinct; recorded implies latent by construction and test.
10. **Identification:** `contact_rate` remains unlicensed for Nepal calibration because formation scale, movement, detection, logistics, and reporting remain jointly confounded. The model has moved from near-zero to a nondegenerate regime; that is a structural validation result, not historical fit.

## Decision

The opportunity ceiling is resolved sufficiently to proceed to construct-aligned historical validation, but the model is **not ready to freeze or calibrate**. Next work is a district-week temporal/geographic holdout comparison, sensitivity to the declared force-token sizes and logistics reserve, and the separate sparse control/presence evidence stream. Severity calibration remains blocked.
"""
    (OUT/"armed_interaction_opportunity_report.md").write_text(report)
    print(OUT/"armed_interaction_opportunity_report.md")


if __name__ == "__main__": main()
