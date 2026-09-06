from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "studies"
    / "research_program"
    / "scripts"
    / "run_afghanistan_resolution_convergence.py"
)
SPEC = importlib.util.spec_from_file_location("resolution_convergence", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_resolution_comparison_includes_zero_probability_surface_cells():
    first = {"A|0": 0.5, "B|0": 0.0, "C|0": 0.0}
    second = {"A|0": 0.5, "B|0": 0.0, "C|0": 0.0}
    result = MODULE.compare_probability_fields(first, second)
    assert result["cells"] == 3
    assert result["spearman"] == 1.0
    assert result["mean_absolute_difference"] == 0.0


def test_morans_i_is_undefined_for_constant_intensity():
    assert MODULE.morans_i(
        {"A": 1.0, "B": 1.0},
        {"A": {"B": 1.0}, "B": {"A": 1.0}},
    ) is None
