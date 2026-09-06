"""Build deterministic blind source-locator tasks for civilian-harm recoding."""
from __future__ import annotations
import csv, hashlib, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies/research_program"
FIRST = PROGRAM / "civilian_harm_first_coder_v1.csv"
EXPOSURE = PROGRAM / "civilian_harm_source_exposure_log_v1.csv"
CONTRACT = PROGRAM / "civilian_harm_adjudication_contract_v1.json"
INSTRUCTIONS = PROGRAM / "civilian_harm_second_coder_instructions_v1.md"
PACKET = PROGRAM / "civilian_harm_second_coder_packet_v1.csv"
KEY = PROGRAM / "civilian_harm_second_coder_blind_key_v1.json"
MANIFEST = PROGRAM / "civilian_harm_second_coder_packet_manifest_v1.json"
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def blind_id(source_id, locator): return hashlib.sha256(f"pineland-civilian-harm-v1|{source_id}|{locator}".encode()).hexdigest()[:12]
def main():
    with FIRST.open(encoding="utf-8-sig", newline="") as f: first=list(csv.DictReader(f))
    with EXPOSURE.open(encoding="utf-8-sig", newline="") as f: exposure=list(csv.DictReader(f))
    source_by_id={r["candidate_source_id"]:r for r in exposure}
    if len(source_by_id)!=len(exposure): raise RuntimeError("candidate_source_id must be unique")
    manual_ids={sid for sid,r in source_by_id.items() if r["source_family"]!="UCDP_GED"}
    locators={sid:set() for sid in manual_ids}
    for row in first:
        sid=row["candidate_source_id"]
        if sid in locators: locators[sid].add(row["source_locator"] or "whole_source_review")
    for sid in manual_ids:
        if not locators[sid]: locators[sid].add("whole_source_review_against_frozen_coding_contract")
    fields=["blind_task_id","candidate_source_id","case_id","publisher_or_originator","source_title","source_url_or_archive_ref","locator_hint","task_instruction"]
    packet=[]; key=[]
    for sid in sorted(locators):
        src=source_by_id[sid]
        for locator in sorted(locators[sid]):
            bid=blind_id(sid,locator)
            packet.append({"blind_task_id":bid,"candidate_source_id":sid,"case_id":src["case_id"],"publisher_or_originator":src["publisher_or_originator"],"source_title":src["source_title"],"source_url_or_archive_ref":src["source_url_or_archive_ref"],"locator_hint":locator,"task_instruction":"Independently extract all claims at this locator that satisfy civilian_harm_coding_contract_v1.json; output NONE if there are no admissible claims."})
            key.append({"blind_task_id":bid,"candidate_source_id":sid,"source_locator":locator,"first_coder_claim_ids":sorted(r["harm_record_id"] for r in first if r["candidate_source_id"]==sid and (r["source_locator"] or "whole_source_review")==locator)})
    if len({r["blind_task_id"] for r in packet})!=len(packet): raise RuntimeError("blind task id collision")
    with PACKET.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(packet)
    key_payload={"schema_version":"pineland.civilian_harm_second_coder_blind_key.v1","status":"confidential_mapping_not_second_coder_input","first_coder_sha256":sha(FIRST),"exposure_log_sha256":sha(EXPOSURE),"adjudication_contract_sha256":sha(CONTRACT),"tasks":key}
    KEY.write_text(json.dumps(key_payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    manifest={"schema_version":"pineland.civilian_harm_second_coder_packet_manifest.v1","status":"packet_frozen_before_second_coding","task_count":len(packet),"candidate_source_count":len({r["candidate_source_id"] for r in packet}),"case_counts":{case:sum(r["case_id"]==case for r in packet) for case in sorted({r["case_id"] for r in packet})},"packet_sha256":sha(PACKET),"blind_key_sha256":sha(KEY),"instructions_sha256":sha(INSTRUCTIONS),"adjudication_contract_sha256":sha(CONTRACT),"structured_ucdp_excluded_from_human_packet":True}
    MANIFEST.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(manifest,indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
