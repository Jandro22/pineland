"""Cross-subsystem causal-integrity and pathology-watchlist diagnostics."""
from __future__ import annotations

from statistics import mean

from .entities import OrganizationKind


def causal_integrity_diagnostics(world) -> dict:
    active_insurgents = [org for org in world.organizations.values()
                         if org.kind is OrganizationKind.INSURGENT and org.status == "active"]
    physical_government = [locality.control["government"].physical
                           for locality in world.localities.values()]
    physical_insurgent = [locality.control.get("insurgent").physical
                          if "insurgent" in locality.control else 0.0
                          for locality in world.localities.values()]
    belief_confidence = [belief.confidence for belief in world.control_beliefs.values()]
    contradictions = [belief.contradiction_index for belief in world.control_beliefs.values()]
    eligible = [row for row in world.organization_eligibility_log if row["eligible"]]
    recruitment_events = sum(entry.event_type == "recruitment" for entry in world.event_log)
    warnings = []
    residual = world.supply_conservation_residual()
    if abs(residual) > 1e-6:
        warnings.append("supply_conservation_residual")
    if active_insurgents and recruitment_events == 0:
        warnings.append("recruitment_clock_missing")
    if active_insurgents and max(physical_insurgent, default=0.0) <= 0:
        warnings.append("insurgent_physical_reach_missing")
    if belief_confidence and mean(belief_confidence) < .02:
        warnings.append("belief_confidence_collapse")
    return {
        "supply_conservation_residual": residual,
        "active_insurgent_organizations": len(active_insurgents),
        "recruitment_events": recruitment_events,
        "physical_control_mean": {
            "government": mean(physical_government) if physical_government else 0.0,
            "insurgent": mean(physical_insurgent) if physical_insurgent else 0.0,
        },
        "belief_confidence": {
            "mean": mean(belief_confidence) if belief_confidence else 0.0,
            "minimum": min(belief_confidence) if belief_confidence else 0.0,
            "mean_contradiction": mean(contradictions) if contradictions else 0.0,
        },
        "organization_split_eligibility": {
            "periods": len(world.organization_eligibility_log),
            "eligible_periods": len(eligible),
            "conditional_split_probability": (
                mean(row["split"] for row in eligible) if eligible else 0.0
            ),
        },
        "patronage_stock": {
            "total": sum(branch.patronage_stock for branch in world.party_branches.values()),
            "maximum_branch": max((branch.patronage_stock for branch in world.party_branches.values()),
                                   default=0.0),
        },
        "warnings": warnings,
    }
