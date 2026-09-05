"""Materialize reproduction-decomposition benchmark tables from genealogy JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "studies" / "research_program"))
sys.path.insert(0, str(ROOT / "src"))

from reproduction_competitors import GenealogyRun, build_reproduction_tables, decomposition_summary  # noqa: E402
from pineland_sim.reproducibility import build_run_manifest, file_sha256  # noqa: E402


def _parse_run(value: str) -> tuple[Path, str]:
    if "::" not in value:
        raise argparse.ArgumentTypeError("run must be PATH::SPLIT")
    path, split = value.rsplit("::", 1)
    return Path(path), split


def _locality_universe(path: Path) -> dict[str, tuple[str, ...]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return {"*": tuple(str(value) for value in raw)}
    if not isinstance(raw, dict):
        raise ValueError("locality universe must be a JSON list or run-id mapping")
    return {str(key): tuple(str(value) for value in values) for key, values in raw.items()}


def _adjacency(path: Path | None) -> dict[str, list[str]]:
    if path is None:
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "neighbors" in raw:
        raw = raw["neighbors"]
    return {str(key): [str(value) for value in values] for key, values in raw.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", type=_parse_run, required=True)
    parser.add_argument("--localities", type=Path, required=True)
    parser.add_argument("--adjacency", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bin-days", type=float, default=7.0)
    parser.add_argument("--deepening-horizon-days", type=float, default=30.0)
    parser.add_argument("--survival-horizon-days", type=float, default=14.0)
    args = parser.parse_args()

    universe = _locality_universe(args.localities)
    runs = []
    input_paths = []
    for index, (path, split) in enumerate(args.run):
        genealogy = json.loads(path.read_text(encoding="utf-8"))
        run_id = str(genealogy.get("seed", path.stem))
        localities = universe.get(run_id, universe.get("*"))
        if localities is None:
            raise ValueError(f"no locality universe declared for run {run_id}")
        runs.append(GenealogyRun(run_id, split, genealogy, localities))
        input_paths.append(path)
    tables = build_reproduction_tables(
        runs,
        bin_days=args.bin_days,
        deepening_horizon_days=args.deepening_horizon_days,
        survival_horizon_days=args.survival_horizon_days,
        adjacency=_adjacency(args.adjacency),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_files = {}
    for name, frame in tables.items():
        path = args.output_dir / f"{name}.csv"
        frame.to_csv(path, index=False)
        output_files[name] = path
    summary = decomposition_summary(tables)
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    files = [*input_paths, args.localities]
    if args.adjacency:
        files.append(args.adjacency)
    specification = {
        "reproduction_estimand": "decomposed",
        "components": [
            "local_spontaneous_ignition",
            "parent_attributed_colonization",
            "foothold_to_saturated_access",
            "foothold_to_fielded_force",
            "post_establishment_survival",
        ],
        "formation_relocation_counted_as_colonization": False,
        "unresolved_parentage_imputed": False,
        "full_locality_risk_set_required": True,
        "bin_days": args.bin_days,
        "deepening_horizon_days": args.deepening_horizon_days,
        "survival_horizon_days": args.survival_horizon_days,
        "summary": summary,
    }
    manifest = build_run_manifest(
        specification,
        execution_mode="observation_only_reproduction_benchmark_table_materialization",
        output_schema={"name": "reproduction_benchmark_tables", "version": "1.0.0"},
        case_files=files,
        repo_root=ROOT,
        extra={
            "runner_sha256": file_sha256(Path(__file__)),
            "library_sha256": file_sha256(ROOT / "studies" / "research_program" / "reproduction_competitors.py"),
            "output_hashes": {name: file_sha256(path) for name, path in output_files.items()},
        },
    )
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
