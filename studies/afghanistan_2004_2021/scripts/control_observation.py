"""Prospective SIGAR observation operator, separate from latent model code."""
from __future__ import annotations

from math import exp
import random
from typing import Mapping


CONTROL_DIMENSIONS = ("formal", "physical", "administrative", "legal", "fiscal", "social", "expected")
SIGAR_CATEGORIES = ("Insurgent Control", "Insurgent Influence", "Contested",
                    "GIRoA Influence", "GIRoA Control")


class OrdinalControlObservationModel:
    def __init__(self, weights: Mapping[str, float],
                 cutpoints: tuple[float, float, float, float], error_scale: float = 0.08):
        self.weights = dict(weights); self.cutpoints = tuple(cutpoints); self.error_scale = error_scale
        if set(self.weights) != set(CONTROL_DIMENSIONS):
            raise ValueError("weights must cover exactly the seven control dimensions")
        if any(value < 0 for value in self.weights.values()) or sum(self.weights.values()) <= 0:
            raise ValueError("control weights must be nonnegative with positive total")
        if tuple(sorted(self.cutpoints)) != self.cutpoints or len(set(self.cutpoints)) != 4:
            raise ValueError("four unique increasing cutpoints are required")
        if self.cutpoints[0] <= 0 or self.cutpoints[-1] >= 1 or self.error_scale <= 0:
            raise ValueError("cutpoints must be inside (0, 1) and error_scale must be positive")

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "OrdinalControlObservationModel":
        return cls({str(k): float(v) for k, v in dict(payload["weights"]).items()},
                   tuple(float(v) for v in payload["cutpoints"]), float(payload["error_scale"]))

    def latent_score(self, government, insurgent) -> float:
        government = government.to_dict() if hasattr(government, "to_dict") else government
        insurgent = insurgent.to_dict() if hasattr(insurgent, "to_dict") else insurgent
        # Score signed control advantage rather than the ratio g / (g + i).
        # The ratio discards absolute reach: 0.01 vs 0.00 and 1.00 vs 0.00
        # both become 1.0.  A control observation operator should distinguish
        # negligible uncontested presence from comprehensive control.  The
        # affine difference below is bounded in [0, 1], actor-symmetric around
        # 0.5, and preserves the declared dimension weights.
        score = 0.0
        for dimension, weight in self.weights.items():
            g = min(1.0, max(0.0, float(government[dimension])))
            i = min(1.0, max(0.0, float(insurgent[dimension])))
            score += weight * (0.5 + 0.5 * (g - i))
        return score / sum(self.weights.values())

    def probabilities(self, government, insurgent) -> dict[str, float]:
        score = self.latent_score(government, insurgent)
        cumulative = [1 / (1 + exp(-max(-700.0, min(700.0, (cut - score) / self.error_scale))))
                      for cut in self.cutpoints]
        masses = [cumulative[0], *(cumulative[i] - cumulative[i - 1] for i in range(1, 4)),
                  1 - cumulative[-1]]
        return dict(zip(SIGAR_CATEGORIES, masses))

    def expected_index(self, government, insurgent) -> float:
        probabilities = self.probabilities(government, insurgent)
        return sum(i * .25 * probabilities[category] for i, category in enumerate(SIGAR_CATEGORIES))

    def modal_category(self, government, insurgent) -> str:
        probabilities = self.probabilities(government, insurgent)
        return max(SIGAR_CATEGORIES, key=probabilities.__getitem__)

    def synthetic_recovery(self, *, samples_per_category: int = 200, seed: int = 20260904) -> dict:
        if samples_per_category <= 0:
            raise ValueError("samples_per_category must be positive")
        rng = random.Random(seed); boundaries = (0.0, *self.cutpoints, 1.0); correct = 0
        for index, category in enumerate(SIGAR_CATEGORIES):
            for _ in range(samples_per_category):
                value = rng.uniform(boundaries[index] + 1e-6, boundaries[index + 1] - 1e-6)
                g = {dimension: value for dimension in CONTROL_DIMENSIONS}
                i = {dimension: 1 - value for dimension in CONTROL_DIMENSIONS}
                correct += self.modal_category(g, i) == category
        total = samples_per_category * len(SIGAR_CATEGORIES)
        return {"status": "synthetic_observation_recovery_not_historical_fit", "samples": total,
                "correct": correct, "accuracy": correct / total, "seed": seed}
