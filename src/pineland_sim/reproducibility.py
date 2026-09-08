"""Scientific execution provenance, canonical hashes, and determinism checks.

This module is intentionally outside the substantive model domains.  It
defines how a run is identified and compared without changing any transition
equation or stochastic decision rule.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from array import array
from dataclasses import asdict, fields, is_dataclass
from enum import Enum
import hashlib
from importlib import metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Iterable

from .config import SimulationConfig


MANIFEST_SCHEMA_VERSION = "1.0.0"

# Acquisition/verification bookkeeping may change when a source is rechecked
# without changing the source or case construction.  Raw hashes remain
# available in manifests; only the substantive hash ignores these fields.
VOLATILE_PROVENANCE_KEYS = frozenset({
    "acquired_at_utc", "checked_at_utc", "downloaded_at_utc",
    "downloaded_this_invocation", "retrieved_at_utc", "verified_at_utc",
    "verification_timestamp", "last_verified_at_utc",
})

# These fields are append-only diagnostics, empirical-record output, or
# retention archives.  None is read by a latent decision rule.  Active
# information relays and their referenced observations are handled separately
# because they *can* affect a future information update.
OUTPUT_ONLY_WORLD_FIELDS = frozenset({
    "event_log", "event_counts", "contact_event_times",
    "contact_event_localities", "contact_funnel_records",
    "contact_funnel_counts", "recruitment_total", "behavior_change_total",
    "action_funnel_counts", "action_funnel_by_actor_locality",
    "activity_hazard_ledger",
    "behavior_change_represented_population",
    "causal_ledger", "synthetic_records", "checkpoints", "state_deltas",
    "stock_transactions", "organization_eligibility_log",
    "organization_onset_log", "observation_index",
    "information_detections", "information_detection_by_source",
    "civilian_harm_events", "resource_flows",
    "information_detections", "information_detection_by_source",
    "stock_ledger_deltas", "stock_ledger_by_class",
    "stock_ledger_by_boundary", "stock_ledger_by_flow_kind",
    "stock_ledger_event_ids", "stock_ledger_transaction_count",
    "stock_ledger_last_totals",
    "locality_path_cache", "locality_travel_time_cache",
    "locality_route_metrics_cache", "physical_distance_cache",
    "physical_distance_signature", "command_path_cache",
    "in_transit_supply_total",
    "active_shipment_ids", "active_movement_order_ids",
    "person_ids_by_residence_locality",
    "person_ids_by_organization", "unassigned_person_ids",
    "represented_weight_by_locality", "represented_weight_by_community",
    "primary_language_by_locality", "multilingual_locality_ids",
    "ordered_district_ids", "ordered_locality_ids", "ordered_person_ids",
    "ordered_social_community_ids", "person_ids_by_community",
    "ordered_microzone_ids", "ordered_organization_ids",
    "active_organization_ids", "active_insurgent_organization_ids",
    "operational_locality_ids_by_organization",
    "active_operational_locality_ids",
    "active_physical_locality_ids",
    "evaluation_region_by_locality",
    "microzones_by_locality", "formation_ids_by_locality",
    "formation_ids_by_organization",
    "patrol_ids_by_locality", "patrol_ids_by_formation",
    "security_posts_by_locality", "social_community_ids_by_locality",
    "information_execution_cache",
    "information_cache_active",
    "community_selection_cache", "community_selection_cache_dirty",
    "execution_profile", "execution_backend", "performance_counters",
    "compact_control_state", "compact_presence_state",
    "compact_node_presence_state", "compact_zone_state",
    "compact_observation_state", "compact_relay_state",
    "numeric_information_runtime", "information_relay_due_heap",
    "deferred_presence_fusions", "defer_presence_fusions",
    "engagements", "state_based_event_times",
    "state_based_event_localities", "state_based_events",
})

# Particle propagation needs the future-decision state, not the forensic
# archives accumulated for publication.  Keep this narrower than
# OUTPUT_ONLY_WORLD_FIELDS: active shipment/movement indexes and route caches
# are derived execution state that still affect future transitions.
PARTICLE_ARCHIVE_WORLD_FIELDS = frozenset({
    "event_log", "event_counts", "contact_event_times",
    "contact_event_localities", "contact_funnel_records",
    "contact_funnel_counts", "action_funnel_counts",
    "action_funnel_by_actor_locality", "recruitment_total",
    "behavior_change_total", "behavior_change_represented_population",
    "causal_ledger", "synthetic_records", "checkpoints", "state_deltas",
    "stock_transactions", "organization_eligibility_log",
    "organization_onset_log", "state_based_event_times",
    "state_based_event_localities", "state_based_events",
    "civilian_harm_events", "resource_flows",
    "information_execution_cache",
    "information_cache_active", "deferred_control_fusions",
    "defer_control_fusions", "deferred_presence_fusions", "defer_presence_fusions",
    "performance_counters", "engagements",
})

OUTPUT_ONLY_SUMMARY_FIELDS = frozenset({
    "output_mode", "events", "synthetic_records", "synthetic_recording_rate",
    "state_delta_records", "stock_ledger_transactions", "observations",
    "mean_observation_confidence", "mean_effective_observation_confidence",
    "contact_funnel",
})

REQUIRED_MANIFEST_FIELDS = frozenset({
    "schema_version", "commit_hash", "dirty_tree", "tracked_diff_sha256", "model_sha256",
    "config_sha256", "parameter_registry_sha256", "case_data_hashes",
    "split_sha256", "environment", "seeds", "output_schema",
    "execution_mode",
})


def _normalized(value: Any) -> Any:
    """Return a deterministic, JSON-safe representation of arbitrary state."""
    if is_dataclass(value):
        return {
            item.name: _normalized(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, array):
        return {
            "__array_typecode__": value.typecode,
            "values": [_normalized(item) for item in value],
        }
    if isinstance(value, Enum):
        return _normalized(value.value)
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        if all(isinstance(key, str) for key in value):
            return {key: _normalized(value[key]) for key in sorted(value)}
        entries = [(_normalized(key), _normalized(item)) for key, item in value.items()]
        entries.sort(key=lambda pair: canonical_json(pair[0]))
        return {"__mapping__": [[key, item] for key, item in entries]}
    if isinstance(value, (set, frozenset)):
        items = [_normalized(item) for item in value]
        items.sort(key=canonical_json)
        return {"__set__": items}
    if isinstance(value, (list, tuple, deque)):
        return [_normalized(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value):
            return {"__float__": "nan"}
        if math.isinf(value):
            return {"__float__": "inf" if value > 0 else "-inf"}
        # State can cross the rich/numeric boundary with the same scalar
        # represented once as ``0`` and once as ``0.0`` (for example, an
        # initial timestamp).  Those values are identical to every latent
        # transition and must have one canonical scientific representation.
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if hasattr(value, "__dict__"):
        return _normalized(vars(value))
    # Compact execution objects intentionally use ``__slots__`` to avoid a
    # per-instance dictionary.  Falling through to repr() would put a process
    # memory address into the scientific decision hash, making an otherwise
    # identical native/fallback run appear non-deterministic.
    slots = getattr(type(value), "__slots__", ())
    if isinstance(slots, str):
        slots = (slots,)
    if slots:
        return {
            "__type__": f"{type(value).__module__}.{type(value).__qualname__}",
            "__slots__": {
                slot: _normalized(getattr(value, slot))
                for slot in slots
                if hasattr(value, slot)
            },
        }
    return repr(value)


def canonical_json(value: Any) -> str:
    return json.dumps(_normalized(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strip_volatile_provenance(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_volatile_provenance(item)
            for key, item in value.items()
            if key not in VOLATILE_PROVENANCE_KEYS
        }
    if isinstance(value, list):
        return [_strip_volatile_provenance(item) for item in value]
    return value


def substantive_file_sha256(path: str | Path) -> str:
    """Hash substantive content while ignoring verification-time metadata.

    Non-JSON files use their exact byte hash.  JSON source manifests retain
    source/version/license/archive hashes and all case inputs; only volatile
    acquisition/verification timestamps and invocation flags are removed.
    """
    path = Path(path)
    if path.suffix.lower() != ".json":
        return file_sha256(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return canonical_sha256(_strip_volatile_provenance(payload))


def _repo_root(start: str | Path | None = None) -> Path:
    current = Path(start or __file__).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    raise FileNotFoundError("could not locate repository root")


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return completed.stdout.strip()


def repository_state(repo_root: str | Path | None = None) -> dict[str, Any]:
    repo = _repo_root(repo_root)
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    paths = [line[3:] for line in status.splitlines() if len(line) >= 4]
    diff_bytes = subprocess.run(
        ["git", "diff", "--binary", "HEAD"], cwd=repo, check=True,
        capture_output=True,
    ).stdout
    return {
        "commit_hash": _git(repo, "rev-parse", "HEAD"),
        "dirty_tree": bool(status),
        "dirty_paths": sorted(paths),
        "tracked_diff_sha256": hashlib.sha256(diff_bytes).hexdigest(),
    }


def model_sha256(repo_root: str | Path | None = None) -> str:
    """Hash the live model source rather than relying on the commit alone."""
    repo = _repo_root(repo_root)
    paths = sorted((repo / "src" / "pineland_sim").rglob("*.py"))
    if (repo / "pyproject.toml").exists():
        paths.append(repo / "pyproject.toml")
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(repo).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def certified_core_status(repo_root: str | Path | None = None) -> dict[str, Any]:
    """Compare the live model source with the active research freeze.

    Long empirical runs must fail before worker launch when the checkout no
    longer matches the content-addressed core certificate.  This is separate
    from per-trajectory start/end checks: those checks protect an individual
    run, while this preflight prevents wasting hours on a run that cannot
    become admissible evidence in the first place.
    """
    repo = _repo_root(repo_root)
    freeze_path = repo / "studies" / "research_program" / "core_freeze.json"
    if not freeze_path.exists():
        return {
            "passed": False,
            "reason": "missing_core_freeze",
            "freeze_path": freeze_path.as_posix(),
            "expected_model_sha256": None,
            "live_model_sha256": model_sha256(repo),
        }
    try:
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
        expected = freeze.get("model_sha256")
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "passed": False,
            "reason": "invalid_core_freeze",
            "freeze_path": freeze_path.as_posix(),
            "error": str(exc),
            "expected_model_sha256": None,
            "live_model_sha256": model_sha256(repo),
        }
    live = model_sha256(repo)
    return {
        "passed": isinstance(expected, str) and live == expected,
        "reason": "matches_certificate" if live == expected else "live_core_mismatch",
        "freeze_path": freeze_path.as_posix(),
        "freeze_id": freeze.get("freeze_id"),
        "expected_model_sha256": expected,
        "live_model_sha256": live,
    }


def require_certified_core(repo_root: str | Path | None = None) -> dict[str, Any]:
    """Raise before an expensive run if the active core certificate is stale."""
    status = certified_core_status(repo_root)
    if not status["passed"]:
        raise RuntimeError(
            "refusing to launch empirical workers: live core is not the active "
            f"certificate ({status['reason']}; expected="
            f"{status.get('expected_model_sha256')}, live="
            f"{status.get('live_model_sha256')})"
        )
    return status


def environment_manifest() -> dict[str, Any]:
    packages: dict[str, str] = {}
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            packages[name.lower()] = distribution.version
    deterministic_env = {
        key: os.environ.get(key)
        for key in (
            "PYTHONHASHSEED", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
            "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS",
        )
    }
    return {
        "python": sys.version,
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "logical_cpu_count": os.cpu_count(),
        "environment_variables": deterministic_env,
        "packages": dict(sorted(packages.items())),
    }


def scientific_config_payload(config: SimulationConfig) -> dict[str, Any]:
    """Configuration that can affect latent decisions/state.

    Synthetic recording parameters are intentionally omitted: they describe
    the empirical observation/output operator.  Bounded archive retention and
    output fidelity are also non-substantive execution settings.
    """
    payload = config.to_dict()
    payload.pop("output_mode", None)
    payload.pop("recording", None)
    information = dict(payload.get("information", {}))
    information.pop("observation_retention_days", None)
    payload["information"] = information
    return payload


def scientific_config_sha256(config: SimulationConfig) -> str:
    return canonical_sha256(scientific_config_payload(config))


def _numeric_active_information_payloads(
    world: Any,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Expose numeric in-flight information in the rich state schema.

    The ensemble backend deliberately does not populate ``Observation`` or
    ``InformationRelay`` maps.  Those maps are nevertheless part of the
    future-decision state when a report is still in transit, so hashes and
    checkpoint comparisons need a representation-independent view.  This
    adapter decodes only active fixed-width rows; it does not mutate the
    numeric runtime or construct rich model objects.
    """
    runtime = getattr(world, "numeric_information_runtime", None)
    if runtime is None:
        return None
    relay_buffer = getattr(runtime, "relay_buffer", None)
    event_rows = getattr(runtime, "event_rows", None)
    engine = getattr(runtime, "engine", None)
    plan = getattr(engine, "plan", None)
    codes = getattr(plan, "codes", None)
    if relay_buffer is None or event_rows is None or codes is None:
        return None

    from .information import _decay_rate

    def value(code: Any) -> str | None:
        return codes.value(int(code)) if int(code) else None

    active_relays: dict[str, Any] = {}
    active_observations: dict[str, Any] = {}
    control_dimensions = (
        "formal", "physical", "administrative", "legal",
        "fiscal", "social", "expected",
    )
    for index in range(len(relay_buffer)):
        if int(relay_buffer.status[index]) != 0:
            continue
        sequence = int(relay_buffer.observation_sequence[index])
        row = event_rows.get(sequence)
        if row is None:
            continue

        observation_id = f"OBS{sequence:010d}"
        relay_id = f"IR{int(relay_buffer.ids[index]):010d}"
        observation_type = (
            "detection" if int(row[12]) == 1 else "physical_control"
        )
        target_actor_id = value(row[7])
        target_formation_id = value(row[8]) if observation_type == "detection" else None
        if observation_type == "detection":
            target_id = target_formation_id
            estimated_value = {
                "presence": float(row[14]),
                "personnel": float(row[15]),
                "detection_probability": float(row[16]),
                "detected": bool(row[17]),
                "attribution_confidence": float(row[18]),
            }
        else:
            target_id = target_actor_id
            estimated_value = {
                "control": {
                    name: float(observed)
                    for name, observed in zip(control_dimensions, row[13])
                },
                "physical_control": float(row[19]),
                "violence": float(row[20]),
            }
        active_observations[observation_id] = {
            "observation_id": observation_id,
            "target_id": target_id,
            "locality_id": value(row[5]),
            "timestamp": float(row[9]),
            "source_id": value(row[3]),
            "source_type": value(row[4]),
            "observation_type": observation_type,
            "estimated_value": estimated_value,
            "confidence": float(row[10]),
            "observer_actor_id": value(row[1]),
            "microzone_id": value(row[6]),
            "observer_node_id": value(row[2]),
            "quality": float(row[11]),
            "decay_rate": _decay_rate(
                world, observation_type, target_formation_id
            ),
            "target_actor_id": target_actor_id,
            "target_formation_id": target_formation_id,
            "received_at": float(row[9]),
        }
        active_relays[relay_id] = {
            "relay_id": relay_id,
            "observation_id": observation_id,
            "organization_id": value(relay_buffer.organization[index]),
            "source_node_id": value(relay_buffer.source[index]),
            "destination_node_id": value(relay_buffer.destination[index]),
            "route": [
                value(code) for code in relay_buffer.route_codes_for(index)
            ],
            "sent_at": float(relay_buffer.sent_at[index]),
            "arrives_at": float(relay_buffer.arrives_at[index]),
            "reliability": float(relay_buffer.reliability[index]),
            "latency_hours": float(relay_buffer.latency_hours[index]),
            "status": "in_transit",
            "delivered_at": None,
        }
    return active_relays, active_observations


