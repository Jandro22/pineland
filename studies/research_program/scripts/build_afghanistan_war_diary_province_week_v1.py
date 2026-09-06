"""Materialize the preregistered Afghan War Diary province-week surface."""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta
import hashlib
from itertools import chain
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

from shapely.geometry import Point, shape
from shapely.strtree import STRtree


ROOT = Path(__file__).resolve().parents[3]
CONTRACT = (
    ROOT
    / "studies/research_program/afghanistan_awd_2007_independent_holdout_contract_v1.json"
)
ADMIN = (
    ROOT
    / "studies/afghanistan_2004_2021/data/raw/afg_admin_boundaries.geojson.zip"
)
PROVINCES = (
    ROOT
    / "studies/afghanistan_2004_2021/data/processed/provinces.csv"
)
INITIAL = date(2004, 1, 1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def week_index(when: date) -> int:
    return (when - INITIAL).days // 7


def parse_date(value: str, formats: list[str]) -> date:
    text = str(value or "").strip()
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unparseable DateOccurred: {value!r}")


def numeric(value: str) -> float:
    try:
        return max(0.0, float(str(value or "").strip()))
    except ValueError:
        return 0.0


def row_qualifies(
    row: dict[str, str],
    combat: re.Pattern[str],
    taliban: re.Pattern[str],
    enemy_affiliation: re.Pattern[str],
    enemy_display: re.Pattern[str],
) -> tuple[bool, bool]:
    casualty_fields = [
        "FriendlyWounded", "FriendlyKilled",
        "HostNationWounded", "HostNationKilled",
        "EnemyWounded", "EnemyKilled",
    ]
    enemy_fields = ["EnemyWounded", "EnemyKilled", "EnemyDetained"]
    violent_text = " ".join(
        str(row.get(field) or "")
        for field in ("EventType", "Category", "Title", "Summary")
    )
    adversary_text = " ".join(
        str(row.get(field) or "")
        for field in ("Title", "Summary")
    )
    violent = (
        any(numeric(row.get(field, "")) > 0 for field in casualty_fields)
        or bool(combat.search(violent_text))
    )
    hostile = (
        bool(enemy_affiliation.search(str(row.get("Affiliation") or "")))
        or bool(enemy_display.search(str(row.get("DisplayColor") or "")))
        or any(numeric(row.get(field, "")) > 0 for field in enemy_fields)
        or bool(taliban.search(adversary_text))
    )
    return violent, hostile


def _boundaries() -> tuple[list, list[str], STRtree]:
    with zipfile.ZipFile(ADMIN) as archive:
        data = json.loads(archive.read("afg_admin1.geojson"))
    geometries = []
    province_ids = []
    for feature in data["features"]:
        geometries.append(shape(feature["geometry"]))
        province_ids.append(feature["properties"]["adm1_pcode"])
    if len(geometries) != 34 or len(set(province_ids)) != 34:
        raise RuntimeError("frozen Afghanistan admin1 geography is not 34 provinces")
    return geometries, province_ids, STRtree(geometries)


def _province_for_point(
    longitude: float,
    latitude: float,
    geometries: list,
    province_ids: list[str],
    tree: STRtree,
) -> str | None:
    point = Point(longitude, latitude)
    matches = [
        int(index)
        for index in tree.query(point, predicate="intersects")
        if geometries[int(index)].covers(point)
    ]
    if len(matches) != 1:
        return None
    return province_ids[matches[0]]


def _extract_csv(archive_path: Path, destination: Path) -> Path:
    if archive_path.suffix.casefold() == ".csv":
        return archive_path
    destination.mkdir(parents=True, exist_ok=True)
    if archive_path.suffix.casefold() == ".zip":
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(destination)
    elif archive_path.suffix.casefold() == ".7z":
        seven_zip = shutil.which("7z")
        if not seven_zip:
            raise RuntimeError("7z is required to extract the frozen War Diary archive")
        subprocess.run(
            [seven_zip, "e", "-y", f"-o{destination}", str(archive_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    else:
        raise RuntimeError(f"unsupported War Diary archive type: {archive_path.suffix}")
    candidates = sorted(
        destination.rglob("*.csv"),
        key=lambda path: path.stat().st_size,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError("War Diary archive contained no CSV")
    return candidates[0]


def _province_registry() -> tuple[list[str], dict[str, str]]:
    with PROVINCES.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 34 or len({row["province_id"] for row in rows}) != 34:
        raise RuntimeError("frozen province registry is not 34 provinces")
    return (
        [row["province_id"] for row in rows],
        {row["province_id"]: row["region_id"] for row in rows},
    )


def build(
    archive_path: Path,
    acquisition_manifest: Path,
    output_dir: Path,
) -> dict:
    contract_bytes = CONTRACT.read_bytes()
    contract = json.loads(contract_bytes)
    acquisition = json.loads(acquisition_manifest.read_text(encoding="utf-8"))
    contract_sha = hashlib.sha256(contract_bytes).hexdigest()
    if acquisition["contract_sha256"] != contract_sha:
        raise RuntimeError("War Diary archive belongs to a different frozen mapping")
    if sha256_file(archive_path) != acquisition["artifact"]["sha256"]:
        raise RuntimeError("War Diary archive hash mismatch")

    mapping = contract["mapping_frozen_before_rows"]
    combat = re.compile(mapping["combat_regex"])
    taliban = re.compile(mapping["taliban_regex"])
    enemy_affiliation = re.compile(mapping["enemy_affiliation_regex"])
    enemy_display = re.compile(mapping["enemy_display_regex"])
    fields = list(contract["frozen_fields"])
    geometries, province_ids, tree = _boundaries()
    registry_ids, regions = _province_registry()
    if set(registry_ids) != set(province_ids):
        raise RuntimeError("province geometry and registry IDs disagree")

    positives: set[tuple[str, int]] = set()
    stats = {
        "rows_total": 0,
        "rows_2004_2009": 0,
        "qualifying_rows": 0,
        "rejected_invalid_date": 0,
        "rejected_invalid_coordinate": 0,
        "rejected_unmapped_point": 0,
    }
    with tempfile.TemporaryDirectory(prefix="pineland-awd-") as tmp:
        csv_path = _extract_csv(archive_path, Path(tmp))
        raw_sha = sha256_file(csv_path)
        with csv_path.open(
            encoding="utf-8-sig", errors="replace", newline=""
        ) as handle:
            reader = csv.reader(handle)
            first = next(reader, None)
            if first is None:
                raise RuntimeError("War Diary CSV is empty")
            if first and first[0].strip() == "ReportKey":
                header = [item.strip() for item in first]
            else:
                header = fields
                reader = chain([first], reader)
            if len(header) < len(fields):
                raise RuntimeError("War Diary CSV has fewer columns than frozen schema")
            for values in reader:
                stats["rows_total"] += 1
                if len(values) < len(fields):
                    values = list(values) + [""] * (len(fields) - len(values))
                row = dict(zip(header, values))
                try:
                    when = parse_date(row.get("DateOccurred", ""), mapping["date_formats"])
                except ValueError:
                    stats["rejected_invalid_date"] += 1
                    continue
                if not (2004 <= when.year <= 2009):
                    continue
                stats["rows_2004_2009"] += 1
                violent, hostile = row_qualifies(
                    row, combat, taliban, enemy_affiliation, enemy_display
                )
                if not (violent and hostile):
                    continue
                stats["qualifying_rows"] += 1
                try:
                    latitude = float(str(row.get("Latitude") or "").strip())
                    longitude = float(str(row.get("Longitude") or "").strip())
                except ValueError:
                    stats["rejected_invalid_coordinate"] += 1
                    continue
                province_id = _province_for_point(
                    longitude, latitude, geometries, province_ids, tree
                )
                if province_id is None:
                    stats["rejected_unmapped_point"] += 1
                    continue
                positives.add((province_id, week_index(when)))

    first_week = 0
    last_week = week_index(date(2009, 12, 31))
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "awd_afghanistan_province_week.csv"
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "province_id",
                "region_id",
                "week_index",
                "week_start",
                "awd_reported_hostile_active",
            ],
        )
        writer.writeheader()
        for index in range(first_week, last_week + 1):
            start = INITIAL + timedelta(days=7 * index)
            for province_id in registry_ids:
                writer.writerow({
                    "province_id": province_id,
                    "region_id": regions[province_id],
                    "week_index": index,
                    "week_start": start.isoformat(),
                    "awd_reported_hostile_active": int(
                        (province_id, index) in positives
                    ),
                })
    manifest = {
        "schema_version": "pineland.afghanistan.awd_province_week_manifest.v1",
        "contract_sha256": contract_sha,
        "acquisition_manifest_sha256": sha256_file(acquisition_manifest),
        "archive_sha256": sha256_file(archive_path),
        "extracted_csv_sha256": raw_sha,
        "mapping_changed_after_row_inspection": False,
        "pineland_outputs_used_to_build_mapping": False,
        "ucdp_outcomes_used_to_build_mapping": False,
        "stats": stats,
        "output": {
            "path": str(target.resolve().relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(target),
            "rows": (last_week - first_week + 1) * 34,
            "reported_active_cells": len(positives),
        },
        "interpretation_guard": mapping["negative_cell_rule"],
    }
    (output_dir / "province_week_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--acquisition-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(
        build(args.archive, args.acquisition_manifest, args.output_dir),
        indent=2,
        sort_keys=True,
    ))


if __name__ == "__main__":
    main()
