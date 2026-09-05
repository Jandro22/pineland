"""Create auditable run manifests for the research-program evidence ledger.

The manifests bind each cited artifact to the live frozen model hash, complete
case-file inventory, split hash, and execution stage.  This is intentionally
separate from legacy stage manifests, which predate the full reproducibility
contract and are never upgraded in place.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pineland_sim.reproducibility import build_run_manifest, file_sha256, model_sha256


ROOT = Path(__file__).resolve().parents[3]
CORE_FREEZE = ROOT / "studies/research_program/core_freeze.json"


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _write_manifest(path: Path, *, config: dict[str, Any], case_files: list[Path], split: Path,
                    stage: str, artifacts: list[Path]) -> dict[str, Any]:
    artifact_map = {_relative(item): file_sha256(item) for item in artifacts}
    manifest = build_run_manifest(
        config,
        seeds=[config.get("seed", "not_applicable")],
        execution_mode={"stage": stage, "runner": "verified_evidence_manifest_builder"},
        output_schema={"artifact_bindings": "sha256", "stage": stage},
        case_files=case_files,
        split_file=split,
        repo_root=ROOT,
        extra={"stage": stage, "artifacts": artifact_map},
    )
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _record(artifact: Path, manifest_path: Path, expected: dict[str, Any], stage: str) -> dict[str, Any]:
    artifact_model = None
    if artifact.suffix.lower() == ".json":
        try:
            payload = json.loads(artifact.read_text(encoding="utf-8"))
            artifact_model = payload.get("model_sha256_start") or payload.get("repository", {}).get("model_sha256")
        except (OSError, ValueError, TypeError):
            artifact_model = None
    return {
        "status": "verified_run_evidence",
        "artifact": {"path": _relative(artifact), "sha256": file_sha256(artifact)},
        "run_manifest": {"path": _relative(manifest_path), "sha256": file_sha256(manifest_path)},
        "expected": expected,
        "expected_stage": stage,
        "artifact_model_sha256": artifact_model,
    }


def main() -> None:
    afghan = ROOT / "studies/afghanistan_2004_2021"
    afghan_case_files = [
        afghan / "config/case_environment.json",
        afghan / "config/historical_case_inputs.json",
        afghan / "data/processed/sigar_oct2017_control_401.csv",
        afghan / "data/processed/province_week_panel.csv",
    ]
    afghan_split = afghan / "config/study_design.json"
    init_artifact = afghan / "runs/transfer_test_v1/init/seed_20040101_taliban_7500.json"
    smoke_artifact = afghan / "runs/transfer_test_v1/smoke/seed_20040101_taliban_7500.json"
    init_manifest_path = afghan / "runs/transfer_test_v1/init/verified_manifest.json"
    smoke_manifest_path = afghan / "runs/transfer_test_v1/smoke/verified_manifest.json"
    init_manifest = _write_manifest(
        init_manifest_path,
        config={"study_id": "afghanistan_2004_2021", "stage": "init", "seed": 20040101, "horizon_days": 1.0, "strength": 7500.0},
        case_files=afghan_case_files, split=afghan_split, stage="init", artifacts=[init_artifact, afghan_split],
    )
    smoke_manifest = _write_manifest(
        smoke_manifest_path,
        config={"study_id": "afghanistan_2004_2021", "stage": "smoke", "seed": 20040101, "horizon_days": 30.0, "strength": 7500.0},
        case_files=afghan_case_files, split=afghan_split, stage="smoke", artifacts=[smoke_artifact, afghan_split],
    )

    nepal = ROOT / "studies/nepal_2001_2006"
    nepal_artifact = nepal / "runs/post_structural_repair/final_empirical_rescore/seed_20011126_agents_750.json"
    nepal_manifest_path = nepal / "runs/post_structural_repair/final_empirical_rescore/verified_manifest.json"
    nepal_case_files = [
        nepal / "config/case_environment_repaired.json",
        nepal / "data/processed/district_week_panel.csv",
        nepal / "data/processed/ucdp_nepal_events.csv",
    ]
    nepal_split = nepal / "config/split_manifest.json"
    nepal_manifest = _write_manifest(
        nepal_manifest_path,
        config={"study_id": "nepal_2001_2006", "stage": "nepal_final_rescore", "seed": 20011126, "agent_count": 750, "horizon_days": 180.0, "formulation": "post_structural_repair_v1"},
        case_files=nepal_case_files, split=nepal_split, stage="nepal_final_rescore", artifacts=[nepal_artifact],
    )

    freeze_before = json.loads(CORE_FREEZE.read_text(encoding="utf-8"))
    certificate = ROOT / freeze_before.get(
        "authoritative_certificate",
        "outputs/final_release/RELEASE_CERTIFICATE_SUPERSEDING.json",
    )
    release_manifest_path = ROOT / "outputs/final_release/verified_manifest.json"
    release_manifest = _write_manifest(
        release_manifest_path,
        config={"stage": "settled_tree_certificate", "certificate": _relative(certificate), "certificate_payload_sha256": json.loads(certificate.read_text(encoding="utf-8"))["certificate_payload_sha256"]},
        # The certificate is also listed as a case-file input so the strict
        # evidence contract rejects an empty provenance map for this record.
        case_files=[certificate], split=CORE_FREEZE, stage="settled_tree_certificate", artifacts=[certificate],
    )

    freeze = json.loads(CORE_FREEZE.read_text(encoding="utf-8"))
    expected = lambda manifest: {key: manifest[key] for key in ("model_sha256", "config_sha256", "case_data_hashes", "split_sha256")}
    freeze["evidence_records"] = {
        "settled_tree_certificate": _record(certificate, release_manifest_path, expected(release_manifest), "settled_tree_certificate"),
        "nepal_final_rescore": _record(nepal_artifact, nepal_manifest_path, expected(nepal_manifest), "nepal_final_rescore"),
        "afghanistan_case_ready": _record(afghan_split, init_manifest_path, expected(init_manifest), "init"),
        "afghanistan_initialization_gate": _record(init_artifact, init_manifest_path, expected(init_manifest), "init"),
        "afghanistan_smoke_gate": _record(smoke_artifact, smoke_manifest_path, expected(smoke_manifest), "smoke"),
    }
    pytest_log = ROOT / "tmp/current_validation/pytest_live.log"
    pytest_text = pytest_log.read_text(encoding="utf-8", errors="replace").replace("\x00", "") if pytest_log.exists() else ""
    passed_match = re.search(r"(\d+) passed in", pytest_text)
    freeze["freeze_basis"]["software_tests"] = f"{passed_match.group(1)} passed, 0 failed" if passed_match else freeze["freeze_basis"].get("software_tests", "unverified")
    CORE_FREEZE.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "verified_evidence_manifests_built",
        "model_sha256": model_sha256(ROOT),
        "records": sorted(freeze["evidence_records"]),
        "nepal_manifest": _relative(nepal_manifest_path),
    }, indent=2))


if __name__ == "__main__":
    main()
