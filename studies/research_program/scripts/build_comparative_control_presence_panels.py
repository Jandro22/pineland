"""Build immutable, scope-explicit comparative control/presence panels.

The builder preserves reported categories and missingness.  It deliberately
does not equate non-reporting with absence, expand an anchor to a country, or
impose a common numeric control scale on unlike historical instruments.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies/research_program"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_path(path: Path) -> str:
    try:
        path = path.relative_to(ROOT)
    except ValueError:
        pass
    return str(path).replace("\\", "/")


def period_bounds(value: str) -> tuple[str, str]:
    years = re.findall(r"(?:19|20)\d{2}", value or "")
    if not years:
        return "", ""
    return f"{years[0]}-01-01", f"{years[-1]}-12-31"


def write_csv(path: Path, fieldnames: list[str], rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def build_colombia(source: Path, output: Path) -> dict:
    fields = [
        "case_id", "unit_id", "period_start", "period_end", "longitude", "latitude",
        "observation_type", "reported_value", "observation_status", "spatial_scope",
        "temporal_scope", "missingness_reason", "source_artifact", "source_row_id",
    ]

    def rows():
        with source.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                start, end = period_bounds(row.get("period", ""))
                reported = bool(start)
                yield {
                    "case_id": "colombia_1984_2016",
                    "unit_id": f"cnmh:{row['service']}:{row['layer_id']}:{row['feature_id']}",
                    "period_start": start, "period_end": end,
                    "longitude": row.get("longitude", ""), "latitude": row.get("latitude", ""),
                    "observation_type": "armed_structure_presence_point",
                    "reported_value": "present" if reported else "",
                    "observation_status": "reported" if reported else "not_temporally_located",
                    "spatial_scope": "CNMH_DAV_selected_structure_layers_point",
                    "temporal_scope": row.get("period", ""),
                    "missingness_reason": "" if reported else "source_has_no_reported_period",
                    "source_artifact": artifact_path(source),
                    "source_row_id": row.get("feature_id", ""),
                }

    count = write_csv(output, fields, rows())
    return {"rows": count, "status": "partial_longitudinal_point_inventory", "run_license": False,
            "limitation": "Selected structure layers only; points are not municipality control states."}


def build_iraq(source: Path, output: Path) -> dict:
    fields = [
        "case_id", "unit_id", "period_start", "period_end", "longitude", "latitude",
        "observation_type", "reported_value", "observation_status", "spatial_scope",
        "temporal_scope", "missingness_reason", "source_artifact", "source_row_id",
    ]

    def rows():
        with source.open(encoding="utf-8-sig", newline="") as handle:
            for index, row in enumerate(csv.DictReader(handle), 1):
                reported = row["evidence_status"] != "not_reported"
                yield {
                    "case_id": row["case_id"], "unit_id": row["anchor_unit"],
                    "period_start": row["month"], "period_end": row["month"],
                    "longitude": "", "latitude": "",
                    "observation_type": "control_responsibility",
                    "reported_value": row["control_responsibility"] if reported else "",
                    "observation_status": row["evidence_status"],
                    "spatial_scope": "Rusafa_political_district_anchor_only",
                    "temporal_scope": row["date_precision"],
                    "missingness_reason": "" if reported else "outside_reported_operational_window",
                    "source_artifact": artifact_path(source),
                    "source_row_id": str(index),
                }

    count = write_csv(output, fields, rows())
    return {"rows": count, "status": "anchor_only_longitudinal_panel", "run_license": False,
            "limitation": "Rusafa anchor only; must not be treated as a whole-Iraq proxy."}


def build_vietnam(source: Path, output: Path) -> dict:
    try:
        import pyreadr
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pyreadr is required to build the Vietnam HES panel") from exc
    frame = next(iter(pyreadr.read_r(str(source)).values()))
    measures = [
        "hcat_hamlet_category", "mod6a_political_control_macromodel",
        "mod6b_military_control_macromodel", "mod1a_enemy_military_presence_submodel",
        "mod1d_friendly_military_presence_submodel", "mod1h_enemy_political_presence_submodel",
    ]
    selected = frame.loc[
        (frame["rectp_record_type"] == "Hamlet Record") & frame["date"].notna(),
        ["us_hamlet_id", "date", "hamlet_lat", "hamlet_lng", "hpopul_hamlet_population", *measures],
    ].copy()
    selected["date"] = selected["date"].map(lambda value: value.isoformat() if hasattr(value, "isoformat") else str(value))
    selected.to_csv(output, index=False, compression="gzip")
    observed = int(selected[measures].notna().any(axis=1).sum())
    return {
        "rows": int(len(selected)), "rows_with_any_measure": observed,
        "status": "longitudinal_hamlet_instrument_panel", "run_license": False,
        "limitation": "Raw HES ordinal categories retained; no cross-case numeric equivalence or population crosswalk asserted.",
        "measures": measures,
    }


def build_all(output_dir: Path = PROGRAM / "data/processed/comparative_control_presence") -> dict:
    sources = {
        "colombia_1984_2016": ROOT / "studies/colombia_1984_2016/data/processed/cnmh_dav_control_presence_inventory.csv",
        "iraq_2003_2011": ROOT / "studies/iraq_2003_2011/data/processed/sigir_rusafa_control_presence_panel.csv",
        "vietnam_1955_1975": ROOT / "studies/vietnam_1955_1975/data/raw/vietwar_hes70.rds",
    }
    outputs = {
        "colombia_1984_2016": output_dir / "colombia_control_presence.csv",
        "iraq_2003_2011": output_dir / "iraq_control_presence.csv",
        "vietnam_1955_1975": output_dir / "vietnam_hes_control_presence.csv.gz",
    }
    details = {
        "colombia_1984_2016": build_colombia(sources["colombia_1984_2016"], outputs["colombia_1984_2016"]),
        "iraq_2003_2011": build_iraq(sources["iraq_2003_2011"], outputs["iraq_2003_2011"]),
        "vietnam_1955_1975": build_vietnam(sources["vietnam_1955_1975"], outputs["vietnam_1955_1975"]),
    }
    for case_id, detail in details.items():
        detail.update({
            "source": artifact_path(sources[case_id]),
            "source_sha256": sha256(sources[case_id]),
            "output": artifact_path(outputs[case_id]),
            "output_sha256": sha256(outputs[case_id]),
        })
    manifest = {
        "schema_version": "1.0.0", "status": "frozen_processed_observation_layer",
        "comparability": "schema_and_provenance_only_not_common_cardinal_scale",
        "zero_imputation": False, "cases": details,
        "model_use_gate": "Case-specific validation and declared measurement mapping required before fitting.",
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=PROGRAM / "data/processed/comparative_control_presence")
    args = parser.parse_args()
    result = build_all(args.output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
