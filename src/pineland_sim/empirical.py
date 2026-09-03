"""Evidence-facing data contracts and provenance-preserving transformations.

Raw case data is intentionally represented independently of :mod:`pineland_sim`
simulation state. The boundary is explicit: raw recorded observations are
transformed into weighted targets with measurement uncertainty, and only those
targets enter validation/calibration.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from .validation import TARGET_FAMILIES, empirical_target_contract


@dataclass(frozen=True, slots=True)
class RawObservation:
    observation_id: str
    case_id: str
    timestamp: str
    geography: str | None
    measure: str
    value: float
    source: str
    source_url: str | None = None
    recorded_uncertainty: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TransformationRecord:
    transformation_id: str
    operation: str
    input_observation_ids: tuple[str, ...]
    output_metric: str
    formula: str
    assumptions: tuple[str, ...]
    source_hash: str
    created_by: str = "pineland_sim.empirical"


@dataclass(frozen=True, slots=True)
class EmpiricalTarget:
    metric: str
    value: float
    uncertainty: float
    weight: float
    transformation_id: str
    case_id: str
    split: str
    missing: bool = False


@dataclass(slots=True)
class CasePackage:
    case_id: str
    name: str
    description: str
    time_window: dict[str, str]
    geography: dict[str, Any]
    observations: list[RawObservation] = field(default_factory=list)
    targets: list[EmpiricalTarget] = field(default_factory=list)
    transformations: list[TransformationRecord] = field(default_factory=list)
    missing_metrics: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def target_contract(self, source: str | None = None) -> dict[str, Any]:
        values = {target.metric: target.value for target in self.targets if not target.missing}
        weights = {target.metric: target.weight for target in self.targets if not target.missing}
        tolerances = {target.metric: target.uncertainty for target in self.targets if not target.missing}
        family = self.metadata.get("family", "all")
        contract = empirical_target_contract(values, family, source or self.metadata.get("source", self.name),
                                             self.case_id, self.metadata.get("split", "training"))
        for metric in values:
            contract["targets"][metric]["weight"] = weights[metric]
            contract["targets"][metric]["tolerance"] = max(1e-12, tolerances[metric])
        contract["missing_metrics"] = list(self.missing_metrics)
        contract["case_metadata"] = {"name": self.name, "time_window": self.time_window,
                                      "geography": self.geography}
        return contract


def _hash_rows(rows: Iterable[dict[str, Any]]) -> str:
    serialized = json.dumps(list(rows), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def load_raw_observations(path: str | Path, case_id: str | None = None) -> list[RawObservation]:
    """Load CSV or JSON/JSONL without coercing away measurement provenance."""
    path = Path(path)
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    else:
        text = path.read_text(encoding="utf-8")
        parsed = json.loads(text) if text.lstrip().startswith("[") else [json.loads(line) for line in text.splitlines() if line.strip()]
        rows = parsed if isinstance(parsed, list) else parsed.get("observations", [])
    result = []
    for index, row in enumerate(rows):
        metadata = row.get("metadata", {})
        if isinstance(metadata, str):
            metadata = json.loads(metadata) if metadata else {}
        result.append(RawObservation(
            str(row.get("observation_id", f"OBS{index+1:07d}")), str(row.get("case_id", case_id or "unspecified")),
            str(row.get("timestamp", "")), row.get("geography"), str(row.get("measure", "value")),
            float(row["value"]), str(row.get("source", "unspecified")), row.get("source_url"),
            float(row["recorded_uncertainty"]) if row.get("recorded_uncertainty") not in (None, "") else None,
            metadata))
    return result


def aggregate_observations(observations: list[RawObservation], output_metric: str,
                           operation: str = "mean", case_id: str | None = None,
                           split: str = "training", weight: float = 1.0,
                           uncertainty: float | None = None,
                           assumptions: tuple[str, ...] = ()) -> tuple[EmpiricalTarget, TransformationRecord]:
    if not observations:
        raise ValueError("cannot transform an empty observation set")
    values = [row.value for row in observations]
    if operation == "mean":
        value = mean(values); formula = "mean(value_i)"
    elif operation == "sum":
        value = sum(values); formula = "sum(value_i)"
    elif operation == "rate":
        durations = [float(row.metadata.get("duration", 1.0)) for row in observations]
        value = sum(values) / max(1e-12, sum(durations)); formula = "sum(value_i)/sum(duration_i)"
    else:
        raise ValueError(f"unsupported transformation operation: {operation}")
    uncertainty = uncertainty if uncertainty is not None else max(
        max((row.recorded_uncertainty or 0.0) for row in observations),
        (max(values) - min(values)) / max(1.0, len(values)))
    source_hash = _hash_rows([asdict(row) for row in observations])
    transform = TransformationRecord(
        f"TR{source_hash[:12]}", operation, tuple(row.observation_id for row in observations),
        output_metric, formula, assumptions, source_hash)
    target = EmpiricalTarget(output_metric, value, max(1e-12, uncertainty), weight,
                             transform.transformation_id, case_id or observations[0].case_id, split)
    return target, transform


def build_case_package(case_id: str, name: str, observations: list[RawObservation],
                       target_specs: list[dict[str, Any]],
                       *, description: str = "", time_window: dict[str, str] | None = None,
                       geography: dict[str, Any] | None = None,
                       missing_metrics: tuple[str, ...] = (), metadata: dict[str, Any] | None = None) -> CasePackage:
    package = CasePackage(case_id, name, description, time_window or {}, geography or {}, observations,
                          missing_metrics=missing_metrics, metadata=metadata or {})
    for spec in target_specs:
        selected = [row for row in observations if row.measure == spec["measure"]]
        target, transform = aggregate_observations(selected, spec["metric"], spec.get("operation", "mean"),
            case_id, spec.get("split", package.metadata.get("split", "training")), spec.get("weight", 1.0),
            spec.get("uncertainty"), tuple(spec.get("assumptions", ())))
        package.targets.append(target); package.transformations.append(transform)
    return package


def save_case_package(package: CasePackage, path: str | Path) -> None:
    payload = asdict(package)
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_case_package(path: str | Path) -> CasePackage:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload["observations"] = [RawObservation(**row) for row in payload.get("observations", [])]
    payload["targets"] = [EmpiricalTarget(**row) for row in payload.get("targets", [])]
    payload["transformations"] = [TransformationRecord(**row) for row in payload.get("transformations", [])]
    return CasePackage(**payload)


def recorded_synthetic_observations(world) -> list[RawObservation]:
    """Export the model's researcher-facing recorded layer, never hidden truth."""
    return [RawObservation(record.event_id, "synthetic", str(record.time), record.locality_id,
                           record.event_type, record.reported_severity, "Pineland synthetic record",
                           recorded_uncertainty=.5 if record.geocoding_error else .2,
                           metadata={"reported_actor": record.reported_actor,
                                     "geocoding_error": record.geocoding_error,
                                     "geocoding_error_distance_km": record.geocoding_error_distance_km})
            for record in world.synthetic_records if record.recorded]


