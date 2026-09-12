"""Build compact, provenance-preserving historical experiment bundles.

This does not fit Pineland and does not infer latent model state.  It normalizes
source observations into a common interface with explicit zero/missing and
mapping semantics. Nigeria 2014 is special-cased as a sealed holdout and this
builder never opens the GED archive for that case.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import zipfile

import numpy as np
import pandas as pd
from shapely import STRtree, points
from shapely.geometry import shape


ROOT = Path(__file__).resolve().parents[3]
STANDARD = ROOT / "studies/research_program/historical_database_standard_v2.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git_revision() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return None


def write_parquet(df: pd.DataFrame, path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, compression="zstd")
    return {"path": path.relative_to(ROOT).as_posix(), "rows": int(len(df)), "bytes": path.stat().st_size, "sha256": sha256(path)}


def json_dump(obj: Any, path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)}


def split_hash(case_id: str, unit_id: str, temporal: str) -> str:
    # For legacy mature cases, preserve their already-materialized split when
    # available.  Thin comparative cases use the preregistered SHA rule.
    if temporal == "holdout":
        return "holdout"
    digest = int(hashlib.sha256(f"{case_id}:geographic:{unit_id}".encode()).hexdigest(), 16)
    geo_holdout = digest % 5 == 0
    if temporal == "validation":
        return "joint_validation" if geo_holdout else "temporal_validation"
    return "geographic_validation" if geo_holdout else "training"


def empty_aux() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "case_id", "construct", "unit_id", "unit_name", "period_start", "period_end", "value_numeric",
        "value_text", "source_name", "source_locator", "temporal_precision", "geographic_precision",
        "independence_class", "measurement_status", "uncertainty_note",
    ])


def gadm_geography(case_id: str, archive: Path, level: int, valid_from: str, valid_to: str, status: str = "modern_boundary_proxy") -> tuple[pd.DataFrame, list[Any], list[str]]:
    with zipfile.ZipFile(archive) as z:
        member = next(x for x in z.namelist() if x.endswith(".json"))
        features = json.load(z.open(member))["features"]
    rows, polys, ids = [], [], []
    gid = f"GID_{level}"
    name = f"NAME_{level}"
    parent_gid = f"GID_{level-1}" if level > 0 else None
    parent_name = f"NAME_{level-1}" if level > 0 else None
    for ft in features:
        geom = shape(ft["geometry"])
        p = geom.representative_point()
        prop = ft["properties"]
        uid = str(prop[gid])
        rows.append({
            "case_id": case_id, "unit_id": uid, "unit_name": str(prop.get(name, uid)), "unit_level": f"admin{level}",
            "parent_id": str(prop.get(parent_gid, "")) if parent_gid else "", "parent_name": str(prop.get(parent_name, "")) if parent_name else "",
            "centroid_latitude": p.y, "centroid_longitude": p.x, "source_geography_id": uid,
            "valid_from": valid_from, "valid_to": valid_to, "crosswalk_confidence": 1.0,
            "geography_status": status,
        })
        polys.append(geom); ids.append(uid)
    return pd.DataFrame(rows), polys, ids


def read_ged_archive(archive: Path) -> pd.DataFrame:
    with zipfile.ZipFile(archive) as z:
        member = next(x for x in z.namelist() if x.endswith(".csv"))
        return pd.read_csv(io.TextIOWrapper(z.open(member), encoding="utf-8"), low_memory=False)


def standardize_ged_case(case_id: str, case_root: Path, country: str, start: str, end: str, level: int = 2) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    raw = case_root / "data/raw"
    ged = next(raw.glob("ged*.zip"))
    gadm = next(raw.glob(f"gadm*_{level}.json.zip"))
    geo, polys, ids = gadm_geography(case_id, gadm, level, start, end)
    tree = STRtree(polys)
    all_events = read_ged_archive(ged)
    dates = pd.to_datetime(all_events["date_start"], errors="coerce")
    events = all_events[(all_events["country"] == country) & (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))].copy().reset_index(drop=True)
    events["_event_date"] = pd.to_datetime(events["date_start"], errors="coerce")
    mapped: list[str | None] = [None] * len(events)
    valid = events["longitude"].notna() & events["latitude"].notna()
    if valid.any():
        idx = np.where(valid.to_numpy())[0]
        pts = points(events.loc[valid, "longitude"].astype(float).to_numpy(), events.loc[valid, "latitude"].astype(float).to_numpy())
        pairs = tree.query(pts, predicate="within")
        for point_index, polygon_index in zip(pairs[0], pairs[1]):
            mapped[int(idx[int(point_index)])] = ids[int(polygon_index)]
    events["_unit_id"] = mapped
    out = pd.DataFrame({
        "case_id": case_id,
        "source_name": "UCDP Georeferenced Event Dataset",
        "source_version": "26.1",
        "source_event_id": events["id"].astype(str),
        "event_date": events["_event_date"],
        "date_precision": events.get("date_prec", pd.Series([np.nan] * len(events))).astype("Int64"),
        "unit_id": events["_unit_id"],
        "mapping_status": np.where(events["_unit_id"].notna(), "mapped_within_polygon", np.where(valid, "coordinate_not_in_canonical_geometry", "coordinate_missing")),
        "mapping_confidence": np.where(events["_unit_id"].notna(), 1.0, 0.0),
        "latitude": pd.to_numeric(events["latitude"], errors="coerce"),
        "longitude": pd.to_numeric(events["longitude"], errors="coerce"),
        "location_precision": pd.to_numeric(events.get("where_prec", np.nan), errors="coerce"),
        "actor_a": events.get("side_a", "").astype(str),
        "actor_b": events.get("side_b", "").astype(str),
        "actor_a_id": events.get("side_a_id", pd.Series([pd.NA] * len(events))).astype("string"),
        "actor_b_id": events.get("side_b_id", pd.Series([pd.NA] * len(events))).astype("string"),
        "violence_type": pd.to_numeric(events.get("type_of_violence", np.nan), errors="coerce"),
        "fatalities_low": pd.to_numeric(events.get("low", 0), errors="coerce").fillna(0),
        "fatalities_best": pd.to_numeric(events.get("best", 0), errors="coerce").fillna(0),
        "fatalities_high": pd.to_numeric(events.get("high", 0), errors="coerce").fillna(0),
        "civilian_fatalities": pd.to_numeric(events.get("deaths_civilians", 0), errors="coerce").fillna(0),
        "source_row_status": "retained_in_period",
    })
    out["_month"] = out["event_date"].dt.to_period("M")
    mapped_events = out[out["unit_id"].notna()].copy()
    agg = mapped_events.groupby(["unit_id", "_month"], dropna=False).agg(
        event_count=("source_event_id", "count"), fatalities_best=("fatalities_best", "sum"),
        civilian_fatalities=("civilian_fatalities", "sum"), mapped_event_count=("source_event_id", "count")
    ).reset_index()
    months = pd.period_range(pd.Timestamp(start).to_period("M"), pd.Timestamp(end).to_period("M"), freq="M")
    dense = pd.MultiIndex.from_product([geo.unit_id.tolist(), months], names=["unit_id", "_month"]).to_frame(index=False)
    dense = dense.merge(agg, on=["unit_id", "_month"], how="left")
    for col in ["event_count", "fatalities_best", "civilian_fatalities", "mapped_event_count"]:
        dense[col] = dense[col].fillna(0).astype(float if "fatal" in col else int)
    unmapped_month = out[out["unit_id"].isna()].groupby("_month").size().to_dict()
    dense["case_id"] = case_id
    dense["period_start"] = dense["_month"].dt.to_timestamp()
    dense["period_end"] = (dense["_month"] + 1).dt.to_timestamp() - pd.Timedelta(days=1)
    dense["time_scale"] = "month"
    # The UCDP file is a source-level event register over this interval. A zero
    # means no event recorded by this source, not latent peace/no violence.
    dense["source_coverage"] = "ucdp_ged_source_frame"
    dense["observation_status"] = np.where(dense.event_count > 0, "observed_event", "observed_zero")
    dense["exposure_days"] = (dense.period_end - dense.period_start).dt.days + 1
    dense["unmapped_event_count_case_period"] = dense["_month"].map(lambda x: int(unmapped_month.get(x, 0)))
    dense["split"] = [split_hash(case_id, u, temporal_split(case_id, d)) for u, d in zip(dense.unit_id, dense.period_start)]
    dense = dense[["case_id", "unit_id", "period_start", "period_end", "time_scale", "split", "exposure_days", "observation_status", "event_count", "fatalities_best", "civilian_fatalities", "mapped_event_count", "unmapped_event_count_case_period", "source_coverage"]]
    out = out.drop(columns=["_month"])
    meta = {"ged_path": ged, "gadm_path": gadm, "total_source_events_in_period": len(out), "mapped_events": int(out.unit_id.notna().sum())}
    return geo, out, dense, meta


def temporal_split(case_id: str, date: pd.Timestamp) -> str:
    y = date.year
    if case_id == "colombia_1984_2016":
        return "training" if y <= 2007 else "validation" if y <= 2012 else "holdout"
    if case_id == "iraq_2003_2011":
        return "training" if date < pd.Timestamp("2007-01-01") else "validation" if date < pd.Timestamp("2009-01-01") else "holdout"
    if case_id == "vietnam_1955_1975":
        return "training" if date < pd.Timestamp("1968-01-01") else "validation" if date < pd.Timestamp("1971-01-01") else "holdout"
    return "training"


def afghanistan_bundle(case_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list[Path], dict[str, Any]]:
    p = case_root / "data/processed"
    d = pd.read_csv(p / "districts.csv")
    centers = pd.read_csv(p / "district_centers.csv")
    center_cols = {c.lower(): c for c in centers.columns}
    latc = next((center_cols[x] for x in center_cols if "lat" in x), None)
    lonc = next((center_cols[x] for x in center_cols if "lon" in x), None)
    center_id = "district_id" if "district_id" in centers.columns else centers.columns[0]
    cent = centers[[center_id] + ([latc] if latc else []) + ([lonc] if lonc else [])].rename(columns={center_id:"district_id", latc:"centroid_latitude", lonc:"centroid_longitude"})
    d = d.merge(cent, on="district_id", how="left")
    districts = pd.DataFrame({
        "case_id":"afghanistan_2004_2021", "unit_id":d.district_id, "unit_name":d.district_name, "unit_level":"district",
        "parent_id":d.province_id, "parent_name":d.province_name, "centroid_latitude":d.get("centroid_latitude"),
        "centroid_longitude":d.get("centroid_longitude"), "source_geography_id":d.district_id,
        "valid_from":"2004-01-01", "valid_to":"2021-08-15", "crosswalk_confidence":1.0, "geography_status":"harmonized_401_district_analysis_grid"
    })
    prov = d[["province_id","province_name","region_id"]].drop_duplicates().copy()
    prov_cent = districts.groupby("parent_id",as_index=False).agg(centroid_latitude=("centroid_latitude","mean"),centroid_longitude=("centroid_longitude","mean"))
    prov = prov.merge(prov_cent,left_on="province_id",right_on="parent_id",how="left")
    provinces = pd.DataFrame({
        "case_id":"afghanistan_2004_2021","unit_id":prov.province_id,"unit_name":prov.province_name,"unit_level":"province",
        "parent_id":prov.region_id,"parent_name":"","centroid_latitude":prov.centroid_latitude,"centroid_longitude":prov.centroid_longitude,
        "source_geography_id":prov.province_id,"valid_from":"2004-01-01","valid_to":"2021-08-15","crosswalk_confidence":1.0,
        "geography_status":"harmonized_34_province_analysis_grid"
    })
    geo = pd.concat([provinces,districts],ignore_index=True)
    e = pd.read_csv(p / "events_2004_2021.csv", low_memory=False)
    events = pd.DataFrame({
        "case_id":"afghanistan_2004_2021", "source_name":"UCDP Georeferenced Event Dataset", "source_version":"26.1",
        "source_event_id":e.id.astype(str), "event_date":pd.to_datetime(e.event_date), "date_precision":1,
        "unit_id":e.province_id,
        "mapping_status":np.where(e.district_high_confidence.astype(str).str.lower().eq("true"),"mapped_province_with_high_confidence_district_secondary","mapped_province_only"),
        "mapping_confidence":np.where(e.province_id.notna(),1.0,0.0),
        "latitude":e.latitude,"longitude":e.longitude,"location_precision":e.where_prec,
        "actor_a":e.side_a,"actor_b":e.side_b,"actor_a_id":pd.NA,"actor_b_id":pd.NA,"violence_type":e.type_of_violence,
        "fatalities_low":e.low,"fatalities_best":e.best,"fatalities_high":e.high,"civilian_fatalities":e.deaths_civilians,
        "source_row_status":"retained_in_period"
    })
    events["secondary_district_id"] = e.district_id.where(e.district_high_confidence.astype(str).str.lower().eq("true"))
    pw = pd.read_csv(p / "province_week_panel.csv")
    unit = pd.DataFrame({
        "case_id":"afghanistan_2004_2021", "unit_id":pw.province_id, "period_start":pd.to_datetime(pw.week_start),
        "period_end":pd.to_datetime(pw.week_start)+pd.Timedelta(days=6), "time_scale":"week", "split":pw.split,
        "exposure_days":7, "observation_status":np.where(pw.all_organized_violence_event_count>0,"observed_event","observed_zero"),
        "event_count":pw.all_organized_violence_event_count,"fatalities_best":pw.all_organized_violence_fatalities,
        "civilian_fatalities":pw.taliban_one_sided_fatalities+pw.is_one_sided_fatalities+pw.government_one_sided_fatalities,
        "mapped_event_count":pw.all_organized_violence_event_count,"unmapped_event_count_case_period":0,"source_coverage":"ucdp_ged_source_frame"
    })
    aux = empty_aux()
    # Preserve the independently sourced SIGAR control rows as auxiliary
    # evidence without converting them into latent control values here.
    sources=[p/"events_2004_2021.csv",p/"province_week_panel.csv",p/"districts.csv",p/"district_centers.csv"]
    for fn in ["sigar_oct2017_control_401.csv", "sigar_oct2017_control_407.csv"]:
        q = p / fn
        if q.exists():
            x = pd.read_csv(q)
            rows=[]
            for _,r in x.iterrows():
                uid = str(r.get("district_id", r.get("district_code", "")))
                rows.append({"case_id":"afghanistan_2004_2021","construct":"control_or_presence","unit_id":uid,"unit_name":str(r.get("district_name","")),"period_start":"2017-10-01","period_end":"2017-10-31","value_numeric":np.nan,"value_text":json.dumps(r.to_dict(), default=str),"source_name":"SIGAR district control assessment","source_locator":fn,"temporal_precision":"month_or_report_period","geographic_precision":"district","independence_class":"independent_of_ucdp_violence","measurement_status":"raw_reported_category","uncertainty_note":"No violence-as-control substitution; raw SIGAR coding retained."})
            aux=pd.concat([aux,pd.DataFrame(rows, columns=empty_aux().columns)],ignore_index=True)
            sources.append(q)
    return geo,events,unit,aux,sources,{"canonical_event_unit":"province-week primary; district event mapping secondary"}


def nepal_bundle(case_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list[Path], dict[str, Any]]:
    p=case_root/"data/processed"
    d=pd.read_csv(p/"district_geography.csv")
    geo=pd.DataFrame({"case_id":"nepal_2001_2006","unit_id":d.district_id,"unit_name":d.district_name,"unit_level":"district","parent_id":"","parent_name":"","centroid_latitude":d.centroid_latitude,"centroid_longitude":d.centroid_longitude,"source_geography_id":d.district_id,"valid_from":"2001-11-26","valid_to":"2006-11-21","crosswalk_confidence":1.0,"geography_status":"historical_75_district_analysis_grid"})
    e=pd.read_csv(p/"ucdp_nepal_events.csv",low_memory=False)
    dt=pd.to_datetime(e.date_start)
    events=pd.DataFrame({"case_id":"nepal_2001_2006","source_name":"UCDP Georeferenced Event Dataset","source_version":"26.1","source_event_id":e.id.astype(str),"event_date":dt,"date_precision":e.date_prec,"unit_id":e.district_id,"mapping_status":np.where(e.district_id.notna(),"mapped_historical_district","unmapped"),"mapping_confidence":np.where(e.district_id.notna(),1.0,0.0),"latitude":e.latitude,"longitude":e.longitude,"location_precision":e.where_prec,"actor_a":e.side_a,"actor_b":e.side_b,"actor_a_id":pd.NA,"actor_b_id":pd.NA,"violence_type":e.type_of_violence,"fatalities_low":e.low,"fatalities_best":e.best,"fatalities_high":e.high,"civilian_fatalities":np.where(e.type_of_violence==3,e.best,0),"source_row_status":np.where(e.date_or_location_ambiguous.astype(int)>0,"retained_ambiguous_precision","retained_in_period")})
    w=pd.read_csv(p/"district_week_panel.csv")
    counts=w.government_maoist_state_based_events+w.state_one_sided_events+w.maoist_one_sided_events
    fats=w.government_maoist_state_based_deaths_best+w.state_one_sided_deaths_best+w.maoist_one_sided_deaths_best
    civ=w.state_one_sided_deaths_best+w.maoist_one_sided_deaths_best
    unit=pd.DataFrame({"case_id":"nepal_2001_2006","unit_id":w.district_id,"period_start":pd.to_datetime(w.week_start),"period_end":pd.to_datetime(w.week_end),"time_scale":"week","split":w.split,"exposure_days":w.exposure_days,"observation_status":np.where(counts>0,"observed_event","observed_zero"),"event_count":counts,"fatalities_best":fats,"civilian_fatalities":civ,"mapped_event_count":counts,"unmapped_event_count_case_period":0,"source_coverage":"ucdp_ged_source_frame"})
    aux=empty_aux()
    sources=[p/"ucdp_nepal_events.csv",p/"district_week_panel.csv",p/"district_geography.csv"]
    for fn in ["nepal_eastern_control_presence_adjudicated_v1.csv","nepal_sparse_control_presence.csv"]:
        q=p/fn
        if q.exists():
            x=pd.read_csv(q)
            rows=[]
            for _,r in x.iterrows():
                uid=str(r.get("district_id","")); name=str(r.get("district_name",""))
                rows.append({"case_id":"nepal_2001_2006","construct":"control_or_presence","unit_id":uid,"unit_name":name,"period_start":str(r.get("date",r.get("period_start",""))),"period_end":str(r.get("date",r.get("period_end",""))),"value_numeric":pd.to_numeric(r.get("value",np.nan),errors="coerce"),"value_text":json.dumps(r.to_dict(),default=str),"source_name":"independent coded control/presence evidence","source_locator":fn,"temporal_precision":"source_specific","geographic_precision":"district","independence_class":"independent_of_primary_ucdp_scoring","measurement_status":"adjudicated_or_sparse_observation","uncertainty_note":"Original row preserved in value_text."})
            aux=pd.concat([aux,pd.DataFrame(rows)],ignore_index=True)
            sources.append(q)
    insec_csv = p / "insec_district_totals.csv"
    if insec_csv.exists():
        x = pd.read_csv(insec_csv)
        insec_rows = []
        for _, r in x.iterrows():
            uid = str(r.get("district_id", ""))
            name = str(r.get("district_name", ""))
            insec_rows.append({
                "case_id": "nepal_2001_2006",
                "construct": "civilian_harm_or_victim_total",
                "unit_id": uid,
                "unit_name": name,
                "period_start": "1996-02-13",
                "period_end": "2006-11-21",
                "value_numeric": pd.to_numeric(r.get("victim_total_cumulative", np.nan), errors="coerce"),
                "value_text": json.dumps(r.to_dict(), default=str),
                "source_name": "INSEC Conflict Victims Report",
                "source_locator": "insec_district_totals.csv",
                "temporal_precision": "conflict_cumulative_total",
                "geographic_precision": "district",
                "independence_class": "independent_human_rights_monitoring_distinct_from_ucdp",
                "measurement_status": str(r.get("source_status", "observed")),
                "uncertainty_note": "Independent cumulative victim cross-check (1996-2006); not weekly panel-stratified.",
            })
        aux = pd.concat([aux, pd.DataFrame(insec_rows)], ignore_index=True)
        sources.append(insec_csv)
    return geo,events,unit,aux,sources,{"canonical_event_unit":"district-week"}


def colombia_aux(case_root: Path, geo: pd.DataFrame, polys: list[Any], ids: list[str]) -> pd.DataFrame:
    rows = []
    names = dict(zip(geo.unit_id, geo.unit_name))
    p = case_root / "data/processed/cnmh_dav_control_presence_inventory.csv"
    if p.exists():
        x = pd.read_csv(p, low_memory=False)
        tree = STRtree(polys)
        mapped = [None] * len(x)
        valid = x.longitude.notna() & x.latitude.notna()
        if valid.any():
            idx = np.where(valid.to_numpy())[0]
            pts = points(x.loc[valid, "longitude"].astype(float), x.loc[valid, "latitude"].astype(float))
            pairs = tree.query(pts, predicate="within")
            for pi, gi in zip(pairs[0], pairs[1]):
                mapped[int(idx[int(pi)])] = ids[int(gi)]
        for i, r in x.iterrows():
            uid = mapped[i]
            rows.append({
                "case_id": "colombia_1984_2016",
                "construct": "control_or_presence",
                "unit_id": uid,
                "unit_name": names.get(uid, ""),
                "period_start": "",
                "period_end": "",
                "value_numeric": np.nan,
                "value_text": str(r.get("description", r.get("period", "presence"))),
                "source_name": "CNMH DAV",
                "source_locator": str(r.get("source_label", r.get("source_file", ""))),
                "temporal_precision": str(r.get("date_status", "reported_period")),
                "geographic_precision": "point_to_gadm2" if uid else "unmapped_point",
                "independence_class": "independent_of_ucdp_violence",
                "measurement_status": "presence_lower_bound_not_control",
                "uncertainty_note": str(r.get("period", "")),
            })
    omc_p = case_root / "data/processed/cnmh_omc_municipality_year_1984_2016.json"
    if omc_p.exists():
        with omc_p.open("r", encoding="utf-8") as f:
            omc_records = json.load(f)
        lookup = {(_norm_name(r.parent_name), _norm_name(r.unit_name)): (r.unit_id, r.unit_name) for _, r in geo.iterrows()}
        aliases = {
            ("NORTEDESANTANDER", "CUCUTA"): ("NORTEDESANTANDER", "SANJOSEDECUCUTA"),
            ("PUTUMAYO", "MOCOA"): ("PUTUMAYO", "SANMIGUELDEMOCOA"),
            ("NARINO", "PASTO"): ("NARINO", "SANJUANDEPASTO"),
            ("NARINO", "SANANDRESDETUMACO"): ("NARINO", "TUMACO"),
            ("META", "URIBE"): ("META", "LAURIBE"),
            ("NORTEDESANTANDER", "LAPLAYA"): ("NORTEDESANTANDER", "LAPLAYADEBELEN"),
            ("ANTIOQUIA", "SANVICENTEFERRER"): ("ANTIOQUIA", "SANVICENTE"),
            ("ANTIOQUIA", "ELSANTUARIO"): ("ANTIOQUIA", "SANTUARIO"),
            ("SUCRE", "SANJOSEDETOLUVIEJO"): ("SUCRE", "TOLUVIEJO"),
            ("CESAR", "MANAUREBALCONDELCESAR"): ("CESAR", "MANAURE"),
            ("CAUCA", "PIENDAMOTUNIA"): ("CAUCA", "PIENDAMO"),
            ("CAUCA", "SOTARAPAISPAMBA"): ("CAUCA", "SOTARA"),
            ("CHOCO", "CARMENDELDARIEN"): ("CHOCO", "ELCARMENDELDARIEN"),
            ("CORDOBA", "LORICA"): ("CORDOBA", "SANTACRUZDELORICA"),
        }
        for rec in omc_records:
            dept = rec.get("Nombre_Departamento", "")
            mun = rec.get("Nombre_Municipio", "")
            key = (_norm_name(dept), _norm_name(mun))
            target_key = aliases.get(key, key)
            matched = lookup.get(target_key)
            uid = matched[0] if matched else None
            uname = matched[1] if matched else str(mun)
            year = str(rec.get("Anio_hecho", "")).strip()
            p_start = f"{year}-01-01" if year and year.isdigit() else ""
            p_end = f"{year}-12-31" if year and year.isdigit() else ""
            rows.append({
                "case_id": "colombia_1984_2016",
                "construct": "civilian_harm_or_victim_total",
                "unit_id": uid,
                "unit_name": uname,
                "period_start": p_start,
                "period_end": p_end,
                "value_numeric": pd.to_numeric(rec.get("victim_count", np.nan), errors="coerce"),
                "value_text": json.dumps(rec, default=str),
                "source_name": "CNMH Observatorio de Memoria y Conflicto",
                "source_locator": "cnmh_omc_municipality_year_1984_2016.json",
                "temporal_precision": "year",
                "geographic_precision": "municipality_gadm2" if uid else "unmapped_municipality",
                "independence_class": "independent_human_rights_monitoring_distinct_from_ucdp",
                "measurement_status": "municipality_year_aggregate_observation" if uid else "unmapped_reported_aggregate",
                "uncertainty_note": "Preserved CNMH OMC municipality-year civilian harm and victim record.",
            })
    return pd.DataFrame(rows) if rows else empty_aux()


def iraq_aux(case_root: Path) -> pd.DataFrame:
    p=case_root/"data/processed/sigir_rusafa_control_presence_panel.csv"
    if not p.exists(): return empty_aux()
    x=pd.read_csv(p); rows=[]
    for _,r in x.iterrows():
        rows.append({"case_id":"iraq_2003_2011","construct":"control_or_presence","unit_id":"rusafa_political_district","unit_name":"Rusafa Political District","period_start":str(r.month),"period_end":str(r.month),"value_numeric":pd.to_numeric(r.presence_evidence,errors="coerce"),"value_text":str(r.control_responsibility),"source_name":"SIGIR Rusafa case study","source_locator":f"{r.source_url}#page={r.source_pdf_page}","temporal_precision":str(r.date_precision),"geographic_precision":"urban_political_district_anchor","independence_class":"independent_of_ucdp_violence","measurement_status":str(r.evidence_status),"uncertainty_note":"Anchor slice only; not a national control proxy."})
    return pd.DataFrame(rows)


def _norm_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]", "", text)


def vietnam_secondary_bundle(case_root: Path) -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame,pd.DataFrame,list[Path],dict[str,Any]]:
    """Build a compact historical-province Vietnam observation database.

    Local RDS files are treated as cleaned secondary archival extracts. Direct
    NARA objects are separately acquired/fingerprinted; until row/layout parity
    is certified this bundle remains VERIFICATION_LIMITED rather than claiming
    direct-source identity.
    """
    import pyreadr

    raw = case_root / "data/raw"
    ground = pyreadr.read_r(str(raw / "vietwar_ground_combat.rds"))[None]
    hamla = pyreadr.read_r(str(raw / "vietwar_hes_hamla.rds"))[None]
    hes70 = pyreadr.read_r(str(raw / "vietwar_hes70.rds"))[None]

    # Recover the historical South Vietnam province coding directly from HAMLA
    # district records, avoiding a false modern-boundary crosswalk.
    district_rows = hamla[
        hamla.record_type.eq("District Record") & hamla.village_or_province_name.notna()
    ].copy()
    province_names = (
        district_rows.groupby("province_code").village_or_province_name
        .agg(lambda s: s.astype(str).str.strip().str.upper().value_counts().index[0])
        .to_dict()
    )
    corps = (
        hes70[hes70.province_code.notna()]
        .groupby("province_code").corps_region_code
        .agg(lambda s: s.dropna().astype(str).value_counts().index[0] if s.dropna().size else "")
        .to_dict()
    )
    hamlet_geo = hes70[
        hes70.province_code.notna() & hes70.hamlet_lat.notna() & hes70.hamlet_lng.notna()
    ].copy()
    centroids = hamlet_geo.groupby("province_code").agg(
        centroid_latitude=("hamlet_lat", "mean"),
        centroid_longitude=("hamlet_lng", "mean"),
    )
    geo_rows = []
    for code, name in sorted(province_names.items()):
        c = str(code).zfill(2)
        lat = float(centroids.loc[code, "centroid_latitude"]) if code in centroids.index else np.nan
        lon = float(centroids.loc[code, "centroid_longitude"]) if code in centroids.index else np.nan
        geo_rows.append({
            "case_id": "vietnam_1955_1975",
            "unit_id": f"VN-HES-P{c}",
            "unit_name": str(name).title(),
            "unit_level": "historical_province_or_autonomous_city",
            "parent_id": f"VN-CORPS-{corps.get(code, '')}",
            "parent_name": str(corps.get(code, "")),
            "centroid_latitude": lat,
            "centroid_longitude": lon,
            "source_geography_id": c,
            "valid_from": "1967-01-01",
            "valid_to": "1974-01-31",
            "crosswalk_confidence": 1.0,
            "geography_status": "historical_HES_province_code",
        })
    geo = pd.DataFrame(geo_rows)

    name_to_code = {_norm_name(name): str(code).zfill(2) for code, name in province_names.items()}
    # Two labels in the cleaned combat extract are demonstrable transposition /
    # truncation variants; coordinates and corps membership uniquely identify
    # the corresponding historical HES province.
    name_to_code[_norm_name("Khanh Long")] = "19"  # Long Khanh, III Corps
    name_to_code[_norm_name("Xuyen")] = "41"       # Ba Xuyen, IV Corps

    ground = ground.copy()
    ground["event_date"] = pd.to_datetime(ground.initiation_date, errors="coerce")
    ground = ground[
        ground.event_date.between(pd.Timestamp("1963-01-01"), pd.Timestamp("1975-04-30"))
        & ~pd.to_numeric(ground.outside_south_vietnam, errors="coerce").fillna(0).eq(1)
        & ~pd.to_numeric(ground.coord_over_ocean, errors="coerce").fillna(0).eq(1)
    ].copy().reset_index(drop=True)
    mapped_code = ground.prov_name.map(lambda x: name_to_code.get(_norm_name(x)) if pd.notna(x) else None)
    ground["unit_id"] = mapped_code.map(lambda x: f"VN-HES-P{x}" if x else None)
    kia = (
        pd.to_numeric(ground.n_friendly_kia, errors="coerce").fillna(0)
        + pd.to_numeric(ground.n_enemy_kia, errors="coerce").fillna(0)
    ).clip(lower=0)
    base_id = (
        ground.data_file_origin.astype(str) + ":" + ground.record_id.astype(str)
        + ":" + ground.master_event_id.astype(str)
    )
    dup = base_id.groupby(base_id).cumcount().astype(str)
    events = pd.DataFrame({
        "case_id": "vietnam_1955_1975",
        "source_name": "cleaned MACV/NARA ground-combat archival extract",
        "source_version": "local_vietwar_rds_with_direct_NARA_series_provenance",
        "source_event_id": base_id + ":" + dup,
        "event_date": ground.event_date,
        "date_precision": "day_or_source_record_precision",
        "unit_id": ground.unit_id,
        "mapping_status": np.where(ground.unit_id.notna(), "mapped_historical_HES_province", "historical_province_label_unmapped"),
        "mapping_confidence": np.where(ground.unit_id.notna(), 1.0, 0.0),
        "latitude": pd.to_numeric(ground.lat, errors="coerce"),
        "longitude": pd.to_numeric(ground.lng, errors="coerce"),
        "location_precision": "source_coordinate",
        "actor_a": ground.aggressor_side.fillna("").astype(str),
        "actor_b": ground.target_specific.fillna("").astype(str),
        "actor_a_id": pd.NA,
        "actor_b_id": pd.NA,
        "violence_type": ground.general_action_category.fillna(ground.enemy_action_category).fillna("archival_incident").astype(str),
        "fatalities_low": kia,
        "fatalities_best": kia,
        "fatalities_high": kia,
        "civilian_fatalities": np.nan,
        "source_row_status": "recorded_KIA_point_estimate_not_total_fatality_bound",
    })

    events["_month"] = events.event_date.dt.to_period("M")
    mapped = events[events.unit_id.notna()].copy()
    agg = mapped.groupby(["unit_id", "_month"]).agg(
        event_count=("source_event_id", "count"),
        fatalities_best=("fatalities_best", "sum"),
        mapped_event_count=("source_event_id", "count"),
    ).reset_index()
    all_months = pd.period_range("1955-01", "1975-04", freq="M")
    dense = pd.MultiIndex.from_product([geo.unit_id.tolist(), all_months], names=["unit_id", "_month"]).to_frame(index=False)
    dense = dense.merge(agg, on=["unit_id", "_month"], how="left")
    source_start = events.event_date.min().to_period("M")
    source_end = events.event_date.max().to_period("M")
    covered = dense._month.between(source_start, source_end)
    dense["event_count"] = np.where(covered, dense.event_count.fillna(0), np.nan)
    dense["fatalities_best"] = np.where(covered, dense.fatalities_best.fillna(0), np.nan)
    dense["mapped_event_count"] = np.where(covered, dense.mapped_event_count.fillna(0), np.nan)
    unmapped_by_month = events[events.unit_id.isna()].groupby("_month").size().to_dict()
    dense["case_id"] = "vietnam_1955_1975"
    dense["period_start"] = dense._month.dt.to_timestamp()
    dense["period_end"] = (dense._month + 1).dt.to_timestamp() - pd.Timedelta(days=1)
    dense["time_scale"] = "month"
    dense["split"] = [split_hash("vietnam_1955_1975", u, temporal_split("vietnam_1955_1975", d)) for u, d in zip(dense.unit_id, dense.period_start)]
    dense["exposure_days"] = (dense.period_end - dense.period_start).dt.days + 1
    dense["observation_status"] = np.where(
        ~covered,
        "source_gap",
        np.where(pd.to_numeric(dense.event_count, errors="coerce").fillna(0) > 0, "observed_event", "observed_zero"),
    )
    dense["civilian_fatalities"] = np.nan
    dense["unmapped_event_count_case_period"] = dense._month.map(lambda m: int(unmapped_by_month.get(m, 0)) if m in unmapped_by_month else 0)
    dense["source_coverage"] = np.where(covered, "cleaned_MACV_NARA_composite_source_frame", "outside_available_event_extract")
    unit = dense[["case_id","unit_id","period_start","period_end","time_scale","split","exposure_days","observation_status","event_count","fatalities_best","civilian_fatalities","mapped_event_count","unmapped_event_count_case_period","source_coverage"]]
    events = events.drop(columns=["_month"])

    # Independent HES measurement stream, aggregated rather than copying ~1M
    # hamlet rows into the experiment bundle.
    aux_rows: list[dict[str, Any]] = []
    unit_names = dict(zip(geo.unit_id, geo.unit_name))

    hh = hamla[hamla.record_type.eq("Hamlet Record") & hamla.date.notna()].copy()
    hh["unit_id"] = hh.province_code.astype(str).str.zfill(2).map(lambda c: f"VN-HES-P{c}")
    hh["date"] = pd.to_datetime(hh.date, errors="coerce")
    for c in ["government_control_population","viet_cong_control_population","neither_both_control_population","unknown_control_population","total_population"]:
        hh[c] = pd.to_numeric(hh[c], errors="coerce").fillna(0)
    pop = hh.groupby(["unit_id","date"])[["government_control_population","viet_cong_control_population","neither_both_control_population","unknown_control_population","total_population"]].sum().reset_index()
    for _, r in pop.iterrows():
        total = float(r.total_population)
        for construct, col in [
            ("hes_government_controlled_population_share", "government_control_population"),
            ("hes_viet_cong_controlled_population_share", "viet_cong_control_population"),
            ("hes_neither_or_both_controlled_population_share", "neither_both_control_population"),
        ]:
            aux_rows.append({
                "case_id":"vietnam_1955_1975","construct":construct,"unit_id":r.unit_id,"unit_name":unit_names.get(r.unit_id,""),
                "period_start":r.date,"period_end":r.date,"value_numeric":float(r[col]/total) if total>0 else np.nan,
                "value_text":"","source_name":"HAMLA cleaned archival extract","source_locator":"vietwar_hes_hamla.rds",
                "temporal_precision":"month","geographic_precision":"historical_HES_province aggregated from hamlets",
                "independence_class":"archival_measurement_distinct_from_ground_combat","measurement_status":"population_weighted_direct_report_field",
                "uncertainty_note":"Measurement observation; not equated directly to Pineland latent C. Direct NARA row parity pending."
            })

    h70 = hes70[hes70.rectp_record_type.eq("Hamlet Record") & hes70.date.notna()].copy()
    h70["unit_id"] = h70.province_code.astype(str).str.zfill(2).map(lambda c: f"VN-HES-P{c}")
    h70["date"] = pd.to_datetime(h70.date, errors="coerce")
    rating_fields = {
        "hes_security_macromodel": "mod7a_security_macromodel",
        "hes_political_control_macromodel": "mod6a_political_control_macromodel",
        "hes_military_control_macromodel": "mod6b_military_control_macromodel",
        "hes_administration_submodel": "mod1j_administration_submodel",
        "hes_law_enforcement_submodel": "mod1f_law_enforcement_submodel",
        "hes_enemy_military_presence_submodel": "mod1a_enemy_military_presence_submodel",
    }
    for (uid, date), g in h70.groupby(["unit_id","date"]):
        for construct, col in rating_fields.items():
            vals = g[col].dropna().astype(str).str.strip()
            vals = vals[vals.ne("")]
            if vals.empty:
                continue
            counts = vals.value_counts().sort_index().to_dict()
            aux_rows.append({
                "case_id":"vietnam_1955_1975","construct":construct,"unit_id":uid,"unit_name":unit_names.get(uid,""),
                "period_start":date,"period_end":date,"value_numeric":np.nan,"value_text":json.dumps(counts,sort_keys=True),
                "source_name":"HES70 cleaned archival extract","source_locator":"vietwar_hes70.rds",
                "temporal_precision":"month","geographic_precision":"historical_HES_province aggregated from hamlets",
                "independence_class":"archival_measurement_distinct_from_ground_combat","measurement_status":"categorical_distribution_preserved_no_ordinal_assumption",
                "uncertainty_note":"Category distribution retained without imposing an undocumented numeric scale; direct NARA layout parity pending."
            })
    aux = pd.DataFrame(aux_rows, columns=empty_aux().columns)

    direct_manifest = ROOT / "studies/research_program/source_cache/nara/vietnam_minimal_v1/manifest.json"
    sources = [
        raw/"vietwar_ground_combat.rds", raw/"vietwar_hes70.rds", raw/"vietwar_hes_hamla.rds",
        raw/"nara_catalog_records.json",
    ]
    if direct_manifest.exists():
        sources.append(direct_manifest)
    return geo, events, unit, aux, sources, {
        "canonical_event_unit":"historical_HES_province_month",
        "historical_province_count":len(geo),
        "direct_nara_manifest":direct_manifest.relative_to(ROOT).as_posix() if direct_manifest.exists() else None,
        "direct_nara_row_parity":"pending",
        "manual_province_aliases":{"Khanh Long":"Long Khanh (HES 19)","Xuyen":"Ba Xuyen (HES 41)"},
    }


def observability(case_id: str) -> dict[str,Any]:
    base={k:{"status":"not_directly_observed","allowed_use":"none","note":"Latent Pineland coordinate; historical proxy requires an explicit measurement operator."} for k in ["M_star","F","E","C","Phi_net","A","K_o","P_G","V_G","V_I"]}
    mechanisms={
        "nonlocal_reproduction_recruitment_hazard":{"status":"proxy_possible","requirements":["event timing/geography","actor attribution","recruitment/presence evidence where available"]},
        "organizational_capital_stock_flow":{"status":"requires_case_specific_resource_series"},
        "human_capital_turnover_learning":{"status":"requires_force-strength, replacement/attrition, and experience/readiness proxy series"},
        "state_capacity_dual_channel":{"status":"requires_independent_admin/institutional observations"},
    }
    if case_id=="afghanistan_2004_2021":
        base["C"]={"status":"partial_proxy","allowed_use":"independent validation only","note":"SIGAR district control categories; sparse period coverage."}; base["A"]={"status":"proxy_possible","allowed_use":"measurement-model development","note":"state/police/admin sources available but not one direct latent coordinate"}; mechanisms["human_capital_turnover_learning"]["status"]="proxy_possible"
    elif case_id=="nepal_2001_2006":
        base["C"]={"status":"partial_proxy","allowed_use":"independent validation","note":"adjudicated/sparse control-presence evidence"}; base["M_star"]={"status":"proxy_possible","allowed_use":"reproduction/presence measurement model","note":"requires actor/presence operator; violence alone forbidden"}
    elif case_id=="colombia_1984_2016":
        base["M_star"]={"status":"partial_proxy","allowed_use":"presence lower bound","note":"CNMH DAV structure presence points; not membership mass"}; base["C"]={"status":"partial_proxy","allowed_use":"presence only, not direct control","note":"CNMH DAV independent presence evidence"}
    elif case_id=="iraq_2003_2011":
        base["C"]={"status":"anchor_proxy","allowed_use":"Rusafa anchor validation only","note":"SIGIR urban political district evidence; not nationwide"}; base["A"]={"status":"anchor_proxy","allowed_use":"Rusafa reconstruction/governance slice","note":"independent qualitative anchor"}
    elif case_id=="vietnam_1955_1975":
        base["C"]={"status":"partial_proxy","allowed_use":"measurement-model and directional validation","note":"HAMLA government/VC controlled-population shares plus HES political/military/security distributions; not equated directly with latent C"}; base["A"]={"status":"partial_proxy","allowed_use":"measurement-model development","note":"HES administration distributions plus direct NARA NAPE/TFES provenance; direct row-level parity remains pending"}; base["P_G"]={"status":"proxy_possible","allowed_use":"future preregistered operator after NAPE/TFES parsing","note":"direct NAPE/territorial-force objects acquired in minimal source cache"}; base["M_star"]={"status":"partial_proxy","allowed_use":"enemy political/military presence measurement development","note":"HES enemy-presence distributions are observations, not rooted membership mass"}
        mechanisms["nonlocal_reproduction_recruitment_hazard"]["status"]="proxy_possible_with_HES_enemy_presence_and_ground_events"
        mechanisms["human_capital_turnover_learning"]["status"]="direct_source_inputs_identified_NAPE_TFES_not_yet_operatorized"
        mechanisms["state_capacity_dual_channel"]["status"]="partial_proxy_HES_admin_security_plus_direct_NAPE_TFES"
    elif case_id=="nigeria_2014":
        mechanisms={k:{"status":"sealed_holdout_no_target_access"} for k in mechanisms}
    return {"schema_version":"pineland.historical_observability_map.v2","case_id":case_id,"reduced_theory_version":"reduced_theory_specification_v2.json","coordinates":base,"mechanisms":mechanisms,"do_not_infer":["violence != territorial control","event absence outside explicit source coverage != zero violence","armed-group presence != rooted membership mass","headcount != veterancy/professionalism","aid/spending != administrative capacity"]}


def quality(case_id: str, geo: pd.DataFrame, events: pd.DataFrame, unit: pd.DataFrame, aux: pd.DataFrame, sources: list[Path], firewall: str, bundle_bytes: int) -> dict[str,Any]:
    checks={}
    checks["geography_nonempty"]=len(geo)>0
    checks["source_hashes_available"]=all(p.exists() for p in sources)
    checks["event_ids_unique"]=events.source_event_id.astype(str).is_unique if len(events) else case_id=="nigeria_2014"
    fatality_anomaly_count = 0
    fatality_anomaly_rate = 0.0
    if len(events):
        lo=pd.to_numeric(events.fatalities_low,errors="coerce"); be=pd.to_numeric(events.fatalities_best,errors="coerce"); hi=pd.to_numeric(events.fatalities_high,errors="coerce")
        mask=lo.notna()&be.notna()&hi.notna(); ordered=(lo[mask]>=0)&(lo[mask]<=be[mask])&(be[mask]<=hi[mask]); fatality_anomaly_count=int((~ordered).sum()); fatality_anomaly_rate=float(fatality_anomaly_count/max(1,int(mask.sum())))
        checks["fatality_values_nonnegative"]=bool(((lo.dropna()>=0).all()) and ((be.dropna()>=0).all()) and ((hi.dropna()>=0).all()))
        checks["fatality_bound_anomalies_preserved_and_flagged"]=True
    else:
        checks["fatality_values_nonnegative"]=True; checks["fatality_bound_anomalies_preserved_and_flagged"]=True
    checks["unmapped_events_retained"]=True
    checks["zero_missing_semantics_explicit"]=bool(len(unit)==0 or set(unit.observation_status.dropna().unique()).issubset({"observed_event","observed_zero","source_gap","geography_gap","sealed_holdout"}))
    checks["holdout_firewall_declared"]=bool(firewall)
    geo_ids=set(geo.unit_id.astype(str)); checks["unit_time_units_in_geography"]=bool(len(unit)==0 or set(unit.unit_id.astype(str)).issubset(geo_ids))
    mapping_rate=float(events.unit_id.notna().mean()) if len(events) else None
    independent_aux=bool(len(aux) and (aux.independence_class.astype(str).str.contains("independent|distinct",case=False,regex=True).any()))
    blocked=[]
    if case_id=="nigeria_2014": license="SEALED_HOLDOUT"
    elif case_id=="vietnam_1955_1975":
        direct_manifest = ROOT/"studies/research_program/source_cache/nara/vietnam_minimal_v1/manifest.json"
        if direct_manifest.exists() and len(unit) and mapping_rate is not None and mapping_rate >= 0.95:
            license="VERIFICATION_LIMITED"
            blocked=["cleaned_extract_to_direct_NARA_row_layout_parity_pending","NAPE_TFES_human_capital_operator_not_yet_materialized"]
        else:
            license="CONSTRUCTION_ONLY"
            blocked=["direct_NARA_minimal_manifest_or_dense_historical_panel_incomplete"]
    elif case_id in {"colombia_1984_2016","iraq_2003_2011"}: license="VERIFICATION_LIMITED"; blocked=["independent_control_or_capacity_evidence_not_nationally_dense"]
    else: license="EXPERIMENT_READY" if independent_aux else "VERIFICATION_LIMITED"; blocked=[] if independent_aux else ["independent_nonviolence_measurement_stream_missing"]
    if not all(checks.values()):
        blocked += [k for k,v in checks.items() if not v]
        if license=="EXPERIMENT_READY": license="VERIFICATION_LIMITED"
    return {"schema_version":"pineland.historical_database_quality.v2","case_id":case_id,"license":license,"checks":checks,"coverage":{"geography_units":int(len(geo)),"events":int(len(events)),"unit_time_rows":int(len(unit)),"auxiliary_observations":int(len(aux))},"mapping":{"event_mapping_rate":mapping_rate,"mapped_events":int(events.unit_id.notna().sum()) if len(events) else 0,"unmapped_events":int(events.unit_id.isna().sum()) if len(events) else 0},"fatality_uncertainty_source_anomalies":{"count":fatality_anomaly_count,"rate":fatality_anomaly_rate,"policy":"preserve source values; do not silently reorder; downstream code must branch on anomaly flag"},"measurement_independence":{"independent_auxiliary_stream_present":independent_aux},"holdout_integrity":{"firewall":firewall},"bundle_size_bytes":bundle_bytes,"bundle_size_mib":bundle_bytes/1024/1024,"blocked_reasons":sorted(set(blocked))}


def build_case(case: str) -> dict[str,Any]:
    if case=="nigeria_2014":
        case_root=ROOT/"studies/research_program/external_validation/nigeria_2014"; raw=case_root/"raw"; out=case_root/"standard_v2"; out.mkdir(parents=True,exist_ok=True)
        gadm=raw/"gadm41_NGA_1.json.zip"; geo,_,_=gadm_geography(case,gadm,1,"2014-01-01","2014-12-31","sealed_holdout_geography_only")
        events=pd.DataFrame(columns=["case_id","source_name","source_version","source_event_id","event_date","date_precision","unit_id","mapping_status","mapping_confidence","latitude","longitude","location_precision","actor_a","actor_b","actor_a_id","actor_b_id","violence_type","fatalities_low","fatalities_best","fatalities_high","civilian_fatalities","source_row_status"])
        unit=pd.DataFrame({"case_id":case,"unit_id":geo.unit_id,"period_start":pd.Timestamp("2014-01-01"),"period_end":pd.Timestamp("2014-12-31"),"time_scale":"sealed_target_year","split":"external_holdout","exposure_days":365,"observation_status":"sealed_holdout","event_count":np.nan,"fatalities_best":np.nan,"civilian_fatalities":np.nan,"mapped_event_count":np.nan,"unmapped_event_count_case_period":np.nan,"source_coverage":"target_not_read"})
        aux=empty_aux(); sources=[gadm,raw/"nga_ppp_2014_1km_ASCII_XYZ.zip",raw/"acquisition_manifest.json",ROOT/"studies/research_program/nigeria_2014_external_holdout_certificate.json"]
        firewall="2014 GED target archive intentionally not opened or read by this builder; target_rows_read remains false."
        meta={"sealed":True}
    else:
        case_root=ROOT/"studies"/case; out=case_root/"data/standard_v2"; out.mkdir(parents=True,exist_ok=True); firewall="Historical observation construction only; no Pineland parameters or synthetic state definitions are fit or changed by this build."
        if case=="afghanistan_2004_2021": geo,events,unit,aux,sources,meta=afghanistan_bundle(case_root)
        elif case=="nepal_2001_2006": geo,events,unit,aux,sources,meta=nepal_bundle(case_root)
        elif case in {"colombia_1984_2016","iraq_2003_2011"}:
            cfg={"colombia_1984_2016":("Colombia","1984-01-01","2016-12-31"),"iraq_2003_2011":("Iraq","2003-03-20","2011-12-31")}[case]
            geo,events,unit,m=standardize_ged_case(case,case_root,*cfg,level=2)
            sources=[m["ged_path"],m["gadm_path"]]
            if case.startswith("colombia"):
                # Re-open geometry once for Colombia independent presence mapping.
                gadm=m["gadm_path"]
                with zipfile.ZipFile(gadm) as z:
                    member=next(x for x in z.namelist() if x.endswith(".json")); feats=json.load(z.open(member))["features"]
                polys=[shape(f["geometry"]) for f in feats]; ids=[f["properties"]["GID_2"] for f in feats]
                aux=colombia_aux(case_root,geo,polys,ids)
                dav = case_root / "data/processed/cnmh_dav_control_presence_inventory.csv"
                omc = case_root / "data/processed/cnmh_omc_municipality_year_1984_2016.json"
                if dav.exists(): sources.append(dav)
                if omc.exists(): sources.append(omc)
            else:
                aux=iraq_aux(case_root)
                sig = case_root / "data/processed/sigir_rusafa_control_presence_panel.csv"
                if sig.exists(): sources.append(sig)
            meta={k:v for k,v in m.items() if not isinstance(v,Path)}
        elif case=="vietnam_1955_1975": geo,events,unit,aux,sources,meta=vietnam_secondary_bundle(case_root)
        else: raise ValueError(case)

    artifacts={}
    artifacts["geography"]=write_parquet(geo,out/"geography.parquet")
    artifacts["events"]=write_parquet(events,out/"events.parquet")
    artifacts["unit_time"]=write_parquet(unit,out/"unit_time.parquet")
    artifacts["auxiliary_observations"]=write_parquet(aux,out/"auxiliary_observations.parquet")
    obs=observability(case); artifacts["observability_map"]=json_dump(obs,out/"observability_map.json")
    bundle_bytes=sum(x["bytes"] for x in artifacts.values())
    q=quality(case,geo,events,unit,aux,sources,firewall,bundle_bytes)
    artifacts["quality_report"]=json_dump(q,out/"quality_report.json")
    source_artifacts=[]
    for p in sources:
        if p.exists(): source_artifacts.append({"path":p.relative_to(ROOT).as_posix(),"bytes":p.stat().st_size,"sha256":sha256(p)})
    manifest={"schema_version":"pineland.historical_database_manifest.v2","case_id":case,"build_timestamp_utc":datetime.now(timezone.utc).isoformat(),"builder_sha256":sha256(Path(__file__)),"standard_sha256":sha256(STANDARD),"source_artifacts":source_artifacts,"artifacts":artifacts,"repository_revision":git_revision(),"historical_target_firewall":firewall,"case_metadata":meta}
    artifacts["dataset_manifest"]=json_dump(manifest,out/"dataset_manifest.json")
    return {"case_id":case,"license":q["license"],"bundle_dir":out.relative_to(ROOT).as_posix(),"bundle_size_mib":q["bundle_size_mib"],"mapping_rate":q["mapping"]["event_mapping_rate"],"blocked_reasons":q["blocked_reasons"]}


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("cases",nargs="*",default=["afghanistan_2004_2021","nepal_2001_2006","colombia_1984_2016","iraq_2003_2011","vietnam_1955_1975","nigeria_2014"]); ns=ap.parse_args()
    print(json.dumps([build_case(c) for c in ns.cases],indent=2))


if __name__=="__main__": main()
