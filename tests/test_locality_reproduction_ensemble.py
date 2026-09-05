from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "run_locality_reproduction_ensemble.py"
SPEC = importlib.util.spec_from_file_location("run_locality_reproduction_ensemble", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_compact_ensemble_is_synthetic_hash_stable_and_preserves_negative_results():
    report = MODULE.run_ensemble(
        seeds=(2026090511, 2026090512),
        agent_count=180,
        locality_count=24,
        horizon_days=8,
        reproduction_horizon_days=3,
        parent_overlap_days=1,
    )
    assert report["historical_outcomes_used"] is False
    assert report["empirical_parameter_fitting"] is False
    assert report["negative_results_must_be_preserved"] is True
    assert report["model_sha256_start"] == report["model_sha256_end"]
    assert report["summary"]["run_count"] == 2
    assert len(report["runs"]) == 2
    for row in report["runs"]:
        assert 0.0 <= row["parentage_coverage"]["fraction"] <= 1.0
        assert row["typed_R_I"]["conservative_upper_spectral_radius"] >= \
            row["typed_R_I"]["lower_spectral_radius"]
        assert row["typed_R_I"]["criticality_identification"] in {
            "identified_subcritical",
            "identified_supercritical",
            "partially_identified_across_criticality_threshold",
        }
