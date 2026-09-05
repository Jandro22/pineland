"""Acquire the official Nepal 2001 census report bundle."""
from __future__ import annotations

import hashlib
from pathlib import Path
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "studies" / "nepal_2001_2006" / "data" / "raw"
URL = "https://microdata.nsonepal.gov.np/index.php/catalog/42/download/543"
EXPECTED = "3cf0048fce15aba12adb9558ca45d5e3679d10e325e8911f7232f963cb137f9a"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    archive = RAW / "nepal_census_2001_national_report.zip"
    if not archive.exists():
        urllib.request.urlretrieve(URL, archive)
    actual = digest(archive)
    if actual != EXPECTED:
        raise RuntimeError(f"frozen census archive changed: expected {EXPECTED}, got {actual}")
    destination = RAW / "census2001"
    destination.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(destination)
    print(f"verified {archive} sha256={actual}")


if __name__ == "__main__":
    main()
