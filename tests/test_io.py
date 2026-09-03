import json
from pathlib import Path
import tempfile
import unittest

from pineland_sim import Simulation, SimulationConfig, generate_pineland


class IOTests(unittest.TestCase):
    def test_configuration_round_trip_and_result_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = SimulationConfig(agent_count=100, locality_count=17, horizon_days=1)
            config.save(root / "scenario.json")
            loaded = SimulationConfig.load(root / "scenario.json")
            self.assertEqual(config.to_dict(), loaded.to_dict())
            world = Simulation(generate_pineland(loaded)).run().world
            world.write_results(root / "result")
            summary = json.loads((root / "result" / "summary.json").read_text())
            self.assertEqual(summary["districts"], 17)
            self.assertTrue((root / "result" / "causal_ledger.jsonl").exists())
            diagnostics = json.loads((root / "result" / "network_diagnostics.json").read_text())
            self.assertEqual(diagnostics["nodes"], 100)
            physical = json.loads((root / "result" / "physical_diagnostics.json").read_text())
            self.assertGreaterEqual(physical["microzones"], 17 * 3)
            logistics = json.loads((root / "result" / "logistics_diagnostics.json").read_text())
            self.assertAlmostEqual(logistics["supply_conservation"]["residual"], 0.0)
            self.assertTrue((root / "result" / "combat_diagnostics.json").exists())
            self.assertTrue((root / "result" / "engagements.jsonl").exists())
            self.assertTrue((root / "result" / "organization_ecology.json").exists())
            self.assertTrue((root / "result" / "organization_transitions.jsonl").exists())
            self.assertTrue((root / "result" / "resource_flows.jsonl").read_text())
            information = json.loads((root / "result" / "information_diagnostics.json").read_text())
            self.assertIn("belief_error", information)
            self.assertIn("information_age", information)
            self.assertTrue((root / "result" / "observations.jsonl").read_text())
            self.assertTrue((root / "result" / "information_relays.jsonl").read_text())


if __name__ == "__main__":
    unittest.main()
