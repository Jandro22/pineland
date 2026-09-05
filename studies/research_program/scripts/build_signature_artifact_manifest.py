"""Create a content-addressed manifest for the historical signature artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies" / "research_program"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record(path: str, builder: str) -> dict[str, Any]:
    artifact = ROOT / path
    builder_path = ROOT / builder
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    refs: list[dict[str, str]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
                refs.append({"path": value["path"], "sha256": value["sha256"]})
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload.get("cases", []))
    unique_refs = sorted({(item["path"], item["sha256"]) for item in refs})
    return {
        "path": path,
        "sha256": _sha256(artifact),
        "builder": builder,
        "builder_sha256": _sha256(builder_path),
        "source_refs": [{"path": path, "sha256": sha256} for path, sha256 in unique_refs],
        "historical_outcomes_used": payload.get("historical_outcomes_used") is True,
        "core_change_licensed": payload.get("core_change_licensed") is True,
    }


def build() -> dict[str, Any]:
    artifacts = [
        _record(
            "studies/research_program/harmonized_historical_event_signatures.json",
            "studies/research_program/scripts/build_harmonized_historical_signatures.py",
        ),
        _record(
            "studies/research_program/historical_signature_competitor_benchmark.json",
            "studies/research_program/scripts/build_historical_signature_competitor_benchmark.py",
        ),
        _record(
            "studies/research_program/actor_continuity_diagnostic.json",
            "studies/research_program/scripts/build_actor_continuity_diagnostic.py",
        ),
        _record(
            "studies/research_program/historical_assignment_sensitivity.json",
            "studies/research_program/scripts/build_assignment_sensitivity.py",
        ),
    ]
    return {
        "schema_version": "1.0.0",
        "program_id": "comparative-insurgency-v1",
        "status": "content_addressed_historical_signature_artifacts",
        "artifacts": artifacts,
        "guard": "Manifest binds descriptive historical evidence to its builders and source hashes; it does not certify the simulator core or theory.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PROGRAM / "historical_signature_artifact_manifest.json")
    args = parser.parse_args()
    report = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
