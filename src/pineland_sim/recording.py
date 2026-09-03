"""Diagnostics for the synthetic event-recording observation operator."""
from __future__ import annotations

from statistics import mean


def recording_diagnostics(world) -> dict:
    """Summarize recorded-vs-generated events without treating records as truth.

    Every event-log entry is a generated event; the synthetic record is a
    noisy observation of it.  False-event precision is therefore reported as
    ``None`` until an explicit false-event process is configured, rather than
    silently claiming perfect precision.
    """
    generated = list(world.event_log)
    records = {record.event_id: record for record in world.synthetic_records}
    recorded = [record for record in records.values() if record.recorded]

    def strata(key):
        by_key: dict[str, dict[str, float | int | None]] = {}
        generated_keys = {key(event, records.get(event.event_id)) for event in generated}
        recorded_keys = {key(None, record) for record in recorded}
        for value in sorted(generated_keys | recorded_keys):
            events = [event for event in generated if key(event, records.get(event.event_id)) == value]
            rows = [record for record in recorded if key(None, record) == value]
            by_key[value] = {
                "generated_events": len(events),
                "recorded_events": len(rows),
                "recall_p_recorded_given_true": len(rows) / max(1, len(events)),
                "precision": None,
                "false_events_per_locality_day": 0.0,
            }
        return by_key
    by_type = strata(lambda event, record: event.event_type if event is not None else record.event_type)
    by_source = strata(lambda event, record: records.get(event.event_id).source_type
                       if event is not None and event.event_id in records
                       else record.source_type)
    geocoding_distances = [r.geocoding_error_distance_km for r in recorded]
    geocoding_flags = [r.geocoding_error for r in recorded]
    return {
        "generated_events": len(generated),
        "recorded_events": len(recorded),
        "recording_rate": len(recorded) / max(1, len(generated)),
        "precision": None,
        "recall_p_recorded_given_true": len(recorded) / max(1, len(generated)),
        "false_events_per_locality_day": 0.0,
        "geocoding_error_rate": mean(geocoding_flags) if geocoding_flags else 0.0,
        "geocoding_error_distance_km": {
            "mean": mean(geocoding_distances) if geocoding_distances else 0.0,
            "maximum": max(geocoding_distances) if geocoding_distances else 0.0,
            "n": len(geocoding_distances),
        },
        "by_event_type": by_type,
        "by_source_type": by_source,
        "model_note": "precision is undefined until an explicit false-event generator is enabled",
    }
