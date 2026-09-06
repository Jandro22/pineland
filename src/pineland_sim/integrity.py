"""Cross-subsystem causal-integrity and pathology-watchlist diagnostics."""
from __future__ import annotations

from statistics import mean

from .entities import OrganizationKind


def causal_integrity_diagnostics(world) -> dict:
    from .physical import aggregate_insurgent_control

    active_insurgents = [org for org in world.organizations.values()
                         if org.kind is OrganizationKind.INSURGENT and org.status == "active"]
    physical_government = [locality.control["government"].physical
                           for locality in world.localities.values()]
    physical_insurgent = [
        aggregate_insurgent_control(world, locality.locality_id).physical
        for locality in world.localities.values()
    ]
    belief_confidence = [belief.confidence for belief in world.control_beliefs.values()]
    contradictions = [belief.contradiction_index for belief in world.control_beliefs.values()]
    eligible = [row for row in world.organization_eligibility_log if row["eligible"]]
    event_counts = dict(getattr(world, "event_counts", {}))
    for entry in world.event_log:
        event_counts[entry.event_type] = event_counts.get(entry.event_type, 0) + 1
    recruitment_events = event_counts.get("recruitment", 0)
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
    stock_report = world.stock_ledger_diagnostics()
    accounting_report = world.global_accounting_diagnostics()
    stock_residual = stock_report["residual"]
    if abs(stock_residual) > 1e-6:
        warnings.append("cross_stock_ledger_residual")
    if accounting_report["max_abs_stock_residual"] > 1e-6 or abs(accounting_report["population_residual"]) > 1e-6:
        warnings.append("global_accounting_residual")
    if active_insurgents and not world.organization_eligibility_log:
        warnings.append("fragmentation_eligibility_not_logged")
    if active_insurgents and world.time >= 365 and not eligible:
        warnings.append("fragmentation_eligibility_floor")
    momentum = [engagement.perceived_momentum_signal for engagement in world.engagements.values()]
    if momentum and mean(abs(value - .5) for value in momentum) < .02:
        warnings.append("combat_momentum_cancellation")
    patronage_series = [snapshot.get("pathology", {}).get("patronage_total", 0.0)
                        for snapshot in world.checkpoints]
    if len(patronage_series) >= 4 and patronage_series[-1] > max(patronage_series[:-1]) * 1.5:
        warnings.append("runaway_patronage")
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
        "stock_ledger": {
            "transactions": len(world.stock_transactions),
            "residual": stock_residual,
            "initial": dict(world.initial_tracked_stocks),
            "current": world.tracked_stock_totals(),
            "by_class": stock_report["by_class"],
            "by_boundary_net": stock_report["by_boundary_net"],
            "resource_to_supply_conversion": stock_report["resource_to_supply_conversion"],
            "by_flow_kind_net": stock_report.get("by_flow_kind_net", {}),
            "flow_kind_summary": accounting_report.get("flow_kind_summary", {}),
        },
        "global_accounting": accounting_report,
        "pathology_watchlist": {
            "checkpoint_count": len(world.checkpoints),
            "patronage_series": patronage_series,
            "belief_confidence_series": [snapshot.get("pathology", {}).get("belief_mean_confidence", 0.0)
                                          for snapshot in world.checkpoints],
            "active_insurgent_series": [snapshot.get("pathology", {}).get("active_insurgent_organizations", 0)
                                         for snapshot in world.checkpoints],
            "eligibility_series": [snapshot.get("pathology", {}).get("eligible_periods", 0)
                                   for snapshot in world.checkpoints],
            "event_counts": event_counts,
            "momentum_mean_absolute_deviation": (
                mean(abs(value - .5) for value in momentum) if momentum else None),
        },
        "state_delta_records": len(world.state_deltas),
        "warnings": warnings,
    }