def decision_state_payload(world: Any) -> dict[str, Any]:
    """Canonical future-decision state, excluding output-only archives."""
    materialize = getattr(world, "materialize_compact_information_confidences", None)
    if materialize is not None:
        materialize()
    numeric_payloads = _numeric_active_information_payloads(world)
    if numeric_payloads is not None:
        active_relays, active_observations = numeric_payloads
        active_relay_ids = set(active_relays)
    else:
        active_relay_ids = set(getattr(world, "active_information_relays", set()))
        active_relays = {
            relay_id: (
                world.information_relays[relay_id].to_payload()
                if hasattr(world.information_relays[relay_id], "to_payload")
                else world.information_relays[relay_id]
            )
            for relay_id in sorted(active_relay_ids)
            if relay_id in world.information_relays
        }
        active_observations = {}
    pending_observation_ids = {
        relay["observation_id"] if isinstance(relay, dict) else relay.observation_id
        for relay in active_relays.values()
    }
    if numeric_payloads is None:
        for observation_id in sorted(pending_observation_ids):
            observation = world.observations.get(observation_id)
            if observation is None:
                continue
            observation_payload = (
                observation.to_payload()
                if hasattr(observation, "to_payload") else asdict(observation)
            )
            # Provenance is archival metadata. Future fusion consumes the typed
            # observation fields directly and never reads this dictionary.
            observation_payload.pop("provenance", None)
            active_observations[observation_id] = observation_payload
    # Corroboration has an explicit three-day memory.  Dormant index entries
    # older than that can remain in a full forensic archive, but _store_observation
    # discards them before the next fusion operation, so they are not part of
    # the future-decision state.
    corroboration_cutoff = float(world.time) - 3.0
    live_source_index = {}
    for key, history in world.observation_source_index.items():
        live = [item for item in history if item[0] >= corroboration_cutoff]
        if live:
            live_source_index[key] = live
    payload: dict[str, Any] = {}
    for item in fields(world):
        name = item.name
        if name in OUTPUT_ONLY_WORLD_FIELDS:
            continue
        if name == "config":
            payload[name] = scientific_config_payload(world.config)
        elif name == "active_information_relays":
            payload[name] = active_relay_ids
        elif name == "observations":
            payload[name] = active_observations
        elif name == "information_relays":
            payload[name] = active_relays
        elif name == "observation_source_index":
            payload[name] = live_source_index
        else:
            payload[name] = getattr(world, name)
    return payload


