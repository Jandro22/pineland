"""Reproduce the frozen UCDP GED 26.1 acquisition."""
from __future__ import annotations

import hashlib
from pathlib import Path
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "studies" / "nepal_2001_2006" / "data" / "raw"
URL = "https://ucdp.uu.se/downloads/ged/ged261-csv.zip"
EXPECTED_SHA256 = "8c941d84954e555ee2e54f40fa04d9203bf1e2f962203d0a9930966c4947c667"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    archive = RAW / "ged261-csv.zip"
    if not archive.exists():
        urllib.request.urlretrieve(URL, archive)
    actual = sha256(archive)
    if actual != EXPECTED_SHA256:
        raise RuntimeError(
            f"UCDP archive hash changed: expected {EXPECTED_SHA256}, got {actual}. "
            "Do not silently update a frozen study source."
        )
    destination = RAW / "ged261"
    destination.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(destination)
    print(f"verified {archive} sha256={actual}")


if __name__ == "__main__":
    main()
