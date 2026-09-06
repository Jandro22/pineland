"""Materialize the frozen archival ACLED Afghanistan province-week mapping."""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = (
    ROOT
    / "studies/research_program/afghanistan_acled_independent_measurement_contract_v1.json"
)
ADMIN = (
    ROOT
    / "studies/afghanistan_2004_2021/data/raw/afg_admin_boundaries.geojson.zip"
)
CALENDAR = (
    ROOT
    / "studies/afghanistan_2004_2021/data/processed/province_week_panel.csv"
)
PROVINCES = (
    ROOT
    / "studies/afghanistan_2004_2021/data/processed/provinces.csv"
)
INITIAL = date(2004, 1, 1)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_event_date(value: str) -> date:
    text = value.strip()
    for fmt in ("%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unparseable EVENT_DATE: {value!r}")


def week_index(when: date) -> int:
    return (when - INITIAL).days // 7


def actor_mapping(
    row: dict[str, str], insurgent: re.Pattern[str], state: re.Pattern[str],
    actor_fields: list[str],
) -> tuple[bool, bool]:
    values = [str(row.get(field) or "") for field in actor_fields]
    return (
        any(insurgent.search(value) for value in values),
        any(state.search(value) for value in values),
    )


def _boundaries() -> tuple[list, list[str], STRtree]:
    with zipfile.ZipFile(ADMIN) as archive:
        data = json.loads(archive.read("afg_admin1.geojson"))
    geometries = []
    province_ids = []
    for feature in data["features"]:
        geometries.append(shape(feature["geometry"]))
        province_ids.append(feature["properties"]["adm1_pcode"])
    if len(geometries) != 34 or len(set(province_ids)) != 34:
        raise RuntimeError("Afghanistan admin1 geography is not the frozen 34-province surface")
    return geometries, province_ids, STRtree(geometries)


def _province_for_point(
    longitude: float, latitude: float, geometries: list,
    province_ids: list[str], tree: STRtree,
) -> str | None:
    point = Point(longitude, latitude)
    candidates = tree.query(point, predicate="intersects")
    matches = [
        int(index)
        for index in candidates
        if geometries[int(index)].covers(point)
    ]
    if len(matches) != 1:
        return None
    return province_ids[matches[0]]


def _calendar_rows(year: int) -> list[dict[str, str]]:
    # A calendar-year event on 1 January can belong to a seven-day cell whose
    # absolute week starts in the previous year. Build the grid from the frozen
    # absolute week definition rather than filtering on week_start text.
    with PROVINCES.open(encoding="utf-8", newline="") as handle:
        province_ids = [
            row["province_id"] for row in csv.DictReader(handle)
        ]
    if len(province_ids) != 34 or len(set(province_ids)) != 34:
        raise RuntimeError("frozen province registry is not a 34-province surface")
    first = week_index(date(year, 1, 1))
    last = week_index(date(year, 12, 31))
    rows = []
    for index in range(first, last + 1):
        start = INITIAL.fromordinal(INITIAL.toordinal() + 7 * index)
        for province_id in province_ids:
            rows.append({
                "province_id": province_id,
                "week_index": str(index),
                "week_start": start.isoformat(),
            })
    return rows


