"""Acquire Nigeria 2014 non-outcome case inputs without reading GED rows."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
DESIGN = ROOT / "studies/research_program/nigeria_2014_external_holdout_design.json"
CERT = ROOT / "studies/research_program/nigeria_2014_external_holdout_certificate.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def acquire(output_dir: Path) -> dict:
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    cert = json.loads(CERT.read_text(encoding="utf-8"))
    if cert["target_labels_previously_inspected"] is not False:
        raise RuntimeError("Nigeria holdout certificate is already contaminated")
    output_dir.mkdir(parents=True, exist_ok=True)

    geography = output_dir / "gadm41_NGA_1.json.zip"
    population = output_dir / "nga_ppp_2014_1km_ASCII_XYZ.zip"
    ged = output_dir / "ged261-csv.zip"
    urllib.request.urlretrieve(design["geography_source"]["url"], geography)
    urllib.request.urlretrieve(design["population_source"]["url"], population)
    source_ged = ROOT / design["outcome_source"]["archive"]
    if sha256(source_ged) != design["outcome_source"]["archive_sha256"]:
        raise RuntimeError("source GED archive hash differs from sealed design")
    shutil.copyfile(source_ged, ged)

    payload = {
        "schema_version": "pineland.nigeria_2014_case_input_acquisition.v1",
        "target_rows_read": False,
        "ged_rows_read": False,
        "design_sha256": sha256(DESIGN),
        "exposure_certificate_sha256": sha256(CERT),
        "artifacts": {
            "gadm_admin1": {
                "path": str(geography.resolve()),
                "sha256": sha256(geography),
                "bytes": geography.stat().st_size,
            },
            "worldpop_2014": {
                "path": str(population.resolve()),
                "sha256": sha256(population),
                "bytes": population.stat().st_size,
            },
            "ged261": {
                "path": str(ged.resolve()),
                "sha256": sha256(ged),
                "bytes": ged.stat().st_size,
            },
        },
    }
    manifest = output_dir / "acquisition_manifest.json"
    manifest.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(acquire(args.output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
