"""Validate that preregistered synthetic protocols discriminate rival gap mechanisms.

These are deliberately study-layer surrogate equations, not Pineland mechanisms.
They exist only to prove that the future experiments are structurally
identifying before any core implementation or historical confrontation.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.reproducibility import file_sha256, model_sha256, repository_state  # noqa: E402

CONTRACT = ROOT / "studies/research_program/missing_construct_mechanism_discrimination_contract_v1.json"
OUTPUT = ROOT / "studies/research_program/missing_construct_mechanism_discrimination_recovery_v1.json"

DAYS = 80


def clamp(x: float) -> float:
    return min(1.0, max(0.0, x))


def governance_protocol(name: str, high: bool = False) -> dict[str, list[float]]:
    presence = [0.0] * DAYS
    investment = [0.0] * DAYS
    events = [0.0] * DAYS
    if name == "presence_pulse_then_withdrawal":
        for t in range(10, 31):
            presence[t] = 0.8
            investment[t] = 0.65
    elif name == "silent_governance_investment_without_events":
        for t in range(10, 41):
            presence[t] = 0.75
            investment[t] = 0.7
    elif name == "event_pulse_without_continuing_presence":
        for t in range(10, 16):
            presence[t] = 0.8
            events[t] = 0.9
    elif name == "low_vs_high_investment_dose":
        dose = 0.8 if high else 0.25
        for t in range(10, 41):
            presence[t] = 0.75
            investment[t] = dose
            events[t] = 0.35
    elif name == "repeated_pulses_with_washout":
        for start in (8, 36):
            for t in range(start, start + 8):
                presence[t] = 0.8
                investment[t] = 0.65
                events[t] = 0.55
    else:
        raise KeyError(name)
    return {"presence": presence, "investment": investment, "events": events}


def governance_candidate(name: str, p: dict[str, list[float]]) -> list[float]:
    out = [0.0] * DAYS
    stock = 0.0
    for t in range(DAYS):
        presence = p["presence"][t]
        investment = p["investment"][t]
        event = p["events"][t]
        if name == "G0_instant_presence":
            out[t] = clamp(presence * (0.35 + 0.65 * max(investment, event)))
        elif name == "G1_capacity_stock":
            stock *= math.exp(-0.055)
            build = 0.075 * presence * investment * (1.0 - stock)
            stock = clamp(stock + build)
            out[t] = stock
        elif name == "G2_event_reinforcement":
            stock *= math.exp(-0.055)
            stock = clamp(stock + 0.085 * event * (1.0 - stock))
            out[t] = stock
        else:
            raise KeyError(name)
    return out


def access_protocol(name: str, high: bool = False) -> dict[str, list[float]]:
    presence = [0.0] * DAYS
    effort = [0.0] * DAYS
    event = [0.0] * DAYS
    if name == "presence_without_blockade":
        for t in range(10, 41):
            presence[t] = 0.8
    elif name == "single_blockade_pulse_then_withdrawal":
        for t in range(10, 16):
            presence[t] = 0.8
            effort[t] = 0.75
        event[10] = 1.0
    elif name == "low_vs_high_blockade_effort":
        dose = 0.8 if high else 0.25
        for t in range(10, 31):
            presence[t] = 0.75
            effort[t] = dose
        event[10] = dose
    elif name == "target_edge_vs_adjacent_edge_placebo":
        for t in range(10, 31):
            presence[t] = 0.7
            effort[t] = 0.7
        event[10] = 1.0
    elif name == "repeated_blockade_events_with_spacing":
        for start in (10, 30, 50):
            for t in range(start, start + 4):
                presence[t] = 0.75
                effort[t] = 0.65
            event[start] = 1.0
    else:
        raise KeyError(name)
    return {"presence": presence, "effort": effort, "event": event}


def access_candidate(name: str, p: dict[str, list[float]], *, target_edge: bool = True) -> list[float]:
    out = [0.0] * DAYS
    stock = 0.0
    event_remaining = 0
    edge_factor = 1.0 if target_edge else 0.05
    for t in range(DAYS):
        presence = p["presence"][t]
        effort = p["effort"][t] * edge_factor
        event = p["event"][t] * edge_factor
        if name == "A0_instant_presence":
            out[t] = clamp(presence * edge_factor)
        elif name == "A1_edge_restriction_stock":
            stock *= math.exp(-0.08)
            stock = clamp(stock + 0.11 * effort * presence * (1.0 - stock))
            out[t] = stock
        elif name == "A2_discrete_blockade_event":
            if event >= 0.5:
                event_remaining = 7
            out[t] = 0.9 * edge_factor if event_remaining > 0 else 0.0
            event_remaining = max(0, event_remaining - 1)
        else:
            raise KeyError(name)
    return out


def mean(xs: list[float]) -> float:
    return sum(xs) / max(1, len(xs))


def signatures() -> tuple[dict, dict]:
    gov_names = ["G0_instant_presence", "G1_capacity_stock", "G2_event_reinforcement"]
    gov = {}
    pulse = governance_protocol("presence_pulse_then_withdrawal")
    silent = governance_protocol("silent_governance_investment_without_events")
    event_only = governance_protocol("event_pulse_without_continuing_presence")
    low = governance_protocol("low_vs_high_investment_dose", high=False)
    high = governance_protocol("low_vs_high_investment_dose", high=True)
    repeat = governance_protocol("repeated_pulses_with_washout")
    for name in gov_names:
        yp = governance_candidate(name, pulse)
        ys = governance_candidate(name, silent)
        ye = governance_candidate(name, event_only)
        yl = governance_candidate(name, low)
        yh = governance_candidate(name, high)
        yr = governance_candidate(name, repeat)
        gov[name] = {
            "pulse_peak": max(yp),
            "post_withdrawal_day_40": yp[40],
            "post_withdrawal_mean_35_50": mean(yp[35:51]),
            "silent_investment_day_35": ys[35],
            "event_only_day_20": ye[20],
            "high_minus_low_day_35": yh[35] - yl[35],
            "repeat_second_pulse_peak": max(yr[36:50]),
            "washout_day_30": yr[30],
        }

    acc_names = ["A0_instant_presence", "A1_edge_restriction_stock", "A2_discrete_blockade_event"]
    acc = {}
    presence = access_protocol("presence_without_blockade")
    pulse_a = access_protocol("single_blockade_pulse_then_withdrawal")
    low_a = access_protocol("low_vs_high_blockade_effort", high=False)
    high_a = access_protocol("low_vs_high_blockade_effort", high=True)
    topology = access_protocol("target_edge_vs_adjacent_edge_placebo")
    repeat_a = access_protocol("repeated_blockade_events_with_spacing")
    for name in acc_names:
        ypresence = access_candidate(name, presence)
        yp = access_candidate(name, pulse_a)
        yl = access_candidate(name, low_a)
        yh = access_candidate(name, high_a)
        yt = access_candidate(name, topology, target_edge=True)
        ya = access_candidate(name, topology, target_edge=False)
        yr = access_candidate(name, repeat_a)
        acc[name] = {
            "presence_without_blockade_day_25": ypresence[25],
            "pulse_peak": max(yp),
            "post_withdrawal_day_25": yp[25],
            "post_withdrawal_mean_20_30": mean(yp[20:31]),
            "high_minus_low_day_25": yh[25] - yl[25],
            "target_edge_day_20": yt[20],
            "adjacent_edge_day_20": ya[20],
            "topology_contrast_day_20": yt[20] - ya[20],
            "repeat_midwashout_day_24": yr[24],
        }
    return gov, acc


def pairwise_differences(rows: dict[str, dict], threshold: float = 0.08) -> dict:
    names = sorted(rows)
    out = {}
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            diffs = {
                key: abs(float(rows[left][key]) - float(rows[right][key]))
                for key in rows[left]
            }
            separated = [key for key, value in diffs.items() if value >= threshold]
            out[f"{left}__vs__{right}"] = {
                "differences": diffs,
                "separating_signatures": separated,
                "separating_signature_count": len(separated),
                "passes_two_signature_rule": len(separated) >= 2,
            }
    return out


def main() -> int:
    repo_before = repository_state(ROOT)
    model_before = model_sha256(ROOT)
    gov, acc = signatures()
    gov_pairs = pairwise_differences(gov)
    acc_pairs = pairwise_differences(acc)

    persistence_separation = (
        gov["G1_capacity_stock"]["post_withdrawal_day_40"] > 0.08
        and gov["G0_instant_presence"]["post_withdrawal_day_40"] < 1e-9
        and acc["A1_edge_restriction_stock"]["post_withdrawal_day_25"] > 0.08
        and acc["A0_instant_presence"]["post_withdrawal_day_25"] < 1e-9
    )
    investment_event_separation = (
        gov["G1_capacity_stock"]["silent_investment_day_35"] > 0.15
        and gov["G2_event_reinforcement"]["silent_investment_day_35"] < 1e-9
        and gov["G2_event_reinforcement"]["event_only_day_20"] > 0.08
    )
    topology_placebo = (
        acc["A1_edge_restriction_stock"]["topology_contrast_day_20"] > 0.10
        and acc["A1_edge_restriction_stock"]["adjacent_edge_day_20"] < 0.08
    )
    repo_after = repository_state(ROOT)
    model_after = model_sha256(ROOT)
    gates = {
        "all_governance_pairs_have_two_signatures": all(v["passes_two_signature_rule"] for v in gov_pairs.values()),
        "all_access_pairs_have_two_signatures": all(v["passes_two_signature_rule"] for v in acc_pairs.values()),
        "persistence_decay_discrimination_present": persistence_separation,
        "investment_vs_event_discrimination_present": investment_event_separation,
        "access_topology_placebo_present": topology_placebo,
        "model_hash_stable": model_before == model_after,
        "tracked_diff_stable": repo_before.get("tracked_diff_sha256") == repo_after.get("tracked_diff_sha256"),
    }
    payload = {
        "schema_version": "pineland.missing_construct_mechanism_discrimination_recovery.v1",
        "experiment_id": "missing_construct_mechanism_discrimination_v1",
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_modified": False,
        "surrogate_equations_are_pineland_mechanisms": False,
        "contract_sha256": file_sha256(CONTRACT),
        "runner_sha256": file_sha256(Path(__file__)),
        "governance_signatures": gov,
        "access_signatures": acc,
        "governance_pairwise_discrimination": gov_pairs,
        "access_pairwise_discrimination": acc_pairs,
        "gates": gates,
        "passed": all(gates.values()),
        "scientific_interpretation": (
            "The predeclared synthetic protocols can discriminate the rival mechanism classes before implementation. This selects no mechanism. Future candidate implementations must reproduce their class-specific signatures in synthetic Pineland worlds before any historical use."
        ),
        "historical_rerun_authorized": False,
        "core_change_authorized_during_active_historical_confrontation": False,
        "repository_before": repo_before,
        "repository_after": repo_after,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "pineland.missing_construct_mechanism_discrimination_manifest.v1",
        "artifact": OUTPUT.relative_to(ROOT).as_posix(),
        "artifact_sha256": file_sha256(OUTPUT),
        "contract": CONTRACT.relative_to(ROOT).as_posix(),
        "contract_sha256": file_sha256(CONTRACT),
        "runner": Path(__file__).relative_to(ROOT).as_posix(),
        "runner_sha256": file_sha256(Path(__file__)),
        "passed": payload["passed"],
    }
    OUTPUT.with_name(OUTPUT.stem + "_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "passed": payload["passed"],
        "gates": gates,
        "governance_pair_counts": {k: v["separating_signature_count"] for k, v in gov_pairs.items()},
        "access_pair_counts": {k: v["separating_signature_count"] for k, v in acc_pairs.items()},
        "output": str(OUTPUT),
    }, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
