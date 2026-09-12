"""Acquire a compact direct-NARA verification set for the Vietnam case.

The goal is strong provenance without mirroring the full Vietnam electronic
archive.  We download all SITRA translated data files, the national police and
territorial-force data needed for human-capital/state-capacity tests, the HES
gazetteer, and one canonical tab-delimited HES/HAMLA lineage rather than both
fixed-width and tab-delimited duplicates.
"""
from __future__ import annotations

import hashlib
import gzip
import json
from pathlib import Path
from typing import Any
import requests

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "studies/research_program/source_cache/nara/vietnam_minimal_v1"

SERIES = {
    "sitra": "604416",
    "nape": "620476",
    "hes": "4616225",
    "npiass": "609777",
    "tfes_vnus": "598773",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def get_json(url: str) -> dict[str, Any]:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.json()


def descendants(series_id: str) -> list[dict[str, Any]]:
    j = get_json(
        f"https://catalog.archives.gov/proxy/records/search?ancestorNaId={series_id}&levelOfDescription=fileUnit&rows=200"
    )
    return [h["_source"]["record"] for h in j["body"]["hits"]["hits"]]


def details(naid: str) -> dict[str, Any]:
    j = get_json(f"https://catalog.archives.gov/proxy/records/search?naId={naid}")
    return j["body"]["hits"]["hits"][0]["_source"]["record"]


def wanted(series: str, file_unit: dict[str, Any], obj: dict[str, Any]) -> bool:
    fn = str(obj.get("objectFilename", ""))
    designator = str(obj.get("objectDesignator", ""))
    title = str(file_unit.get("title", ""))
    if series == "sitra":
        # Keep all four translated SITRA data spans plus shared layout/docs.
        return designator == "Electronic Records" or fn in {
            "SITRA.TR.LAY.txt", "131.1DP.pdf", "SITRA_TSS131.pdf"
        }
    if series == "nape":
        return True
    if series == "npiass":
        # Geography/coding bridge only; do not mirror the 29 MiB person-level
        # NPIASS-II file at this stage.
        return fn in {
            "RG349.NPIASS.HGAZ", "RG349.NPIASS.HGZSF.txt", "RG349.NPIASS.GZSF.txt",
            "RG349.NPIASS.HVGZ.txt", "133.2DP.pdf", "NPIASS_TSS133.pdf", "RG349.NPIASS.GNBK"
        }
    if series == "tfes_vnus":
        return True
    if series == "hes":
        # Use one canonical ASCII tab-delimited representation and its layouts,
        # not the duplicated fixed-width variants. Limit to HAMLA 1967-69 and
        # HES70 1969-71, matching the local compact extracts used in this case.
        relevant_title = (
            "HAMLA" in title or "HES70" in title
        ) and any(y in title for y in ["1967", "1968", "1969", "1970", "1971"])
        if not relevant_title:
            return False
        if designator == "Electronic Records":
            return "ARTB" in fn
        return fn.endswith("ARLAY.html") or fn in {"132.1DP.pdf", "132.2DP.pdf", "HES330_TSS132.pdf"}
    return False


def download(
    url: str,
    dest: Path,
    expected_bytes: int | None,
    strict_catalog_size: bool,
) -> dict[str, Any]:
    """Download and content-hash a NARA object.

    NARA Catalog objectFileSize occasionally differs from the served object by
    a few bytes. Treat <=1 KiB as catalog-metadata drift, record it explicitly,
    and fail on larger discrepancies. Large non-PDF/non-ZIP data files are
    gzip-compressed *after* hashing to keep the local provenance cache compact.
    """
    gz_dest = dest.with_name(dest.name + ".gz")
    if gz_dest.exists():
        # Existing compressed object is accepted only through its sidecar,
        # written after a fully verified download.
        sidecar = gz_dest.with_name(gz_dest.name + ".source.json")
        if sidecar.exists():
            return json.loads(sidecar.read_text(encoding="utf-8"))
    if (
        dest.exists()
        and expected_bytes is not None
        and strict_catalog_size
        and abs(dest.stat().st_size - expected_bytes) > 1024
    ):
        dest.unlink()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with dest.open("wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
    actual = dest.stat().st_size
    delta = None if expected_bytes is None else actual - expected_bytes
    if delta is not None and strict_catalog_size and abs(delta) > 1024:
        raise RuntimeError(f"catalog size mismatch >1KiB for {dest.name}: {actual} != {expected_bytes}")
    source_sha = sha256(dest)
    compress = dest.suffix.lower() not in {".pdf", ".zip", ".gz"} and actual > 256 * 1024
    stored = dest
    if compress:
        with dest.open("rb") as src, gzip.open(gz_dest, "wb", compresslevel=9) as dst:
            for block in iter(lambda: src.read(1024 * 1024), b""):
                dst.write(block)
        stored = gz_dest
        dest.unlink()
    result = {
        "catalog_expected_bytes": expected_bytes,
        "source_bytes": actual,
        "catalog_size_delta_bytes": delta,
        "catalog_size_check": "strict_data_object" if strict_catalog_size else "metadata_only_documentation",
        "source_sha256": source_sha,
        "stored_path": stored.relative_to(ROOT).as_posix(),
        "stored_bytes": stored.stat().st_size,
        "stored_sha256": sha256(stored),
        "storage_encoding": "gzip" if compress else "identity",
    }
    if compress:
        gz_dest.with_name(gz_dest.name + ".source.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return result


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    selected = []
    for series, sid in SERIES.items():
        for fu in descendants(sid):
            rec = details(str(fu["naId"]))
            for obj in rec.get("digitalObjects", []):
                if not wanted(series, rec, obj):
                    continue
                fn = str(obj.get("objectFilename"))
                url = str(obj.get("objectUrl"))
                size = int(obj.get("objectFileSize") or 0) or None
                dest = OUT / series / str(rec["naId"]) / fn
                stored = download(
                    url,
                    dest,
                    size,
                    strict_catalog_size=obj.get("objectDesignator") == "Electronic Records",
                )
                selected.append({
                    "series": series,
                    "series_naid": sid,
                    "file_unit_naid": str(rec["naId"]),
                    "file_unit_title": rec.get("title"),
                    "filename": fn,
                    "url": url,
                    "object_id": obj.get("objectId"),
                    "object_designator": obj.get("objectDesignator"),
                    "object_type": obj.get("objectType"),
                    **stored,
                })
    manifest = {
        "schema_version": "pineland.vietnam_direct_nara_minimal.v1",
        "selection_policy": {
            "sitra": "all translated data spans plus shared documentation",
            "nape": "complete file unit",
            "hes": "tab-delimited HAMLA 1967-69 and HES70 1969-71 only; fixed-width duplicates excluded",
            "npiass": "HES gazetteer/coding documentation and Greenbook only",
            "tfes_vnus": "complete TFES/VNUS file units",
        },
        "files": selected,
        "total_source_bytes": sum(x["source_bytes"] for x in selected),
        "total_stored_bytes": sum(x["stored_bytes"] for x in selected),
    }
    m = OUT / "manifest.json"
    m.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "files": len(selected),
        "source_mib": manifest["total_source_bytes"] / 1024 / 1024,
        "stored_mib": manifest["total_stored_bytes"] / 1024 / 1024,
        "manifest": str(m),
    }, indent=2))


if __name__ == "__main__":
    main()
