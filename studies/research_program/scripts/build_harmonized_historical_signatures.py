"""Build a common monthly, observation-only signature across four cases.

The input panels are historical event records, not simulator output. The
builder puts each case on a case-native local-unit/month grid, uses only the
declared adjacency topology, and retains the temporal-lead and topology-label
shuffle diagnostics. It never fits parameters and cannot certify the core or
promote a causal reproduction theory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from shapely.geometry import shape
from shapely.strtree import STRtree


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies" / "research_program"
HORIZONS = (1, 2, 4, 8)
SHUFFLE_SEED = 20260905


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ref(path: Path) -> dict[str, str]:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": _sha256(path)}


def _months(start: str, end: str) -> list[str]:
    sy, sm = (int(x) for x in start.split("-"))
    ey, em = (int(x) for x in end.split("-"))
    out: list[str] = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + (m == 12), 1 if m == 12 else m + 1)
    return out


def _read_json_neighbors(path: Path) -> dict[str, set[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        unit: set(neighbors)
        for unit, neighbors in payload.get("neighbors", {}).items()
    }


def _read_gadm_neighbors(path: Path) -> dict[str, set[str]]:
    with zipfile.ZipFile(path) as archive:
        name = archive.namelist()[0]
        payload = json.loads(archive.read(name))
    geometries: dict[str, Any] = {}
    for feature in payload.get("features", []):
        gid = feature.get("properties", {}).get("GID_2")
        if gid and feature.get("geometry"):
            geometries[gid] = shape(feature["geometry"])
    ordered = list(geometries)
    tree = STRtree([geometries[unit] for unit in ordered])
    neighbors: dict[str, set[str]] = {unit: set() for unit in ordered}
    for i, unit in enumerate(ordered):
        geometry = geometries[unit]
        for candidate in tree.query(geometry):
            j = int(candidate)
            if i != j and geometry.touches(geometries[ordered[j]]):
                neighbors[unit].add(ordered[j])
    return neighbors


def _read_panel(path: Path, case_id: str) -> tuple[dict[tuple[str, str], int], set[str], set[str], Counter[str]]:
    values: dict[tuple[str, str], int] = defaultdict(int)
    units: set[str] = set()
    observed_months: set[str] = set()
    split_counts: Counter[str] = Counter()
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if case_id == "nepal_2001_2006":
                unit = row["district_id"]
                month = row["week_start"][:7]
                event_columns = [name for name in row if name.endswith("_events")]
                event_count = sum(int(float(row[name] or 0)) for name in event_columns)
            elif case_id == "afghanistan_2004_2021":
                unit = row["district_id"]
                month = row["month_start"][:7]
                event_columns = [name for name in row if name.endswith("_events")]
                event_count = sum(int(float(row[name] or 0)) for name in event_columns)
            else:
                unit = row["geography_id"]
                month = row["month"][:7]
                event_count = int(float(row["event_count"] or 0))
            units.add(unit)
            observed_months.add(month)
            values[(unit, month)] += event_count
            split_counts[row.get("split", "not_declared")] += 1
    return dict(values), units, observed_months, split_counts


def _stratum_values(path: Path, case_id: str) -> dict[str, tuple[dict[tuple[str, str], int], list[str]]]:
    """Return case-native event-class panels for measurement sensitivity checks."""
    if case_id == "nepal_2001_2006":
        groups = {
            "government_maoist_state_based": ["government_maoist_state_based_events"],
            "state_one_sided": ["state_one_sided_events"],
            "maoist_one_sided": ["maoist_one_sided_events"],
        }
    elif case_id == "afghanistan_2004_2021":
        groups = {
            "taliban_state_based": ["taliban_state_based_events"],
            "taliban_one_sided": ["taliban_one_sided_events"],
            "taliban_faction": [
                "taliban_faction_nonstate_events",
                "taliban_faction_state_based_events",
            ],
            "government_one_sided": ["government_one_sided_events"],
            "external_state_based": ["external_state_based_events"],
        }
    else:
        return {}
    values: dict[str, dict[tuple[str, str], int]] = {
        name: defaultdict(int) for name in groups
    }
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if case_id == "nepal_2001_2006":
                unit, month = row["district_id"], row["week_start"][:7]
            else:
                unit, month = row["district_id"], row["month_start"][:7]
            for name, columns in groups.items():
                values[name][(unit, month)] += sum(
                    int(float(row.get(column, 0) or 0)) for column in columns
                )
    return {
        name: (dict(panel), groups[name])
        for name, panel in values.items()
        if any(panel.values())
    }


def _metrics(
    values: dict[tuple[str, str], int],
    units: list[str],
    months: list[str],
    neighbors: dict[str, set[str]],
    horizon: int,
) -> dict[str, Any]:
    index = {month: i for i, month in enumerate(months)}
    activity = {
        (unit, index[month]): values.get((unit, month), 0) > 0
        for unit in units
        for month in months
    }
    renew_n = renew_d = inactive_n = inactive_d = adjacent_n = adjacent_d = lead_n = lead_d = 0
    for t in range(len(months) - horizon):
        future = t + horizon
        for unit in units:
            now = activity[(unit, t)]
            later = activity[(unit, future)]
            if now:
                renew_d += 1
                renew_n += int(later)
            else:
                inactive_d += 1
                inactive_n += int(later)
                exposed = any(activity.get((neighbor, t), False) for neighbor in neighbors.get(unit, ()))
                if exposed:
                    adjacent_d += 1
                    adjacent_n += int(later)
            # Reverse-time placebo: future neighbor activity must not predict
            # a target state that was already active in the past. Conditioning
            # on future target inactivity keeps the placebo distinct from the
            # forward transition estimand.
            if not later:
                future_exposed = any(
                    activity.get((neighbor, future), False) for neighbor in neighbors.get(unit, ())
                )
                if future_exposed:
                    lead_d += 1
                    lead_n += int(now)
    def rate(n: int, d: int) -> float | None:
        return n / d if d else None
    return {
        "horizon_months": horizon,
        "same_unit_renewal": {"numerator": renew_n, "denominator": renew_d, "rate": rate(renew_n, renew_d)},
        "inactive_unit_activation": {"numerator": inactive_n, "denominator": inactive_d, "rate": rate(inactive_n, inactive_d)},
        "adjacent_exposure_activation": {"numerator": adjacent_n, "denominator": adjacent_d, "rate": rate(adjacent_n, adjacent_d)},
        "temporal_lead_placebo": {"numerator": lead_n, "denominator": lead_d, "rate": rate(lead_n, lead_d)},
    }


def _shuffle(neighbors: dict[str, set[str]], seed: int) -> dict[str, set[str]]:
    units = sorted(neighbors)
    shuffled = units[:]
    random.Random(seed).shuffle(shuffled)
    relabel = dict(zip(units, shuffled))
    inverse = {new: old for old, new in relabel.items()}
    # Apply the permutation to both endpoints so the null is isomorphic and
    # preserves symmetry, degree sequence, and the absence of self-loops.
    return {
        unit: {relabel[neighbor] for neighbor in neighbors.get(inverse[unit], set())}
        for unit in units
    }


def _case(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    panel = root / spec["panel"]
    topology_file = root / spec["topology"]
    values, event_units, observed, split_counts = _read_panel(panel, spec["case_id"])
    start = min(observed)
    end = max(observed)
    months = _months(start, end)
    neighbors = _read_json_neighbors(topology_file) if spec["topology_type"] == "json" else _read_gadm_neighbors(topology_file)
    topology_units = sorted(neighbors)
    units = topology_units
    metrics = [_metrics(values, units, months, neighbors, h) for h in HORIZONS]
    shuffled = _shuffle(neighbors, SHUFFLE_SEED)
    null_metrics = [_metrics(values, units, months, shuffled, h) for h in HORIZONS]
    stratum_sensitivity = []
    for stratum, (stratum_values, source_columns) in _stratum_values(panel, spec["case_id"]).items():
        stratum_sensitivity.append(
            {
                "stratum": stratum,
                "source_columns": source_columns,
                "metrics": _metrics(stratum_values, units, months, neighbors, 1),
                "interpretation": "Case-native event-class sensitivity only; not a common insurgent outcome or actor-identification result.",
            }
        )
    return {
        "case_id": spec["case_id"],
        "frequency": "monthly",
        "period": {"start": start, "end": end, "months": len(months)},
        "panel_scope": {
            "topology_units": len(topology_units),
            "event_units": len(event_units),
            "unmatched_event_units": sorted(event_units - set(topology_units)),
            "event_rows": len(values),
            "split_counts": dict(split_counts),
        },
        "metrics": metrics,
        "stratum_sensitivity": stratum_sensitivity,
        "topology_label_shuffle_null": {"seed": SHUFFLE_SEED, "metrics": null_metrics},
        "provenance": [_ref(panel), _ref(topology_file)],
        "interpretation": "Historical event recurrence and adjacency are descriptive proxies; they do not identify actor-level reproduction, control, or intervention efficacy.",
    }


def _pooled(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, horizon in enumerate(HORIZONS):
        pooled: dict[str, dict[str, int]] = {}
        means: dict[str, list[float]] = defaultdict(list)
        for case in cases:
            for name in ("same_unit_renewal", "inactive_unit_activation", "adjacent_exposure_activation", "temporal_lead_placebo"):
                item = case["metrics"][index][name]
                pooled.setdefault(name, {"numerator": 0, "denominator": 0})
                pooled[name]["numerator"] += item["numerator"]
                pooled[name]["denominator"] += item["denominator"]
                if item["rate"] is not None:
                    means[name].append(item["rate"])
        for name, item in pooled.items():
            item["rate"] = item["numerator"] / item["denominator"] if item["denominator"] else None
            item["case_unweighted_mean_rate"] = sum(means[name]) / len(means[name]) if means[name] else None
        output.append({"horizon_months": horizon, "pooled": pooled})
    return output


def build(root: Path = ROOT) -> dict[str, Any]:
    specs = [
        {
            "case_id": "nepal_2001_2006",
            "panel": "studies/nepal_2001_2006/data/processed/district_week_panel.csv",
            "topology": "studies/nepal_2001_2006/data/processed/district_adjacency.json",
            "topology_type": "json",
        },
        {
            "case_id": "afghanistan_2004_2021",
            "panel": "studies/afghanistan_2004_2021/data/processed/district_month_panel.csv",
            "topology": "studies/afghanistan_2004_2021/data/processed/district_adjacency.json",
            "topology_type": "json",
        },
        {
            "case_id": "colombia_1984_2016",
            "panel": "studies/colombia_1984_2016/data/processed/ucdp_colombia_1984_2016_geography_month_panel.csv",
            "topology": "studies/colombia_1984_2016/data/raw/gadm41_COL_2.json.zip",
            "topology_type": "gadm",
        },
        {
            "case_id": "iraq_2003_2011",
            "panel": "studies/iraq_2003_2011/data/processed/ucdp_iraq_2003_2011_geography_month_panel.csv",
            "topology": "studies/iraq_2003_2011/data/raw/gadm41_IRQ_2.json.zip",
            "topology_type": "gadm",
        },
    ]
    cases = [_case(root, spec) for spec in specs]
    return {
        "schema_version": "1.0.0",
        "program_id": "comparative-insurgency-v1",
        "status": "harmonized_historical_event_signature_not_causal",
        "historical_outcomes_used": True,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
        "frequency": "monthly",
        "event_definition": "case-native organized-violence event count > 0 in the local unit-month",
        "stratum_sensitivity_definition": "Nepal and Afghanistan are re-screened by case-native event columns at one month; these are measurement sensitivity checks, not pooled outcomes.",
        "topology_definition": "declared case adjacency; GADM level-2 polygon touch adjacency where no processed adjacency artifact exists",
        "topology_null_definition": "uniform random permutation of both graph endpoints, preserving node labels, symmetry, degree sequence, and no self-loops",
        "negative_constraints": [
            "event recurrence is not actor-level insurgent reproduction",
            "adjacency must exceed temporal-lead and topology-label-shuffle nulls before propagation is considered",
            "violence-only signatures cannot establish control or COIN efficacy",
        ],
        "measurement_limitations": [
            "case-native event classes differ: Nepal uses mapped strata, Afghanistan aggregates event strata, and Colombia/Iraq use all UCDP events",
            "unassigned or low-confidence event locations are not recovered as observed actor absence; assignment-sensitivity analysis remains required",
            "Nepal weekly rows are aggregated to months, so source split labels are descriptive and not a frozen holdout",
            "the reverse-time placebo has a different conditioning set and is directional, not a causal null",
            "topology nulls use full endpoint relabeling and preserve the graph degree sequence; they are still observation-only nulls",
        ],
        "cases": cases,
        "pooled_descriptive_summary": _pooled(cases),
        "promotion_decision": {
            "stable_general_theory_licensed": False,
            "reason": "All four cases remain observation-only; Nepal and Afghanistan are legacy-bound to the moving core, while Colombia and Iraq lack complete control/presence measurement joins.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PROGRAM / "harmonized_historical_event_signatures.json")
    args = parser.parse_args()
    report = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
