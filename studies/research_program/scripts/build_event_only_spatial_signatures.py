"""Compute bounded observation-only spatial signatures from event panels.

This diagnostic uses only hashed UCDP geography-month event panels and GADM
topology. It intentionally does not require the moving simulator core or the
missing control/presence joins. Results are violence-proxy diagnostics, not
identified local reproduction or causal propagation estimates.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from shapely.geometry import shape
from shapely.strtree import STRtree


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies" / "research_program"
HORIZONS = (1, 2, 4, 8)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ref(path: Path) -> dict[str, str]:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": _sha256(path)}


def _month_index(start: str, end: str) -> list[str]:
    sy, sm = (int(x) for x in start.split("-"))
    ey, em = (int(x) for x in end.split("-"))
    out: list[str] = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + (m == 12), 1 if m == 12 else m + 1)
    return out


def _read_event_panel(path: Path) -> tuple[dict[tuple[str, str], int], list[str], list[str]]:
    values: dict[tuple[str, str], int] = {}
    units: set[str] = set()
    months: set[str] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            unit = row["geography_id"]
            month = row["month"]
            units.add(unit)
            months.add(month)
            values[(unit, month)] = values.get((unit, month), 0) + int(row["event_count"])
    return values, sorted(units), sorted(months)


def _read_topology(path: Path) -> tuple[dict[str, Any], dict[str, int]]:
    with zipfile.ZipFile(path) as archive:
        name = archive.namelist()[0]
        payload = json.loads(archive.read(name))
    geometries: dict[str, Any] = {}
    for feature in payload.get("features", []):
        gid = feature.get("properties", {}).get("GID_2")
        geometry = feature.get("geometry")
        if gid and geometry:
            geometries[gid] = shape(geometry)
    ordered = list(geometries)
    tree = STRtree([geometries[gid] for gid in ordered])
    neighbors: dict[str, set[str]] = {gid: set() for gid in ordered}
    for i, gid in enumerate(ordered):
        geometry = geometries[gid]
        for candidate in tree.query(geometry):
            j = int(candidate)
            if j != i and geometry.touches(geometries[ordered[j]]):
                neighbors[gid].add(ordered[j])
    return neighbors, {gid: i for i, gid in enumerate(ordered)}


def _activity_grid(
    values: dict[tuple[str, str], int], units: list[str], months: list[str]
) -> dict[tuple[str, int], bool]:
    month_index = {month: i for i, month in enumerate(months)}
    return {
        (unit, month_index[month]): values.get((unit, month), 0) > 0
        for unit in units
        for month in months
    }


def _propagation_metrics(
    activity: dict[tuple[str, int], bool],
    units: list[str],
    months: list[str],
    neighbors: dict[str, set[str]],
    *,
    horizon: int,
) -> dict[str, Any]:
    max_t = len(months) - horizon
    renew_n = renew_d = base_n = base_d = adjacency_n = adjacency_d = 0
    lead_n = lead_d = 0
    for t in range(max_t):
        future_t = t + horizon
        for unit in units:
            now = activity[(unit, t)]
            future = activity[(unit, future_t)]
            if now:
                renew_d += 1
                renew_n += int(future)
            else:
                base_d += 1
                base_n += int(future)
                exposure = any(activity.get((neighbor, t), False) for neighbor in neighbors.get(unit, ()))
                if exposure:
                    adjacency_d += 1
                    adjacency_n += int(future)
            # Reverse-time placebo: future neighbor activity must not predict
            # a target state that was already active in the past. Conditioning
            # on future target inactivity keeps this distinct from the forward
            # transition estimand above.
            if not future:
                lead_exposure = any(
                    activity.get((neighbor, future_t), False) for neighbor in neighbors.get(unit, ())
                )
                if lead_exposure:
                    lead_d += 1
                    lead_n += int(now)
    return {
        "horizon_months": horizon,
        "same_unit_renewal": {"numerator": renew_n, "denominator": renew_d, "rate": renew_n / renew_d if renew_d else None},
        "inactive_unit_activation": {"numerator": base_n, "denominator": base_d, "rate": base_n / base_d if base_d else None},
        "adjacent_exposure_activation": {"numerator": adjacency_n, "denominator": adjacency_d, "rate": adjacency_n / adjacency_d if adjacency_d else None},
        "temporal_lead_placebo": {"numerator": lead_n, "denominator": lead_d, "rate": lead_n / lead_d if lead_d else None},
    }


def _shuffle_neighbors(neighbors: dict[str, set[str]], seed: int) -> dict[str, set[str]]:
    units = sorted(neighbors)
    shuffled = units[:]
    random.Random(seed).shuffle(shuffled)
    relabel = dict(zip(units, shuffled))
    inverse = {new: old for old, new in relabel.items()}
    # Relabel both endpoints of every edge. Neighbor-only remapping can
    # create asymmetric graphs and self-loops, invalidating the null.
    return {
        unit: {relabel[neighbor] for neighbor in neighbors.get(inverse[unit], set())}
        for unit in units
    }


def _case(root: Path, case_id: str, event_path: str, topology_path: str, start: str, end: str) -> dict[str, Any]:
    event_file = root / event_path
    topology_file = root / topology_path
    values, event_units, observed_months = _read_event_panel(event_file)
    months = _month_index(start, end)
    topology, _ = _read_topology(topology_file)
    topology_units = sorted(topology)
    units = topology_units
    activity = _activity_grid(values, units, months)
    shuffled = _shuffle_neighbors(topology, seed=20260905)
    metrics = [_propagation_metrics(activity, units, months, topology, horizon=h) for h in HORIZONS]
    shuffle_metrics = [_propagation_metrics(activity, units, months, shuffled, horizon=h) for h in HORIZONS]
    unmatched = sorted(set(event_units) - set(topology_units))
    return {
        "case_id": case_id,
        "status": "violence_proxy_signature_not_case_ready",
        "panel_scope": {
            "unit": "GADM level-2 geography",
            "period_start": start,
            "period_end": end,
            "months": len(months),
            "topology_units": len(topology_units),
            "event_units": len(event_units),
            "event_rows": len(values),
            "event_units_unmatched_to_topology": unmatched,
        },
        "metrics": metrics,
        "topology_label_shuffle_null": {"seed": 20260905, "metrics": shuffle_metrics},
        "provenance": [_ref(event_file), _ref(topology_file)],
        "guard": "Event recurrence and adjacency are descriptive violence proxies. Missing control/presence and actor identity prevent causal reproduction or transfer claims.",
    }


def build(root: Path = ROOT) -> dict[str, Any]:
    cases = [
        _case(
            root,
            "colombia_1984_2016",
            "studies/colombia_1984_2016/data/processed/ucdp_colombia_1984_2016_geography_month_panel.csv",
            "studies/colombia_1984_2016/data/raw/gadm41_COL_2.json.zip",
            "1989-01",
            "2016-12",
        ),
        _case(
            root,
            "iraq_2003_2011",
            "studies/iraq_2003_2011/data/processed/ucdp_iraq_2003_2011_geography_month_panel.csv",
            "studies/iraq_2003_2011/data/raw/gadm41_IRQ_2.json.zip",
            "2003-03",
            "2011-12",
        ),
    ]
    return {
        "schema_version": "1.0.0",
        "program_id": "comparative-insurgency-v1",
        "status": "event_only_spatial_signature_diagnostic_not_causal",
        "historical_outcomes_used": True,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
        "topology_method": "GADM level-2 polygon touch adjacency",
        "topology_null_definition": "uniform random permutation of both graph endpoints, preserving node labels, symmetry, degree sequence, and no self-loops",
        "complete_grid_rule": "All GADM units are crossed with the declared observed-data period; absent event rows are represented as zero only within the event-observation proxy.",
        "interpretation_guard": "These metrics test whether violence events exhibit renewal or spatial clustering. They do not identify insurgent local reproduction, actor transmission, control, or COIN efficacy.",
        "measurement_limitations": [
            "event rows are a violence-observation proxy and do not identify actor-level reproduction",
            "unassigned or low-confidence event locations are not equivalent to verified zero activity",
            "Colombia and Iraq event classes are case-native UCDP aggregates rather than a common insurgent outcome",
            "topology nulls use full endpoint relabeling and preserve graph symmetry and degree sequence",
        ],
        "promotion_decision": {
            "stable_general_theory_licensed": False,
            "reason": "Control/presence joins, actor identity, and case-level measurement models remain incomplete.",
        },
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PROGRAM / "event_only_spatial_signature_diagnostic.json")
    args = parser.parse_args()
    report = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
