from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BATTERY = ROOT / "studies" / "research_program" / "competitor_battery.json"
MODULE_PATH = ROOT / "studies" / "research_program" / "simple_competitors.py"
SPEC = importlib.util.spec_from_file_location("simple_competitors_contract", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_mandatory_battery_models_are_implemented_or_episode_baselines():
    battery = json.loads(BATTERY.read_text(encoding="utf-8"))
    implemented = {row["model"] for row in MODULE.competitor_registry()}
    episode_models = {
        "constant_probability",
        "locality_empirical_bayes",
        "parentage_class_empirical_bayes",
    }
    required = set()
    for section in (
        battery["binary_incidence_or_site_state"],
        battery["event_counts"],
        battery["continuous_or_control_state"],
    ):
        required.update(section.get("mandatory", []))
        required.update(section.get("mandatory_when_inputs_exist", []))
    for component in battery["reproduction_decomposition"].values():
        required.update(component.get("mandatory", []))
    assert required <= implemented | episode_models


def test_battery_has_strict_holdout_and_occam_contract():
    battery = json.loads(BATTERY.read_text(encoding="utf-8"))
    assert "simpler model wins" in battery["scientific_rule"]
    firewall = battery["fit_firewall"]
    assert firewall["fit_split"] == "training"
    assert firewall["holdout_refit"] is False
    assert firewall["holdout_target_updates"] is False
    assert firewall["unresolved_parentage_imputed"] is False
    assert "strict_joint_holdout" in battery["required_scoring_dimensions"]


def test_reproduction_contract_excludes_relocation_from_colonization():
    battery = json.loads(BATTERY.read_text(encoding="utf-8"))
    colonization = battery["reproduction_decomposition"][
        "parent_attributed_cross_local_colonization"
    ]
    assert "formation_relocation" in colonization["exclusions"]
    assert "unresolved_parentage" in colonization["exclusions"]


def test_runners_exist_for_generic_and_reproduction_benchmarks():
    scripts = ROOT / "studies" / "research_program" / "scripts"
    for name in (
        "run_simple_competitors.py",
        "build_reproduction_benchmark_tables.py",
        "run_reproduction_component_competitors.py",
    ):
        assert (scripts / name).is_file()
