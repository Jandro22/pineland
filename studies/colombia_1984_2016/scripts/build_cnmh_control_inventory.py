"""Flatten acquired official CNMH DAV control/presence layers for review.

The inventory preserves layer/feature provenance and does not invent dates when
the source layer has no period field.  It is therefore an auditable construction
artifact, not a run-ready municipality-year panel.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]


def _point(geometry: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not geometry:
        return None, None
    coords = geometry.get("coordinates")
    if geometry.get("type") == "Point" and isinstance(coords, list) and len(coords) >= 2:
        return coords[0], coords[1]
    return None, None


def build(case_root: Path, output: Path) -> dict[str, Any]:
    raw = case_root / "data" / "raw"
    index_path = raw / "cnmh_dav_control_presence_acquisition.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for item in index:
        source_path = ROOT / Path(item["path"])
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        for feature in payload.get("features", []):
            props = feature.get("properties") or {}
            lon, lat = _point(feature.get("geometry"))
            rows.append({
                "case_id": "colombia_1984_2016",
                "provider": "CNMH DAV",
                "service": item["service"],
                "layer_id": item["layer_id"],
                "source_file": source_path.relative_to(case_root).as_posix(),
                "feature_id": feature.get("id") or props.get("OBJECTID"),
                "geometry_type": (feature.get("geometry") or {}).get("type"),
                "longitude": lon,
                "latitude": lat,
                "period": props.get("Periodo"),
                "type": props.get("Tipo"),
                "place_name": props.get("Nombre_Lugar") or props.get("Nombre_lugar"),
                "structure": props.get("Estructura"),
                "sub_structure": props.get("Sub_estructura"),
                "description": props.get("Descripcion"),
                "source_label": props.get("Fuente"),
                "properties_json": json.dumps(props, ensure_ascii=False, sort_keys=True),
                "date_status": "reported_period" if props.get("Periodo") else "no_period_field_or_null",
            })
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["case_id"]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return {
        "schema_version": "1.0.0",
        "case_id": "colombia_1984_2016",
        "status": "inventory_built_not_run_ready",
        "output": output.relative_to(case_root).as_posix(),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "bytes": output.stat().st_size,
        "rows": len(rows),
        "layers": len(index),
        "rows_with_reported_period": sum(row["date_status"] == "reported_period" for row in rows),
        "rows_without_reported_period": sum(row["date_status"] != "reported_period" for row in rows),
        "run_license": False,
        "limitation": "Heterogeneous structure layers are preserved; no municipality-year join or date imputation is performed.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-root", type=Path, default=ROOT / "studies/colombia_1984_2016")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    case_root = args.case_root if args.case_root.is_absolute() else ROOT / args.case_root
    output = args.output or case_root / "data/processed/cnmh_dav_control_presence_inventory.csv"
    if not output.is_absolute():
        output = ROOT / output
    manifest = build(case_root, output)
    manifest_path = output.with_name("cnmh_dav_control_presence_inventory_manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
