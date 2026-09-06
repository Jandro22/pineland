"""Build a deterministic blind packet for independent Nepal control/presence coding."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "studies/nepal_2001_2006/data/processed/nepal_eastern_control_presence_staging_v1.csv"
PACKET = ROOT / "studies/research_program/nepal_second_coder_packet_v1.csv"
KEY = ROOT / "studies/research_program/nepal_second_coder_blind_key_v1.json"
INSTRUCTIONS = ROOT / "studies/research_program/nepal_second_coder_instructions_v1.md"
NAMESPACE = "nepal-control-presence-second-coder-v1:"

LOCATOR_HINTS = {
    "nepalitimes_reciprocal_2005": "article body; inspect all Eastern-district statements",
    "nepalitimes_sankhuwasabha_2005": "article body; inspect Sankhuwasabha statements",
    "ohchr_nepal_2006_commission": "E/CN.4/2006/107, paragraph 56 / report page 17",
    "himalayantimes_jhapa_tax_2006": "article body, Damak report",
    "nepalitimes_code_breach_2006": "article body; inspect Sunsari/Khanar passage",
    "nepalitimes_misconduct_2006": "article body; inspect Morang rural-area passage",
    "nepalitimes_trekker_tax_2004": "article body; inspect Solukhumbu passage",
    "insec_yearbook_2005": "chapter 'Maoists Insurgency and The Fear', printed pp. 96-97",
}


def blind_id(record_id: str) -> str:
    return hashlib.sha256((NAMESPACE + record_id).encode("utf-8")).hexdigest()[:12]


def main() -> int:
    with SOURCE.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    packet_fields = [
        "blind_id", "source_title", "publisher", "source_url_or_archive_ref",
        "source_locator_hint", "target_district_id", "target_district_name",
        "sampling_date_start", "sampling_date_end",
        "coder_date_start", "coder_date_end", "actor_id", "observable",
        "value_or_category", "spatial_scope", "temporal_precision", "confidence",
        "coding_rationale", "second_coder", "second_coder_notes"
    ]
    packet_rows = []
    key = {}
    for row in rows:
        bid = blind_id(row["record_id"])
        key[bid] = {
            "first_coder_record_id": row["record_id"],
            "source_id": row["source_id"],
            "district_id": row["district_id"],
        }
        packet_rows.append({
            "blind_id": bid,
            "source_title": row["source_title"],
            "publisher": row["publisher"],
            "source_url_or_archive_ref": row["source_url_or_archive_ref"],
            "source_locator_hint": LOCATOR_HINTS.get(row["source_id"], "article/report body"),
            "target_district_id": row["district_id"],
            "target_district_name": row["district_name"],
            "sampling_date_start": row["date_start"],
            "sampling_date_end": row["date_end"],
            "coder_date_start": "",
            "coder_date_end": "",
            "actor_id": "",
            "observable": "",
            "value_or_category": "",
            "spatial_scope": "",
            "temporal_precision": "",
            "confidence": "",
            "coding_rationale": "",
            "second_coder": "",
            "second_coder_notes": "",
        })
    packet_rows.sort(key=lambda row: row["blind_id"])

    with PACKET.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=packet_fields)
        writer.writeheader()
        writer.writerows(packet_rows)
    KEY.write_text(json.dumps({
        "schema_version": "1.0.0",
        "namespace": NAMESPACE,
        "purpose": "Link blind second-coder rows to first-coder records only after independent coding is complete.",
        "do_not_provide_to_second_coder": True,
        "mapping": key,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    INSTRUCTIONS.write_text("""# Nepal control/presence second-coder protocol v1

Work only from `nepal_second_coder_packet_v1.csv` and the linked sources. Do **not** inspect the first-coder staging file or blind key until your coding is final.

For each row, independently decide whether the source supports a dated, actor-specific control/presence observable in the target district. The target district and sampling window identify the preregistered search cell; they are not a required answer. If the source does not support an admissible observation, write `NOT_ADMISSIBLE` in `observable` and explain why.

Allowed observables are: `government_armed_presence`, `maoist_armed_presence`, `government_administrative_presence`, `maoist_shadow_governance`, `checkpoint_or_patrol_presence`, `security_post_or_garrison_presence`, `territorial_access_constraint`, `territorial_control_claim`.

Do not infer control from violence, fatalities, attack occurrence, non-reporting, or presumed political support. Preserve the narrowest spatial and temporal scope directly supported by the source. Do not carry an observation forward/backward. Use `HIGH`, `MEDIUM`, or `LOW` confidence and explain the basis briefly.

Fill every `coder_*`, actor/observable/value/scope/confidence field plus your coder name/identifier. Return the completed CSV without consulting the first-pass codes. Adjudication occurs only after both codings are locked.
""", encoding="utf-8")
    print(json.dumps({
        "packet": str(PACKET),
        "blind_key": str(KEY),
        "instructions": str(INSTRUCTIONS),
        "rows": len(packet_rows),
        "first_coder_labels_exposed_in_packet": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