def decision_state_sha256(world: Any) -> str:
    return canonical_sha256(decision_state_payload(world))


def decision_state_component_hashes(world: Any) -> dict[str, str]:
    """Per-component hashes used to localize determinism failures."""
    payload = decision_state_payload(world)
    return {key: canonical_sha256(value) for key, value in sorted(payload.items())}


def simulation_execution_payload(
    simulation: Any, *, lineage_id: str | None = None
) -> dict[str, Any]:
    """Future stochastic execution state beyond the WorldState snapshot."""
    scheduler = simulation.scheduler
    pending = (
        scheduler.pending_events()
        if hasattr(scheduler, "pending_events") else ()
    )
    process_rngs = {
        name: rng.getstate()
        for name, rng in sorted(
            simulation.processes._process_rngs.items()
        )
    }
    return {
        "world_decision_state_sha256": decision_state_sha256(
            simulation.world
        ),
        "scheduler_next_sequence": scheduler._next_sequence,
        "scheduler_pending": pending,
        "simulation_rng_state": simulation.rng.getstate(),
        "process_rng_states": process_rngs,
        "process_default_rng_state": simulation.processes.rng.getstate(),
        "process_event_counter": simulation.processes.event_counter,
        "stream_namespace": simulation.stream_namespace,
        "process_stream_namespace": simulation.processes.stream_namespace,
        "lineage_id": lineage_id,
    }


