"""Compare archived pre-repair and current post-repair Nepal diagnostics."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
OUT = STUDY / "results" / "contact_forensic"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summary(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    overall = payload.get("overall", payload)
    totals = overall.get("totals", {})
    return {
        "attempts": overall.get("attempts", payload.get("attempts", 0)),
        "proximity_qualified_pairs": totals.get("proximity_qualified_pairs", 0),
        "detected_opponent_sides": totals.get("detected_opponent_sides", 0),
        "readiness_available_pairs": totals.get("readiness_available_pairs", 0),
        "supply_eligible_pairs": totals.get("supply_eligible_pairs", 0),
        "engagement_hazard_draws": totals.get("engagement_hazard_draws", 0),
        "engagement_hazard_passes": totals.get("engagement_hazard_passes", 0),
        "realized_latent_contacts": totals.get("realized_latent_contacts", 0),
        "recorded_attempt_passes": totals.get("recorded_contacts", 0),
        "failure_reasons": overall.get("failure_reasons", payload.get("failure_reasons", {})),
        "first_zero_gate": overall.get("first_zero_gate", payload.get("first_zero_gate")),
    }


def model_summary(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "total_recorded_contacts": payload.get("total_recorded_contacts", 0),
        "total_realized_latent_contacts": payload.get("total_realized_latent_contacts", 0),
        "total_contact_attempt_records": payload.get("total_contact_attempt_records", 0),
        "contact_generation_failure": payload.get("contact_generation_failure"),
    }


def main() -> None:
    pre = OUT / "pre_repair" / "contact_funnel_summary.json"
    post = OUT / "contact_funnel_summary.json"
    pre_model = STUDY / "results" / "benchmark" / "pre_repair" / "untuned_benchmark.json"
    post_model = STUDY / "results" / "benchmark" / "untuned_benchmark.json"
    output = {
        "schema_version": "1.0.0", "study_id": "nepal_2001_2006",
        "comparison": "general source-catchment correction plus no-hard-contact-supply-gate; no contact_rate change",
        "pre_repair": {"funnel": summary(pre), "model": model_summary(pre_model),
                       "funnel_sha256": digest(pre), "model_sha256": digest(pre_model)},
        "post_repair": {"funnel": summary(post), "model": model_summary(post_model),
                        "funnel_sha256": digest(post), "model_sha256": digest(post_model)},
        "historical_inputs_unchanged": True,
        "calibration_performed": False,
        "interpretation": "Post-repair latent contact occurrence is nonzero (two engagements in NP-D32 during weeks 3 and 4), but both were unrecorded; recorded-contact incidence remains zero and therefore remains a historical mismatch rather than a calibration target.",
    }
    path = OUT / "pre_post_repair_comparison.json"
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path)}))


if __name__ == "__main__":
    main()
