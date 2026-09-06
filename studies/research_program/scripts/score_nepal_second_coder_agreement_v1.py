"""Score blind first/second-coder agreement after second coding is locked."""
from __future__ import annotations

import csv
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.reproducibility import file_sha256, repository_state  # noqa: E402

CONTRACT = ROOT / "studies/research_program/nepal_control_presence_adjudication_contract_v1.json"
FIRST = ROOT / "studies/nepal_2001_2006/data/processed/nepal_eastern_control_presence_staging_v1.csv"
SECOND = ROOT / "studies/research_program/nepal_second_coder_completed_v1.csv"
KEY = ROOT / "studies/research_program/nepal_second_coder_blind_key_v1.json"
OUT = ROOT / "studies/research_program/nepal_second_coder_agreement_v1.json"


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def overlap(a0: str, a1: str, b0: str, b1: str) -> bool:
    try:
        return max(date.fromisoformat(a0), date.fromisoformat(b0)) <= min(date.fromisoformat(a1), date.fromisoformat(b1))
    except Exception:
        return False


def main() -> int:
    if not SECOND.exists():
        raise SystemExit(f"missing locked second-coder file: {SECOND}")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    key = json.loads(KEY.read_text(encoding="utf-8"))["mapping"]
    first_by_id = {row["record_id"]: row for row in read_csv(FIRST)}
    second = read_csv(SECOND)
    rows = []
    for s in second:
        mapping = key.get(s["blind_id"])
        if mapping is None:
            rows.append({"blind_id": s["blind_id"], "error": "blind_id_not_in_key"})
            continue
        f = first_by_id[mapping["first_coder_record_id"]]
        second_admissible = s.get("observable", "").strip().upper() not in {"", "NOT_ADMISSIBLE"}
        first_admissible = f.get("observable", "").strip().upper() not in {"", "NOT_ADMISSIBLE"}
        joint = first_admissible and second_admissible
        rows.append({
            "blind_id": s["blind_id"],
            "first_record_id": f["record_id"],
            "district_id": f["district_id"],
            "first_admissible": first_admissible,
            "second_admissible": second_admissible,
            "admissibility_agree": first_admissible == second_admissible,
            "jointly_admissible": joint,
            "actor_agree": (f["actor_id"] == s.get("actor_id", "")) if joint else None,
            "observable_agree": (f["observable"] == s.get("observable", "")) if joint else None,
            "temporal_overlap": overlap(f["date_start"], f["date_end"], s.get("coder_date_start", ""), s.get("coder_date_end", "")) if joint else None,
            "first": {
                "actor_id": f["actor_id"], "observable": f["observable"],
                "date_start": f["date_start"], "date_end": f["date_end"],
                "spatial_scope": f["spatial_scope"], "confidence": f["confidence"]
            },
            "second": {
                "actor_id": s.get("actor_id", ""), "observable": s.get("observable", ""),
                "date_start": s.get("coder_date_start", ""), "date_end": s.get("coder_date_end", ""),
                "spatial_scope": s.get("spatial_scope", ""), "confidence": s.get("confidence", ""),
                "notes": s.get("second_coder_notes", "")
            }
        })
    valid = [r for r in rows if "error" not in r]
    joint = [r for r in valid if r["jointly_admissible"]]
    def mean(items, field):
        vals = [bool(item[field]) for item in items if item.get(field) is not None]
        return sum(vals) / len(vals) if vals else None
    metrics = {
        "rows_expected": len(first_by_id),
        "rows_received": len(second),
        "rows_validly_linked": len(valid),
        "admissibility_agreement": mean(valid, "admissibility_agree"),
        "jointly_admissible_rows": len(joint),
        "actor_agreement_among_jointly_admissible": mean(joint, "actor_agree"),
        "observable_agreement_among_jointly_admissible": mean(joint, "observable_agree"),
        "temporal_overlap_among_jointly_admissible": mean(joint, "temporal_overlap"),
    }
    thresholds = contract["pre_adjudication_quality_gate"]
    gates = {
        "complete": metrics["rows_received"] == metrics["rows_expected"] == metrics["rows_validly_linked"],
        "admissibility": metrics["admissibility_agreement"] is not None and metrics["admissibility_agreement"] >= thresholds["minimum_admissibility_agreement"],
        "actor": metrics["actor_agreement_among_jointly_admissible"] is not None and metrics["actor_agreement_among_jointly_admissible"] >= thresholds["minimum_actor_agreement_among_jointly_admissible"],
        "observable": metrics["observable_agreement_among_jointly_admissible"] is not None and metrics["observable_agreement_among_jointly_admissible"] >= thresholds["minimum_observable_agreement_among_jointly_admissible"],
        "temporal": metrics["temporal_overlap_among_jointly_admissible"] is not None and metrics["temporal_overlap_among_jointly_admissible"] >= thresholds["minimum_temporal_overlap_among_jointly_admissible"],
    }
    disagreements = [
        r for r in valid if (
            not r["admissibility_agree"] or
            (r["jointly_admissible"] and not all([r["actor_agree"], r["observable_agree"], r["temporal_overlap"]]))
        )
    ]
    payload = {
        "schema_version": "pineland.nepal_second_coder_agreement.v1",
        "status": "pre_adjudication_agreement_only",
        "contract_sha256": file_sha256(CONTRACT),
        "first_coder_sha256": file_sha256(FIRST),
        "second_coder_sha256": file_sha256(SECOND),
        "blind_key_sha256": file_sha256(KEY),
        "metrics": metrics,
        "quality_gates": gates,
        "pre_adjudication_quality_gate_passed": all(gates.values()),
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
        "all_rows": rows,
        "construct_validity_use_authorized": False,
        "next_required_action": "Adjudicate every disagreement against the underlying source, then rerun the frozen acquisition coverage gate on the adjudicated evidence.",
        "repository_state": repository_state(ROOT)
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "metrics": metrics,
        "quality_gates": gates,
        "pre_adjudication_quality_gate_passed": payload["pre_adjudication_quality_gate_passed"],
        "disagreement_count": len(disagreements),
        "second_coder_sha256": payload["second_coder_sha256"]
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