def simulation_execution_sha256(
    simulation: Any, *, lineage_id: str | None = None
) -> str:
    return canonical_sha256(
        simulation_execution_payload(
            simulation, lineage_id=lineage_id
        )
    )


def trajectory_payload(world: Any) -> list[dict[str, Any]]:
    """Compact checkpoint trajectory with retention/output fields removed."""
    result: list[dict[str, Any]] = []
    for checkpoint in world.checkpoints:
        row = dict(checkpoint)
        summary = dict(row.get("summary", {}))
        for key in OUTPUT_ONLY_SUMMARY_FIELDS:
            summary.pop(key, None)
        row["summary"] = summary
        information = dict(row.get("information", {}))
        information.pop("observations", None)
        row["information"] = information
        result.append(row)
    return result


def trajectory_sha256(world: Any) -> str:
    return canonical_sha256(trajectory_payload(world))


def isolated_run_signature(config_values: Mapping[str, Any]) -> dict[str, Any]:
    """Run one complete trajectory in the calling process and hash its state.

    The function is module-level and picklable, so ProcessPoolExecutor can use
    it directly on Windows spawn workers without sharing simulator objects.
    """
    from .generator import generate_pineland
    from .simulation import Simulation

    config = SimulationConfig.from_dict(dict(config_values))
    world = Simulation(generate_pineland(config)).run().world
    return {
        "decision_state_sha256": decision_state_sha256(world),
        "trajectory_sha256": trajectory_sha256(world),
        "component_sha256": decision_state_component_hashes(world),
    }


