"""Fail-closed validation for historical_database_standard_v2 bundles."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
STANDARD=json.loads((ROOT/"studies/research_program/historical_database_standard_v2.json").read_text(encoding="utf-8"))

def sha256(p:Path)->str:
    h=hashlib.sha256();
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def validate(bundle:Path)->dict:
    manifest=json.loads((bundle/"dataset_manifest.json").read_text(encoding="utf-8")); quality=json.loads((bundle/"quality_report.json").read_text(encoding="utf-8")); obs=json.loads((bundle/"observability_map.json").read_text(encoding="utf-8"))
    checks={}
    checks["standard_hash_matches"]=manifest.get("standard_sha256")==sha256(ROOT/"studies/research_program/historical_database_standard_v2.json")
    checks["builder_hash_present"]=bool(manifest.get("builder_sha256"))
    checks["source_hashes_valid"]=all((ROOT/x["path"]).is_file() and sha256(ROOT/x["path"])==x["sha256"] for x in manifest.get("source_artifacts",[]))
    for name,spec in STANDARD["required_tables"].items():
        p=bundle/name; key=name.replace(".parquet","")
        checks[f"{key}_exists"]=p.is_file()
        if p.is_file():
            df=pd.read_parquet(p); checks[f"{key}_schema"]=set(spec["required_columns"]).issubset(df.columns)
            art=manifest["artifacts"].get(key,{}); checks[f"{key}_hash"]=art.get("sha256")==sha256(p) and art.get("rows")==len(df)
    if (bundle/"events.parquet").is_file():
        e=pd.read_parquet(bundle/"events.parquet")
        checks["event_ids_unique"]=e.source_event_id.astype(str).is_unique if len(e) else True
        if len(e):
            lo=pd.to_numeric(e.fatalities_low,errors="coerce");be=pd.to_numeric(e.fatalities_best,errors="coerce");hi=pd.to_numeric(e.fatalities_high,errors="coerce");checks["fatality_values_nonnegative"]=bool((lo.dropna()>=0).all() and (be.dropna()>=0).all() and (hi.dropna()>=0).all())
        else: checks["fatality_values_nonnegative"]=True
    if (bundle/"unit_time.parquet").is_file():
        u=pd.read_parquet(bundle/"unit_time.parquet"); allowed=set(STANDARD["required_tables"]["unit_time.parquet"]["observation_status_enum"]); checks["unit_time_status_enum"]=set(u.observation_status.dropna().astype(str)).issubset(allowed)
        g=pd.read_parquet(bundle/"geography.parquet"); checks["unit_time_units_in_geography"]=bool(len(u)==0 or set(u.unit_id.astype(str)).issubset(set(g.unit_id.astype(str))))
    checks["quality_internal_checks_pass"]=all(quality.get("checks",{}).values())
    checks["observability_frozen_theory_version"]=obs.get("reduced_theory_version")=="reduced_theory_specification_v2.json"
    if quality.get("license")=="SEALED_HOLDOUT": checks["sealed_holdout_has_no_events"]=len(pd.read_parquet(bundle/"events.parquet"))==0 and "not opened or read" in manifest.get("historical_target_firewall","")
    return {"case_id":manifest.get("case_id"),"license":quality.get("license"),"passed":all(checks.values()),"checks":checks,"blocked_reasons":quality.get("blocked_reasons",[])}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("bundles",nargs="+");ns=ap.parse_args();results=[validate((ROOT/Path(x)) if not Path(x).is_absolute() else Path(x)) for x in ns.bundles];print(json.dumps(results,indent=2));raise SystemExit(0 if all(r["passed"] for r in results) else 2)
if __name__=="__main__":main()
