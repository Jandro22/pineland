"""Validate the prospective SIGAR observation operator on synthetic states."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
STUDY = ROOT / "studies" / "afghanistan_2004_2021"
MODEL = STUDY / "config" / "control_observation_model.json"
OUT = STUDY / "results" / "control_observation_synthetic_recovery.json"


def main() -> int:
    from control_observation import OrdinalControlObservationModel
    from pineland_sim.reproducibility import build_run_manifest, file_sha256

    parser = argparse.ArgumentParser()
    parser.add_argument("--samples-per-category", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260904)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    specification = json.loads(MODEL.read_text(encoding="utf-8"))
    operator = OrdinalControlObservationModel.from_dict(specification)
    recovery = operator.synthetic_recovery(samples_per_category=args.samples_per_category,
                                           seed=args.seed)
    result = {
        "schema_version": "1.0.0",
        "operator_sha256": file_sha256(MODEL),
        "operator_status": specification["status"],
        "historical_target_used_for_fit": False,
        "recovery": recovery,
        "passed": recovery["accuracy"] >= 0.75,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = build_run_manifest(
        {"operator_sha256": result["operator_sha256"], "samples_per_category": args.samples_per_category},
        seeds=[args.seed], execution_mode="deterministic_synthetic_observation_recovery",
        output_schema={"name": "control_observation_recovery", "version": "1.0.0"},
        case_files=[MODEL], repo_root=ROOT,
        extra={"stage": "prospective_control_observation_validation",
               "artifacts": {args.output.relative_to(ROOT).as_posix(): file_sha256(args.output)}},
    )
    manifest_path = args.output.with_name(args.output.stem + "_manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
