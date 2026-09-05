"""Acquire and verify frozen public source files for the Afghanistan study."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "afghanistan_2004_2021"
RAW = STUDY / "data" / "raw"
PROCESSED = STUDY / "data" / "processed"

SOURCES = {
    "cod_boundaries": {
        "filename": "afg_admin_boundaries.geojson.zip",
        "url": "https://data.humdata.org/dataset/4c303d7b-8eae-4a5a-a3aa-b2331fa39d74/resource/330aad34-2254-4622-afac-e98ace1524ae/download/afg_admin_boundaries.geojson.zip",
        "sha256": "5ac4daf868a9a03cbb26d5702fdb52d06eb00d4b084483f991bffcf956aa8cc3",
        "role": "harmonized region/province/district polygons and administrative-center points",
    },
    "worldpop_2004": {
        "filename": "afg_ppp_2004_1km_UNadj_ASCII_XYZ.zip",
        "url": "https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/2004/AFG/afg_ppp_2004_1km_UNadj_ASCII_XYZ.zip",
        "sha256": "73e4fa24825238ccf361c09f45908f343f2c8b659d6df7b90ab91c6671139919",
        "role": "2004 initial population spatial distribution",
    },
    "cso_2016_crosscheck": {
        "filename": "afg_cso_pop_district_2016_2017_ocha_20160811.xlsx",
        "url": "https://data.humdata.org/dataset/914eb41e-adbc-4b1b-9ab3-b3787f3c7191/resource/575d52da-9de3-4cf3-87b8-e87c78634396/download/afg_cso_pop_district_2016_2017_ocha_20160811.xlsx",
        "sha256": "d2d145d929deb166973bdacde9cb1cf10921cc0d3269b5059d6f3a7bcb427a71",
        "role": "later official district-population cross-check only",
    },
    "ucdp_ged_26_1": {
        "filename": "ged261-csv.zip",
        "url": "https://ucdp.uu.se/downloads/ged/ged261-csv.zip",
        "sha256": "8c941d84954e555ee2e54f40fa04d9203bf1e2f962203d0a9930966c4947c667",
        "role": "organized-violence event observations",
    },
    "geonames": {
        "filename": "geonames_AF.zip",
        "url": "https://download.geonames.org/export/dump/AF.zip",
        "sha256": "09e9b3748ba4ff999ab6a6fc58d466679d26157ae0a76ca99d416d97079e4b94",
        "role": "settlement-name and coordinate cross-check / future locality expansion",
    },
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    verified = {}
    for source_id, source in SOURCES.items():
        path = RAW / source["filename"]
        downloaded = False
        if not path.exists():
            temporary = path.with_suffix(path.suffix + ".tmp")
            urllib.request.urlretrieve(source["url"], temporary)
            temporary.replace(path)
            downloaded = True
        actual = digest(path)
        if actual != source["sha256"]:
            raise RuntimeError(
                f"frozen source changed for {source_id}: expected {source['sha256']}, got {actual}"
            )
        verified[source_id] = {
            **source, "bytes": path.stat().st_size,
            "downloaded_this_invocation": downloaded,
        }
    payload = {
        "schema_version": "1.0.0",
        "study_id": "afghanistan_2004_2021",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": verified,
    }
    destination = PROCESSED / "source_manifest.json"
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
