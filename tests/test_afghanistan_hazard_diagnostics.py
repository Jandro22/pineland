import importlib.util
from pathlib import Path
from types import SimpleNamespace

from pineland_sim import SimulationConfig


def test_v5_empty_legacy_funnel_does_not_claim_zero_violence_is_certain():
    path = Path(__file__).resolve().parents[1] / "studies/afghanistan_2004_2021/scripts/run_transfer_test.py"
    spec = importlib.util.spec_from_file_location("afghan_hazard_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = SimulationConfig()
    config.combat.organized_action_architecture = "multichannel_v5"
    world = SimpleNamespace(config=config, action_funnel_counts={"state_based_violence_events": 24},
                            contact_funnel_records=[])
    result = module.hazard_diagnostics(world)
    assert result["probability_zero_contacts"] is None
    assert result["expected_contacts"] is None
    assert result["action_funnel"]["state_based_violence_events"] == 24
