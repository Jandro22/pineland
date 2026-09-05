"""Write the genuine post-repair Nepal rescore and bind it to fresh runs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
STUDY = ROOT / "studies" / "nepal_2001_2006"


def main() -> int:
    from pineland_sim.config import SimulationConfig
    from pineland_sim.reproducibility import build_run_manifest, file_sha256

    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    args = parser.parse_args()
    runs_dir = args.runs_dir.resolve(); results_dir = args.results_dir.resolve()
    run_manifest_path = runs_dir / "manifest_agents_750.json"
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    benchmark = json.loads((results_dir / "untuned_benchmark.json").read_text(encoding="utf-8"))
    first_run = json.loads((runs_dir / run_manifest["runs"][0]["file"]).read_text(encoding="utf-8"))
    rows = {row["split"]: row for row in benchmark["uncertainty"]}
    report_path = results_dir / "nepal_final_rescore.md"
    lines = [
        "# Nepal post-structural-repair final rescore",
        "",
        "This is a fresh execution under the frozen core, not reconstructed legacy provenance.",
        "No parameter was fitted and no holdout was refit.",
        "",
        f"- Trajectories: {benchmark['runs']} fixed seeds at 750 represented agents",
        f"- Latent realized contacts: {benchmark['total_realized_latent_contacts']}",
        f"- Recorded realized contacts: {benchmark['total_recorded_contacts']}",
        f"- Run manifest: `{run_manifest_path.relative_to(ROOT).as_posix()}`",
        "",
        "| Split | Mean recorded contacts | 5–95% interval | Mean district Gini | Mean Moran's I |",
        "|---|---:|---:|---:|---:|",
    ]
    for split in ("training", "temporal_validation", "geographic_validation", "strict_joint_holdout"):
        row = rows[split]
        lines.append(
            f"| {split} | {row['recorded_contact_count_mean']:.4f} | "
            f"{row['recorded_contact_count_p05']:.4f}–{row['recorded_contact_count_p95']:.4f} | "
            f"{row['district_count_gini_mean']:.4f} | {row['morans_i_events_per_100k_mean']:.4f} |"
        )
    lines.extend([
        "", "## Decision", "",
        "This rescore remains a falsification unless the frozen historical targets are reproduced on the declared holdouts and simple competitors are surpassed. It does not license Nepal tuning, a general transfer claim, or COIN inference.", "",
    ])
    results_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    case_files = [
        STUDY / "config" / "case_environment_repaired.json",
        STUDY / "config" / "case_environment.json",
        STUDY / "config" / "study.json",
        STUDY / "data" / "manifests" / "sources.json",
        run_manifest_path,
        results_dir / "untuned_benchmark.json",
        results_dir / "untuned_contact_metrics.csv",
        results_dir / "untuned_contact_uncertainty.csv",
    ]
    manifest = build_run_manifest(
        SimulationConfig.from_dict(first_run["config"]),
        seeds=run_manifest["seeds"],
        execution_mode="deterministic_post_repair_rescore_analysis",
        output_schema={"name": "nepal_final_rescore", "version": "2.0.0"},
        case_files=case_files,
        split_file=STUDY / "config" / "split_manifest.json",
        repo_root=ROOT,
        extra={
            "stage": "nepal_post_structural_repair_final_rescore",
            "source_run_manifest_sha256": file_sha256(run_manifest_path),
            "artifacts": {report_path.relative_to(ROOT).as_posix(): file_sha256(report_path)},
            "parameter_fit": False,
            "holdout_refit": False,
        },
    )
    manifest_path = results_dir / "final_rescore_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report_path), "manifest": str(manifest_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