def parameter_registry_sha256(config: SimulationConfig) -> str:
    # Local import prevents a module cycle during validation imports.
    from .validation import registry_document
    return canonical_sha256(registry_document(config))


def _hash_inventory(paths: Iterable[str | Path] | None) -> dict[str, dict[str, str]]:
    inventory: dict[str, dict[str, str]] = {}
    for raw_path in paths or ():
        path = Path(raw_path).resolve()
        inventory[path.as_posix()] = {
            "sha256": file_sha256(path),
            "substantive_sha256": substantive_file_sha256(path),
        }
    return dict(sorted(inventory.items()))


def build_run_manifest(
    config: SimulationConfig | Mapping[str, Any],
    *,
    seeds: Iterable[int | str] | None = None,
    execution_mode: Mapping[str, Any] | str,
    output_schema: Mapping[str, Any] | str,
    case_files: Iterable[str | Path] | None = None,
    split_file: str | Path | None = None,
    repo_root: str | Path | None = None,
    parameter_registry_config: SimulationConfig | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    repo = _repo_root(repo_root)
    git_state = repository_state(repo)
    if isinstance(config, SimulationConfig):
        config_payload = config.to_dict()
        scientific_hash = scientific_config_sha256(config)
        registry_config = config
        default_seeds: list[int | str] = [config.seed]
    else:
        # Deterministic competitor/analysis jobs also need a complete
        # reproducibility envelope even though they are not simulator
        # trajectories.  Their explicit analysis specification is the config.
        config_payload = dict(config)
        scientific_hash = canonical_sha256(config_payload)
        registry_config = parameter_registry_config or SimulationConfig()
        default_seeds = ["not_applicable_deterministic"]
    seed_values = list(seeds) if seeds is not None else default_seeds
    normalized_seeds = sorted(
        (int(seed) if isinstance(seed, int) or str(seed).lstrip("-").isdigit()
         else str(seed) for seed in seed_values),
        key=lambda value: (isinstance(value, str), str(value)),
    )
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        **git_state,
        "model_sha256": model_sha256(repo),
        "config_sha256": canonical_sha256(config_payload),
        "scientific_config_sha256": scientific_hash,
        "parameter_registry_sha256": parameter_registry_sha256(registry_config),
        "case_data_hashes": _hash_inventory(case_files),
        "split_sha256": file_sha256(split_file) if split_file else None,
        "environment": environment_manifest(),
        "seeds": normalized_seeds,
        "output_schema": _normalized(output_schema),
        "execution_mode": _normalized(execution_mode),
    }
    if extra:
        manifest["extra"] = _normalized(extra)
    return manifest


