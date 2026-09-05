"""Measure dyad-consistent renewal and adjacency in raw historical events.

The recorded dyad is only an actor-identity proxy: it can merge organizations,
miss actors, or reflect reporting conventions. The diagnostic therefore tests
whether the candidate's local-reproduction signature survives a conservative
identity consistency check; it is not causal evidence.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_harmonized_historical_signatures import (  # noqa: E402
    ROOT,
    _months,
    _read_json_neighbors,
    _ref,
)


PROGRAM = ROOT / "studies" / "research_program"
HORIZONS = (1, 2, 4, 8)
SHUFFLE_SEED = 20260905


def _read_events(path: Path, unit_field: str) -> tuple[dict[tuple[str, str], set[str]], set[str], set[str], int, int]:
    dyads: dict[tuple[str, str], set[str]] = defaultdict(set)
    units: set[str] = set()
    months: set[str] = set()
    rows = with_unit = 0
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            unit = row.get(unit_field, "")
            if not unit:
                continue
            date_value = row.get("date_start") or row.get("event_date") or ""
            if len(date_value) < 7:
                continue
            month = date_value[:7]
            dyad = row.get("dyad_name") or row.get("stratum") or "unclassified"
            dyads[(unit, month)].add(dyad)
            units.add(unit)
            months.add(month)
            with_unit += 1
    return dict(dyads), units, months, rows, with_unit


def _shuffle(neighbors: dict[str, set[str]], seed: int) -> dict[str, set[str]]:
    units = sorted(neighbors)
    shuffled = units[:]
    random.Random(seed).shuffle(shuffled)
    relabel = dict(zip(units, shuffled))
    inverse = {new: old for old, new in relabel.items()}
    # Relabel both endpoints; neighbor-only remapping creates an invalid null.
    return {
        unit: {relabel[neighbor] for neighbor in neighbors.get(inverse[unit], set())}
        for unit in units
    }


def _metrics(
    dyads: dict[tuple[str, str], set[str]],
    units: list[str],
    months: list[str],
    neighbors: dict[str, set[str]],
    horizon: int,
) -> dict[str, Any]:
    index = {month: i for i, month in enumerate(months)}
    renewal_d = renewal_n = actor_renewal_n = 0
    adjacency_d = adjacency_n = actor_adjacency_n = 0
    lead_d = lead_n = actor_lead_n = 0
    for t in range(len(months) - horizon):
        future = t + horizon
        now_month = months[t]
        future_month = months[future]
        for unit in units:
            now_set = dyads.get((unit, now_month), set())
            future_set = dyads.get((unit, future_month), set())
            if now_set:
                renewal_d += 1
                renewal_n += int(bool(future_set))
                actor_renewal_n += int(bool(now_set & future_set))
            else:
                neighbor_sets = [dyads.get((neighbor, now_month), set()) for neighbor in neighbors.get(unit, ())]
                exposed_dyads = set().union(*neighbor_sets) if neighbor_sets else set()
                if exposed_dyads:
                    adjacency_d += 1
                    adjacency_n += int(bool(future_set))
                    actor_adjacency_n += int(bool(future_set & exposed_dyads))
            if not future_set:
                future_neighbor_sets = [dyads.get((neighbor, future_month), set()) for neighbor in neighbors.get(unit, ())]
                future_exposed = set().union(*future_neighbor_sets) if future_neighbor_sets else set()
                if future_exposed:
                    lead_d += 1
                    lead_n += int(bool(now_set))
                    actor_lead_n += int(bool(now_set & future_exposed))
    def rate(n: int, d: int) -> float | None:
        return n / d if d else None
    return {
        "horizon_months": horizon,
        "renewal": {
            "generic_numerator": renewal_n,
            "actor_consistent_numerator": actor_renewal_n,
            "denominator": renewal_d,
            "generic_rate": rate(renewal_n, renewal_d),
            "actor_consistent_rate": rate(actor_renewal_n, renewal_d),
        },
        "adjacent_activation": {
            "generic_numerator": adjacency_n,
            "actor_consistent_numerator": actor_adjacency_n,
            "denominator": adjacency_d,
            "generic_rate": rate(adjacency_n, adjacency_d),
            "actor_consistent_rate": rate(actor_adjacency_n, adjacency_d),
            "actor_consistent_share_of_generic": rate(actor_adjacency_n, adjacency_n),
        },
        "reverse_time_placebo": {
            "generic_numerator": lead_n,
            "actor_consistent_numerator": actor_lead_n,
            "denominator": lead_d,
            "generic_rate": rate(lead_n, lead_d),
            "actor_consistent_rate": rate(actor_lead_n, lead_d),
        },
    }


def _case(root: Path, spec: dict[str, str]) -> dict[str, Any]:
    event_path = root / spec["events"]
    topology_path = root / spec["topology"]
    dyads, event_units, observed, rows, with_unit = _read_events(event_path, spec["unit_field"])
    months = _months(min(observed), max(observed))
    neighbors = _read_json_neighbors(topology_path)
    units = sorted(neighbors)
    metrics = [_metrics(dyads, units, months, neighbors, h) for h in HORIZONS]
    shuffled_metrics = [_metrics(dyads, units, months, _shuffle(neighbors, SHUFFLE_SEED), h) for h in HORIZONS]
    return {
        "case_id": spec["case_id"],
        "status": "recorded_dyad_identity_proxy_not_causal",
        "period": {"start": min(observed), "end": max(observed), "months": len(months)},
        "coverage": {
            "raw_event_rows": rows,
            "events_with_unit": with_unit,
            "unit_coverage": with_unit / rows if rows else None,
            "event_units": len(event_units),
            "topology_units": len(units),
            "unmatched_event_units": sorted(event_units - set(units)),
        },
        "metrics": metrics,
        "topology_label_shuffle_null": {"seed": SHUFFLE_SEED, "metrics": shuffled_metrics},
        "provenance": [_ref(event_path), _ref(topology_path)],
        "identity_guard": "dyad_name/stratum is a reporting identity proxy, not a verified insurgent organization genealogy.",
    }


def build(root: Path = ROOT) -> dict[str, Any]:
    specs = [
        {
            "case_id": "nepal_2001_2006",
            "events": "studies/nepal_2001_2006/data/processed/ucdp_nepal_events.csv",
            "topology": "studies/nepal_2001_2006/data/processed/district_adjacency.json",
            "unit_field": "district_id",
        },
        {
            "case_id": "afghanistan_2004_2021",
            "events": "studies/afghanistan_2004_2021/data/processed/ucdp_afghanistan_events.csv",
            "topology": "studies/afghanistan_2004_2021/data/processed/district_adjacency.json",
            "unit_field": "district_id",
        },
    ]
    cases = [_case(root, spec) for spec in specs]
    return {
        "schema_version": "1.0.0",
        "program_id": "comparative-insurgency-v1",
        "status": "recorded_dyad_continuity_diagnostic_not_causal",
        "historical_outcomes_used": True,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
        "identity_unit": "recorded dyad_name, falling back to stratum",
        "topology_null_definition": "uniform random permutation of both graph endpoints, preserving node labels, symmetry, degree sequence, and no self-loops",
        "negative_constraints": [
            "same recorded dyad is not proof of the same insurgent organization",
            "generic violence renewal must not be relabeled actor-level reproduction",
            "adjacent actor-consistency must beat reverse-time and topology-shuffle nulls before propagation is considered",
        ],
        "cases": cases,
        "promotion_decision": {
            "stable_general_theory_licensed": False,
            "reason": "Only two cases expose comparable raw dyad fields, and those fields are reporting proxies without verified actor genealogy or current-core transfer validation.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PROGRAM / "actor_continuity_diagnostic.json")
    args = parser.parse_args()
    report = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
