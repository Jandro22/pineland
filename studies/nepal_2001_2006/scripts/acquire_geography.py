"""Acquire the non-redistributed provisional 75-district geometry."""
from __future__ import annotations

import hashlib
from pathlib import Path
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "studies" / "nepal_2001_2006" / "data" / "raw"
URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_NPL_3.json.zip"
EXPECTED = "028544920ca55f21d342b31c280554368aebf1f4415164ed30f64658c1975385"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    archive = RAW / "gadm41_NPL_3.json.zip"
    if not archive.exists():
        urllib.request.urlretrieve(URL, archive)
    actual = digest(archive)
    if actual != EXPECTED:
        raise RuntimeError(f"frozen geography changed: expected {EXPECTED}, got {actual}")
    destination = RAW / "gadm41"
    destination.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(destination)
    print(f"verified {archive} sha256={actual}")


if __name__ == "__main__":
    main()
