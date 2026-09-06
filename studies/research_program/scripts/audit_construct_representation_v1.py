"""Synthetic + source-path audit of Pineland construct representation."""
from __future__ import annotations

from collections import defaultdict
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim import Simulation, SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.processes import ProcessEngine  # noqa: E402
from pineland_sim.reproducibility import file_sha256, model_sha256, repository_state  # noqa: E402

RETENTION_V1 = ROOT / "studies/research_program/scripts/validate_prospective_measurement_retention_v1.py"
spec = importlib.util.spec_from_file_location("retention_helpers", RETENTION_V1)
helpers = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(helpers)

CONTRACT = ROOT / "studies/research_program/construct_representation_contract_v1.json"
OUTPUT = ROOT / "studies/research_program/construct_representation_audit_v1.json"

NONPHYSICAL = ("formal", "administrative", "legal", "fiscal", "social", "expected")


def control_state(world) -> dict[tuple[str, str], dict[str, float]]:
    return {
        (locality_id, actor): vector.to_dict()
        for locality_id, locality in world.localities.items()
        for actor, vector in locality.control.items()
    }


class ControlWriteAuditEngine(ProcessEngine):
    def __init__(self, world, writes: list[dict]):
        super().__init__(world)
        self.writes = writes

    def execute(self, event):
        before = control_state(self.world)
        event_id = super().execute(event)
        after = control_state(self.world)
        for key in sorted(set(before) | set(after)):
            old = before.get(key, {})
            new = after.get(key, {})
            locality_id, actor = key
            for dim in helpers.CONTROL_DIMS:
                delta = float(new.get(dim, 0.0)) - float(old.get(dim, 0.0))
                if abs(delta) > 1e-15:
                    self.writes.append({
                        "time": float(event.time),
                        "event_type": event.event_type,
                        "event_id": event_id,
                        "locality_id": locality_id,
                        "actor": actor,
                        "dimension": dim,
                        "delta": delta,
                    })
        return event_id


def run_seed(seed: int, design: dict) -> dict:
    config = SimulationConfig(
        seed=seed,
        agent_count=int(design["agent_count"]),
        locality_count=int(design["locality_count"]),
        horizon_days=float(design["horizon_days"]),
        output_mode="forensic",
    )
    baseline_world = generate_pineland(config)
    baseline = Simulation(baseline_world)
    baseline.run(until=float(design["horizon_days"]))
    baseline_fp = helpers.retained_fingerprint(baseline_world)

    audit_world = generate_pineland(config)
    writes: list[dict] = []
    audit = Simulation(audit_world)
    audit.processes = ControlWriteAuditEngine(audit_world, writes)
    audit.run(until=float(design["horizon_days"]))
    audit_fp = helpers.retained_fingerprint(audit_world)

    summary: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {
        "count": 0, "positive": 0, "negative": 0, "absolute_delta": 0.0,
        "event_types": set(),
    }))
    for row in writes:
        actor = row["actor"]
        dim = row["dimension"]
        cell = summary[actor][dim]
        cell["count"] += 1
        cell["positive"] += int(row["delta"] > 0)
        cell["negative"] += int(row["delta"] < 0)
        cell["absolute_delta"] += abs(row["delta"])
        cell["event_types"].add(row["event_type"])

    serial = {
        actor: {
            dim: {
                **{k: v for k, v in cell.items() if k != "event_types"},
                "event_types": sorted(cell["event_types"]),
            }
            for dim, cell in dims.items()
        }
        for actor, dims in summary.items()
    }
    return {
        "seed": seed,
        "observer_dynamics_invariant": baseline_fp == audit_fp,
        "baseline_final_fingerprint": baseline_fp,
        "audit_final_fingerprint": audit_fp,
        "control_write_count": len(writes),
        "write_summary": serial,
        "writes": writes,
    }


