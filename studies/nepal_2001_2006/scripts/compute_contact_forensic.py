"""Aggregate instrumented contact funnels without fitting or outcome tuning."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
RUNS = STUDY / "runs" / "untuned_realized"
OUT = STUDY / "results" / "contact_forensic"


GATES = [
    "opposing_armed_organizations", "opposing_formation_candidate_pairs",
    "same_locality_candidate_pairs", "microzone_eligible_candidate_pairs",
    "proximity_qualified_pairs", "true_target_presence_cases",
    "detected_opponent_sides", "readiness_available_pairs",
    "supply_eligible_pairs", "command_eligible_pairs",
    "engagement_hazard_draws", "engagement_hazard_passes",
    "realized_latent_contacts", "recorded_contacts",
]


def load_payloads() -> list[dict]:
    return [json.loads(path.read_text()) for path in sorted(RUNS.glob("seed_*_agents_*.json"))]


def records(payloads: list[dict]) -> list[dict]:
    rows = []
    for payload in payloads:
        path = RUNS / f"seed_{payload['seed']}_agents_{payload['agent_count']}.json"
        for trace in payload.get("contact_funnel", []):
            counts = trace.get("gate_counts", {})
            row = {"seed": payload["seed"], "agent_count": payload["agent_count"],
                   "run_file": path.name, "time": trace.get("time"),
                   "week_index": trace.get("week_index"),
                   "district_id": trace.get("locality_id"),
                   "microzone_id": trace.get("microzone_id"),
                   "selected_government_formation_id": trace.get("selected_government_formation_id"),
                   "selected_insurgent_formation_id": trace.get("selected_insurgent_formation_id"),
                   "failure_reason": trace.get("failure_reason"),
                   "detected_by": ",".join(trace.get("detected_by", [])),
                   "readiness": json.dumps(trace.get("readiness", {}), sort_keys=True),
                   "availability": json.dumps(trace.get("availability", {}), sort_keys=True),
                   "supply_fraction": json.dumps(trace.get("supply_fraction", {}), sort_keys=True),
                   "command": json.dumps(trace.get("command", {}), sort_keys=True),
                   "contact_hazard": trace.get("contact_hazard", 0.0),
                   "hazard_draw": trace.get("hazard_draw"),
                   "candidate_pairs": json.dumps(trace.get("candidate_pairs", []), sort_keys=True)}
            row.update({gate: int(counts.get(gate, 0)) for gate in GATES})
            rows.append(row)
    return rows


def formation_audit(payloads: list[dict]) -> dict:
    rows = []
    for payload in payloads:
        for phase in ("initial_formations", "final_formations"):
            formations = payload.get(phase, [])
            rows.append({
                "seed": payload["seed"], "phase": phase.removesuffix("_formations"),
                "formation_count": len(formations),
                "insurgent_physical_formations": sum(
                    item["organization_id"] == "insurgent" and
                    item.get("operational_status") == "effective" and
                    (phase == "initial_formations" or item.get("organization_status") == "active")
                    for item in formations),
                "government_physical_formations": sum(
                    item["organization_id"] in {"fdf", "police"} and
                    item.get("operational_status") == "effective"
                    for item in formations),
                "effective_readiness_mean": (
                    sum(float(item.get("effective_readiness", 0.0)) for item in formations) /
                    max(1, len(formations))),
                "available_personnel_total": sum(float(item.get("available_personnel", 0.0)) for item in formations),
                "supply_fraction_mean": (
                    sum(float(item.get("supply_fraction", 0.0)) for item in formations) /
                    max(1, len(formations))),
                "locations": sorted({item.get("locality_id") for item in formations}),
                "microzones": sorted({item.get("microzone_id") for item in formations}),
                "insurgent_locations": sorted({item.get("locality_id") for item in formations
                                                if item.get("organization_id") == "insurgent"}),
            })
    return {"rows": rows,
            "interpretation": "Formation existence, physical locality/microzone, supply, readiness, and availability are recorded separately from social or political presence."
            }


def aggregate(frame: pd.DataFrame) -> dict:
    totals = {gate: int(frame[gate].sum()) for gate in GATES}
    denominators = {
        "same_locality_candidate_pairs": totals["opposing_formation_candidate_pairs"],
        "microzone_eligible_candidate_pairs": totals["same_locality_candidate_pairs"],
        "proximity_qualified_pairs": totals["microzone_eligible_candidate_pairs"],
        "detected_opponent_sides": totals["true_target_presence_cases"],
        "readiness_available_pairs": totals["proximity_qualified_pairs"],
        # Supply and command are evaluated diagnostically even when the
        # readiness gate fails, so their denominator is the same spatially
        # qualified pair set rather than the preceding passing subset.
        "supply_eligible_pairs": totals["proximity_qualified_pairs"],
        "command_eligible_pairs": totals["proximity_qualified_pairs"],
        "engagement_hazard_draws": totals["detected_opponent_sides"],
        "engagement_hazard_passes": totals["engagement_hazard_draws"],
        "realized_latent_contacts": totals["engagement_hazard_passes"],
        # This gate records the observation-layer pass on each scheduled
        # contact attempt, including a failed/hazard-rejected attempt.  It is
        # therefore an attempt-record rate, not realized-contact recall.
        "recorded_contacts": int(len(frame)),
    }
    rates = {
        gate: (totals[gate] / denominators[gate] if denominators[gate] else None)
        for gate in denominators
    }
    reason_counts = frame.failure_reason.value_counts().sort_index().astype(int).to_dict()
    first_collapse = next((gate for gate in (
        "opposing_armed_organizations", "opposing_formation_candidate_pairs",
        "microzone_eligible_candidate_pairs", "detected_opponent_sides",
        "readiness_available_pairs", "supply_eligible_pairs",
        "command_eligible_pairs", "engagement_hazard_passes",
        "realized_latent_contacts") if totals[gate] == 0), None)
    return {"attempts": int(len(frame)), "totals": totals,
            "conditional_pass_rates": rates, "failure_reasons": reason_counts,
            "first_zero_gate": first_collapse}


def grouped(frame: pd.DataFrame, column: str) -> dict:
    output = {}
    for key, group in frame.groupby(column, dropna=False, sort=True):
        item = aggregate(group)
        item["key"] = key.item() if hasattr(key, "item") else key
        output[str(item["key"])] = item
    return output


def main() -> None:
    payloads = load_payloads()
    rows = records(payloads)
    if not rows:
        raise SystemExit("no contact funnel records found; rerun the untuned benchmark")
    OUT.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "contact_funnel_records.csv", index=False)
    (OUT / "formation_presence_audit.json").write_text(
        json.dumps(formation_audit(payloads), indent=2, default=str) + "\n"
    )
    output = {
        "schema_version": "1.0.0", "study_id": "nepal_2001_2006",
        "comparison": "instrumented scheduler-to-realized-contact pipeline",
        "overall": aggregate(frame),
        "by_seed": grouped(frame, "seed"),
        "by_district": grouped(frame, "district_id"),
        "by_week": grouped(frame, "week_index"),
        "by_government_formation": grouped(frame.fillna({"selected_government_formation_id": "none"}),
                                            "selected_government_formation_id"),
        "by_insurgent_formation": grouped(frame.fillna({"selected_insurgent_formation_id": "none"}),
                                           "selected_insurgent_formation_id"),
        "realized_contact_distribution": {
            "by_district": frame.loc[frame["realized_latent_contacts"] > 0]
                .groupby("district_id").size().astype(int).to_dict(),
            "by_week": frame.loc[frame["realized_latent_contacts"] > 0]
                .groupby("week_index").size().astype(int).to_dict(),
            "recorded_realized_contacts": int(
                sum(
                    int(row.get("realized_latent_contacts", 0) > 0 and row.get("recorded", False))
                    for payload in payloads for row in payload.get("contact_funnel", [])
                )
            ),
        },
        "interpretation": "A first-zero gate is descriptive only. The traces preserve all scheduler executions and rejection reasons; no contact or severity parameter is fitted.",
    }
    (OUT / "contact_funnel_summary.json").write_text(json.dumps(output, indent=2, default=str) + "\n")
    print(json.dumps({"attempts": len(frame), "first_zero_gate": output["overall"]["first_zero_gate"],
                      "output": str(OUT / "contact_funnel_summary.json")}))


if __name__ == "__main__":
    main()
