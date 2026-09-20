#!/usr/bin/env python3
"""Generate the cryptographic freeze for the integrated Stage-4 program."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
BASE = REPO / "studies/research_program/general_theory_v1/partner_force_autonomy"
V5 = BASE / "contracts/partner_force_autonomy_preregistration_freeze_v5.json"
OUT = BASE / "contracts/partner_force_stage4_integrated_freeze_v1.json"


def canonical_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def digest(path: Path) -> str:
    return hashlib.sha256(canonical_bytes(path)).hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def main() -> None:
    previous = json.loads(V5.read_text(encoding="utf-8"))
    artifacts: dict[str, dict[str, str]] = {}
    for artifact_id, entry in previous["frozen_artifacts"].items():
        path = REPO / entry["path"]
        if not path.exists():
            raise SystemExit(f"missing inherited freeze artifact: {path}")
        artifacts[artifact_id] = {"path": rel(path), "sha256": digest(path)}

    additions = {
        "stage4_foundation_reference": BASE / "contracts/stage4_foundation_reference_v1.json",
        "stage4_engineering_calibration_decision": BASE / "contracts/stage4_engineering_calibration_decision_v1.json",
        "stage4_integrated_protocol": BASE / "STAGE4_INTEGRATED_PROTOCOL_v1.md",
        "stage4_integrated_launch_plan": BASE / "contracts/stage4_integrated_launch_plan_v1.json",
        "stage4_phase_map_contract": BASE / "contracts/stage4_autonomy_phase_map_v1.json",
        "stage4_bottleneck_migration_contract": BASE / "contracts/stage4_bottleneck_migration_v1.json",
        "stage4_substitution_development_contract": BASE / "contracts/stage4_substitution_development_v1.json",
        "stage4_design_generator": BASE / "analysis/generate_stage4_integrated_designs.py",
        "stage4_freeze_generator": BASE / "analysis/generate_stage4_freeze.py",
        "stage4_integrated_analysis": BASE / "analysis/analyze_stage4_integrated.py",
        "stage4_array_wrapper": BASE / "arc/stage4_array.sbatch",
        "stage4_postprocess_wrapper": BASE / "arc/stage4_postprocess.sbatch",
        "stage4_finalize_wrapper": BASE / "arc/stage4_finalize.sbatch",
        "stage4_integrated_launcher": BASE / "arc/launch_stage4_integrated.sh",
        "stage4_merge_code": BASE / "arc/merge_partner_force_shards.py",
        "stage4_research_program_memo": BASE / "RESEARCH_PROGRAM_MEMO_2026-09-20.md",
    }
    for artifact_id, path in additions.items():
        if not path.exists():
            raise SystemExit(f"missing Stage-4 freeze artifact: {path}")
        artifacts[artifact_id] = {"path": rel(path), "sha256": digest(path)}

    payload = {
        "schema_version": "pineland.partner_force_stage4_integrated_freeze.v1",
        "status": "FROZEN_BEFORE_STAGE4_PRODUCTION",
        "hash_canonicalization": "crlf_to_lf_v1",
        "historical_stage4_outcomes_used": False,
        "engineering_calibration_seed_namespace": "2026290000-series; excluded from production inference",
        "stage3_foundation_commit": "e536251c6d9faeb37e948d81179ada99a042d94a",
        "description": "Integrated Stage-4 one-paper freeze: autonomy phase map, bottleneck migration, and substitution-versus-development. Inherits and re-hashes the Stage-3 v5 scientific foundation, then freezes all Stage-4 treatment, design, analysis, merge, and ARC wrapper artifacts.",
        "frozen_artifacts": artifacts,
        "required_artifact_count": len(artifacts),
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {rel(OUT)} with {len(artifacts)} frozen artifacts")


if __name__ == "__main__":
    main()