def source_inventory() -> dict:
    package_dir = SRC / "pineland_sim"
    files = sorted(package_dir.glob("*.py"))
    source = {p.name: p.read_text(encoding="utf-8") for p in files}
    flat = re.sub(r"\s+", " ", "\n".join(source.values()))
    processes = source["processes.py"]
    political = source["political_order.py"]
    logistics = source["logistics.py"]
    entities = source["entities.py"]
    ecology = source["organization_ecology.py"]
    return {
        "explicit_latent_structures": {
            "armed_formation": "class ArmedFormation" in entities,
            "security_post": "class SecurityPost" in entities,
            "patrol": "class Patrol" in entities,
            "seven_dimensional_control": "CONTROL_DIMENSIONS =" in entities,
            "civilian_access_constraint_state": bool(re.search(
                r"class\s+\w*(AccessConstraint|Blockade|MovementRestriction)\w*", entities,
                flags=re.IGNORECASE,
            )),
        },
        "government_nonphysical_writer": {
            "governance_process": all(token in processes for token in [
                '"government", "governance"', "administrative=.006", "legal=.004",
                "fiscal=.003", "social=.003", "expected=.002",
            ]),
            "political_order_process": all(token in political for token in [
                'locality.control["government"].update({', '"administrative":', '"legal":',
                '"social":', '"expected":',
            ]),
        },
        "insurgent_nonphysical_paths": {
            "social_dynamic_writer": 'self._control(event_id, locality_id, "insurgent", "social_network_influence", social=insurgent_delta)' in processes,
            "fiscal_downstream_read": 'locality.control["insurgent"].fiscal' in processes,
            "direct_fiscal_update_literal": 'locality.control["insurgent"].update({' in flat and '"fiscal"' in flat,
            "direct_administrative_update_literal": 'locality.control["insurgent"].update({' in flat and '"administrative"' in flat,
            "initial_low_nonphysical_control": 'ControlVector(0, .01, 0, .01, .01, .04, .08)' in source["generator.py"],
            "emergent_org_low_nonphysical_control": 'ControlVector(0, .005, 0, .005, .005, .015, .03)' in ecology,
            "split_merge_inheritance": (
                "inherited_control" in ecology and "first_control" in ecology and "second_control" in ecology
            ),
        },
        "access_and_route_semantics": {
            "military_route_risk": "_believed_route_risk" in logistics,
            "logistics_route_interdiction": "route_interdiction" in logistics,
            "civilian_access_constraint_process_literal": bool(re.search(
                r"civilian.{0,80}(blockade|access constraint|movement restriction)|"
                r"(blockade|access constraint|movement restriction).{0,80}civilian",
                flat, flags=re.IGNORECASE,
            )),
        },
    }


