from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ProcessIntervals:
    patrol: float = 0.25
    physical_refresh: float = 0.25
    beliefs: float = 1.0
    social_influence: float = 1.0
    mobility: float = 1.0
    recruitment: float = 7.0
    governance: float = 30.0
    economy: float = 30.0
    checkpoint: float = 30.0


@dataclass(slots=True)
class SocialNetworkConfig:
    target_community_size: int = 100
    minimum_community_size: int = 50
    maximum_community_size: int = 150
    mean_social_degree: float = 8.0
    maximum_social_degree: int = 24
    bridge_fraction: float = 0.03
    behavior_update_rate: float = 0.12
    household_tie_strength: float = 0.95
    community_tie_strength: float = 0.65
    bridge_tie_strength: float = 0.45
    behavior_exposure_weight: float = 0.35
    recruitment_exposure_weight: float = 0.25

    def validate(self) -> None:
        if not 1 <= self.minimum_community_size <= self.target_community_size <= self.maximum_community_size:
            raise ValueError("community sizes must satisfy 1 <= minimum <= target <= maximum")
        if not 1 <= self.mean_social_degree <= self.maximum_social_degree:
            raise ValueError("mean_social_degree must be between 1 and maximum_social_degree")
        for name in ("bridge_fraction", "behavior_update_rate", "household_tie_strength",
                     "community_tie_strength", "bridge_tie_strength"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        for name in ("behavior_exposure_weight", "recruitment_exposure_weight"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")


@dataclass(slots=True)
class PhysicalModelConfig:
    village_microzones: int = 3
    town_microzones: int = 5
    city_microzones: int = 8
    extra_edge_probability: float = 0.22
    presence_memory_days: float = 2.0
    response_decay_hours: float = 0.75
    patrol_presence_gain: float = 0.35
    fixed_post_presence_gain: float = 0.25
    zone_observation_noise: float = 0.12
    patrol_route_randomness: float = 0.15

    def validate(self) -> None:
        if not 2 <= self.village_microzones <= self.town_microzones <= self.city_microzones:
            raise ValueError("microzone counts must satisfy 2 <= village <= town <= city")
        for name in ("extra_edge_probability", "patrol_presence_gain", "fixed_post_presence_gain",
                     "zone_observation_noise", "patrol_route_randomness"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.presence_memory_days <= 0 or self.response_decay_hours <= 0:
            raise ValueError("physical decay time constants must be positive")


@dataclass(slots=True)
class SimulationConfig:
    seed: int = 20260902
    horizon_days: float = 365.0
    agent_count: int = 75_000
    locality_count: int = 72
    burn_in_days: float = 30.0
    include_insurgency: bool = True
    initial_insurgent_share: float = 0.001
    observation_noise: float = 0.08
    reporting_error: float = 0.12
    movement_rate: float = 0.015
    recruitment_rate: float = 0.001
    contact_rate: float = 0.08
    random_stream_namespace: str = "baseline"
    intervals: ProcessIntervals = field(default_factory=ProcessIntervals)
    social_network: SocialNetworkConfig = field(default_factory=SocialNetworkConfig)
    physical: PhysicalModelConfig = field(default_factory=PhysicalModelConfig)

    def validate(self) -> None:
        if self.agent_count < 1:
            raise ValueError("agent_count must be positive")
        if not 17 <= self.locality_count:
            raise ValueError("locality_count must be at least 17")
        if self.horizon_days <= 0:
            raise ValueError("horizon_days must be positive")
        for name in ("initial_insurgent_share", "observation_noise", "reporting_error"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        for name in ("movement_rate", "recruitment_rate", "contact_rate"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        for name, value in asdict(self.intervals).items():
            if value <= 0:
                raise ValueError(f"interval {name} must be positive")
        self.social_network.validate()
        self.physical.validate()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "SimulationConfig":
        values = dict(values)
        if isinstance(values.get("intervals"), dict):
            values["intervals"] = ProcessIntervals(**values["intervals"])
        if isinstance(values.get("social_network"), dict):
            values["social_network"] = SocialNetworkConfig(**values["social_network"])
        if isinstance(values.get("physical"), dict):
            values["physical"] = PhysicalModelConfig(**values["physical"])
        config = cls(**values)
        config.validate()
        return config

    @classmethod
    def load(cls, path: str | Path) -> "SimulationConfig":
        with Path(path).open("r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    def save(self, path: str | Path) -> None:
        with Path(path).open("w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, sort_keys=True)
