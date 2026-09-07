from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import json

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.reproducibility import (
    audit_run_manifest,
    build_run_manifest,
    decision_state_sha256,
    isolated_run_signature,
    substantive_file_sha256,
    simulation_execution_sha256,
    trajectory_sha256,
)


def _config(*, seed: int = 20260904, days: float = 6,
            mode: str = "forensic") -> SimulationConfig:
    return SimulationConfig(
        agent_count=60, locality_count=17, horizon_days=days,
        seed=seed, output_mode=mode,
    )


def test_output_modes_have_identical_full_decision_state_and_trajectory():
    signatures = []
    for mode in ("forensic", "ensemble", "calibration"):
        world = Simulation(generate_pineland(_config(mode=mode))).run().world
        signatures.append((decision_state_sha256(world), trajectory_sha256(world)))
    assert signatures[1:] == signatures[:-1]


def test_recording_settings_cannot_advance_latent_rng_streams():
    signatures = []
    for enabled, false_rate in ((True, 0.0), (False, 0.0), (True, 1.0)):
        config = _config(days=12, mode="calibration")
        config.recording.enabled = enabled
        config.recording.false_event_rate = false_rate
        world = Simulation(generate_pineland(config)).run().world
        signatures.append((decision_state_sha256(world), trajectory_sha256(world)))
    assert len(set(signatures)) == 1


def test_ninety_day_information_retention_matches_full_retention():
    signatures = []
    observation_counts = []
    for retention in (0.0, 90.0):
        config = _config(days=105, mode="ensemble")
        config.information.observation_retention_days = retention
        world = Simulation(generate_pineland(config)).run().world
        signatures.append((decision_state_sha256(world), trajectory_sha256(world)))
        observation_counts.append(len(world.observations))
    assert signatures[0] == signatures[1]
    assert observation_counts[1] < observation_counts[0]


def test_active_observation_provenance_is_not_decision_state():
    world = Simulation(generate_pineland(_config(days=1, mode="ensemble"))).run(
        until=0.25
    ).world
    active = [
        world.observations[world.information_relays[relay_id].observation_id]
        for relay_id in world.active_information_relays
        if relay_id in world.information_relays
        and world.information_relays[relay_id].observation_id in world.observations
    ]
    if active:
        before = decision_state_sha256(world)
        active[0].provenance["forensic_only_probe"] = "changed"
        assert decision_state_sha256(world) == before


def test_process_isolated_parallel_execution_is_deterministic():
    configs = [_config(seed=91001 + offset, days=4, mode="ensemble").to_dict()
               for offset in range(3)]
    sequential = [isolated_run_signature(values) for values in configs]
    with ProcessPoolExecutor(max_workers=2) as executor:
        parallel = list(executor.map(isolated_run_signature, configs))
    for expected, actual in zip(sequential, parallel, strict=True):
        differing_components = sorted(
            key for key, value in expected["component_sha256"].items()
            if value != actual["component_sha256"].get(key)
        )
        assert not differing_components, differing_components
        assert actual["decision_state_sha256"] == expected["decision_state_sha256"]
        assert actual["trajectory_sha256"] == expected["trajectory_sha256"]


def test_simulation_execution_hash_covers_scheduler_and_rng_future():
    world = generate_pineland(_config(days=2, mode="ensemble"))
    simulation = Simulation(world)
    simulation.run(until=0.5)
    clone = simulation.clone()
    assert simulation_execution_sha256(clone) == (
        simulation_execution_sha256(simulation)
    )
    clone.set_stream_namespace("different-lineage")
    assert simulation_execution_sha256(clone) != (
        simulation_execution_sha256(simulation)
    )


def test_verification_timestamps_do_not_change_substantive_case_hash(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    payload = {
        "source": "example",
        "archive_sha256": "abc123",
        "verified_at_utc": "2026-09-04T10:00:00Z",
        "nested": {"retrieved_at_utc": "2026-09-01T10:00:00Z", "value": 7},
    }
    first.write_text(json.dumps(payload), encoding="utf-8")
    payload["verified_at_utc"] = "2027-01-01T00:00:00Z"
    payload["nested"]["retrieved_at_utc"] = "2027-01-01T00:00:00Z"
    second.write_text(json.dumps(payload), encoding="utf-8")
    assert substantive_file_sha256(first) == substantive_file_sha256(second)


def test_run_manifest_contains_reproduction_contract(tmp_path):
    case = tmp_path / "case.json"
    split = tmp_path / "split.json"
    case.write_text('{"case":"compact","verified_at_utc":"2026-09-04T10:00:00Z"}',
                    encoding="utf-8")
    split.write_text('{"split":"fixed"}', encoding="utf-8")
    config = _config(days=1, mode="ensemble")
    manifest = build_run_manifest(
        config,
        seeds=[config.seed],
        execution_mode={"mode": "test", "workers": 1, "process_isolated": True},
        output_schema={"name": "unit-test", "version": "1"},
        case_files=[case],
        split_file=split,
    )
    audit = audit_run_manifest(manifest)
    assert audit["valid"], audit
    assert manifest["commit_hash"]
    assert isinstance(manifest["dirty_tree"], bool)
    assert manifest["tracked_diff_sha256"]
    assert manifest["model_sha256"]
    assert manifest["config_sha256"]
    assert manifest["parameter_registry_sha256"]
    assert manifest["case_data_hashes"]
    assert manifest["split_sha256"]
    assert manifest["environment"]["python"]
    assert manifest["environment"]["packages"]
    assert manifest["seeds"] == [config.seed]


def test_run_manifest_audit_requires_exact_diff_identity_and_well_formed_hashes(tmp_path):
    case = tmp_path / "case.json"
    split = tmp_path / "split.json"
    case.write_text('{"case":"compact"}', encoding="utf-8")
    split.write_text('{"split":"fixed"}', encoding="utf-8")
    config = _config(days=1, mode="ensemble")
    manifest = build_run_manifest(
        config,
        execution_mode={"mode": "test", "workers": 1},
        output_schema={"name": "unit-test", "version": "1"},
        case_files=[case],
        split_file=split,
    )

    missing_diff = dict(manifest)
    missing_diff.pop("tracked_diff_sha256")
    audit = audit_run_manifest(missing_diff)
    assert not audit["valid"]
    assert "tracked_diff_sha256" in audit["missing_fields"]

    malformed = dict(manifest)
    malformed["model_sha256"] = "not-a-sha256"
    malformed["dirty_tree"] = "false"
    malformed["case_data_hashes"] = {"case.json": "bad"}
    audit = audit_run_manifest(malformed)
    assert not audit["valid"]
    assert {"model_sha256", "dirty_tree", "case_data_hashes"} <= set(audit["invalid_fields"])


def test_nonempirical_manifest_may_explicitly_have_no_split_but_must_keep_field():
    config = _config(days=1, mode="ensemble")
    manifest = build_run_manifest(
        config,
        execution_mode={"mode": "synthetic_null", "workers": 1},
        output_schema={"name": "synthetic", "version": "1"},
    )
    assert manifest["split_sha256"] is None
    assert audit_run_manifest(manifest)["valid"]

    missing = dict(manifest)
    missing.pop("split_sha256")
    audit = audit_run_manifest(missing)
    assert not audit["valid"]
    assert "split_sha256" in audit["missing_fields"]
