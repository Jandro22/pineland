"""Aggregate the frozen 2004 WorldPop 1-km grid into 401 COD districts."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from math import floor
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
from shapely import STRtree, points
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "afghanistan_2004_2021"
RAW = STUDY / "data" / "raw"
OUT = STUDY / "data" / "processed"
WORLDPOP = RAW / "afg_ppp_2004_1km_UNadj_ASCII_XYZ.zip"
COD = RAW / "afg_admin_boundaries.geojson.zip"
DISTRICTS = OUT / "districts.csv"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    district_meta = {row["district_id"]: row for row in csv.DictReader(DISTRICTS.open(encoding="utf-8"))}
    with zipfile.ZipFile(COD) as archive:
        features = json.load(archive.open("afg_admin2.geojson"))["features"]
    pcodes = [feature["properties"]["adm2_pcode"] for feature in features]
    polygons = [shape(feature["geometry"]) for feature in features]
    if len(pcodes) != 401 or len(set(pcodes)) != 401:
        raise RuntimeError("expected 401 unique COD district polygons")
    tree = STRtree(polygons)
    totals = np.zeros(len(polygons), dtype=float)
    squared_totals = np.zeros(len(polygons), dtype=float)
    populated_cells = np.zeros(len(polygons), dtype=np.int64)
    matched_points = 0
    boundary_reassigned_points = 0
    matched_population = 0.0
    boundary_reassigned_population = 0.0
    maximum_boundary_reassignment_km = 0.0
    with zipfile.ZipFile(WORLDPOP) as archive:
        member = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
        with io.TextIOWrapper(archive.open(member), encoding="utf-8") as stream:
            for chunk in pd.read_csv(stream, chunksize=150_000):
                values = chunk["Z"].to_numpy(dtype=float)
                valid = np.isfinite(values) & (values > 0)
                if not valid.any():
                    continue
                xs = chunk.loc[valid, "X"].to_numpy(dtype=float)
                ys = chunk.loc[valid, "Y"].to_numpy(dtype=float)
                vals = values[valid]
                point_array = points(xs, ys)
                pairs = tree.query(point_array, predicate="within")
                point_indices, polygon_indices = pairs[0], pairs[1]
                if len(point_indices):
                    # COD polygons do not overlap substantively; guard against
                    # accidental double assignment anyway.
                    unique_points, counts = np.unique(point_indices, return_counts=True)
                    if np.any(counts > 1):
                        raise RuntimeError("WorldPop point matched multiple COD districts")
                    np.add.at(totals, polygon_indices, vals[point_indices])
                    np.add.at(squared_totals, polygon_indices, vals[point_indices] ** 2)
                    np.add.at(populated_cells, polygon_indices, 1)
                    matched_points += len(point_indices)
                    matched_population += float(vals[point_indices].sum())
                matched_mask = np.zeros(len(vals), dtype=bool)
                matched_mask[point_indices] = True
                unmatched_indices = np.flatnonzero(~matched_mask)
                if len(unmatched_indices):
                    nearest_pairs, nearest_distance = tree.query_nearest(
                        point_array[unmatched_indices], return_distance=True, all_matches=False
                    )
                    source_indices = unmatched_indices[nearest_pairs[0]]
                    nearest_polygon_indices = nearest_pairs[1]
                    distance_km = nearest_distance * 111.0
                    if float(distance_km.max()) > 10.0:
                        raise RuntimeError(
                            f"WorldPop/COD boundary mismatch exceeds 10 km: {float(distance_km.max())}"
                        )
                    np.add.at(totals, nearest_polygon_indices, vals[source_indices])
                    np.add.at(
                        squared_totals,
                        nearest_polygon_indices,
                        vals[source_indices] ** 2,
                    )
                    np.add.at(populated_cells, nearest_polygon_indices, 1)
                    boundary_reassigned_points += len(source_indices)
                    boundary_reassigned_population += float(vals[source_indices].sum())
                    maximum_boundary_reassignment_km = max(
                        maximum_boundary_reassignment_km, float(distance_km.max())
                    )

    national_target = round(float(totals.sum()))
    integers = np.floor(totals).astype(int)
    remainder = national_target - int(integers.sum())
    fractional = totals - integers
    if remainder < 0 or remainder > len(integers):
        raise RuntimeError(f"unexpected largest-remainder allocation: {remainder}")
    if remainder:
        order = np.lexsort((np.array(pcodes), -fractional))
        integers[order[:remainder]] += 1
    if int(integers.sum()) != national_target:
        raise RuntimeError("district integer populations do not conserve national total")
    if np.any(integers <= 0):
        raise RuntimeError("nonpositive district population after WorldPop aggregation")

    rows = []
    for index, pcode in enumerate(pcodes):
        meta = district_meta[pcode]
        area_sqkm = float(meta["area_sqkm"])
        total = float(totals[index])
        sum_squares = float(squared_totals[index])
        rows.append({
            "district_id": pcode,
            "district_name": meta["district_name"],
            "province_id": meta["province_id"],
            "province_name": meta["province_name"],
            "region_id": meta["region_id"],
            "worldpop_2004_float": f"{totals[index]:.6f}",
            "population_2004": int(integers[index]),
            "area_sqkm": f"{area_sqkm:.8f}",
            "population_density_per_sqkm": f"{total / area_sqkm:.8f}",
            "positive_worldpop_1km_cells": int(populated_cells[index]),
            # Expected grid-cell population experienced by a randomly selected
            # resident. This is threshold-free and rises when settlement is
            # concentrated into denser 1-km cells.
            "population_weighted_cell_density": f"{sum_squares / total:.8f}",
            # Inverse-HHI effective number of populated cells. Together with
            # total population it distinguishes diffuse from concentrated
            # settlement without choosing an arbitrary urban cutoff.
            "effective_populated_cells": f"{(total * total) / sum_squares:.8f}",
            "settlement_concentration_hhi": f"{sum_squares / (total * total):.12f}",
        })
    rows.sort(key=lambda row: row["district_id"])
    with (OUT / "population_2004.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    manifest = {
        "schema_version": "1.0.0",
        "worldpop_sha256": digest(WORLDPOP),
        "cod_sha256": digest(COD),
        "district_registry_sha256": digest(DISTRICTS),
        "districts": len(rows),
       "national_population_2004": national_target,
       "retained_settlement_covariates": [
           "population_density_per_sqkm",
           "positive_worldpop_1km_cells",
           "population_weighted_cell_density",
           "effective_populated_cells",
           "settlement_concentration_hhi",
       ],
       "matched_positive_grid_points": matched_points,
        "boundary_reassigned_positive_grid_points": boundary_reassigned_points,
       "matched_population": matched_population,
        "boundary_reassigned_population": boundary_reassigned_population,
        "boundary_reassigned_population_share": boundary_reassigned_population / max(
            1e-12, matched_population + boundary_reassigned_population
        ),
        "maximum_boundary_reassignment_km": maximum_boundary_reassignment_km,
        "boundary_harmonization_rule": "positive WorldPop cells outside COD polygons are assigned to nearest COD district; abort above 10 km",
        "integerization": "floor district zonal sums then largest fractional remainder; national rounded total conserved",
        "future_outcomes_used": False,
    }
    (OUT / "population_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
