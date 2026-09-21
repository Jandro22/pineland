from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT
    / "studies"
    / "research_program"
    / "general_theory_v1"
    / "partner_force_autonomy"
    / "evidence"
    / "stage4"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_stage4_compact_evidence_manifest_matches_files() -> None:
    manifest = json.loads((EVIDENCE / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE"
    assert manifest["production_worlds"] == 2808
    assert manifest["final_integrity_errors"] == 0

    for name, expected in manifest["files"].items():
        path = EVIDENCE / name
        assert path.is_file(), name
        assert sha256(path) == expected, name


def test_stage4_ready_provenance_is_internally_consistent() -> None:
    manifest = json.loads((EVIDENCE / "MANIFEST.json").read_text(encoding="utf-8"))
    integrated = json.loads(
        (EVIDENCE / "READY_STAGE4_INTEGRATED.json").read_text(encoding="utf-8")
    )
    paper = json.loads(
        (EVIDENCE / "READY_STAGE4_PAPER_SECONDARY.json").read_text(encoding="utf-8")
    )

    assert integrated["status"] == "STAGE4_INTEGRATED_PROGRAM_COMPLETE"
    assert integrated["production_worlds"] == manifest["production_worlds"]
    assert integrated["production_git_commit"] == manifest["production_git_commit"]
    assert integrated["analysis_git_commit"] == manifest["postprocess_git_commit"]
    assert sum(module["expected_worlds"] for module in integrated["modules"]) == 2808

    assert paper["status"] == "STAGE4_PAPER_SECONDARY_COMPLETE"
    assert paper["production_git_commit"] == manifest["production_git_commit"]
    assert paper["postprocess_git_commit"] == manifest["postprocess_git_commit"]
    assert paper["paper_analysis_git_commit"] == manifest["paper_analysis_git_commit"]
    assert paper["integrated_ready_sha256"] == sha256(
        EVIDENCE / "READY_STAGE4_INTEGRATED.json"
    )

    for name, expected in paper["outputs"].items():
        assert sha256(EVIDENCE / name) == expected, name
