"""Build the outcome-independent Afghanistan region/province/district registry."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import zipfile

from pyproj import CRS, Transformer

ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "afghanistan_2004_2021"
RAW = STUDY / "data" / "raw"
OUT = STUDY / "data" / "processed"
CONFIG = STUDY / "config"
SOURCE = RAW / "afg_admin_boundaries.geojson.zip"
DESIGN = CONFIG / "study_design.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise RuntimeError(f"refusing to write empty table: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    CONFIG.mkdir(parents=True, exist_ok=True)
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    held_out = set(design["geographic_holdout"]["selected_region_codes"])
    with zipfile.ZipFile(SOURCE) as archive:
        regions = json.load(archive.open("afg_regions.geojson"))["features"]
        provinces = json.load(archive.open("afg_admin1.geojson"))["features"]
        districts = json.load(archive.open("afg_admin2.geojson"))["features"]
        capitals = json.load(archive.open("afg_admincapitals.geojson"))["features"]
        lines = json.load(archive.open("afg_adminlines.geojson"))["features"]
    if (len(regions), len(provinces), len(districts), len(capitals)) != (8, 34, 401, 401):
        raise RuntimeError(
            f"unexpected COD dimensions: regions={len(regions)} provinces={len(provinces)} "
            f"districts={len(districts)} capitals={len(capitals)}"
        )

    region_props = {f["properties"]["region_pcode"]: f["properties"] for f in regions}
    province_props = {f["properties"]["adm1_pcode"]: f["properties"] for f in provinces}
    district_props = {f["properties"]["adm2_pcode"]: f["properties"] for f in districts}
    capital_props = {}
    for feature in capitals:
        pcode = feature["properties"]["adm2_pcode"]
        if pcode in capital_props:
            raise RuntimeError(f"duplicate district capital: {pcode}")
        capital_props[pcode] = (feature["properties"], feature["geometry"])
    if set(capital_props) != set(district_props):
        raise RuntimeError(
            f"district-capital coverage mismatch: missing={sorted(set(district_props)-set(capital_props))[:10]} "
            f"extra={sorted(set(capital_props)-set(district_props))[:10]}"
        )

    # Local azimuthal-equidistant coordinates provide kilometre-scale physical
    # distances without forcing Afghanistan across multiple UTM zones.
    local_crs = CRS.from_proj4(
        "+proj=aeqd +lat_0=33.9 +lon_0=67.7 +datum=WGS84 +units=m +no_defs"
    )
    transformer = Transformer.from_crs("EPSG:4326", local_crs, always_xy=True)

    region_rows = []
    for pcode, row in sorted(region_props.items()):
        region_rows.append({
            "region_id": pcode,
            "region_name": row["region_name"],
            "is_geographic_holdout": str(pcode in held_out).lower(),
            "area_sqkm": row.get("area_sqkm", ""),
        })

    province_rows = []
    for pcode, row in sorted(province_props.items()):
        province_rows.append({
            "province_id": pcode,
            "province_name": row["adm1_name"],
            "region_id": row["regioncode"],
            "region_name": row["regionname_en"],
            "is_geographic_holdout": str(row["regioncode"] in held_out).lower(),
            "area_sqkm": row.get("area_sqkm", ""),
            "center_latitude": row.get("center_lat", ""),
            "center_longitude": row.get("center_lon", ""),
        })

    district_rows = []
    center_rows = []
    for pcode, row in sorted(district_props.items()):
        province_id = row["adm1_pcode"]
        region_id = row["regioncode"]
        if province_id not in province_props or region_id not in region_props:
            raise RuntimeError(f"invalid hierarchy for district {pcode}")
        cap, geometry = capital_props[pcode]
        if geometry.get("type") != "Point":
            raise RuntimeError(f"district capital is not a point: {pcode}")
        lon, lat = map(float, geometry["coordinates"])
        x_m, y_m = transformer.transform(lon, lat)
        district_rows.append({
            "district_id": pcode,
            "district_name": row["adm2_name"],
            "province_id": province_id,
            "province_name": row["adm1_name"],
            "region_id": region_id,
            "region_name": row["regionname_en"],
            "is_geographic_holdout": str(region_id in held_out).lower(),
            "area_sqkm": row.get("area_sqkm", ""),
            "unit_type": row.get("unittype", "District"),
        })
        center_rows.append({
            "locality_id": f"{pcode}-HQ",
            "district_id": pcode,
            "district_name": row["adm2_name"],
            "province_id": province_id,
            "region_id": region_id,
            "name": cap["name"],
            "capital_level": cap["adm_p_lvl"],
            "latitude": lat,
            "longitude": lon,
            "x_km": x_m / 1000.0,
            "y_km": y_m / 1000.0,
            "administrative_role": "district_headquarters",
        })

    adjacency = {pcode: set() for pcode in district_props}
    for feature in lines:
        row = feature["properties"]
        first, second = row.get("right_pcod"), row.get("left_pcod")
        if first in district_props and second in district_props and first != second:
            adjacency[first].add(second)
            adjacency[second].add(first)
    isolated = [pcode for pcode, neighbors in adjacency.items() if not neighbors]
    if isolated:
        raise RuntimeError(f"isolated COD districts: {isolated}")
    # Topological connectivity is a hard requirement for physical movement.
    seen = set()
    stack = [next(iter(adjacency))]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adjacency[node] - seen)
    if len(seen) != len(adjacency):
        raise RuntimeError(f"district adjacency graph disconnected: {len(seen)}/{len(adjacency)}")

    write_csv(OUT / "regions.csv", region_rows)
    write_csv(OUT / "provinces.csv", province_rows)
    write_csv(OUT / "districts.csv", district_rows)
    write_csv(OUT / "district_centers.csv", center_rows)
    adjacency_payload = {
        "schema_version": "1.0.0",
        "districts": len(adjacency),
        "undirected_edges": sum(len(v) for v in adjacency.values()) // 2,
        "neighbors": {key: sorted(value) for key, value in sorted(adjacency.items())},
    }
    (OUT / "district_adjacency.json").write_text(
        json.dumps(adjacency_payload, indent=2) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": "1.0.0",
        "source_sha256": digest(SOURCE),
        "study_design_sha256": digest(DESIGN),
        "regions": len(region_rows),
        "provinces": len(province_rows),
        "districts": len(district_rows),
        "district_centers": len(center_rows),
        "held_out_region_codes": sorted(held_out),
        "adjacency_edges": adjacency_payload["undirected_edges"],
        "adjacency_connected": True,
        "outcome_data_used": False,
    }
    (OUT / "geography_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
