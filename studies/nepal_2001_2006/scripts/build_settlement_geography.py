"""Build a settlement-resolution Nepal case without using study-period violence.

The 75 historical districts remain the validation units.  Each district is
represented by four real named settlement anchors: its district headquarters
and three additional GeoNames populated places chosen by deterministic
farthest-point sampling within the same administrative district code.  Modern
gazetteer population is never used for selection or weighting; each anchor is
a spatial catchment carrying a neutral share of the district's 2001 census
population.

This file intentionally creates a new schema-v2 case package rather than
overwriting the frozen district-resolution case used by earlier falsification
runs.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from math import hypot
from pathlib import Path
import re
import unicodedata
import zipfile

import pandas as pd
from pyproj import Transformer


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
DATA = STUDY / "data"
OUT = DATA / "processed"
GEONAMES = DATA / "raw" / "geonames_NP.zip"
SETTLEMENTS_PER_DISTRICT = 4

REGIONS = {
    "Eastern": ("NP-R1", "Eastern Development Region"),
    "Central": ("NP-R2", "Central Development Region"),
    "Western": ("NP-R3", "Western Development Region"),
    "Mid-Western": ("NP-R4", "Mid-Western Development Region"),
    "Far-Western": ("NP-R5", "Far-Western Development Region"),
}

ZONE_DISTRICTS = {
    "Mechi": ["Taplejung", "Panchthar", "Ilam", "Jhapa"],
    "Koshi": ["Sankhuwasabha", "Bhojpur", "Dhankuta", "Terhathum", "Sunsari", "Morang"],
    "Sagarmatha": ["Solukhumbu", "Okhaldhunga", "Khotang", "Udayapur", "Saptari", "Siraha"],
    "Janakpur": ["Dhanusha", "Mahottari", "Sarlahi", "Sindhuli", "Ramechhap", "Dolakha"],
    "Bagmati": ["Sindhupalchok", "Kavrepalanchok", "Bhaktapur", "Lalitpur", "Kathmandu", "Nuwakot", "Rasuwa", "Dhading"],
    "Narayani": ["Makwanpur", "Rautahat", "Bara", "Parsa", "Chitwan"],
    "Gandaki": ["Gorkha", "Lamjung", "Tanahun", "Syangja", "Kaski", "Manang"],
    "Dhaulagiri": ["Mustang", "Myagdi", "Parbat", "Baglung"],
    "Lumbini": ["Gulmi", "Palpa", "Nawalparasi", "Rupandehi", "Arghakhanchi", "Kapilvastu"],
    "Rapti": ["Rukum", "Rolpa", "Pyuthan", "Salyan", "Dang"],
    "Bheri": ["Banke", "Bardiya", "Surkhet", "Dailekh", "Jajarkot"],
    "Karnali": ["Dolpa", "Humla", "Jumla", "Kalikot", "Mugu"],
    "Seti": ["Bajura", "Bajhang", "Achham", "Doti", "Kailali"],
    "Mahakali": ["Kanchanpur", "Dadeldhura", "Baitadi", "Darchula"],
}
ZONE_IDS = {name: f"NP-Z{index:02d}" for index, name in enumerate(ZONE_DISTRICTS, 1)}
DISTRICT_ZONE = {district: zone for zone, districts in ZONE_DISTRICTS.items() for district in districts}

# Headquarters names are administrative geography, not conflict outcomes.
# Primary reference: OpenStreetMap Wiki Nepal/Boundaries/Districts. Historical
# 75-district merge names (Rukum, Nawalparasi) use their pre-2015 headquarters.
HQ_ALIASES = {
    "Taplejung": ["Taplejung"], "Panchthar": ["Phidim"], "Ilam": ["Ilam"],
    "Jhapa": ["Bhadrapur"], "Morang": ["Biratnagar"], "Sunsari": ["Inaruwa"],
    "Dhankuta": ["Dhankuta"], "Terhathum": ["Myanglung", "Myanglung Bazar"],
    "Sankhuwasabha": ["Khandbari"], "Bhojpur": ["Bhojpur"],
    "Solukhumbu": ["Salleri"], "Okhaldhunga": ["Okhaldhunga"],
    "Khotang": ["Diktel"], "Udayapur": ["Gaighat", "Triyuga"],
    "Saptari": ["Rajbiraj"], "Siraha": ["Siraha"],
    "Dhanusha": ["Janakpur", "Janakpur Dham"], "Mahottari": ["Jaleshwar"],
    "Sarlahi": ["Malangwa"], "Sindhuli": ["Sindhuli", "Kamalamai"],
    "Ramechhap": ["Manthali", "Ramechhap"], "Dolakha": ["Charikot", "Bhimeshwar"],
    "Sindhupalchok": ["Chautara"], "Kavrepalanchok": ["Dhulikhel"],
    "Bhaktapur": ["Bhaktapur"], "Lalitpur": ["Lalitpur", "Patan"],
    "Kathmandu": ["Kathmandu"], "Nuwakot": ["Bidur"], "Rasuwa": ["Dhunche"],
    "Dhading": ["Dhading Besi", "Dhading"], "Makwanpur": ["Hetauda"],
    "Rautahat": ["Gaur"], "Bara": ["Kalaiya"], "Parsa": ["Birgunj"],
    "Chitwan": ["Bharatpur"], "Gorkha": ["Gorkha"], "Lamjung": ["Besisahar"],
    "Tanahun": ["Damauli", "Vyas"], "Syangja": ["Putalibazar"],
    "Kaski": ["Pokhara"], "Manang": ["Chame"], "Mustang": ["Jomsom"],
    "Myagdi": ["Beni"], "Parbat": ["Kusma"], "Baglung": ["Baglung"],
    "Gulmi": ["Tamghas"], "Palpa": ["Tansen"],
    "Nawalparasi": ["Parasi", "Ramgram"], "Rupandehi": ["Siddharthanagar", "Bhairahawa"],
    "Arghakhanchi": ["Sandhikharka"], "Kapilvastu": ["Taulihawa", "Kapilavastu"],
    "Rukum": ["Musikot", "Rukumkot"], "Rolpa": ["Liwang", "Liwang Bazar"],
    "Pyuthan": ["Pyuthan", "Pyuthan Khalanga"], "Salyan": ["Salyan", "Salyan Khalanga"],
    "Dang": ["Ghorahi"], "Banke": ["Nepalgunj", "Nepalganj"],
    "Bardiya": ["Gulariya"], "Surkhet": ["Birendranagar"],
    "Dailekh": ["Dailekh", "Narayan"], "Jajarkot": ["Jajarkot", "Khalanga"],
    "Dolpa": ["Dunai"], "Humla": ["Simikot"], "Jumla": ["Jumla"],
    "Kalikot": ["Manma"], "Mugu": ["Gamgadhi"], "Bajura": ["Martadi"],
    "Bajhang": ["Chainpur", "Jayaprithvi"], "Achham": ["Mangalsen"],
    "Doti": ["Dipayal", "Silgadhi"], "Kailali": ["Dhangadhi"],
    "Kanchanpur": ["Mahendranagar", "Bhimdatta"],
    "Dadeldhura": ["Dadeldhura", "Amargadhi"],
    "Baitadi": ["Baitadi", "Dasharathchand"], "Darchula": ["Darchula", "Khalanga"],
}

# Historical districts split after the benchmark period.  Add one modern
# anchor from the other successor district so secondary-place selection spans
# the full historical territory.
MERGED_DISTRICT_EXTRA_ANCHORS = {
    "Rukum": ["Rukumkot"],
    "Nawalparasi": ["Kawasoti"],
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def read_geonames() -> list[dict]:
    if not GEONAMES.exists():
        raise FileNotFoundError(
            f"{GEONAMES} missing; download https://download.geonames.org/export/dump/NP.zip"
        )
    rows = []
    with zipfile.ZipFile(GEONAMES) as archive:
        reader = csv.reader(io.TextIOWrapper(archive.open("NP.txt"), encoding="utf-8"), delimiter="\t")
        for row in reader:
            if len(row) < 15 or row[6] != "P":
                continue
            names = {norm(row[1]), norm(row[2])}
            names.update(norm(item) for item in row[3].split(",") if item)
            rows.append({
                "geonameid": row[0], "name": row[1], "ascii_name": row[2],
                "names": names, "lat": float(row[4]), "lon": float(row[5]),
                "feature_code": row[7], "admin1": row[10], "admin2": row[11],
                "population": int(row[14] or 0),
            })
    return rows


def best_match(places: list[dict], aliases: list[str], centroid: tuple[float, float]) -> dict:
    lat, lon = centroid
    priority = {"PPLC": 0, "PPLA": 1, "PPLA2": 2, "PPLA3": 3, "PPLA4": 4, "PPL": 5}
    for alias in aliases:
        key = norm(alias)
        candidates = [row for row in places if key in row["names"]]
        if candidates:
            return min(candidates, key=lambda row: (
                priority.get(row["feature_code"], 9),
                (row["lat"] - lat) ** 2 + (row["lon"] - lon) ** 2,
                row["geonameid"],
            ))
    raise RuntimeError({"missing_headquarters": aliases})


def farthest_anchors(candidates: list[dict], hq: dict, count: int) -> list[dict]:
    unique = {}
    for row in candidates:
        key = norm(row["ascii_name"] or row["name"])
        if not key or key in hq["names"]:
            continue
        unique.setdefault(key, row)
    pool = list(unique.values())
    if len(pool) < count:
        raise RuntimeError(f"fewer than {count} secondary populated places for admin2={hq['admin2']}")
    def dist(a, b):
        # Local ranking only; the model itself uses projected kilometre coordinates.
        return hypot((a["lat"] - b["lat"]) * 111.0,
                     (a["lon"] - b["lon"]) * 98.0)
    selected = []
    remaining = list(pool)
    while len(selected) < count:
        anchors = [hq, *selected]
        chosen = max(remaining, key=lambda row: (
            min(dist(row, anchor) for anchor in anchors), row["geonameid"]
        ))
        selected.append(chosen)
        remaining.remove(chosen)
    return selected


def main() -> None:
    districts = pd.read_csv(STUDY / "config" / "districts.csv")
    geography = pd.read_csv(OUT / "district_geography.csv")
    population = pd.read_csv(OUT / "population_2001.csv")
    frame = districts.merge(geography, on=["district_id", "district_name"], validate="one_to_one")
    frame = frame.merge(population[["district_id", "population_2001"]], on="district_id", validate="one_to_one")
    district_neighbors = json.loads((OUT / "district_adjacency.json").read_text())["neighbors"]
    places = read_geonames()
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True)

    selected_by_district: dict[str, list[dict]] = {}
    rows = []
    for district in frame.itertuples():
        if district.district_name not in HQ_ALIASES:
            raise RuntimeError(f"no headquarters declaration for {district.district_name}")
        centroid = (float(district.centroid_latitude), float(district.centroid_longitude))
        hq = best_match(places, HQ_ALIASES[district.district_name], centroid)
        admin2_codes = {hq["admin2"]}
        for alias in MERGED_DISTRICT_EXTRA_ANCHORS.get(district.district_name, []):
            admin2_codes.add(best_match(places, [alias], centroid)["admin2"])
        candidates = [place for place in places if place["admin2"] in admin2_codes]
        secondaries = farthest_anchors(candidates, hq, SETTLEMENTS_PER_DISTRICT - 1)
        selected = [hq, *secondaries]
        selected_by_district[district.district_id] = selected
        total = int(district.population_2001)
        shares = [total // SETTLEMENTS_PER_DISTRICT for _ in range(SETTLEMENTS_PER_DISTRICT)]
        shares[0] += total - sum(shares)
        for index, (place, represented_population) in enumerate(zip(selected, shares), 1):
            x, y = transformer.transform(place["lon"], place["lat"])
            rows.append({
                "locality_id": f"{district.district_id}-{'HQ' if index == 1 else f'S{index-1:02d}'}",
                "district_id": district.district_id,
                "district_name": district.district_name,
                "development_region": district.development_region,
                "zone": DISTRICT_ZONE[district.district_name],
                "name": (HQ_ALIASES[district.district_name][0] if index == 1
                         else place["ascii_name"] or place["name"]),
                "kind": ("city" if index == 1 and total >= 500_000 else
                         "town" if index == 1 else "village-cluster"),
                "administrative_role": "district_headquarters" if index == 1 else "settlement",
                "population": represented_population,
                "latitude": place["lat"], "longitude": place["lon"],
                "x_abs_m": x, "y_abs_m": y,
                "geonameid": place["geonameid"], "geonames_admin2": place["admin2"],
                "selection_role": "district_headquarters" if index == 1 else "farthest_point_anchor",
            })

    min_x = min(row["x_abs_m"] for row in rows)
    min_y = min(row["y_abs_m"] for row in rows)
    for row in rows:
        row["x_km"] = (row.pop("x_abs_m") - min_x) / 1000.0
        row["y_km"] = (row.pop("y_abs_m") - min_y) / 1000.0

    by_district = {}
    for row in rows:
        by_district.setdefault(row["district_id"], []).append(row)
    adjacency = {row["locality_id"]: [] for row in rows}
    def connect(a: str, b: str) -> None:
        if b not in adjacency[a]: adjacency[a].append(b)
        if a not in adjacency[b]: adjacency[b].append(a)
    lookup = {row["locality_id"]: row for row in rows}
    for district_id, localities in by_district.items():
        hq = next(row for row in localities if row["administrative_role"] == "district_headquarters")
        secondary = [row for row in localities if row is not hq]
        for row in localities:
            if row is not hq:
                connect(hq["locality_id"], row["locality_id"])
        # Give the secondary catchments one alternate intradistrict path
        # without turning every district into a complete graph.
        if len(secondary) > 1:
            ordered = [secondary.pop(0)]
            while secondary:
                last = ordered[-1]
                nxt = min(secondary, key=lambda row: hypot(
                    row["x_km"] - last["x_km"], row["y_km"] - last["y_km"]
                ))
                connect(last["locality_id"], nxt["locality_id"])
                ordered.append(nxt)
                secondary.remove(nxt)
    seen_district_edges = set()
    for first, neighbors in district_neighbors.items():
        for second in neighbors:
            edge = tuple(sorted((first, second)))
            if edge in seen_district_edges:
                continue
            seen_district_edges.add(edge)
            pair = min(
                ((a, b) for a in by_district[first] for b in by_district[second]),
                key=lambda pair: hypot(pair[0]["x_km"] - pair[1]["x_km"],
                                       pair[0]["y_km"] - pair[1]["y_km"]),
            )
            connect(pair[0]["locality_id"], pair[1]["locality_id"])
    adjacency = {key: sorted(values) for key, values in sorted(adjacency.items())}
    if any(not values for values in adjacency.values()):
        raise RuntimeError("settlement adjacency contains isolated locality")

    regions = [{
        "region_id": region_id, "name": region_name, "role": "historical development region",
    } for _, (region_id, region_name) in REGIONS.items()]
    district_region_name = {row.district_name: row.development_region for row in frame.itertuples()}
    zones = [{
        "zone_id": ZONE_IDS[name], "name": f"{name} Zone",
        "region_id": REGIONS[district_region_name[districts[0]]][0],
        "role": "historical administrative zone",
    } for name, districts in ZONE_DISTRICTS.items()]
    district_rows = []
    for district in frame.itertuples():
        region_id = REGIONS[district.development_region][0]
        district_rows.append({
            "district_id": district.district_id, "name": district.district_name,
            "population": int(district.population_2001), "region_id": region_id,
            "zone_id": ZONE_IDS[DISTRICT_ZONE[district.district_name]],
            "terrain": "empirical mixed terrain", "urbanization": .35,
            "language_pattern": "FS", "connectivity": .5,
            "role": "historical 2001-2006 validation district",
        })

    localities = [{
        "locality_id": row["locality_id"], "district_id": row["district_id"],
        "name": row["name"], "kind": row["kind"], "population": row["population"],
        "x_km": row["x_km"], "y_km": row["y_km"],
        "terrain_friction": 1.0, "infrastructure": .5, "administrative_capacity": .5,
        "observability": .5, "administrative_role": row["administrative_role"],
        "geonameid": row["geonameid"], "selection_role": row["selection_role"],
    } for row in rows]

    old_case = json.loads((STUDY / "config" / "case_environment.json").read_text())
    initial_district = old_case["initial_insurgent_locality_ids"][0]
    initial_locality = f"{initial_district}-HQ"
    payload = {
        "schema_version": "2.0.0", "case_id": "nepal_2001_2006_settlement_repair",
        "construct": "historical validation districts with exogenous named settlement anchors; no study-period outcomes used for settlement selection",
        "validation_unit": "historical_district",
        "regions": regions, "zones": zones, "districts": district_rows,
        "localities": localities, "adjacency": adjacency,
        "initial_insurgent_locality_ids": [initial_locality],
        "initial_condition_rule": old_case["initial_condition_rule"] + "; mapped to that district's headquarters settlement anchor",
        "preperiod_event_counts": old_case["preperiod_event_counts"],
        "neutral_unidentified_inputs": {
            "population_allocation": "equal four-way district catchments; integer remainder assigned to headquarters",
            "secondary_selection": "three GeoNames populated places by deterministic farthest-point coverage within headquarters admin2 code",
            "headquarters_kind": "city when historical district population_2001 >= 500000, otherwise town; secondary anchors are village-cluster",
            "terrain_friction": 1.0, "infrastructure": .5, "administrative_capacity": .5,
            "observability": .5, "language_pattern": "FS",
        },
        "source_hashes": {
            "district_geography.csv": sha256(OUT / "district_geography.csv"),
            "population_2001.csv": sha256(OUT / "population_2001.csv"),
            "district_adjacency.json": sha256(OUT / "district_adjacency.json"),
            "geonames_NP.zip": sha256(GEONAMES),
        },
        "source_notes": {
            "headquarters_reference": "https://wiki.openstreetmap.org/wiki/Nepal/Boundaries/Districts",
            "geonames": "https://download.geonames.org/export/dump/NP.zip; names/coordinates/admin codes only; gazetteer population excluded",
            "historical_hierarchy": "five development regions, fourteen zones, seventy-five districts",
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).drop(columns=[]).to_csv(OUT / "settlement_geography.csv", index=False)
    destination = STUDY / "config" / "case_environment_repaired.json"
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    provenance = {
        "schema_version": "1.0.0", "output": str(destination.relative_to(ROOT)),
        "settlement_count": len(localities), "district_count": len(district_rows),
        "settlements_per_district": SETTLEMENTS_PER_DISTRICT, "headquarters_count": 75,
        "selection_uses_study_period_violence": False,
        "quantitative_geonames_population_used": False,
        "output_sha256": sha256(destination),
    }
    (OUT / "settlement_geography_provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
