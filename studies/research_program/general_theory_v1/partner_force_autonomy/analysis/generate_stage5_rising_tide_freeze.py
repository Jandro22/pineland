#!/usr/bin/env python3
"""Generate the cryptographic freeze for the Stage-5 rising-tide follow-up."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
BASE = REPO / "studies/research_program/general_theory_v1/partner_force_autonomy"
PREVIOUS = BASE / "contracts/partner_force_stage4_integrated_freeze_v1.json"
OUT = BASE / "contracts/partner_force_stage5_rising_tide_freeze_v1.json"


def canonical_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def digest(path: Path) -> str:
    return hashlib.sha256(canonical_bytes(path)).hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def main() -> None:
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    artifacts: dict[str, dict[str, str]] = {}
    for artifact_id, entry in previous["frozen_artifacts"].items():
        path = REPO / entry["path"]
        if not path.exists():
            raise SystemExit(f"missing inherited scientific artifact: {path}")
        artifacts[f"inherited_{artifact_id}"] = {"path": rel(path), "sha256": digest(path)}

    additions = {
        "stage5_protocol": BASE / "STAGE5_RISING_TIDE_PROTOCOL_v1.md",
        "stage5_contract": BASE / "contracts/stage5_rising_tide_v1.json",
        "stage5_design_generator": BASE / "analysis/generate_stage5_rising_tide_design.py",
        "stage5_analysis": BASE / "analysis/analyze_stage5_rising_tide.py",
        "stage5_freeze_generator": BASE / "analysis/generate_stage5_rising_tide_freeze.py",
        "stage5_array_wrapper": BASE / "arc/stage5_rising_tide_array.sbatch",
        "stage5_postprocess_wrapper": BASE / "arc/stage5_rising_tide_postprocess.sbatch",
        "stage5_launcher": BASE / "arc/launch_stage5_rising_tide.sh",
        "stage5_merge_code": BASE / "arc/merge_partner_force_shards.py",
    }
    for artifact_id, path in additions.items():
        if not path.exists():
            raise SystemExit(f"missing Stage-5 freeze artifact: {path}")
        artifacts[artifact_id] = {"path": rel(path), "sha256": digest(path)}

    payload = {
        "schema_version": "pineland.partner_force_stage5_rising_tide_freeze.v1",
        "status": "FROZEN_BEFORE_STAGE5_PRODUCTION",
        "hash_canonicalization": "crlf_to_lf_v1",
        "stage4_results_known_before_design": True,
        "stage5_outcomes_used_before_freeze": False,
        "description": (
            "Prospective post-Stage-4 freeze for the coordinated indigenous-development "
            "experiment. It re-hashes the inherited scientific foundation and freezes "
            "the Stage-5 protocol, contract, analysis, merge, and ARC execution wrappers."
        ),
        "frozen_artifacts": artifacts,
        "required_artifact_count": len(artifacts),
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {rel(OUT)} with {len(artifacts)} frozen artifacts")


if __name__ == "__main__":
    main()
