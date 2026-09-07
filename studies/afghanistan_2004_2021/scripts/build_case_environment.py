"""Build the untuned Afghanistan schema-v3 empirical case environment.

The physical world uses the 401 harmonized COD districts and their named
administrative centers.  Province and humanitarian-region containers are kept
as explicit hierarchy metadata.  Initial Taliban anchors are derived only from
the immediately pre-benchmark 2003 Government of Afghanistan--Taleban UCDP
state-conflict events, mapped spatially into the frozen COD district polygons.
No 2004-2021 benchmark outcome is used in case construction.
"""
from __future__ import annotations

import csv
from collections import deque
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pandas as pd
from shapely import STRtree, points
from shapely.geometry import shape


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "afghanistan_2004_2021"
RAW = STUDY / "data" / "raw"
PROCESSED = STUDY / "data" / "processed"
CONFIG = STUDY / "config"
DESIGN = CONFIG / "study_design.json"
COD = RAW / "afg_admin_boundaries.geojson.zip"
GED = RAW / "ged261-csv.zip"
OUT = CONFIG / "case_environment.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def topology_connectivity(neighbors: dict[str, list[str]]) -> dict[str, float]:
    """Return outcome-free percentile harmonic closeness on the district graph.

    The empirical adapter previously assigned connectivity=.5 to every Afghan
    district even though a frozen national adjacency graph was already part of
    the case package. Harmonic closeness uses only that pre-outcome topology.
    Percentile scaling preserves ordering without introducing a fitted
    coefficient or importing later road-network data.
    """
    nodes = sorted(neighbors)
    raw: dict[str, float] = {}
    for source in nodes:
        distance = {source: 0}
        queue = deque([source])
        while queue:
            node = queue.popleft()
            for target in neighbors.get(node, []):
                if target not in distance:
                    distance[target] = distance[node] + 1
                    queue.append(target)
        if len(distance) != len(nodes):
            raise RuntimeError(f"district adjacency disconnected from {source}")
        raw[source] = sum(
            1.0 / steps for target, steps in distance.items()
            if target != source and steps > 0
        ) / max(1, len(nodes) - 1)

    ordered_values = sorted(raw.values())
    connectivity = {}
    for node, value in raw.items():
        lower = sum(candidate < value for candidate in ordered_values)
        equal = sum(candidate == value for candidate in ordered_values)
        average_rank = lower + (equal - 1) / 2.0
        connectivity[node] = average_rank / max(1, len(nodes) - 1)
    return connectivity


def percentile_rank(values: dict[str, float]) -> dict[str, float]:
    """Average-rank percentile with no outcome or fitted coefficient."""
    ordered = sorted(values.values())
    result = {}
    for key, value in values.items():
        lower = sum(candidate < value for candidate in ordered)
        equal = sum(candidate == value for candidate in ordered)
        average_rank = lower + (equal - 1) / 2.0
        result[key] = average_rank / max(1, len(ordered) - 1)
    return result


def settlement_spatial_covariates(
    population_covariates: dict[str, dict[str, float]],
    graph_connectivity: dict[str, float],
) -> dict[str, dict[str, float]]:
    density_rank = percentile_rank({
        district_id: values["population_density_per_sqkm"]
        for district_id, values in population_covariates.items()
    })
    weighted_density_rank = percentile_rank({
        district_id: values["population_weighted_cell_density"]
        for district_id, values in population_covariates.items()
    })
    concentration_rank = percentile_rank({
        district_id: values["settlement_concentration_hhi"]
        for district_id, values in population_covariates.items()
    })
    result = {}
    for district_id in population_covariates:
        settlement_intensity = (
            density_rank[district_id] + weighted_density_rank[district_id]
        ) / 2.0
        concentration = concentration_rank[district_id]
        connectivity = graph_connectivity[district_id]
        result[district_id] = {
            "settlement_intensity": settlement_intensity,
            "urbanization": (settlement_intensity + concentration) / 2.0,
            "infrastructure": (
                settlement_intensity + connectivity
            ) / 2.0,
            "observability": (
                settlement_intensity + concentration + connectivity
            ) / 3.0,
        }
    return result