def build(bundle: Path, acquisition_manifest: Path, output_dir: Path) -> dict:
    contract_bytes = CONTRACT.read_bytes()
    contract_sha = sha256_bytes(contract_bytes)
    contract = json.loads(contract_bytes)
    acquisition = json.loads(acquisition_manifest.read_text(encoding="utf-8"))
    if acquisition["contract_sha256"] != contract_sha:
        raise RuntimeError("acquired ACLED bundle belongs to a different mapping contract")
    if sha256_file(bundle) != acquisition["artifacts"]["bundle"]["sha256"]:
        raise RuntimeError("ACLED bundle hash mismatch")

    mapping = contract["mapping_frozen_before_rows"]
    insurgent = re.compile(mapping["insurgent_regex"])
    state = re.compile(mapping["state_or_coalition_regex"])
    actor_fields = list(mapping["actor_fields"])
    primary_year = int(contract["target_surface"]["primary_year"])
    secondary_year = int(contract["target_surface"]["secondary_year"])
    years = (primary_year, secondary_year)

    geometries, province_ids, tree = _boundaries()
    with zipfile.ZipFile(bundle) as archive:
        event_name = contract["source"]["primary_event_file_declared_by_metadata"]
        event_bytes = archive.read(event_name)
    reader = csv.DictReader(io.StringIO(event_bytes.decode("utf-8-sig", errors="replace")))

    positives: dict[int, set[tuple[str, int]]] = {year: set() for year in years}
    stats = {
        "rows_total": 0,
        "afghanistan_rows": 0,
        "year_rows": {str(year): 0 for year in years},
        "actor_construct_rows": {str(year): 0 for year in years},
        "mapped_actor_construct_rows": {str(year): 0 for year in years},
        "rejected_no_actor_match": {str(year): 0 for year in years},
        "rejected_invalid_date": 0,
        "rejected_invalid_coordinate": 0,
        "rejected_unmapped_point": {str(year): 0 for year in years},
    }
    rejected_rows = []
    for row in reader:
        stats["rows_total"] += 1
        if str(row.get("COUNTRY") or "").strip().casefold() != "afghanistan":
            continue
        stats["afghanistan_rows"] += 1
        try:
            when = parse_event_date(str(row.get("EVENT_DATE") or ""))
        except ValueError:
            stats["rejected_invalid_date"] += 1
            continue
        if when.year not in years:
            continue
        year_key = str(when.year)
        stats["year_rows"][year_key] += 1
        has_insurgent, has_state = actor_mapping(
            row, insurgent, state, actor_fields
        )
        if not (has_insurgent and has_state):
            stats["rejected_no_actor_match"][year_key] += 1
            continue
        stats["actor_construct_rows"][year_key] += 1
        try:
            latitude = float(row["LATITUDE"])
            longitude = float(row["LONGITUDE"])
        except (TypeError, ValueError):
            stats["rejected_invalid_coordinate"] += 1
            continue
        province_id = _province_for_point(
            longitude, latitude, geometries, province_ids, tree
        )
        if province_id is None:
            stats["rejected_unmapped_point"][year_key] += 1
            rejected_rows.append({
                "ege_ID": row.get("ege_ID"),
                "EVENT_DATE": row.get("EVENT_DATE"),
                "LATITUDE": row.get("LATITUDE"),
                "LONGITUDE": row.get("LONGITUDE"),
                "reason": "point_not_uniquely_inside_frozen_admin1",
            })
            continue
        stats["mapped_actor_construct_rows"][year_key] += 1
        positives[when.year].add((province_id, week_index(when)))

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for year in years:
        calendar = _calendar_rows(year)
        keys = {
            (row["province_id"], int(row["week_index"]))
            for row in calendar
        }
        outside_calendar = sorted(positives[year] - keys)
        if outside_calendar:
            raise RuntimeError(
                f"ACLED {year} event cells fall outside the frozen calendar: "
                f"{outside_calendar[:5]}"
            )
        target = output_dir / f"acled_afghanistan_{year}_province_week.csv"
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "province_id", "week_index", "week_start",
                    "acled_reported_active",
                ],
            )
            writer.writeheader()
            for row in calendar:
                key = (row["province_id"], int(row["week_index"]))
                writer.writerow({
                    **row,
                    "acled_reported_active": int(key in positives[year]),
                })
        outputs[str(year)] = {
            "path": str(target.resolve().relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(target),
            "rows": len(calendar),
            "reported_active_cells": len(positives[year]),
        }

    rejected = output_dir / "acled_unmapped_actor_construct_rows.csv"
    with rejected.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ege_ID", "EVENT_DATE", "LATITUDE", "LONGITUDE", "reason"],
        )
        writer.writeheader()
        writer.writerows(rejected_rows)

    manifest = {
        "schema_version": "pineland.afghanistan.acled_province_week_manifest.v1",
        "contract_sha256": contract_sha,
        "acquisition_manifest_sha256": sha256_file(acquisition_manifest),
        "bundle_sha256": sha256_file(bundle),
        "event_file_sha256": sha256_bytes(event_bytes),
        "mapping_changed_after_row_inspection": False,
        "pineland_outputs_used_to_build_mapping": False,
        "ucdp_outcomes_used_to_build_mapping": False,
        "stats": stats,
        "outputs": outputs,
        "rejected_rows": {
            "path": str(rejected.resolve().relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(rejected),
            "rows": len(rejected_rows),
        },
        "interpretation_guard": (
            "A zero ACLED cell means source-silent under this archival collection, "
            "not known latent peace. This panel is licensed for independent "
            "source-family predictive scoring/concordance only."
        ),
    }
    manifest_path = output_dir / "province_week_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--acquisition-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(
        build(args.bundle, args.acquisition_manifest, args.output_dir),
        indent=2, sort_keys=True,
    ))


if __name__ == "__main__":
    main()
