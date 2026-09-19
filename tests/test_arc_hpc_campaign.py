from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "rust" / "hpc" / "arc_campaign.py"


def _module():
    spec = importlib.util.spec_from_file_location("arc_campaign", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ArcCampaignTests(unittest.TestCase):
    def setUp(self):
        self.arc = _module()

    def _spec(self):
        return {
            "campaign_id": "unit-v1",
            "binary": "pineland.bin",
            "command": "run",
            "configs": [
                {"id": "control", "path": "control.json"},
                {"id": "treatment", "path": "treatment.json"},
            ],
            "seeds": [11, 22, 33],
            "days": 90,
            "budget_su_cap": 50000,
        }

    def _inputs(self, root: Path):
        (root / "pineland.bin").write_bytes(b"pineland-test-binary")
        (root / "control.json").write_text("{}", encoding="utf-8")
        (root / "treatment.json").write_text("{}", encoding="utf-8")

    def test_manifest_is_deterministic_and_cartesian(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._inputs(root)
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(self._spec()), encoding="utf-8")
            first = self.arc.build_campaign(spec_path, root / "a", root)
            second = self.arc.build_campaign(spec_path, root / "b", root)
            self.assertEqual(first, second)
            self.assertEqual(first["task_count"], 6)
            self.assertEqual((root / "a/tasks.jsonl").read_bytes(), (root / "b/tasks.jsonl").read_bytes())
            self.assertEqual((root / "a/tasks.idx").read_bytes(), (root / "b/tasks.idx").read_bytes())
            manifest, tasks = self.arc.load_campaign(root / "a")
            self.assertEqual(manifest["campaign_id"], "unit-v1")
            self.assertEqual([task["task_id"] for task in tasks], list(range(6)))
            self.assertEqual({task["config_id"] for task in tasks}, {"control", "treatment"})
            self.assertEqual({task["seed"] for task in tasks}, {11, 22, 33})
            self.assertTrue(all(task["config_sha256"] for task in tasks))
            self.assertTrue(all(task["binary_sha256"] for task in tasks))
            self.assertEqual(self.arc.load_task(root / "a", 4)["task_id"], 4)
            self.assertEqual(self.arc.load_task(root / "a", 4)["seed"], 22)

    def test_manifest_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._inputs(root)
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(self._spec()), encoding="utf-8")
            self.arc.build_campaign(spec_path, root / "manifest", root)
            tasks = root / "manifest/tasks.jsonl"
            tasks.write_text(tasks.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
            with self.assertRaises(self.arc.CampaignError):
                self.arc.load_campaign(root / "manifest")

    def test_task_index_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._inputs(root)
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(self._spec()), encoding="utf-8")
            manifest_dir = root / "manifest"
            self.arc.build_campaign(spec_path, manifest_dir, root)
            index_path = manifest_dir / "tasks.idx"
            data = bytearray(index_path.read_bytes())
            data[self.arc.TASK_INDEX.size] ^= 1
            index_path.write_bytes(data)
            with self.assertRaises(self.arc.CampaignError):
                self.arc.load_campaign(manifest_dir)
            with self.assertRaises(self.arc.CampaignError):
                self.arc.load_task(manifest_dir, 1)

    def test_campaign_spec_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._inputs(root)
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(self._spec()), encoding="utf-8")
            manifest_dir = root / "manifest"
            self.arc.build_campaign(spec_path, manifest_dir, root)
            campaign_spec = manifest_dir / "campaign_spec.json"
            value = json.loads(campaign_spec.read_text(encoding="utf-8"))
            value["days"] = 999
            campaign_spec.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(self.arc.CampaignError):
                self.arc.load_campaign(manifest_dir)

    def test_unsafe_config_id_is_rejected(self):
        spec = self._spec()
        spec["configs"] = [{"id": "../escape", "path": "control.json"}]
        with self.assertRaises(self.arc.CampaignError):
            self.arc.normalize_spec(spec)

    def test_extra_args_cannot_override_owned_flags(self):
        spec = self._spec()
        spec["extra_args"] = ["--output=elsewhere"]
        with self.assertRaises(self.arc.CampaignError):
            self.arc.normalize_spec(spec)
        spec["extra_args"] = ["--config", "other.json"]
        with self.assertRaises(self.arc.CampaignError):
            self.arc.normalize_spec(spec)

    def test_config_drift_fails_before_task_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._inputs(root)
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(self._spec()), encoding="utf-8")
            manifest_dir = root / "manifest"
            self.arc.build_campaign(spec_path, manifest_dir, root)
            (root / "control.json").write_text('{"changed": true}', encoding="utf-8")
            with self.assertRaises(self.arc.CampaignError):
                self.arc.run_task(
                    manifest_dir,
                    0,
                    root,
                    root / "scratch",
                    dry_run=True,
                )

    def test_binary_drift_fails_before_task_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._inputs(root)
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(self._spec()), encoding="utf-8")
            manifest_dir = root / "manifest"
            self.arc.build_campaign(spec_path, manifest_dir, root)
            (root / "pineland.bin").write_bytes(b"different-binary")
            with self.assertRaises(self.arc.CampaignError):
                self.arc.run_task(
                    manifest_dir,
                    0,
                    root,
                    root / "scratch",
                    dry_run=True,
                )

    def test_run_task_dry_run_does_not_create_scratch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._inputs(root)
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(self._spec()), encoding="utf-8")
            manifest_dir = root / "manifest"
            self.arc.build_campaign(spec_path, manifest_dir, root)
            scratch = root / "scratch"
            self.assertFalse(scratch.exists())
            self.assertEqual(
                self.arc.run_task(manifest_dir, 0, root, scratch, dry_run=True),
                0,
            )
            self.assertFalse(scratch.exists())

    def test_matching_files_requires_minimums_and_returns_full_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "summary.json").write_text("{}", encoding="utf-8")
            (output / "events.jsonl").write_text('{"event":1}\n', encoding="utf-8")
            checkpoint = output / "checkpoint_0000"
            checkpoint.mkdir()
            (checkpoint / "manifest.json").write_text("{}", encoding="utf-8")
            (checkpoint / "rank_0000.pld").write_bytes(b"state")
            files = self.arc._matching_files(
                output,
                ["summary.json", "checkpoint_*/manifest.json"],
            )
            relative = {
                str(path.relative_to(output)).replace("\\", "/") for path in files
            }
            self.assertEqual(
                relative,
                {
                    "summary.json",
                    "events.jsonl",
                    "checkpoint_0000/manifest.json",
                    "checkpoint_0000/rank_0000.pld",
                },
            )
            with self.assertRaises(self.arc.CampaignError):
                self.arc._matching_files(output, ["missing.json"])

    def test_budget_projection_guards_full_requested_walltime(self):
        profiles, profile = self.arc.load_profile(
            ROOT / "rust/hpc/arc_resource_profiles.json",
            "tinkercliffs-trajectory-normal",
        )
        self.assertEqual(profiles["account"], "will_taggart_mcll")
        projection = self.arc.budget_projection(1000, profile)
        self.assertEqual(projection["task_walltime_hours"], 4.0)
        self.assertEqual(projection["billing_su_per_hour"], 1.75)
        self.assertEqual(projection["worst_case_su"], 7000.0)

    def test_preemptable_profile_projects_zero_su(self):
        _profiles, profile = self.arc.load_profile(
            ROOT / "rust/hpc/arc_resource_profiles.json",
            "tinkercliffs-trajectory-preemptable",
        )
        self.assertEqual(self.arc.budget_projection(100000, profile)["worst_case_su"], 0.0)

    def test_submit_dry_run_has_bounded_array_and_explicit_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._inputs(root)
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(self._spec()), encoding="utf-8")
            manifest_dir = root / "manifest"
            self.arc.build_campaign(spec_path, manifest_dir, root)
            summary = self.arc.submit_campaign(
                manifest_dir,
                ROOT,
                Path("/scratch/tester/pineland"),
                ROOT / "rust/hpc/arc_resource_profiles.json",
                "tinkercliffs-trajectory-normal",
                max_concurrent=3,
                tasks_per_array_element=None,
                budget_cap_su=50000,
                allow_budget_overrun=False,
                dry_run=True,
            )
            self.assertEqual(summary["account"], "will_taggart_mcll")
            self.assertEqual(summary["qos"], "tc_normal_base")
            self.assertIn("--array=0-5%3", summary["command"])
            self.assertIn("--cpus-per-task=1", summary["command"])
            self.assertIn("--qos=tc_normal_base", summary["command"])
            self.assertNotIn("PINELAND_MANIFEST_DIR=", summary["command"])
            self.assertIn("PINELAND_MANIFEST_DIR", summary["environment"])

    def test_submit_can_bundle_short_trajectories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._inputs(root)
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(self._spec()), encoding="utf-8")
            manifest_dir = root / "manifest"
            self.arc.build_campaign(spec_path, manifest_dir, root)
            summary = self.arc.submit_campaign(
                manifest_dir,
                ROOT,
                Path("/scratch/tester/pineland"),
                ROOT / "rust/hpc/arc_resource_profiles.json",
                "tinkercliffs-trajectory-normal",
                max_concurrent=3,
                tasks_per_array_element=2,
                budget_cap_su=50000,
                allow_budget_overrun=False,
                dry_run=True,
            )
            self.assertEqual(summary["tasks"], 6)
            self.assertEqual(summary["array_elements"], 3)
            self.assertEqual(summary["tasks_per_array_element"], 2)
            self.assertIn("--array=0-2%3", summary["command"])
            self.assertEqual(summary["environment"]["PINELAND_TASKS_PER_ARRAY"], "2")

    def test_owl_profile_pins_genoa_and_base_qos(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._inputs(root)
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(self._spec()), encoding="utf-8")
            manifest_dir = root / "manifest"
            self.arc.build_campaign(spec_path, manifest_dir, root)
            summary = self.arc.submit_campaign(
                manifest_dir,
                root,
                root / "scratch",
                ROOT / "rust/hpc/arc_resource_profiles.json",
                "owl-trajectory-normal",
                max_concurrent=2,
                tasks_per_array_element=1,
                budget_cap_su=50000,
                allow_budget_overrun=False,
                dry_run=True,
            )
            self.assertEqual(summary["qos"], "owl_normal_base")
            self.assertEqual(summary["constraint"], "avx512")
            self.assertIn("--qos=owl_normal_base", summary["command"])
            self.assertIn("--constraint=avx512", summary["command"])

    def test_slurm_array_limit_is_parsed_and_enforced(self):
        fake_config = "ClusterName = tinkercliffs\nMaxArraySize = 100\n"
        completed = mock.Mock(returncode=0, stdout=fake_config, stderr="")
        with mock.patch.object(self.arc.shutil, "which", return_value="/usr/bin/scontrol"), mock.patch.object(
            self.arc.subprocess, "run", return_value=completed
        ):
            self.assertEqual(self.arc.slurm_max_array_size(), 100)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._inputs(root)
            spec = self._spec()
            spec["seeds"] = list(range(101))
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            manifest_dir = root / "manifest"
            self.arc.build_campaign(spec_path, manifest_dir, root)
            with mock.patch.object(self.arc, "slurm_max_array_size", return_value=100):
                with self.assertRaisesRegex(self.arc.CampaignError, "tasks-per-array-element 3"):
                    self.arc.submit_campaign(
                        manifest_dir,
                        root,
                        root / "scratch",
                        ROOT / "rust/hpc/arc_resource_profiles.json",
                        "tinkercliffs-trajectory-normal",
                        max_concurrent=None,
                        tasks_per_array_element=1,
                        budget_cap_su=50000,
                        allow_budget_overrun=False,
                        dry_run=True,
                    )

    def test_submit_refuses_budget_overrun(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._inputs(root)
            spec = self._spec()
            spec["seeds"] = list(range(1000))
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            manifest_dir = root / "manifest"
            self.arc.build_campaign(spec_path, manifest_dir, root)
            with self.assertRaises(self.arc.CampaignError):
                self.arc.submit_campaign(
                    manifest_dir,
                    ROOT,
                    Path("/scratch/tester/pineland"),
                    ROOT / "rust/hpc/arc_resource_profiles.json",
                    "owl-trajectory-heavy",
                    max_concurrent=None,
                    tasks_per_array_element=None,
                    budget_cap_su=1000,
                    allow_budget_overrun=False,
                    dry_run=True,
                )


if __name__ == "__main__":
    unittest.main()