def preperiod_taliban_anchors(
    count: int = 8,
    *,
    include_background: bool = False,
) -> tuple[list[str], dict[str, int]] | tuple[list[str], dict[str, int], dict[str, int]]:
    """Return high-precision 2003 Taliban-conflict COD districts.

    The GED where_prec spatial-precision code is used. Codes 1-2 support a
    district-level assignment; lower-precision rows are deliberately excluded
    from exact district occupancy evidence rather than being over-localized.
    """
    with zipfile.ZipFile(COD) as archive:
        features = json.load(archive.open("afg_admin2.geojson"))["features"]
    polygons = [shape(feature["geometry"]) for feature in features]
    pcodes = [feature["properties"]["adm2_pcode"] for feature in features]
    tree = STRtree(polygons)

    with zipfile.ZipFile(GED) as archive:
        member = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
        frame = pd.read_csv(io.TextIOWrapper(archive.open(member), encoding="utf-8"), low_memory=False)
    eligible = frame[
        (frame["country"] == "Afghanistan") &
        (frame["year"] == 2003) &
        (frame["dyad_name"] == "Government of Afghanistan - Taleban") &
        (frame["type_of_violence"] == 1) &
        frame["longitude"].notna() & frame["latitude"].notna()
    ].reset_index(drop=True)
    subset = eligible[
        eligible["where_prec"].fillna(99).astype(float).le(2)
    ].reset_index(drop=True)
    point_array = points(subset["longitude"].to_numpy(dtype=float),
                         subset["latitude"].to_numpy(dtype=float))
    pairs = tree.query(point_array, predicate="within")
    mapping = {int(point_index): pcodes[int(polygon_index)]
               for point_index, polygon_index in zip(pairs[0], pairs[1])}
    if len(mapping) != len(subset):
        missing = len(subset) - len(mapping)
        raise RuntimeError(f"unmapped 2003 Taliban events: {missing}/{len(subset)}")
    counts: dict[str, int] = {}
    for index in range(len(subset)):
        pcode = mapping[index]
        counts[pcode] = counts.get(pcode, 0) + 1
    ordered = sorted(counts, key=lambda pcode: (-counts[pcode], pcode))
    if not include_background:
        return ordered[:count], dict(sorted(counts.items()))

    all_points = points(
        eligible["longitude"].to_numpy(dtype=float),
        eligible["latitude"].to_numpy(dtype=float),
    )
    all_pairs = tree.query(all_points, predicate="within")
    all_mapping = {
        int(point_index): pcodes[int(polygon_index)]
        for point_index, polygon_index in zip(all_pairs[0], all_pairs[1])
    }
    if len(all_mapping) != len(eligible):
        missing = len(eligible) - len(all_mapping)
        raise RuntimeError(f"unmapped eligible 2003 Taliban events: {missing}/{len(eligible)}")
    province_by_pcode = {
        feature["properties"]["adm2_pcode"]: feature["properties"]["adm1_pcode"]
        for feature in features
    }
    background: dict[str, int] = {}
    for index, row in eligible.iterrows():
        precision = float(row["where_prec"]) if pd.notna(row["where_prec"]) else 99.0
        if precision > 2:
            province_id = province_by_pcode[all_mapping[int(index)]]
            background[province_id] = background.get(province_id, 0) + 1
    return ordered[:count], dict(sorted(counts.items())), dict(sorted(background.items()))