def recorded_vs_true_metrics(world) -> dict[str, dict[str, float]]:
    """Return paired metrics to quantify the observation operator's distortion."""
    true_contacts = [event for event in world.event_log if event.event_type == "contact" and
                     event.true_state_delta.get("contact", 0) > 0]
    recorded = recorded_synthetic_observations(world)
    recorded_contacts = [row for row in recorded if row.measure == "contact"]
    true_count, recorded_count = len(true_contacts), len(recorded_contacts)
    return {"event_count": {"true": float(true_count), "recorded": float(recorded_count),
                             "absolute_error": float(recorded_count - true_count)},
            "event_severity_mean": {
                "true": mean([float(e.true_state_delta.get("severity", 0.0)) for e in true_contacts]) if true_contacts else 0.0,
                "recorded": mean([row.value for row in recorded_contacts]) if recorded_contacts else 0.0,
                "absolute_error": (mean([row.value for row in recorded_contacts]) if recorded_contacts else 0.0) -
                                  (mean([float(e.true_state_delta.get("severity", 0.0)) for e in true_contacts]) if true_contacts else 0.0)},
            "geocoding_error_rate": {"true": 0.0,
                                     "recorded": mean(row.metadata.get("geocoding_error", False) for row in recorded) if recorded else 0.0,
                                     "absolute_error": 0.0}}


def case_catalog(paths: Iterable[str | Path]) -> dict[str, Any]:
    packages = [load_case_package(path) for path in paths]
    return {"schema_version": "0.11.0", "cases": [
        {"case_id": p.case_id, "name": p.name, "targets": [t.metric for t in p.targets],
         "missing_metrics": list(p.missing_metrics), "source": p.metadata.get("source")}
        for p in packages]}