def aggregate_runs(results: list[dict]) -> dict:
    agg: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {
        "count": 0, "positive": 0, "negative": 0, "absolute_delta": 0.0,
        "event_types": set(), "seeds_with_write": set(),
    }))
    for run in results:
        for actor, dims in run["write_summary"].items():
            for dim, cell in dims.items():
                out = agg[actor][dim]
                for key in ("count", "positive", "negative", "absolute_delta"):
                    out[key] += cell[key]
                out["event_types"].update(cell["event_types"])
                if cell["count"]:
                    out["seeds_with_write"].add(run["seed"])
    return {
        actor: {
            dim: {
                **{k: v for k, v in cell.items() if k not in {"event_types", "seeds_with_write"}},
                "event_types": sorted(cell["event_types"]),
                "seeds_with_write": sorted(cell["seeds_with_write"]),
            }
            for dim, cell in dims.items()
        }
        for actor, dims in agg.items()
    }


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    design = contract["synthetic_design"]
    repo_before = repository_state(ROOT)
    model_before = model_sha256(ROOT)
    inventory = source_inventory()
    results = [run_seed(int(seed), design) for seed in design["seeds"]]
    aggregate = aggregate_runs(results)
    repo_after = repository_state(ROOT)
    model_after = model_sha256(ROOT)

    gov = aggregate.get("government", {})
    insurgent = aggregate.get("insurgent", {})
    gov_dynamic_nonphysical = {
        dim: int(gov.get(dim, {}).get("count", 0)) > 0
        for dim in ("administrative", "legal", "fiscal", "social", "expected")
    }
    insurgent_dynamic_nonphysical = {
        dim: int(insurgent.get(dim, {}).get("count", 0)) > 0
        for dim in ("administrative", "legal", "fiscal", "social", "expected")
    }

    classifications = {
        "armed_presence": {
            "classification": "DIRECT",
            "reason": "Formations, fixed security posts, and patrols are explicit actor/locality states with substantive movement/presence processes.",
        },
        "government_administrative_presence": {
            "classification": "DIRECT_CONTINUOUS",
            "reason": "Government administrative control has explicit endogenous governance/political writers; it is continuous rather than a literal staff-presence indicator.",
            "dynamic_nonphysical_writes": gov_dynamic_nonphysical,
        },
        "insurgent_shadow_governance": {
            "classification": "PARTIAL_STRUCTURAL_GAP",
            "reason": (
                "Insurgent social/physical authority is dynamic, but administrative/legal/fiscal/expected governance dimensions lack identified endogenous writers in the live source and synthetic trajectory. Fiscal control is read to create extraction revenue rather than built by extraction activity; low legal/fiscal/social/expected values are initialized and inherited."
            ),
            "dynamic_nonphysical_writes": insurgent_dynamic_nonphysical,
        },
        "territorial_access_constraint": {
            "classification": "ABSENT_FIRST_CLASS_CONSTRUCT",
            "reason": (
                "Military/logistics routing contains route risk and interdiction, but no first-class civilian/organizational access-restriction state or generic blockade process was identified. It cannot be inferred from physical control without an independently justified observation model."
            ),
        },
    }

    classification_gate = all([
        inventory["explicit_latent_structures"]["armed_formation"],
        inventory["explicit_latent_structures"]["security_post"],
        inventory["government_nonphysical_writer"]["governance_process"],
        inventory["government_nonphysical_writer"]["political_order_process"],
        inventory["insurgent_nonphysical_paths"]["social_dynamic_writer"],
        inventory["insurgent_nonphysical_paths"]["fiscal_downstream_read"],
        inventory["access_and_route_semantics"]["military_route_risk"],
        not inventory["explicit_latent_structures"]["civilian_access_constraint_state"],
        all(run["observer_dynamics_invariant"] for run in results),
        model_before == model_after,
        repo_before.get("tracked_diff_sha256") == repo_after.get("tracked_diff_sha256"),
    ])

    payload = {
        "schema_version": "pineland.construct_representation_audit.v1",
        "experiment_id": contract["experiment_id"],
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_modified": False,
        "contract_sha256": file_sha256(CONTRACT),
        "runner_sha256": file_sha256(Path(__file__)),
        "retention_helper_sha256": file_sha256(RETENTION_V1),
        "model_sha256": model_before,
        "source_inventory": inventory,
        "synthetic_results": results,
        "aggregate_control_writes": aggregate,
        "classifications": classifications,
        "representation_classification_identified": classification_gate,
        "scientific_gate_passed": classification_gate,
        "historical_fit_explanation_authorized": False,
        "core_change_authorized": False,
        "next_required_action": (
            "After the active historical confrontation is frozen/finalized, design synthetic candidate mechanisms for insurgent governance accumulation/decay and civilian access restriction. Compete those mechanisms in synthetic worlds before any historical rerun or case-specific use."
        ),
        "repository_before": repo_before,
        "repository_after": repo_after,
        "interpretation": contract["interpretation"],
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "pineland.construct_representation_manifest.v1",
        "artifact": OUTPUT.relative_to(ROOT).as_posix(),
        "artifact_sha256": file_sha256(OUTPUT),
        "contract": CONTRACT.relative_to(ROOT).as_posix(),
        "contract_sha256": file_sha256(CONTRACT),
        "runner": Path(__file__).relative_to(ROOT).as_posix(),
        "runner_sha256": file_sha256(Path(__file__)),
        "scientific_gate_passed": payload["scientific_gate_passed"],
    }
    OUTPUT.with_name(OUTPUT.stem + "_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "scientific_gate_passed": payload["scientific_gate_passed"],
        "classifications": {k: v["classification"] for k, v in classifications.items()},
        "government_dynamic_nonphysical": gov_dynamic_nonphysical,
        "insurgent_dynamic_nonphysical": insurgent_dynamic_nonphysical,
        "observer_invariant_all_seeds": all(run["observer_dynamics_invariant"] for run in results),
        "output": str(OUTPUT),
    }, indent=2, sort_keys=True))
    return 0 if classification_gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
