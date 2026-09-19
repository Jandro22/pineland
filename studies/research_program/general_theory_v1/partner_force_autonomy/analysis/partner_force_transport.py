"""Optional transport-assay helpers.

This module is not part of the Stage-3 primary hypothesis evaluator.  It is kept
only as a future behavioral-assay helper and deliberately emits no dependency
verdicts from command-state proxies.
"""
from __future__ import annotations


def compute_relocation_flux(
    movements_completed: int,
    mean_travel_time_hours: float,
    threatened_sectors_reinforced: int,
    total_threatened_sectors: int,
) -> float:
    if total_threatened_sectors <= 0:
        return 0.0
    reinforcement_rate = threatened_sectors_reinforced / total_threatened_sectors
    speed_factor = movements_completed / max(mean_travel_time_hours, 1.0)
    return float(speed_factor * reinforcement_rate)


STAGE3_STATUS = "OPTIONAL_HELPER_NOT_A_PRIMARY_PREDICTOR_OR_OUTCOME"
