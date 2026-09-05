"""Audit preserved scientific run manifests without rewriting their provenance.

Legacy manifests are evidence about old runs.  Missing commit/environment
metadata cannot be truthfully reconstructed from the current checkout, so this
script reports gaps rather than stamping current provenance onto historical
artifacts.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
OUT = STUDY / "results" / "reproducibility"

RESULT_MANIFESTS = (
    STUDY / "results" / "competitors" / "manifest.json",
    STUDY / "results" / "post_structural_repair" / "structural_repair_manifest.json",
    STUDY / "results" / "residual_diagnosis" / "binary_competitor_manifest.json",
)


def scientific_manifest_paths() -> list[Path]:
    paths = list(RESULT_MANIFESTS)
    paths.extend((STUDY / "runs").rglob("manifest*.json"))
    return sorted({path for path in paths if path.exists()})


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from pineland_sim.reproducibility import (
        REQUIRED_MANIFEST_FIELDS, audit_run_manifest, file_sha256,
    )

    rows = []
    for path in scientific_manifest_paths():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        audit = audit_run_manifest(manifest)
        relative = path.relative_to(ROOT).as_posix()
        rows.append({
            "path": relative,
            "sha256": file_sha256(path),
            "valid_current_reproduction_contract": audit["valid"],
            "missing_fields": audit["missing_fields"],
            "empty_required_fields": audit["empty_required_fields"],
            "legacy_schema_version": manifest.get("schema_version"),
            "captured_commit_hash": manifest.get("commit_hash"),
            "captured_dirty_tree": manifest.get("dirty_tree"),
            "captured_model_sha256": manifest.get("model_sha256"),
            "captured_config_sha256": manifest.get("config_sha256"),
            "captured_parameter_registry_sha256": manifest.get("parameter_registry_sha256"),
            "captured_split_sha256": manifest.get("split_sha256"),
            "captured_seeds": manifest.get("seeds"),
        })

    payload = {
        "schema_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "required_fields": sorted(REQUIRED_MANIFEST_FIELDS),
        "policy": (
            "Historical manifests are never backfilled with the current commit "
            "or environment because doing so would falsify original-run provenance."
        ),
        "scientific_run_manifests": rows,
        "manifest_count": len(rows),
        "fully_reproducible_manifest_count": sum(
            row["valid_current_reproduction_contract"] for row in rows
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "manifest_audit.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(path),
        "manifests": payload["manifest_count"],
        "complete": payload["fully_reproducible_manifest_count"],
    }))


if __name__ == "__main__":
    main()
