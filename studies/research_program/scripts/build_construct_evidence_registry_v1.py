"""Build a hash-bound registry of current adjudicated construct evidence.

This registry hashes each coded record and binds it to any existing case source
manifest entry.  It deliberately does not download or alter source documents.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.reproducibility import file_sha256, repository_state  # noqa: E402

EVIDENCE = ROOT / "studies/nepal_2001_2006/data/processed/nepal_eastern_control_presence_adjudicated_v1.csv"
SOURCE_MANIFEST = ROOT / "studies/nepal_2001_2006/data/manifests/sources.json"
SUPPLEMENTAL_ARCHIVE = ROOT / "studies/research_program/nepal_construct_source_archive_manifest_v1.json"
ADJUDICATION = ROOT / "studies/research_program/nepal_control_presence_adjudication_v1.json"
IDENT_CONTRACT = ROOT / "studies/research_program/measurement_error_identification_contract_v1.json"
OUT = ROOT / "studies/research_program/construct_evidence_registry_v1.json"


def stable_hash(value) -> str:
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def source_family(row: dict[str, str]) -> dict[str, str]:
    publisher = row["publisher"].strip()
    if publisher == "Kantipur_via_Nepali_Times":
        return {
            "originating_family": "kantipur",
            "access_carrier": "nepali_times",
            "dependence_note": "Claim is attributed to Kantipur but accessed through Nepali Times; do not count carrier and origin as two independent sources."
        }
    mapping = {
        "Nepali Times": "nepali_times",
        "INSEC": "insec",
        "OHCHR": "ohchr",
        "The Himalayan Times": "himalayan_times",
    }
    family = mapping.get(publisher, publisher.lower().replace(" ", "_"))
    return {"originating_family": family, "access_carrier": family, "dependence_note": "single declared source family"}


def main() -> int:
    evidence = read_csv(EVIDENCE)
    manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    manifest_by_id = {item["source_id"]: item for item in manifest.get("sources", [])}
    supplemental = (
        json.loads(SUPPLEMENTAL_ARCHIVE.read_text(encoding="utf-8"))
        if SUPPLEMENTAL_ARCHIVE.exists() else {"sources": []}
    )
    supplemental_by_id = {item["source_id"]: item for item in supplemental.get("sources", [])}
    records = []
    source_docs = {}
    for row in evidence:
        family = source_family(row)
        manifest_item = manifest_by_id.get(row["source_id"])
        supplemental_item = supplemental_by_id.get(row["source_id"])
        if manifest_item:
            source_status = "registered_in_case_source_manifest"
        elif supplemental_item and supplemental_item.get("retrieval_status") == "archived":
            source_status = "registered_in_supplemental_construct_archive"
        else:
            source_status = "not_registered_in_any_source_archive"
        archive_sha = (
            manifest_item.get("archive_sha256") if manifest_item and manifest_item.get("archive_sha256")
            else supplemental_item.get("archive_sha256") if supplemental_item else None
        )
        immutable_bound = bool(archive_sha)
        record = {
            "record_id": row["record_id"],
            "blind_id": row["blind_id"],
            "source_id": row["source_id"],
            "source_title": row["source_title"],
            "publisher": row["publisher"],
            "source_url_or_archive_ref": row["source_url_or_archive_ref"],
            "source_family": family,
            "source_manifest_status": source_status,
            "source_archive_sha256": archive_sha,
            "source_content_immutable_bound": immutable_bound,
            "evidence_class": "direct_measurement",
            "district_id": row["district_id"],
            "district_name": row["district_name"],
            "date_start": row["date_start"],
            "date_end": row["date_end"],
            "actor_id": row["actor_id"],
            "observable": row["observable"],
            "value_or_category": row["value_or_category"],
            "spatial_scope": row["spatial_scope"],
            "temporal_precision": row["temporal_precision"],
            "confidence": row["confidence"],
            "source_passage_or_precise_locator": row["source_passage_or_precise_locator"],
            "coding_status": row["adjudication_status"],
        }
        record["coded_record_sha256"] = stable_hash(record)
        records.append(record)
        doc = source_docs.setdefault(row["source_id"], {
            "source_id": row["source_id"],
            "source_title": row["source_title"],
            "publisher": row["publisher"],
            "source_url_or_archive_ref": row["source_url_or_archive_ref"],
            "source_family": family,
            "case_source_manifest_status": source_status,
            "archive_sha256": archive_sha,
            "immutable_content_bound": immutable_bound,
            "record_ids": [],
        })
        doc["record_ids"].append(row["record_id"])

    payload = {
        "schema_version": "pineland.construct_evidence_registry.v1",
        "status": "registry_not_measurement_parameter_estimation",
        "case_id": "nepal_2001_2006",
        "evidence_input_sha256": file_sha256(EVIDENCE),
        "source_manifest_sha256": file_sha256(SOURCE_MANIFEST),
        "supplemental_source_archive_sha256": file_sha256(SUPPLEMENTAL_ARCHIVE) if SUPPLEMENTAL_ARCHIVE.exists() else None,
        "adjudication_sha256": file_sha256(ADJUDICATION),
        "measurement_identification_contract_sha256": file_sha256(IDENT_CONTRACT),
        "record_count": len(records),
        "source_document_count": len(source_docs),
        "immutable_source_document_count": sum(bool(item["immutable_content_bound"]) for item in source_docs.values()),
        "source_family_count": len({item["source_family"]["originating_family"] for item in source_docs.values()}),
        "source_documents": sorted(source_docs.values(), key=lambda item: item["source_id"]),
        "records": records,
        "rules": {
            "record_hash_is_coding_identity_not_source_content_identity": True,
            "source_without_archive_hash_is_not_immutable_content_bound": True,
            "model_output_is_not_an_empirical_source": True
        },
        "repository_state": repository_state(ROOT),
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "records": payload["record_count"],
        "source_documents": payload["source_document_count"],
        "immutable_source_documents": payload["immutable_source_document_count"],
        "originating_source_families": payload["source_family_count"],
        "output_sha256": file_sha256(OUT),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