def audit_run_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    missing = sorted(REQUIRED_MANIFEST_FIELDS - set(manifest))
    empty = sorted(
        key for key in REQUIRED_MANIFEST_FIELDS & set(manifest)
        if manifest[key] in (None, "", [], {})
        # A split hash is mandatory as a *field* but may be explicitly null
        # for synthetic/null-model jobs to which an empirical train/holdout
        # partition does not apply. Empirical evidence gates separately pin
        # and compare a real split hash before licensing holdout claims.
        and key not in {"case_data_hashes", "split_sha256"}
    )
    invalid: list[str] = []

    def is_hex_digest(value: Any, length: int) -> bool:
        return (
            isinstance(value, str) and len(value) == length and
            all(character in "0123456789abcdefABCDEF" for character in value)
        )

    if "schema_version" in manifest and manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        invalid.append("schema_version")
    if "dirty_tree" in manifest and not isinstance(manifest.get("dirty_tree"), bool):
        invalid.append("dirty_tree")
    if "commit_hash" in manifest and not is_hex_digest(manifest.get("commit_hash"), 40):
        invalid.append("commit_hash")
    for key in (
        "tracked_diff_sha256", "model_sha256", "config_sha256",
        "parameter_registry_sha256", "split_sha256",
    ):
        if key in manifest and manifest.get(key) not in (None, "") and not is_hex_digest(manifest.get(key), 64):
            invalid.append(key)
    if "case_data_hashes" in manifest:
        inventory = manifest.get("case_data_hashes")
        if not isinstance(inventory, Mapping) or any(
            not isinstance(path, str) or not path or
            not isinstance(digests, Mapping) or
            not is_hex_digest(digests.get("sha256"), 64) or
            not is_hex_digest(digests.get("substantive_sha256"), 64)
            for path, digests in (inventory.items() if isinstance(inventory, Mapping) else ())
        ):
            invalid.append("case_data_hashes")
    if "environment" in manifest and not isinstance(manifest.get("environment"), Mapping):
        invalid.append("environment")
    if "seeds" in manifest and (
        not isinstance(manifest.get("seeds"), list) or not manifest.get("seeds")
    ):
        invalid.append("seeds")
    for key in ("output_schema", "execution_mode"):
        if key in manifest and not isinstance(manifest.get(key), (Mapping, str)):
            invalid.append(key)
    return {
        "valid": not missing and not empty and not invalid,
        "missing_fields": missing,
        "empty_required_fields": empty,
        "invalid_fields": sorted(set(invalid)),
    }
