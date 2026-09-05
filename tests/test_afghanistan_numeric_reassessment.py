from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "afghanistan_2004_2021" / "scripts" / "analyze_transfer_results.py"
SPEC = importlib.util.spec_from_file_location("analyze_transfer_results", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
RUNNER_SCRIPT = ROOT / "studies" / "afghanistan_2004_2021" / "scripts" / "run_transfer_test.py"
RUNNER_SPEC = importlib.util.spec_from_file_location("run_transfer_test_numeric", RUNNER_SCRIPT)
RUNNER = importlib.util.module_from_spec(RUNNER_SPEC)
assert RUNNER_SPEC.loader is not None
RUNNER_SPEC.loader.exec_module(RUNNER)


class LedgerWorld:
    def __init__(self, residual: float, scale: float):
        self.initial_supply_stock = scale
        self.cumulative_supply_produced = scale
        self.cumulative_resource_to_supply = scale
        self.cumulative_supply_consumed = scale
        self.cumulative_supply_lost = scale
        self._residual = residual

    def supply_conservation_residual(self):
        return self._residual


def test_archived_large_supply_ledger_is_reassessed_without_changing_outcomes():
    run = {
        "gate": {"checks": {"reached_horizon": True, "stock_ledger": True,
                              "supply_ledger": False, "processed_events": True}},
        "summary": {"supply_conservation_residual": 4.68e-5,
                    "supply_consumed": 220_000_000.0},
    }
    result = MODULE.structural_gate_assessment(run)
    assert result["passed"]
    assert result["supply_reassessment"]["original_gate_value"] is False
    assert result["supply_reassessment"]["interpretation"].startswith("Numerical conservation")


def test_substantive_supply_error_still_fails():
    run = {
        "gate": {"checks": {"reached_horizon": True, "supply_ledger": False}},
        "summary": {"supply_conservation_residual": 10.0, "supply_consumed": 100.0},
    }
    assert not MODULE.structural_gate_assessment(run)["passed"]


def test_live_transfer_supply_gate_uses_roundoff_scaled_tolerance():
    check = RUNNER.supply_accounting_check(LedgerWorld(4.8e-5, 50_000_000.0))
    assert check["passed"]
    assert check["relative_residual"] < 1e-12


def test_live_transfer_supply_gate_still_rejects_substantive_residual():
    check = RUNNER.supply_accounting_check(LedgerWorld(10.0, 100.0))
    assert not check["passed"]
