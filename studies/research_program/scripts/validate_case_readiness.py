"""Fail closed unless a comparative case has all pre-run artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(contract: dict[str, Any], case_root: Path) -> dict[str, Any]:
    construct_map = contract.get("construct_map", [])
    inputs = contract.get("inputs", [])
    holdouts = contract.get("holdouts", {})
    manifest_path = case_root / "data" / "manifests" / "sources.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest_sources = manifest.get("sources", [])
    acquired_sources_hash_valid = all(
        (case_root / item["local_path"]).is_file()
        and _sha256(case_root / item["local_path"]) == item["sha256"]
        and ("bytes" not in item or (case_root / item["local_path"]).stat().st_size == item["bytes"])
        for item in manifest_sources
        if item.get("acquisition_status") in {"acquired", "partially_acquired"}
    )
    panel_manifest_path = case_root / "data" / "processed" / "panel_manifest.json"
    measurement_audit_path = case_root / "config" / "measurement_audit.json"
    holdout_manifest_path = case_root / "config" / "holdout_manifest.json"
    panel_manifest = json.loads(panel_manifest_path.read_text(encoding="utf-8")) if panel_manifest_path.exists() else {}
    measurement_audit = json.loads(measurement_audit_path.read_text(encoding="utf-8")) if measurement_audit_path.exists() else {}
    holdout_manifest = json.loads(holdout_manifest_path.read_text(encoding="utf-8")) if holdout_manifest_path.exists() else {}
    checks = {
        "preregistered_status": contract.get("status") in {"preregistered", "data_construction", "ready"},
        "calibration_forbidden": contract.get("calibration") == {
            "licensed": False, "training_only": True, "holdout_refit": False
        },
        "construct_measurements_declared": all(
            item.get("source") and item.get("unit") and item.get("measurement_model")
            for item in construct_map
        ),
        "input_sources_declared": all(item.get("source") and item.get("future_outcome_used") is False for item in inputs),
        "holdouts_frozen": all(holdouts.get(name) for name in ("temporal", "geographic", "joint")),
        "outcome_blind_selection": holdouts.get("outcome_blind_selection") is True,
        "source_manifest_ready": (
            manifest.get("status") == "acquired_and_hashed" and
            bool(manifest.get("sources")) and
            all(item.get("acquisition_status") == "acquired" and item.get("sha256")
                for item in manifest["sources"])
        ),
        "acquired_source_hashes_valid": acquired_sources_hash_valid,
        "processed_panel_manifest": panel_manifest.get("status") == "built_and_hashed",
        "measurement_audit": measurement_audit.get("status") == "frozen",
        "holdout_manifest_artifact": holdout_manifest.get("status") == "frozen_materialized",
        "disabled_mechanisms_declared": isinstance(contract.get("disabled_mechanisms"), list),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "blocked_reasons": [name for name, passed in checks.items() if not passed],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path)
    args = parser.parse_args()
    case_root = args.case if args.case.is_absolute() else ROOT / args.case
    contract_path = case_root / "config" / "case_contract.json"
    result = validate(json.loads(contract_path.read_text(encoding="utf-8")), case_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
