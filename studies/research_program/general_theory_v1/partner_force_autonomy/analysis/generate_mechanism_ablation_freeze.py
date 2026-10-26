#!/usr/bin/env python3
"""Freeze the post-review mechanism-ablation sidecar before production."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[5]
BASE = REPO / "studies/research_program/general_theory_v1/partner_force_autonomy"
PREVIOUS = BASE / "contracts/partner_force_stage4_integrated_freeze_v1.json"
OUT = BASE / "contracts/partner_force_mechanism_ablation_freeze_v1.json"


def canonical(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def digest(path: Path) -> str:
    return hashlib.sha256(canonical(path)).hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def main() -> None:
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    artifacts: dict[str, dict[str, str]] = {}
    for artifact_id, entry in previous["frozen_artifacts"].items():
        path = REPO / entry["path"]
        artifacts[f"inherited_{artifact_id}"] = {"path": rel(path), "sha256": digest(path)}

    paths = {
        "protocol": BASE / "MECHANISM_ABLATION_PROTOCOL_v1.md",
        "contract": BASE / "contracts/mechanism_ablation_v1.json",
        "design_generator": BASE / "analysis/generate_mechanism_ablation_design.py",
        "analysis": BASE / "analysis/analyze_mechanism_ablation.py",
        "array_wrapper": BASE / "arc/mechanism_ablation_array.sbatch",
        "freeze_generator": BASE / "analysis/generate_mechanism_ablation_freeze.py",
        "runner": REPO / "rust/pineland-model/examples/partner_force_autonomy_stage3.rs",
        "formal_adapter": REPO / "rust/pineland-model/src/partner_force_formal.rs",
        "source_stage4_contract": BASE / "contracts/stage4_autonomy_phase_map_v1.json",
    }
    for path in paths.values():
        if not path.exists():
            raise SystemExit(f"missing freeze artifact: {path}")
    for name, path in paths.items():
        artifacts[f"ablation_{name}"] = {"path": rel(path), "sha256": digest(path)}
    payload = {
        "schema_version": "pineland.partner_force_mechanism_ablation_freeze.v1",
        "status": "FROZEN_BEFORE_MECHANISM_ABLATION_PRODUCTION",
        "hash_canonicalization": "crlf_to_lf_v1",
        "stage4_results_known_before_design": True,
        "stage5_results_known_before_design": True,
        "reviewer_diagnostics_known_before_design": True,
        "engineering_calibration_seed": 2026999902,
        "engineering_calibration_outcomes_used_for_science": False,
        "production_outcomes_used_before_freeze": False,
        "frozen_artifacts": artifacts,
        "required_artifact_count": len(artifacts),
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {rel(OUT)} with {len(paths)} frozen artifacts")


if __name__ == "__main__":
    main()
