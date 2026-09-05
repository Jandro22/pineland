"""Build the case-input geography without using study-period outcomes."""
from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
from collections import Counter

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
DATA = STUDY / "data"
REGIONS = {"Eastern": "NP-R1", "Central": "NP-R2", "Western": "NP-R3",
           "Mid-Western": "NP-R4", "Far-Western": "NP-R5"}


def main() -> None:
    districts = pd.read_csv(STUDY / "config" / "districts.csv")
    geography = pd.read_csv(DATA / "processed" / "district_geography.csv")
    population = pd.read_csv(DATA / "processed" / "population_2001.csv")
    frame = districts.merge(geography, on=["district_id", "district_name"], validate="one_to_one")
    frame = frame.merge(population[["district_id", "population_2001", "enumeration_affected"]],
                        on="district_id", validate="one_to_one")
    adjacency = json.loads((DATA / "processed" / "district_adjacency.json").read_text())["neighbors"]

    aliases = {}
    for row in districts.itertuples():
        for alias in str(row.aliases).split("|") + [row.district_name]:
            aliases[alias] = row.district_id
    preperiod = Counter()
    source = DATA / "raw" / "ged261" / "GEDEvent_v26_1.csv"
    with source.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["country"] != "Nepal" or "CPN-M" not in row["dyad_name"]:
                continue
            event_date = datetime.fromisoformat(row["date_start"]).date()
            if not (datetime(1996, 2, 13).date() <= event_date < datetime(2001, 11, 26).date()):
                continue
            district_id = aliases.get(row["adm_2"])
            if district_id:
                preperiod[district_id] += 1
    initial = preperiod.most_common(1)[0][0]

    containers = []
    for region, region_frame in frame.groupby("development_region", sort=False):
        containers.append({
            "container_id": REGIONS[region], "name": f"{region} Development Region",
            "population": int(region_frame.population_2001.sum()),
            "terrain": "empirical mixed terrain", "urbanization": .35,
            "language_pattern": "FS", "connectivity": .5,
            "role": "historical development-region container",
        })
    localities = [{
        "locality_id": row.district_id, "container_id": REGIONS[row.development_region],
        "name": row.district_name, "kind": "city" if row.population_2001 >= 500_000 else "town",
        "population": int(row.population_2001), "x_km": float(row.x_km), "y_km": float(row.y_km),
        "terrain_friction": 1.0, "infrastructure": .5, "administrative_capacity": .5,
        "observability": .5, "enumeration_affected": bool(row.enumeration_affected),
    } for row in frame.itertuples()]
    payload = {
        "schema_version": "1.0.0", "case_id": "nepal_2001_2006",
        "construct": "historical case inputs; no study-period outcomes",
        "containers": containers, "localities": localities, "adjacency": adjacency,
        "initial_insurgent_locality_ids": [initial],
        "initial_condition_rule": "district with most mapped pre-period CPN-M UCDP events, 1996-02-13 through 2001-11-25",
        "preperiod_event_counts": dict(sorted(preperiod.items())),
        "neutral_unidentified_inputs": {
            "terrain_friction": 1.0, "infrastructure": .5,
            "administrative_capacity": .5, "observability": .5,
            "language_pattern": "FS",
        },
        "source_hashes": {
            name: hashlib.sha256((DATA / "processed" / name).read_bytes()).hexdigest()
            for name in ("district_geography.csv", "population_2001.csv", "district_adjacency.json")
        },
    }
    destination = STUDY / "config" / "case_environment.json"
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print({"localities": len(localities), "containers": len(containers),
           "initial_insurgent_locality": initial, "preperiod_events": sum(preperiod.values())})


if __name__ == "__main__":
    main()
