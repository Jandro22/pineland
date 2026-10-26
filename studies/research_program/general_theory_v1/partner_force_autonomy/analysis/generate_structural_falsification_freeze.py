#!/usr/bin/env python3
"""Freeze the prospective post-Stage-4 structural falsification sidecar."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[5]
BASE = REPO / "studies/research_program/general_theory_v1/partner_force_autonomy"
PREVIOUS = BASE / "contracts/partner_force_stage4_integrated_freeze_v1.json"
OUT = BASE / "contracts/partner_force_structural_falsification_freeze_v1.json"


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
        artifacts[f"inherited_{artifact_id}"] = {"path": rel(path), "sha256": digest(path)}

    additions = {
        "structural_protocol": BASE / "STRUCTURAL_FALSIFICATION_PROTOCOL_v1.md",
        "structural_contract": BASE / "contracts/structural_falsification_v1.json",
        "structural_design_generator": BASE / "analysis/generate_structural_falsification_design.py",
        "structural_analysis": BASE / "analysis/analyze_structural_falsification.py",
        "structural_freeze_generator": BASE / "analysis/generate_structural_falsification_freeze.py",
        "structural_array_wrapper": BASE / "arc/structural_falsification_array.sbatch",
        "production_runner": REPO / "rust/pineland-model/examples/partner_force_autonomy_stage3.rs",
        "formal_adapter": REPO / "rust/pineland-model/src/partner_force_formal.rs",
    }
    for artifact_id, path in additions.items():
        if not path.exists():
            raise SystemExit(f"missing structural-falsification artifact: {path}")
        artifacts[artifact_id] = {"path": rel(path), "sha256": digest(path)}

    payload = {
        "schema_version": "pineland.partner_force_structural_falsification_freeze.v1",
        "status": "FROZEN_BEFORE_STRUCTURAL_FALSIFICATION_PRODUCTION",
        "hash_canonicalization": "crlf_to_lf_v1",
        "stage4_results_known_before_design": True,
        "stage5_outcomes_used_before_freeze": False,
        "structural_outcomes_used_before_freeze": False,
        "description": (
            "Prospective post-Stage-4 architecture-falsification sidecar. It inherits the Stage-4 "
            "scientific foundation and freezes the four-cell structural design before outcomes."
        ),
        "frozen_artifacts": artifacts,
        "required_artifact_count": len(artifacts),
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {rel(OUT)} with {len(artifacts)} frozen artifacts")


if __name__ == "__main__":
    main()
