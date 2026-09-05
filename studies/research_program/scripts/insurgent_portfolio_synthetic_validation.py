"""Synthetic robustness study for insurgent reallocation portfolio weights.

This study is deliberately theory-only.  It generates Pineland worlds and
constructs matched synthetic counterfactuals; it does not read historical,
empirical, conflict-event, or validation-outcome data and it does not tune any
coefficient.

The preregistered covering design is the complete four-component simplex lattice
at 0.10 resolution, including its boundary, plus two ex ante anchors:

* the documented reference portfolio (0.50, 0.25, 0.15, 0.10), and
* the equal-weight centroid (0.25, 0.25, 0.25, 0.25).

Promotion requires exact synthetic causal invariants across this design rather
than favorable fit at the reference weights.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.entities import OrganizationKind
from pineland_sim.logistics import (
    _sanctuary_access,
    choose_reallocation_orders,
    reallocation_destination_score,
    shortest_locality_travel_times,
)


WEIGHT_FIELDS = (
    "insurgent_frontier_weight",
    "insurgent_foothold_weight",
    "insurgent_stronghold_weight",
    "reallocation_exploration_weight",
)
REFERENCE_WEIGHTS = (0.50, 0.25, 0.15, 0.10)
CENTROID_WEIGHTS = (0.25, 0.25, 0.25, 0.25)
SIMPLEX_DENOMINATOR = 10
SIMPLEX_LATTICE_POINTS = 286
EXPECTED_DESIGN_POINTS = 288
NUMERIC_TOLERANCE = 1e-9


def weight_covering_design() -> tuple[tuple[float, float, float, float], ...]:
    """Return the preregistered full 0.10 simplex lattice plus two anchors."""
    points: list[tuple[float, float, float, float]] = []
    denominator = SIMPLEX_DENOMINATOR
    for frontier in range(denominator + 1):
        for foothold in range(denominator - frontier + 1):
            for stronghold in range(denominator - frontier - foothold + 1):
                exploration = denominator - frontier - foothold - stronghold
                points.append(
                    (
                        frontier / denominator,
                        foothold / denominator,
                        stronghold / denominator,
                        exploration / denominator,
                    )
                )

    for anchor in (REFERENCE_WEIGHTS, CENTROID_WEIGHTS):
        if anchor not in points:
            points.append(anchor)
    return tuple(points)


def _synthetic_world(seed: int):
    config = SimulationConfig(
        agent_count=180,
        locality_count=24,
        horizon_days=2,
        seed=seed,
    )
    config.logistics.reallocation_rate = 1.0
    return generate_pineland(config)


def _focal_insurgent(world):
    return next(
        formation
        for formation in sorted(
            world.formations.values(), key=lambda item: item.formation_id
        )
        if (
            world.organizations[formation.organization_id].kind
            is OrganizationKind.INSURGENT
        )
    )


def _set_control_beliefs(
    world,
    formation,
    locality_id,
    *,
    own,
    opponent,
    own_confidence=1.0,
    opponent_confidence=1.0,
):
    own_target = "insurgent"
    opponent_target = "government"

    legacy = world.beliefs[(formation.organization_id, locality_id)]
    legacy.control_estimate.physical = own
    legacy.confidence = own_confidence

    own_belief = world.control_beliefs[
        (formation.organization_id, own_target, locality_id)
    ]
    own_belief.control_estimate.physical = own
    own_belief.confidence = own_confidence

    opposing = world.control_beliefs[
        (formation.organization_id, opponent_target, locality_id)
    ]
    opposing.control_estimate.physical = opponent
    opposing.confidence = opponent_confidence


def _set_weights(world, weights):
    for field, value in zip(WEIGHT_FIELDS, weights):
        setattr(world.config.logistics, field, value)
    world.config.logistics.validate()


def _score(
    world,
    formation,
    locality_id,
    *,
    own,
    opponent,
    own_confidence=1.0,
    opponent_confidence=1.0,
    foothold=0.0,
    route=None,
):
    _set_control_beliefs(
        world,
        formation,
        locality_id,
        own=own,
        opponent=opponent,
        own_confidence=own_confidence,
        opponent_confidence=opponent_confidence,
    )
    world.localities[locality_id].population = 10_000
    if route is None:
        route = [formation.locality_id, locality_id]
    footholds = {locality_id: foothold} if foothold else {}
    return reallocation_destination_score(
        world,
        formation,
        locality_id,
        travel_hours=4.0,
        maximum_population=10_000,
        footholds=footholds,
        route=route,
    )


def _stage_and_orthogonality_metrics(design, seed):
    world = _synthetic_world(seed)
    formation = _focal_insurgent(world)
    organization = world.organizations[formation.organization_id]
    organization.external_sanctuary = 0.0
    organization.sponsor_dependence = {}

    locality_id = next(
        locality_id
        for locality_id in sorted(world.localities)
        if locality_id != formation.locality_id
    )
    strategic_scale = world.config.logistics.reallocation_strategic_weight

    checks = 0
    passed = 0
    max_weight_recovery_error = 0.0
    max_cross_channel_component_change = 0.0
    uncertainty_frontier_cross_effect = 0.0
    frontier_uncertainty_cross_effect = 0.0
    min_active_utility_gain = math.inf
    min_expected_active_utility_gain = math.inf

    # Stronghold isolation holds frontier fixed analytically:
    # frontier = (1-own) * (1 - 0.65*opponent) = 0.30.
    frontier_target = 0.30
    own_low = 0.20
    own_high = 0.60
    opponent_at_low_own = (
        1.0 - frontier_target / (1.0 - own_low)
    ) / 0.65
    opponent_at_high_own = (
        1.0 - frontier_target / (1.0 - own_high)
    ) / 0.65

    for weights in design:
        _set_weights(world, weights)

        frontier_high = _score(
            world, formation, locality_id, own=0.20, opponent=0.10
        )
        frontier_low = _score(
            world, formation, locality_id, own=0.20, opponent=0.90
        )

        foothold_low = _score(
            world, formation, locality_id, own=0.50, opponent=0.50, foothold=0.0
        )
        foothold_high = _score(
            world, formation, locality_id, own=0.50, opponent=0.50, foothold=1.0
        )

        stronghold_low = _score(
            world,
            formation,
            locality_id,
            own=own_low,
            opponent=opponent_at_low_own,
        )
        stronghold_high = _score(
            world,
            formation,
            locality_id,
            own=own_high,
            opponent=opponent_at_high_own,
        )

        certain = _score(
            world,
            formation,
            locality_id,
            own=0.50,
            opponent=0.50,
            own_confidence=1.0,
            opponent_confidence=1.0,
        )
        uncertain = _score(
            world,
            formation,
            locality_id,
            own=0.50,
            opponent=0.50,
            own_confidence=0.0,
            opponent_confidence=0.0,
        )

        channel_pairs = (
            (
                0,
                frontier_high,
                frontier_low,
                frontier_high["frontier"] - frontier_low["frontier"],
            ),
            (
                1,
                foothold_high,
                foothold_low,
                foothold_high["foothold"] - foothold_low["foothold"],
            ),
            (
                2,
                stronghold_high,
                stronghold_low,
                stronghold_high["stronghold"] - stronghold_low["stronghold"],
            ),
            (
                3,
                uncertain,
                certain,
                uncertain["uncertainty"] - certain["uncertainty"],
            ),
        )

        for index, high, low, component_delta in channel_pairs:
            observed = high["utility"] - low["utility"]
            expected = strategic_scale * weights[index] * component_delta
            recovered_weight = observed / (strategic_scale * component_delta)
            recovery_error = abs(recovered_weight - weights[index])
            max_weight_recovery_error = max(
                max_weight_recovery_error, recovery_error
            )

            check_passed = (
                abs(observed - expected) <= NUMERIC_TOLERANCE
                and (
                    weights[index] == 0.0
                    or observed > 0.0
                )
            )
            checks += 1
            passed += int(check_passed)

            if weights[index] > 0.0:
                min_active_utility_gain = min(
                    min_active_utility_gain, observed
                )
                min_expected_active_utility_gain = min(
                    min_expected_active_utility_gain, expected
                )

        # Portfolio components other than the intervened channel must not move.
        max_cross_channel_component_change = max(
            max_cross_channel_component_change,
            abs(frontier_high["stronghold"] - frontier_low["stronghold"]),
            abs(frontier_high["uncertainty"] - frontier_low["uncertainty"]),
            abs(foothold_high["frontier"] - foothold_low["frontier"]),
            abs(foothold_high["stronghold"] - foothold_low["stronghold"]),
            abs(foothold_high["uncertainty"] - foothold_low["uncertainty"]),
            abs(stronghold_high["frontier"] - stronghold_low["frontier"]),
            abs(stronghold_high["uncertainty"] - stronghold_low["uncertainty"]),
            abs(uncertain["stronghold"] - certain["stronghold"]),
        )

        uncertainty_frontier_cross_effect = max(
            uncertainty_frontier_cross_effect,
            abs(uncertain["frontier"] - certain["frontier"]),
        )
        frontier_uncertainty_cross_effect = max(
            frontier_uncertainty_cross_effect,
            abs(frontier_high["uncertainty"] - frontier_low["uncertainty"]),
        )

    return {
        "checks": checks,
        "pass_rate": passed / checks,
        "max_weight_recovery_error": max_weight_recovery_error,
        "max_cross_channel_component_change": max_cross_channel_component_change,
        "uncertainty_frontier_cross_effect": uncertainty_frontier_cross_effect,
        "frontier_uncertainty_cross_effect": frontier_uncertainty_cross_effect,
        "min_active_utility_gain": min_active_utility_gain,
        "min_expected_active_utility_gain": min_expected_active_utility_gain,
    }


def _sanctuary_metrics(design, seed):
    world = _synthetic_world(seed)
    formation = _focal_insurgent(world)
    organization = world.organizations[formation.organization_id]
    border = next(iter(world.border_segments.values()))

    # Make the synthetic intervention unambiguous: one fully permeable sponsor
    # access point and no competing access point for the same sponsor.
    organization.external_sanctuary = 1.0
    organization.sponsor_dependence = {border.foreign_state_id: 1.0}
    for candidate in world.border_segments.values():
        if candidate.foreign_state_id != border.foreign_state_id:
            continue
        if candidate is border:
            candidate.social_permeability = 1.0
            candidate.kinship_overlap = 1.0
            candidate.language_overlap = 1.0
            candidate.legal_permeability = 1.0
            candidate.infrastructure = 1.0
            candidate.state_monitoring = 0.0
            candidate.terrain_friction = 1.0
        else:
            candidate.state_monitoring = 1.0

    travel = shortest_locality_travel_times(
        world, border.locality_id, formation.mobility
    )
    finite = {
        locality_id: hours
        for locality_id, hours in travel.items()
        if locality_id != border.locality_id and math.isfinite(hours)
    }
    far = max(finite, key=finite.get)
    near = border.locality_id

    near_access = _sanctuary_access(
        world,
        formation.organization_id,
        near,
        mobility=formation.mobility,
    )
    far_access = _sanctuary_access(
        world,
        formation.organization_id,
        far,
        mobility=formation.mobility,
    )

    passes = 0
    min_utility_gain = math.inf
    for weights in design:
        _set_weights(world, weights)
        near_score = _score(
            world, formation, near, own=0.50, opponent=0.50
        )
        far_score = _score(
            world, formation, far, own=0.50, opponent=0.50
        )
        gain = near_score["utility"] - far_score["utility"]
        min_utility_gain = min(min_utility_gain, gain)
        passes += int(
            near_score["sanctuary"] > far_score["sanctuary"]
            and gain > 0.0
        )

    return {
        "pass_rate": passes / len(design),
        "access_gap": near_access - far_access,
        "min_utility_gain": min_utility_gain,
    }


def _route_risk_metrics(design, seed):
    world = _synthetic_world(seed)
    formation = _focal_insurgent(world)
    organization = world.organizations[formation.organization_id]
    organization.external_sanctuary = 0.0
    organization.sponsor_dependence = {}
    organization.phenotype["risk_tolerance"] = 0.0

    candidates = [
        locality_id
        for locality_id in sorted(world.localities)
        if locality_id != formation.locality_id
    ]
    destination, intermediate = candidates[:2]
    route = [formation.locality_id, intermediate, destination]

    _set_control_beliefs(
        world, formation, destination, own=0.50, opponent=0.50
    )
    world.localities[destination].population = 10_000

    passes = 0
    min_utility_drop = math.inf
    max_penalty_identity_error = 0.0

    for weights in design:
        _set_weights(world, weights)

        _set_control_beliefs(
            world, formation, intermediate, own=0.50, opponent=0.10
        )
        low_risk = reallocation_destination_score(
            world,
            formation,
            destination,
            travel_hours=4.0,
            maximum_population=10_000,
            footholds={},
            route=route,
        )

        _set_control_beliefs(
            world, formation, intermediate, own=0.50, opponent=0.90
        )
        high_risk = reallocation_destination_score(
            world,
            formation,
            destination,
            travel_hours=4.0,
            maximum_population=10_000,
            footholds={},
            route=route,
        )

        observed_drop = low_risk["utility"] - high_risk["utility"]
        expected_drop = (
            high_risk["route_risk_penalty"]
            - low_risk["route_risk_penalty"]
        )
        min_utility_drop = min(min_utility_drop, observed_drop)
        max_penalty_identity_error = max(
            max_penalty_identity_error,
            abs(observed_drop - expected_drop),
        )
        passes += int(
            high_risk["route_risk"] > low_risk["route_risk"]
            and observed_drop > 0.0
        )

    return {
        "pass_rate": passes / len(design),
        "min_utility_drop": min_utility_drop,
        "max_penalty_identity_error": max_penalty_identity_error,
    }


class _StayCapturingRng:
    """Always trigger a decision, capture candidates, and choose the stay option."""

    def __init__(self, stay_locality_id):
        self.stay_locality_id = stay_locality_id
        self.candidate_calls: list[tuple[str, ...]] = []

    def random(self):
        return 0.0

    def choices(self, population, weights, k):
        self.candidate_calls.append(tuple(population))
        assert self.stay_locality_id in population
        return [self.stay_locality_id]


def _candidate_and_stay_metrics(seed):
    world = _synthetic_world(seed)
    formation = _focal_insurgent(world)
    for other in world.formations.values():
        if other.formation_id != formation.formation_id:
            other.moving = True

    probes = (
        REFERENCE_WEIGHTS,
        CENTROID_WEIGHTS,
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )

    formation.supply_stock = 1e30
    candidate_sets = []
    all_stay_choices_produce_no_order = True
    for weights in probes:
        _set_weights(world, weights)
        rng = _StayCapturingRng(formation.locality_id)
        orders = choose_reallocation_orders(
            world, 0.0, rng, interval_days=1.0
        )
        all_stay_choices_produce_no_order &= orders == []
        candidate_sets.append(rng.candidate_calls[-1])

    candidate_sets_identical = all(
        candidate_set == candidate_sets[0]
        for candidate_set in candidate_sets[1:]
    )
    stay_available_all = all(
        formation.locality_id in candidate_set
        for candidate_set in candidate_sets
    )

    # With positive movement consumption and zero stock, all non-stay moves must
    # be filtered before random utility choice.  The stay option must survive.
    world.config.logistics.movement_consumption_per_person_km = 1.0
    formation.supply_stock = 0.0
    _set_weights(world, REFERENCE_WEIGHTS)
    rng = _StayCapturingRng(formation.locality_id)
    orders = choose_reallocation_orders(
        world, 0.0, rng, interval_days=1.0
    )
    only_stay_feasible = (
        orders == []
        and rng.candidate_calls
        and rng.candidate_calls[-1] == (formation.locality_id,)
    )

    return {
        "probe_count": len(probes),
        "candidate_sets_identical": candidate_sets_identical,
        "stay_available_all": stay_available_all,
        "stay_choice_produces_no_order": all_stay_choices_produce_no_order,
        "only_stay_feasible_when_nonlocal_moves_unaffordable": only_stay_feasible,
    }


def run_validation(seed: int = 20260905) -> dict:
    """Run the preregistered synthetic program and return its compact artifact."""
    design = weight_covering_design()
    stage = _stage_and_orthogonality_metrics(design, seed)
    sanctuary = _sanctuary_metrics(design, seed + 1)
    route_risk = _route_risk_metrics(design, seed + 2)
    candidate_stay = _candidate_and_stay_metrics(seed + 3)

    design_gate = (
        len(design) == EXPECTED_DESIGN_POINTS
        and len(set(design)) == EXPECTED_DESIGN_POINTS
        and all(
            all(0.0 <= value <= 1.0 for value in weights)
            and math.isclose(sum(weights), 1.0, rel_tol=0.0, abs_tol=1e-12)
            for weights in design
        )
    )
    stage_gate = (
        stage["pass_rate"] == 1.0
        and stage["max_weight_recovery_error"] <= NUMERIC_TOLERANCE
        and stage["max_cross_channel_component_change"] <= NUMERIC_TOLERANCE
        and (
            stage["min_active_utility_gain"]
            + NUMERIC_TOLERANCE
            >= stage["min_expected_active_utility_gain"]
        )
    )
    orthogonality_gate = (
        stage["uncertainty_frontier_cross_effect"] <= NUMERIC_TOLERANCE
        and stage["frontier_uncertainty_cross_effect"] <= NUMERIC_TOLERANCE
    )
    sanctuary_gate = (
        sanctuary["pass_rate"] == 1.0
        and sanctuary["access_gap"] > 0.0
        and sanctuary["min_utility_gain"] > 0.0
    )
    route_risk_gate = (
        route_risk["pass_rate"] == 1.0
        and route_risk["min_utility_drop"] > 0.0
        and route_risk["max_penalty_identity_error"] <= NUMERIC_TOLERANCE
    )
    candidate_stay_gate = all(
        (
            candidate_stay["candidate_sets_identical"],
            candidate_stay["stay_available_all"],
            candidate_stay["stay_choice_produces_no_order"],
            candidate_stay[
                "only_stay_feasible_when_nonlocal_moves_unaffordable"
            ],
        )
    )

    gates = {
        "preregistered_simplex_cover": design_gate,
        "stage_separation": stage_gate,
        "uncertainty_frontier_orthogonality": orthogonality_gate,
        "sanctuary_monotonicity": sanctuary_gate,
        "route_risk_monotonicity": route_risk_gate,
        "candidate_set_and_stay_behavior": candidate_stay_gate,
    }
    failures = [name for name, passed in gates.items() if not passed]

    return {
        "schema_version": "pineland.insurgent_portfolio.synthetic_validation.v1",
        "provenance": {
            "synthetic_only": True,
            "historical_outcomes_used": False,
            "tuning_performed": False,
            "seed": seed,
        },
        "design": {
            "id": "full-simplex-lattice-0.10-plus-reference-and-centroid-v1",
            "simplex_resolution": 0.10,
            "simplex_lattice_points": SIMPLEX_LATTICE_POINTS,
            "anchor_points": 2,
            "point_count": len(design),
            "reference_weights": dict(zip(WEIGHT_FIELDS, REFERENCE_WEIGHTS)),
        },
        "gate_thresholds": {
            "required_pass_rate": 1.0,
            "max_identity_error": NUMERIC_TOLERANCE,
            "strict_monotonic_gain": "> 0",
        },
        "metrics": {
            "stage_separation": stage,
            "sanctuary": sanctuary,
            "route_risk": route_risk,
            "candidate_stay": candidate_stay,
        },
        "gates": gates,
        "promotion": not failures,
        "failures": failures,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run synthetic insurgent portfolio robustness validation."
    )
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the compact JSON artifact.",
    )
    args = parser.parse_args(argv)

    artifact = run_validation(args.seed)
    payload = json.dumps(
        artifact, sort_keys=True, separators=(",", ":")
    )
    if args.output is None:
        print(payload)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0 if artifact["promotion"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
