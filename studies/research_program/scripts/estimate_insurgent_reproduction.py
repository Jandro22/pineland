"""Estimate the provisional insurgent locality reproduction quantity R_I.

This tool does not infer parentage from violence proximity. Its input must
contain parent-attributed locality activations produced by a declared model or
historical coding protocol. Right censoring is handled by requiring a complete
follow-up window for every locality included in the denominator.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import random
from statistics import mean


def estimate(rows: list[dict], *, horizon_days: float, bootstrap: int = 1000,
             seed: int = 20260904,
             minimum_parent_overlap_days: float = 0.0,
             parent_edges: list[dict] | None = None,
             censoring_adjustment: str = "complete_case",
             cluster_field: str | None = None) -> dict:
    if horizon_days <= 0:
        raise ValueError("horizon_days must be positive")
    if minimum_parent_overlap_days < 0:
        raise ValueError("minimum_parent_overlap_days cannot be negative")
    if censoring_adjustment not in {"complete_case", "ipw"}:
        raise ValueError("censoring_adjustment must be 'complete_case' or 'ipw'")
    locality_counts: dict[str, int] = {}
    for row in rows:
        locality = str(row["locality_id"])
        locality_counts[locality] = locality_counts.get(locality, 0) + 1
    repeated_localities = {key for key, count in locality_counts.items() if count > 1}
    if repeated_localities:
        if any(not str(row.get("activation_id") or "").strip() for row in rows):
            raise ValueError(
                "repeated locality activations require explicit activation_id values"
            )
        if any(
            bool(row.get("parent_locality_id")) and
            not str(row.get("parent_activation_id") or "").strip()
            for row in rows
        ):
            raise ValueError(
                "repeated locality activations require parent_activation_id for attributed children"
            )

    def activation_key(row: dict) -> str:
        return str(row.get("activation_id") or row["locality_id"])

    all_activations: dict[str, dict] = {}
    for row in rows:
        key = activation_key(row)
        if key in all_activations:
            raise ValueError(f"duplicate activation identifier: {key}")
        all_activations[key] = row

    viable_activations = {
        key: row for key, row in all_activations.items()
        if bool(row["viable"])
    }
    parents = {
        key: row for key, row in all_activations.items()
        if bool(row["viable"]) and
        float(row["observation_end_day"]) - float(row["activation_day"]) >= horizon_days
    }
    right_censored_parent_activations = len(viable_activations) - len(parents)
    parent_analysis_weight: dict[str, float] = {}
    for key, row in parents.items():
        if censoring_adjustment == "ipw":
            raw_probability = row.get("followup_inclusion_probability")
            if raw_probability in (None, ""):
                raise ValueError(
                    "ipw censoring adjustment requires followup_inclusion_probability "
                    "for every complete-follow-up parent"
                )
            probability = float(raw_probability)
            if not 0 < probability <= 1:
                raise ValueError("followup_inclusion_probability must lie in (0, 1]")
            parent_analysis_weight[key] = 1.0 / probability
        else:
            parent_analysis_weight[key] = 1.0
    child_weight = {activation_id: 0.0 for activation_id in parents}
    gross_child_weight = {activation_id: 0.0 for activation_id in parents}
    pathway_child_weight: dict[str, dict[str, float]] = {}
    gross_pathway_child_weight: dict[str, dict[str, float]] = {}
    unattributed = 0.0
    ineligible_parent = 0.0
    unknown_parent = 0.0
    outside_window = 0.0
    relocation_or_parent_extinction = 0.0
    root_viable_activation_weight = 0.0
    same_time_cross_type_transition_weight = 0.0
    if minimum_parent_overlap_days > 0:
        missing_parent_end = [
            key for key, row in parents.items()
            if row.get("activation_end_day") in (None, "")
        ]
        if missing_parent_end:
            raise ValueError(
                "minimum_parent_overlap_days requires activation_end_day for every eligible parent"
            )
    edges_by_child: dict[str, list[dict]] = {}
    if parent_edges is not None:
        for edge in parent_edges:
            child_id = str(edge.get("child_activation_id") or "").strip()
            if child_id not in all_activations:
                raise ValueError(f"parent edge references unknown child activation: {child_id}")
            weight = float(edge.get("weight", 0.0))
            if not 0 <= weight <= 1:
                raise ValueError("parent edge weights must lie in [0, 1]")
            edges_by_child.setdefault(child_id, []).append(edge)
        for child_id, edges in edges_by_child.items():
            total = sum(float(edge["weight"]) for edge in edges)
            if total > 1.0 + 1e-9:
                raise ValueError(
                    f"parent attribution mass exceeds one for child {child_id}: {total}"
                )

    def attribute_child(
        row: dict, parent_id: str | None, weight: float,
        pathway: str = "unspecified", parent_channel: str | None = None,
    ) -> None:
        nonlocal unattributed, ineligible_parent, unknown_parent, outside_window
        nonlocal relocation_or_parent_extinction
        nonlocal same_time_cross_type_transition_weight
        if weight <= 0:
            return
        if not parent_id:
            unattributed += weight
            return
        parent_id = str(parent_id)
        parent = parents.get(parent_id)
        if parent is None:
            if parent_id in all_activations:
                ineligible_parent += weight
            else:
                unknown_parent += weight
            return
        lag = float(row["activation_day"]) - float(parent["activation_day"])
        child_channel = str(row.get("channel") or "")
        resolved_parent_channel = str(parent_channel or parent.get("channel") or "")
        if (
            abs(lag) <= 1e-12 and child_channel and resolved_parent_channel and
            child_channel != resolved_parent_channel
        ):
            # Same-event type progression is meaningful for the multitype
            # next-generation operator (e.g. member foothold -> fielded force)
            # but is not a new later activation for the scalar locality R_I.
            same_time_cross_type_transition_weight += weight
            return
        if 0 < lag <= horizon_days:
            gross_child_weight[parent_id] += weight
            gross_pathway_child_weight.setdefault(
                pathway or "unspecified",
                {activation_id: 0.0 for activation_id in parents},
            )[parent_id] += weight
            if minimum_parent_overlap_days > 0:
                parent_end = float(parent["activation_end_day"])
                required_end = float(row["activation_day"]) + minimum_parent_overlap_days
                if parent_end + 1e-12 < required_end:
                    relocation_or_parent_extinction += weight
                    return
            child_weight[parent_id] += weight
            pathway_child_weight.setdefault(
                pathway or "unspecified",
                {activation_id: 0.0 for activation_id in parents},
            )[parent_id] += weight
        else:
            outside_window += weight

    for row in rows:
        if not bool(row["viable"]):
            continue
        if str(row.get("cause") or "") == "initial_condition" or bool(row.get("is_root", False)):
            # Founding/root episodes belong in the eligible parent denominator
            # but are not offspring whose missing parentage should be counted as
            # an identification failure.
            root_viable_activation_weight += 1.0
            continue
        child_id = activation_key(row)
        if parent_edges is not None:
            edges = edges_by_child.get(child_id, [])
            if not edges:
                unattributed += 1.0
                continue
            total = sum(float(edge["weight"]) for edge in edges)
            unattributed += max(0.0, 1.0 - total)
            for edge in edges:
                attribute_child(
                    row,
                    edge.get("parent_activation_id"),
                    float(edge["weight"]),
                    str(edge.get("pathway") or "unspecified"),
                    str(edge.get("parent_channel") or ""),
                )
        else:
            parent_id = row.get("parent_activation_id") or row.get("parent_locality_id")
            attribute_child(
                row, parent_id, float(row.get("parent_weight", 1.0)),
                str(row.get("parent_pathway") or "unspecified"),
            )
    parent_ids = list(parents)

    def weighted_parent_mean(values_by_id: dict[str, float], ids: list[str] | None = None):
        selected = parent_ids if ids is None else ids
        denominator = sum(parent_analysis_weight[parent_id] for parent_id in selected)
        if denominator <= 0:
            return None
        return sum(
            parent_analysis_weight[parent_id] * values_by_id[parent_id]
            for parent_id in selected
        ) / denominator

    values = list(child_weight.values())
    gross_values = list(gross_child_weight.values())
    estimate_value = weighted_parent_mean(child_weight) if values else None
    gross_estimate_value = weighted_parent_mean(gross_child_weight) if gross_values else None
    pathway_estimates = {
        pathway: weighted_parent_mean(values_by_id)
        for pathway, values_by_id in sorted(pathway_child_weight.items())
    }
    gross_pathway_estimates = {
        pathway: weighted_parent_mean(values_by_id)
        for pathway, values_by_id in sorted(gross_pathway_child_weight.items())
    }
    interval = [None, None]
    bootstrap_method = "none"
    bootstrap_inferential_license = False
    bootstrap_cluster_count = 0
    if values and bootstrap > 0:
        rng = random.Random(seed)
        if cluster_field:
            clusters: dict[str, list[str]] = {}
            for parent_id, row in parents.items():
                raw_cluster = row.get(cluster_field)
                if raw_cluster in (None, ""):
                    raise ValueError(
                        f"cluster_field {cluster_field!r} is missing for parent {parent_id}"
                    )
                clusters.setdefault(str(raw_cluster), []).append(parent_id)
            cluster_ids = sorted(clusters)
            bootstrap_cluster_count = len(cluster_ids)
            bootstrap_method = "cluster_bootstrap_parent_activations"
            bootstrap_inferential_license = len(cluster_ids) >= 2
            draws = []
            for _ in range(bootstrap):
                sampled_clusters = rng.choices(cluster_ids, k=len(cluster_ids))
                sampled_parent_ids = [
                    parent_id
                    for cluster_id in sampled_clusters
                    for parent_id in clusters[cluster_id]
                ]
                draw = weighted_parent_mean(child_weight, sampled_parent_ids)
                if draw is not None:
                    draws.append(draw)
            draws.sort()
        else:
            bootstrap_method = "iid_parent_activation_descriptive_only"
            draws = []
            for _ in range(bootstrap):
                sampled_parent_ids = rng.choices(parent_ids, k=len(parent_ids))
                draw = weighted_parent_mean(child_weight, sampled_parent_ids)
                if draw is not None:
                    draws.append(draw)
            draws.sort()
        if draws:
            interval = [
                draws[int(0.025 * (len(draws) - 1))],
                draws[int(0.975 * (len(draws) - 1))],
            ]
    return {
        "schema_version": "1.5.0",
        "estimand": "R_I",
        "status": "estimate_not_general_theory_claim",
        "horizon_days": horizon_days,
        "minimum_parent_overlap_days": minimum_parent_overlap_days,
        "parentage_representation": (
            "multi_parent_edge_table" if parent_edges is not None else "legacy_single_parent_columns"
        ),
        "eligible_parent_activations": len(values),
        "eligible_parent_localities": len({row["locality_id"] for row in parents.values()}),
        "right_censored_parent_activations": right_censored_parent_activations,
        "complete_followup_fraction": (
            len(parents) / len(viable_activations) if viable_activations else None
        ),
        "censoring_adjustment": censoring_adjustment,
        "gross_attributed_viable_child_weight": sum(gross_values),
        "gross_attributed_viable_child_weight_by_pathway": {
            pathway: sum(values_by_id.values())
            for pathway, values_by_id in sorted(gross_pathway_child_weight.items())
        },
        "attributed_viable_child_weight": sum(values),
        "attributed_viable_child_weight_by_pathway": {
            pathway: sum(values_by_id.values())
            for pathway, values_by_id in sorted(pathway_child_weight.items())
        },
        "estimate_by_pathway": pathway_estimates,
        "relocation_or_parent_extinction_child_weight": relocation_or_parent_extinction,
        "root_viable_activation_weight": root_viable_activation_weight,
        "same_time_cross_type_transition_weight_excluded_from_scalar_R_I":
            same_time_cross_type_transition_weight,
        "unattributed_viable_child_weight": unattributed,
        "ineligible_parent_child_weight": ineligible_parent,
        "unknown_parent_child_weight": unknown_parent,
        "outside_reproduction_window_child_weight": outside_window,
        "estimate": estimate_value,
        "gross_estimate": gross_estimate_value,
        "gross_estimate_by_pathway": gross_pathway_estimates,
        "bootstrap_95_interval": interval,
        "bootstrap_method": bootstrap_method,
        "bootstrap_inferential_license": bootstrap_inferential_license,
        "bootstrap_cluster_field": cluster_field,
        "bootstrap_cluster_count": bootstrap_cluster_count,
        "bootstrap_repetitions": bootstrap,
        "bootstrap_seed": seed,
        "interpretation": (
            "Mean parent-attributed future viable activation episodes per viable parent activation "
            "with complete follow-up. When minimum_parent_overlap_days is positive, a candidate child "
            "counts as net reproduction only if the parent episode remains viable through that overlap "
            "window; otherwise it is classified as relocation/parent extinction rather than offspring. "
            "gross_estimate retains the unfiltered activation count. Unique-locality data reduce to the original locality estimand. "
            "Repeated activations require explicit activation IDs so parentage is never silently "
            "overwritten. A separate parent-edge table can distribute one child's attribution mass "
            "across multiple candidate parents without duplicating the child. Parent-edge pathways are "
            "reported separately so movement, social seeding, and other competing routes do not collapse "
            "into one opaque scalar. Complete-case censoring is explicit; optional IPW uses declared "
            "follow-up inclusion probabilities. The IID parent bootstrap is descriptive only; inferential "
            "uncertainty should cluster by independent simulation run or another defensible independent unit. "
            "Identification depends on the supplied parentage and viability protocols."
        ),
    }


def estimate_multitype_reproduction(
    rows: list[dict], parent_edges: list[dict], *, horizon_days: float,
    minimum_parent_overlap_days: float = 0.0,
) -> dict:
    """Estimate a next-generation matrix across locality-viability channels.

    Rows are parent channel types and columns are child channel types. The
    spectral radius is a multitype reproduction diagnostic: it can distinguish
    social/member-footprint reproduction from conversion into viable fielded
    force instead of collapsing both processes into one scalar count.
    """
    if horizon_days <= 0:
        raise ValueError("horizon_days must be positive")
    if minimum_parent_overlap_days < 0:
        raise ValueError("minimum_parent_overlap_days cannot be negative")
    by_id: dict[str, dict] = {}
    for row in rows:
        activation_id = str(row.get("activation_id") or "").strip()
        channel = str(row.get("channel") or "").strip()
        if not activation_id or not channel:
            raise ValueError("multitype reproduction requires activation_id and channel")
        if activation_id in by_id:
            raise ValueError(f"duplicate activation identifier: {activation_id}")
        by_id[activation_id] = row

    eligible = {
        activation_id: row for activation_id, row in by_id.items()
        if bool(row["viable"])
        and float(row["observation_end_day"]) - float(row["activation_day"]) >= horizon_days
    }
    if minimum_parent_overlap_days > 0 and any(
        row.get("activation_end_day") in (None, "") for row in eligible.values()
    ):
        raise ValueError("multitype net reproduction requires activation_end_day")

    channels = sorted({str(row["channel"]) for row in rows})
    parent_counts = {
        channel: sum(str(row["channel"]) == channel for row in eligible.values())
        for channel in channels
    }
    totals = {(parent, child): 0.0 for parent in channels for child in channels}
    relocation_weight = 0.0
    unknown_weight = 0.0
    child_mass: dict[str, float] = {}

    for edge in parent_edges:
        child_id = str(edge.get("child_activation_id") or "")
        parent_id = str(edge.get("parent_activation_id") or "")
        weight = float(edge.get("weight", 0.0))
        if not 0 <= weight <= 1:
            raise ValueError("parent edge weights must lie in [0, 1]")
        child_mass[child_id] = child_mass.get(child_id, 0.0) + weight
        child = by_id.get(child_id)
        parent = eligible.get(parent_id)
        if child is None or not bool(child.get("viable", False)):
            continue
        if parent is None:
            unknown_weight += weight
            continue
        lag = float(child["activation_day"]) - float(parent["activation_day"])
        parent_channel = str(parent["channel"])
        child_channel = str(child["channel"])
        # A declared cross-type parent edge may represent an ordered transition
        # inside one scheduler event (e.g. recruitment creates the first member
        # foothold and simultaneously pushes the local fighter pool over the
        # formation threshold). Such zero-lag progression is valid in the typed
        # operator, while zero-lag same-type reproduction is not.
        valid_lag = (
            0 < lag <= horizon_days or
            (abs(lag) <= 1e-12 and parent_channel != child_channel)
        )
        if not valid_lag:
            continue
        if minimum_parent_overlap_days > 0:
            if float(parent["activation_end_day"]) + 1e-12 < (
                float(child["activation_day"]) + minimum_parent_overlap_days
            ):
                relocation_weight += weight
                continue
        totals[(parent_channel, child_channel)] += weight

    if any(total > 1.0 + 1e-9 for total in child_mass.values()):
        raise ValueError("parent attribution mass exceeds one for at least one child")

    matrix = {
        parent: {
            child: (
                totals[(parent, child)] / parent_counts[parent]
                if parent_counts[parent] else 0.0
            )
            for child in channels
        }
        for parent in channels
    }

    def spectral_radius_of(candidate_matrix: dict[str, dict[str, float]]) -> float:
        # Power iteration is dependency-free and works for any number of
        # channel types. The matrix is nonnegative, so Perron-Frobenius gives
        # the relevant dominant reproduction mode when one exists.
        vector = [1.0 / max(1, len(channels)) for _ in channels]
        radius = 0.0
        for _ in range(500):
            new = [
                sum(
                    vector[i] * candidate_matrix[channels[i]][child]
                    for i in range(len(channels))
                )
                for child in channels
            ]
            norm = sum(abs(value) for value in new)
            if norm <= 1e-15:
                return 0.0
            radius = norm / max(1e-15, sum(abs(value) for value in vector))
            vector = [value / norm for value in new]
        return radius

    spectral_radius = spectral_radius_of(matrix)

    # Partial-identification bound for episodes whose producer did not declare
    # a parent edge. Roots are excluded. For every unresolved viable child,
    # identify all parent *channel types* with at least one temporally eligible
    # parent episode. Then add the child once to every feasible channel type.
    # No real attribution can assign that one child to all those channels at
    # once, so this elementwise matrix dominates every admissible single-parent
    # or fractional assignment and its Perron root is a conservative upper
    # bound by monotonicity of nonnegative matrices.
    parented_children = {
        str(edge.get("child_activation_id") or "")
        for edge in parent_edges
        if str(edge.get("parent_activation_id") or "").strip()
    }
    unresolved = [
        row for activation_id, row in by_id.items()
        if bool(row.get("viable", False))
        and str(row.get("cause") or "") != "initial_condition"
        and not bool(row.get("is_root", False))
        and activation_id not in parented_children
    ]
    upper_totals = dict(totals)
    unresolved_by_child_channel = {channel: 0 for channel in channels}
    unresolved_parentable = 0
    unresolved_without_feasible_parent = 0
    feasible_parent_channels_by_child: dict[str, list[str]] = {}
    for child in unresolved:
        child_id = str(child["activation_id"])
        child_channel = str(child["channel"])
        unresolved_by_child_channel[child_channel] += 1
        feasible_channels: set[str] = set()
        for parent in eligible.values():
            parent_channel = str(parent["channel"])
            lag = float(child["activation_day"]) - float(parent["activation_day"])
            if lag < -1e-12 or lag > horizon_days:
                continue
            if abs(lag) <= 1e-12 and parent_channel == child_channel:
                continue
            if minimum_parent_overlap_days > 0 and (
                float(parent["activation_end_day"]) + 1e-12 <
                float(child["activation_day"]) + minimum_parent_overlap_days
            ):
                continue
            feasible_channels.add(parent_channel)
        feasible_parent_channels_by_child[child_id] = sorted(feasible_channels)
        if feasible_channels:
            unresolved_parentable += 1
        else:
            unresolved_without_feasible_parent += 1
        for parent_channel in feasible_channels:
            upper_totals[(parent_channel, child_channel)] += 1.0

    conservative_upper_matrix = {
        parent: {
            child: (
                upper_totals[(parent, child)] / parent_counts[parent]
                if parent_counts[parent] else 0.0
            )
            for child in channels
        }
        for parent in channels
    }
    conservative_upper_radius = spectral_radius_of(conservative_upper_matrix)
    criticality_identification = (
        "identified_supercritical"
        if spectral_radius > 1.0 + 1e-12
        else "identified_subcritical"
        if conservative_upper_radius < 1.0 - 1e-12
        else "partially_identified_across_criticality_threshold"
    )

    return {
        "schema_version": "1.1.0",
        "estimand": "multitype_R_I_next_generation_matrix",
        "status": "diagnostic_not_general_theory_claim",
        "channels": channels,
        "eligible_parent_activations_by_channel": parent_counts,
        "matrix": matrix,
        "spectral_radius": spectral_radius,
        "spectral_radius_lower_bound": spectral_radius,
        "conservative_upper_bound_matrix": conservative_upper_matrix,
        "conservative_upper_bound_spectral_radius": conservative_upper_radius,
        "criticality_identification": criticality_identification,
        "unresolved_nonroot_viable_activation_count": len(unresolved),
        "unresolved_by_child_channel": unresolved_by_child_channel,
        "unresolved_temporally_parentable_activation_count": unresolved_parentable,
        "unresolved_without_temporally_feasible_parent_count":
            unresolved_without_feasible_parent,
        "feasible_parent_channels_by_unresolved_child":
            feasible_parent_channels_by_child,
        "relocation_or_parent_extinction_weight": relocation_weight,
        "unknown_or_ineligible_parent_weight": unknown_weight,
        "interpretation": (
            "Rows are parent viability channels and columns are child viability channels. "
            "The spectral radius summarizes whether the multitype activation process is locally "
            "supercritical under the supplied synthetic parentage protocol. The reported lower "
            "bound uses only declared parent edges. The conservative upper bound assigns every "
            "unresolved non-root child simultaneously to every temporally feasible parent channel; "
            "therefore any admissible attribution is elementwise no larger. If that upper Perron "
            "root is below one, subcriticality is identified despite unresolved parentage. This is "
            "not licensed for empirical inference until synthetic recovery and censoring tests pass."
        ),
    }


PARENTAGE_CLASSES = (
    "local_spontaneous_ignition",
    "social_network_seeded",
    "migrating_member_seeded",
    "formation_recruitment_seeded",
    "formation_relocation",
    "organizational_split_offspring",
    "sanctuary_external_seeded",
    "unresolved",
)


def parentage_class(row: dict) -> str:
    """Map producer-specific causes into the frozen causal parentage ontology."""
    declared = str(row.get("parentage_class") or "").strip()
    if declared in PARENTAGE_CLASSES:
        return declared
    cause = str(row.get("cause") or row.get("parent_pathway") or "").lower()
    event_type = str(row.get("event_type") or "").lower()
    if cause == "formation_relocation":
        return "formation_relocation"
    if cause == "armed_member_migration":
        return "migrating_member_seeded"
    if cause == "stored_social_exposure_recruitment":
        return "social_network_seeded"
    if cause == "formation_seeded_local_recruitment":
        return "formation_recruitment_seeded"
    if "split" in cause or "offspring" in cause:
        return "organizational_split_offspring"
    if any(token in cause or token in event_type for token in (
        "sanctuary", "external", "foreign", "diaspora",
    )):
        return "sanctuary_external_seeded"
    if cause in {"local_recruitment", "local_force_generation"}:
        return "local_spontaneous_ignition"
    return "unresolved"


def estimate_reproduction_decomposition(
    rows: list[dict], parent_edges: list[dict], *, horizon_days: float,
    survival_window_days: float,
) -> dict:
    """Estimate identifiable reproduction components without one omnibus R_I.

    The four components intentionally use different risk sets. Their explicit
    denominators prevent local ignition, cross-local propagation, within-site
    maturation, and persistence from being silently pooled.
    """
    if horizon_days <= 0 or survival_window_days <= 0:
        raise ValueError("horizon_days and survival_window_days must be positive")
    by_id = {
        str(row.get("activation_id") or row.get("locality_id")): row
        for row in rows
    }
    if len(by_id) != len(rows):
        raise ValueError("decomposition requires unique activation identifiers")
    edges_by_child: dict[str, list[dict]] = {}
    for edge in parent_edges:
        child_id = str(edge.get("child_activation_id") or "")
        parent_id = str(edge.get("parent_activation_id") or "")
        if child_id not in by_id or parent_id not in by_id:
            raise ValueError("decomposition parent edge references an unknown activation")
        weight = float(edge.get("weight", 0.0))
        if not 0 <= weight <= 1:
            raise ValueError("parent edge weights must lie in [0, 1]")
        edges_by_child.setdefault(child_id, []).append(edge)
    if any(
        sum(float(edge["weight"]) for edge in edges) > 1.0 + 1e-9
        for edges in edges_by_child.values()
    ):
        raise ValueError("parent attribution mass exceeds one for at least one child")

    nonroot_viable = [
        row for row in rows
        if bool(row.get("viable", False))
        and str(row.get("cause") or "") != "initial_condition"
        and not bool(row.get("is_root", False))
    ]
    class_counts = {name: 0.0 for name in PARENTAGE_CLASSES}
    for row in nonroot_viable:
        child_id = str(row.get("activation_id") or row.get("locality_id"))
        edges = edges_by_child.get(child_id, [])
        attributed = sum(float(edge["weight"]) for edge in edges)
        classification = parentage_class(row)
        class_counts[classification] += max(attributed, 1.0 if not edges else 0.0)
        if edges and attributed < 1.0 - 1e-9:
            class_counts["unresolved"] += 1.0 - attributed

    local_ignition = class_counts["local_spontaneous_ignition"]
    new_foothold_mass = sum(class_counts.values())
    observed_localities = len({str(row["locality_id"]) for row in rows})

    eligible_parents = {
        activation_id: row for activation_id, row in by_id.items()
        if bool(row.get("viable", False))
        and float(row["observation_end_day"]) - float(row["activation_day"])
        >= horizon_days
    }
    colonization_weight = 0.0
    deepening_weight = 0.0
    for child_id, edges in edges_by_child.items():
        child = by_id[child_id]
        for edge in edges:
            parent_id = str(edge["parent_activation_id"])
            parent = eligible_parents.get(parent_id)
            if parent is None or not bool(child.get("viable", False)):
                continue
            lag = float(child["activation_day"]) - float(parent["activation_day"])
            cross_type_same_event = (
                abs(lag) <= 1e-12
                and str(parent.get("channel")) != str(child.get("channel"))
            )
            if not (0 < lag <= horizon_days or cross_type_same_event):
                continue
            weight = float(edge["weight"])
            pathway = str(edge.get("pathway") or child.get("cause") or "")
            if (
                str(parent["locality_id"]) != str(child["locality_id"])
                and pathway != "formation_relocation"
            ):
                colonization_weight += weight
            if (
                str(parent["locality_id"]) == str(child["locality_id"])
                and str(child.get("channel")) == "fielded_force_viable"
                and str(parent.get("channel")) in {
                    "member_foothold_present", "member_access_saturated"
                }
            ):
                deepening_weight += weight

    eligible_foothold_parents = sum(
        str(row.get("channel")) in {
            "member_foothold_present", "member_access_saturated"
        }
        for row in eligible_parents.values()
    )
    survival_risk_set = [
        row for row in rows
        if bool(row.get("viable", False))
        and str(row.get("channel")) in {
            "member_foothold_present", "fielded_force_viable"
        }
        and float(row["observation_end_day"]) - float(row["activation_day"])
        >= survival_window_days
    ]
    survived = sum(
        float(row["activation_end_day"]) - float(row["activation_day"])
        >= survival_window_days
        for row in survival_risk_set
    )

    colonization_yield = (
        colonization_weight / len(eligible_parents) if eligible_parents else None
    )
    deepening_probability = (
        deepening_weight / eligible_foothold_parents
        if eligible_foothold_parents else None
    )
    survival_probability = (
        survived / len(survival_risk_set) if survival_risk_set else None
    )
    durable_yield = (
        colonization_yield * deepening_probability * survival_probability
        if None not in (
            colonization_yield, deepening_probability, survival_probability
        ) else None
    )
    return {
        "schema_version": "2.0.0",
        "estimand": "insurgent_reproduction_component_decomposition",
        "status": "component_estimands_not_general_theory_claim",
        "parentage_ontology": list(PARENTAGE_CLASSES),
        "components": {
            "local_endogenous_ignition": {
                "numerator": local_ignition,
                "denominator": observed_localities,
                "estimate": local_ignition / observed_localities
                if observed_localities else None,
                "unit": "locally ignited viable footholds per observed locality",
            },
            "parent_attributed_cross_local_colonization": {
                "numerator": colonization_weight,
                "denominator": len(eligible_parents),
                "estimate": colonization_yield,
                "unit": "non-relocation cross-local children per complete-followup parent",
            },
            "foothold_deepening_force_formation": {
                "numerator": deepening_weight,
                "denominator": eligible_foothold_parents,
                "estimate": deepening_probability,
                "unit": "fielded-force transitions per complete-followup foothold parent",
            },
            "post_establishment_survival": {
                "numerator": survived,
                "denominator": len(survival_risk_set),
                "estimate": survival_probability,
                "window_days": survival_window_days,
                "unit": "share of observable establishments surviving the fixed window",
            },
        },
        "parentage_mass_by_class": class_counts,
        "nonroot_viable_activation_mass": new_foothold_mass,
        "secondary_derived_quantity": {
            "name": "durable_cross_local_reproduction_yield",
            "estimate": durable_yield,
            "derivation": "colonization_yield * deepening_probability * survival_probability",
            "status": "secondary_diagnostic_not_omnibus_R_I",
        },
        "legacy_scalar_R_I": {
            "status": "deprecated_compatibility_only",
            "reason": "distinct risk sets and mechanisms must not be pooled into one primary estimand",
        },
    }


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["viable"] = str(row["viable"]).strip().lower() in {"1", "true", "yes"}
    return rows


def _read_edges(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_genealogy(path: Path) -> tuple[list[dict], list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    episodes = payload.get("episodes")
    parent_edges = payload.get("parent_edges")
    if not isinstance(episodes, list) or not isinstance(parent_edges, list):
        raise ValueError("genealogy JSON must contain episodes and parent_edges lists")
    if payload.get("historical_outcomes_used") is not False:
        raise ValueError(
            "genealogy JSON must explicitly declare historical_outcomes_used=false"
        )
    return episodes, parent_edges


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, nargs="?")
    parser.add_argument(
        "--genealogy-json",
        type=Path,
        help="Observation-only genealogy JSON containing episodes and parent_edges",
    )
    parser.add_argument("--horizon-days", type=float, required=True)
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260904)
    parser.add_argument("--minimum-parent-overlap-days", type=float, default=0.0)
    parser.add_argument("--parent-edges", type=Path)
    parser.add_argument(
        "--censoring-adjustment",
        choices=("complete_case", "ipw"),
        default="complete_case",
    )
    parser.add_argument("--cluster-field")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (args.input is None) == (args.genealogy_json is None):
        parser.error("provide exactly one of input CSV or --genealogy-json")
    if args.genealogy_json is not None:
        rows, genealogy_edges = _read_genealogy(args.genealogy_json)
        if args.parent_edges is not None:
            parser.error("--parent-edges cannot be combined with --genealogy-json")
        parent_edges = genealogy_edges
    else:
        rows = _read(args.input)
        parent_edges = _read_edges(args.parent_edges) if args.parent_edges else None
    legacy_result = estimate(rows, horizon_days=args.horizon_days,
                             bootstrap=args.bootstrap, seed=args.seed,
                             minimum_parent_overlap_days=args.minimum_parent_overlap_days,
                             parent_edges=parent_edges,
                             censoring_adjustment=args.censoring_adjustment,
                             cluster_field=args.cluster_field)
    if parent_edges is not None:
        result = estimate_reproduction_decomposition(
            rows,
            parent_edges,
            horizon_days=args.horizon_days,
            survival_window_days=max(
                args.minimum_parent_overlap_days, min(args.horizon_days, 30.0)
            ),
        )
        result["legacy_scalar_compatibility_output"] = legacy_result
    else:
        # Legacy CSV inputs may not contain an edge table rich enough for the
        # component estimands. Keep the old estimator available but mark this
        # output form as compatibility-only.
        result = legacy_result
        result["status"] = "legacy_scalar_compatibility_only"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
