"""Build sourced Afghanistan transfer-test inputs without violence tuning."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import zipfile

from shapely.geometry import shape


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
CONFIG = ROOT / "config"
CASE = CONFIG / "case_environment.json"
OUT = CONFIG / "historical_case_inputs.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pakistan_border_districts() -> list[str]:
    """Derive benchmark districts touching the Pakistan boundary.

    COD district boundaries are compared with Natural Earth's independent
    Pakistan national boundary. A narrow tolerance absorbs harmless geometry
    precision differences between the two public products.
    """
    natural_earth = json.loads(
        (RAW / "natural_earth_admin0_10m.geojson").read_text(encoding="utf-8")
    )
    pakistan = next(
        shape(feature["geometry"]) for feature in natural_earth["features"]
        if feature["properties"].get("ADMIN") == "Pakistan"
    )
    boundary_band = pakistan.boundary.buffer(.01)
    with zipfile.ZipFile(RAW / "afg_admin_boundaries.geojson.zip") as archive:
        afghanistan = json.load(archive.open("afg_admin2.geojson"))
    result = []
    for feature in afghanistan["features"]:
        district = shape(feature["geometry"])
        overlap = district.boundary.intersection(boundary_band)
        if not overlap.is_empty and getattr(overlap, "length", 0.0) > .005:
            result.append(feature["properties"]["adm2_pcode"])
    return sorted(result)


def coalition_schedule() -> list[dict]:
    rows = list(csv.DictReader(
        (RAW / "brookings_troop_levels_2001_2019.csv").open(
            encoding="utf-8", newline=""
        )
    ))
    result = []
    # The current Datawrapper export behind the Brookings chart has drifted
    # from the archived published Afghanistan Index for 2017-2018.  Pin those
    # two U.S. annual averages to the frozen publication (p. 5): 14,000 in
    # both years.  This is a source-version repair, not outcome tuning.
    published_us_corrections = {2017: 14000, 2018: 14000}
    for row in rows:
        year = int(row["Year"])
        if 2004 <= year <= 2019:
            us = published_us_corrections.get(year, int(row["U.S. Troops"]))
            other = int(row["Other Troops"])
            result.append({
                "date": f"{year}-01-01",
                "us": us,
                "other": other,
                "total": us + other,
                "observation_type": "annual_average",
                "source_id": "brookings_afghanistan_index_2020",
                "source_version_note": (
                    "archived_publication_overrides_current_machine_table"
                    if year in published_us_corrections else
                    "archived_publication_matches_machine_table"
                ),
            })
    # 2020-2021 switches to dated official snapshots because the annual
    # Brookings series ends in 2019 and the withdrawal chronology matters.
    result.extend([
        {
            "date": "2020-01-01", "us": 13000, "other": 10530, "total": 23530,
            "observation_type": "quarterly_snapshot",
            "source_id": "lead_ig_ofs_2020_q1",
        },
        {
            "date": "2020-07-13", "us": 8600, "other": 7937, "total": 16537,
            "observation_type": "dated_snapshot",
            "source_id": "dod_2020_07_14_plus_nato_2020_06",
        },
        {
            "date": "2020-11-17", "us": 4500, "other": 7856, "total": 12356,
            "observation_type": "dated_snapshot",
            "source_id": "dod_2020_11_17_plus_lead_ig_2020_q4",
        },
        {
            "date": "2021-01-15", "us": 2500, "other": 7092, "total": 9592,
            "observation_type": "dated_us_plus_february_nato_snapshot",
            "source_id": "dod_2021_01_15_plus_nato_2021_02",
        },
        {
            "date": "2021-07-12", "us": 650, "other": 0, "total": 650,
            "observation_type": "residual_diplomatic_security_force",
            "source_id": "post_retrograde_residual_force",
        },
        {
            "date": "2021-08-15", "us": 6000, "other": 0, "total": 6000,
            "observation_type": "evacuation_security_surge",
            "source_id": "dod_state_joint_statement_2021_08_15",
        },
    ])
    return result


def main() -> None:
    case = json.loads(CASE.read_text(encoding="utf-8"))
    anchors = case["initial_insurgent_locality_ids"]
    preperiod = case["preperiod_taliban_state_conflict_counts_2003"]
    anchor_weights = {
        locality_id: preperiod[locality_id.removesuffix("-HQ")]
        for locality_id in anchors
    }
    payload = {
        "schema_version": "1.0.0",
        "study_id": "afghanistan_2004_2021",
        "parameter_fit": False,
        "benchmark_violence_used": False,
        "initialization": {
            "ana": {
                "personnel": 6500,
                "date": "2004-01-01",
                "formation_count": 12,
                "location_rule": "central_corps_kabul_at_benchmark_open",
                "locality_ids": ["AF0101-HQ"],
                "source_id": "un_s_2003_1212",
                "source_observation": (
                    "30 Dec 2003: 12 ANA battalions trained/established, "
                    "6,500 personnel all ranks"
                ),
            },
            "anp": {
                "personnel": 6000,
                "date": "2004-01-01",
                "value_semantics": "conservative_floor_carried_back_from_spring_2004",
                "location_rule": "population_proportional_across_401_district_posts",
                "source_id": "gao_04_403_state_comment",
                "source_observation": (
                    "spring 2004 State comment: rapidly growing police force "
                    "numbers over 6,000; 8,800+ fielded by 29 Apr 2004 testimony"
                ),
                "stock_schedule": [
                    {
                        "date": "2004-01-01",
                        "total": 6000,
                        "observation_type": "conservative_floor_carried_back_from_spring_2004",
                        "source_id": "gao_04_403_state_comment",
                    },
                    {
                        "date": "2004-04-29",
                        "total": 8800,
                        "observation_type": "dated_fielded_strength_floor",
                        "source_id": "gao_04_403_congressional_testimony",
                    },
                ],
                "not_claimed": "exact 1 Jan 2004 police headcount or district deployment",
            },
            "taliban": {
                "personnel_envelope": [5000, 7500, 10000],
                "default_transfer_scenario": 7500,
                "date_semantics": "early insurgency full-time fighter uncertainty",
                "location_rule": "2003_preperiod_event_anchor_weighted",
                "anchor_weights": anchor_weights,
                "source_id": "rand_mg595",
                "source_observation": (
                    "several thousand full-time Taliban fighters; estimates "
                    "ranged from 5,000 to 10,000; author interviews across 2004-2006"
                ),
            },
        },
        "pakistan": {
            "state_id": "pakistan",
            "sanctuary_capability_present": True,
            "model_mapping": {
                "taliban_external_sanctuary": 1.0,
                "semantics": (
                    "binary observed sanctuary availability mapped to the full "
                    "presence indicator; not an estimate of Pakistani support intensity"
                ),
            },
            "border_district_ids": pakistan_border_districts(),
            "border_derivation": (
                "COD 401 district boundaries intersected with independent "
                "Natural Earth 1:10m Pakistan national boundary using 0.01-degree "
                "geometry tolerance"
            ),
            "sanctuary_evidence": (
                "Taliban senior leadership in Quetta; second shura in FATA; "
                "Haqqani support base in Waziristan/Miranshah/Mir Ali"
            ),
            "source_id": "rand_mg595",
        },
        "international_forces": {
            "organization_id": "coalition",
            "stock_schedule": coalition_schedule(),
            "initial_location_rule": (
                "neutral equal allocation within documented 2004 operational footprint; "
                "aggregate stock only, no inferred country-by-country tactical distribution"
            ),
            "initial_locality_ids": [
                "AF0302-HQ",  # Bagram
                "AF2701-HQ",  # Kandahar
                "AF0101-HQ",  # Kabul / ISAF
                "AF1901-HQ",  # Kunduz / early ISAF expansion
            ],
            "later_rsm_footprint_reference": [
                "AF0101-HQ", "AF0302-HQ", "AF2101-HQ", "AF3201-HQ",
                "AF2701-HQ", "AF0701-HQ",
            ],
            "later_rsm_footprint_semantics": (
                "Kabul/Bagram hub plus Mazar-e Sharif, Herat, Kandahar and "
                "Laghman regional commands; retained as provenance/diagnostic "
                "rather than forcing tactical movement"
            ),
        },
        "control_validation": {
            "source_date": "2017-10-15",
            "source_units": 407,
            "benchmark_units": 401,
            "mapped_benchmark_units": 400,
            "missing_benchmark_district_ids": ["AF2409"],
            "crosswalk_file": "data/processed/sigar_407_to_401_crosswalk.csv",
            "control_401_file": "data/processed/sigar_oct2017_control_401.csv",
            "scale": {
                "INS Control": 0.0,
                "INS Influence": 0.25,
                "Contested": 0.5,
                "GIRoA Influence": 0.75,
                "GIRoA Control": 1.0,
            },
            "aggregation": "SIGAR-population-weighted mean for many-to-one mappings",
            "outcome_used_for_initialization": False,
        },
        "sources": {
            "un_s_2003_1212": {
                "url": "https://digitallibrary.un.org/record/510126/files/S_2003_1212-EN.pdf",
                "local_file": "data/raw/un_s_2003_1212.pdf",
                "sha256": sha256(RAW / "un_s_2003_1212.pdf"),
            },
            "gao_04_403_state_comment": {
                "url": "https://www.gao.gov/products/gao-04-403",
            },
            "rand_mg595": {
                "url": "https://www.rand.org/pubs/monographs/MG595.html",
                "local_file": "data/raw/rand_mg595.pdf",
                "sha256": sha256(RAW / "rand_mg595.pdf"),
            },
            "brookings_afghanistan_index_2020": {
                "url": "https://www.brookings.edu/articles/afghanistan-index/",
                "local_file": "data/raw/brookings_afghanistan_index_2020.pdf",
                "sha256": sha256(RAW / "brookings_afghanistan_index_2020.pdf"),
                "machine_table": "data/raw/brookings_troop_levels_2001_2019.csv",
                "machine_table_sha256": sha256(RAW / "brookings_troop_levels_2001_2019.csv"),
            },
            "lead_ig_ofs_2020_q1": {
                "url": (
                    "https://media.defense.gov/2020/Nov/17/2002536762/-1/-1/1/"
                    "LEAD%20INSPECTOR%20GENERAL%20FOR%20OPERATION%20FREEDOM%27S%20SENTINEL.PDF"
                ),
            },
            "dod_2020_07_14_plus_nato_2020_06": {
                "url": (
                    "https://www.defense.gov/News/Releases/Release/Article/2274035/"
                    "statement-from-chief-pentagon-spokesperson-jonathan-hoffman-on-135-days-since-t/"
                ),
            },
            "dod_2020_11_17_plus_lead_ig_2020_q4": {
                "url": (
                    "https://www.defense.gov/News/News-Stories/article/article/2418416/"
                ),
            },
            "dod_2021_01_15_plus_nato_2021_02": {
                "url": (
                    "https://www.defense.gov/News/Releases/Release/Article/2473337/"
                    "statement-by-acting-defense-secretary-christopher-miller-on-force-levels-in-afg/"
                ),
                "nato_local_file": "data/raw/nato_rsm_2021_02.pdf",
                "nato_sha256": sha256(RAW / "nato_rsm_2021_02.pdf"),
            },
            "post_retrograde_residual_force": {
                "url": (
                    "https://www.defense.gov/News/Transcripts/Transcript/Article/2702966/"
                    "secretary-of-defense-austin-and-chairman-of-the-joint-chiefs-of-staff-gen-mille/"
                ),
                "note": (
                    "650 residual diplomatic-security personnel is a secondary "
                    "historical count retained only for the post-retrograde stock"
                ),
            },
            "dod_state_joint_statement_2021_08_15": {
                "url": (
                    "https://www.defense.gov/News/Releases/Release/Article/2732053/"
                    "joint-statement-from-the-department-of-state-and-department-of-defense-update-o/"
                ),
            },
            "sigar_2018_01_30_addendum": {
                "local_file": "data/raw/sigar_2018_01_30_addendum.pdf",
                "sha256": sha256(RAW / "sigar_2018_01_30_addendum.pdf"),
            },
            "natural_earth_admin0_10m": {
                "url": (
                    "https://github.com/nvkelso/natural-earth-vector/"
                    "blob/master/geojson/ne_10m_admin_0_countries.geojson"
                ),
                "local_file": "data/raw/natural_earth_admin0_10m.geojson",
                "sha256": sha256(RAW / "natural_earth_admin0_10m.geojson"),
            },
        },
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(OUT.relative_to(ROOT.parent.parent)),
        "sha256": sha256(OUT),
        "pakistan_border_districts": len(payload["pakistan"]["border_district_ids"]),
        "coalition_schedule_points": len(payload["international_forces"]["stock_schedule"]),
        "taliban_envelope": payload["initialization"]["taliban"]["personnel_envelope"],
    }, indent=2))


if __name__ == "__main__":
    main()