def main() -> None:
    CONFIG.mkdir(parents=True, exist_ok=True)
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    region_rows = rows(PROCESSED / "regions.csv")
    province_rows = rows(PROCESSED / "provinces.csv")
    district_rows = rows(PROCESSED / "districts.csv")
    center_rows = rows(PROCESSED / "district_centers.csv")
    population_rows = rows(PROCESSED / "population_2004.csv")
    adjacency = json.loads((PROCESSED / "district_adjacency.json").read_text(encoding="utf-8"))
    graph_connectivity = topology_connectivity(adjacency["neighbors"])
    if (len(region_rows), len(province_rows), len(district_rows), len(center_rows),
            len(population_rows)) != (8, 34, 401, 401, 401):
        raise RuntimeError("unexpected Afghanistan processed geography dimensions")

    population = {row["district_id"]: int(row["population_2004"])
                  for row in population_rows}
    population_covariates = {
        row["district_id"]: {
            "population_density_per_sqkm": float(row["population_density_per_sqkm"]),
            "positive_worldpop_1km_cells": int(row["positive_worldpop_1km_cells"]),
            "population_weighted_cell_density": float(
                row["population_weighted_cell_density"]
            ),
            "effective_populated_cells": float(row["effective_populated_cells"]),
            "settlement_concentration_hhi": float(row["settlement_concentration_hhi"]),
        }
        for row in population_rows
    }
    spatial_covariates = settlement_spatial_covariates(
        population_covariates, graph_connectivity
    )
    centers = {row["district_id"]: row for row in center_rows}
    if set(population) != {row["district_id"] for row in district_rows} or set(centers) != set(population):
        raise RuntimeError("district population/center registry mismatch")

    containers = []
    for row in sorted(region_rows, key=lambda item: item["region_id"]):
        containers.append({
            "container_id": row["region_id"], "name": row["region_name"],
            "level": "region", "is_geographic_holdout": row["is_geographic_holdout"] == "true",
        })
    for row in sorted(province_rows, key=lambda item: item["province_id"]):
        containers.append({
            "container_id": row["province_id"], "name": row["province_name"],
            "level": "province", "parent_id": row["region_id"],
            "is_geographic_holdout": row["is_geographic_holdout"] == "true",
        })

    districts = []
    localities = []
    for row in sorted(district_rows, key=lambda item: item["district_id"]):
        district_id = row["district_id"]
        center = centers[district_id]
        district_population = population[district_id]
        districts.append({
            "district_id": district_id,
            "name": row["district_name"],
            "population": district_population,
            "container_ids": {"region": row["region_id"], "province": row["province_id"]},
            "terrain": "empirical mixed terrain",
            "urbanization": spatial_covariates[district_id]["urbanization"],
            "language_pattern": "FS",
            "connectivity": graph_connectivity[district_id],
            "empirical_covariates": population_covariates[district_id],
            "role": "harmonized 2004-2021 physical district",
            "unit_type": row["unit_type"],
        })
        capital_level = int(center["capital_level"])
        locality_kind = "city" if capital_level in {0, 1} else "town"
        localities.append({
            "locality_id": center["locality_id"],
            "district_id": district_id,
            "name": center["name"],
            "kind": locality_kind,
            "population": district_population,
            "x_km": float(center["x_km"]),
            "y_km": float(center["y_km"]),
            "administrative_role": "district_headquarters",
            "terrain_friction": 1.0,
            "infrastructure": spatial_covariates[district_id]["infrastructure"],
            "administrative_capacity": 0.5,
            "observability": spatial_covariates[district_id]["observability"],
            "capital_level": capital_level,
            "empirical_covariates": {
                **population_covariates[district_id],
                **spatial_covariates[district_id],
            },
        })

    locality_adjacency = {
        f"{district_id}-HQ": [f"{neighbor}-HQ" for neighbor in neighbors]
        for district_id, neighbors in adjacency["neighbors"].items()
    }
    anchors, preperiod_counts, preperiod_background = preperiod_taliban_anchors(
        8,
        include_background=True,
    )
    payload = {
        "schema_version": "3.0.0",
        "case_id": "afghanistan_2004_2021_untuned_v1",
        "study_id": "afghanistan_2004_2021",
        "construct": (
            "401 harmonized COD districts with named administrative-center localities; "
            "province and humanitarian-region hierarchy retained explicitly"
        ),
        "primary_validation_unit": "province_week",
        "secondary_validation_unit": "district_period_when_crosswalk_high_confidence",
        "geographic_containers": containers,
        "districts": districts,
        "localities": localities,
        "adjacency": locality_adjacency,
        "initial_insurgent_locality_ids": [f"{district_id}-HQ" for district_id in anchors],
        "initial_condition_rule": (
            "eight highest-count COD districts for Government of Afghanistan-Taleban "
            "state-conflict events in calendar year 2003 with GED where_prec <= 2; "
            "benchmark period begins 2004-01-01"
        ),
        "preperiod_location_precision_rule": {
            "source_field": "GED where_prec",
            "district_assignment": "codes 1-2 only",
            "lower_precision_handling": "excluded from exact district counts; "
            "available only for future province/background aggregation",
        },
        "preperiod_taliban_state_conflict_counts_2003": preperiod_counts,
        "preperiod_taliban_state_conflict_province_background_counts_2003": (
            preperiod_background
        ),
        "actor_semantics": {
            "government": "Islamic Republic of Afghanistan state institutions",
            "fdf": "Afghan national security forces aggregate",
            "police": "Afghan police aggregate",
            "insurgent": "Taleban / Taliban movement",
        },
        "neutral_unidentified_inputs": {
            "terrain_friction": 1.0,
            "infrastructure": 0.5,
            "administrative_capacity": 0.5,
            "observability": 0.5,
            "language_pattern": "FS pending independent district language-profile integration",
        },
        "derived_non_outcome_inputs": {
            "district_connectivity": {
                "source": "district_adjacency.json",
                "estimand": "percentile harmonic closeness on the frozen 401-district adjacency graph",
                "historical_outcomes_used": False,
                "fitted_coefficients": False,
            },
            "worldpop_settlement_structure": {
                "source": "afg_ppp_2004_1km_UNadj_ASCII_XYZ.zip",
                "estimands": [
                    "population_density_per_sqkm",
                    "positive_worldpop_1km_cells",
                    "population_weighted_cell_density",
                    "effective_populated_cells",
                    "settlement_concentration_hhi",
                ],
                "historical_outcomes_used": False,
                "fitted_coefficients": False,
                "model_equations_currently_changed_by_covariates": True,
                "mapping": (
                    "equal-weight average-rank transforms into district "
                    "urbanization and locality infrastructure/observability"
                ),
            },
        },
        "source_hashes": {
            "study_design.json": sha256(DESIGN),
            "source_manifest.json": sha256(PROCESSED / "source_manifest.json"),
            "geography_manifest.json": sha256(PROCESSED / "geography_manifest.json"),
            "population_manifest.json": sha256(PROCESSED / "population_manifest.json"),
            "districts.csv": sha256(PROCESSED / "districts.csv"),
            "district_centers.csv": sha256(PROCESSED / "district_centers.csv"),
            "district_adjacency.json": sha256(PROCESSED / "district_adjacency.json"),
            "population_2004.csv": sha256(PROCESSED / "population_2004.csv"),
            "ged261-csv.zip": sha256(GED),
        },
        "outcome_data_used_for_geography": False,
        "benchmark_period_outcomes_used_for_initialization": False,
        "calibration_licensed": False,
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(OUT.relative_to(ROOT)),
        "sha256": sha256(OUT),
        "regions": 8, "provinces": 34, "districts": 401, "localities": 401,
        "initial_taliban_anchors": payload["initial_insurgent_locality_ids"],
        "benchmark_outcomes_used": False,
    }, indent=2))


if __name__ == "__main__":
    main()
