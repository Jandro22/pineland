"""Leakage-controlled simple competitors for Pineland validation panels.

The library is deliberately case-agnostic.  Every fitted quantity is estimated
from rows whose split is exactly ``training``.  Models with autoregressive state
use observed target history only while a row is training; once a unit enters a
holdout, its future state is propagated recursively from its own predictions.

This module is a benchmark layer, not part of Pineland dynamics.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, PoissonRegressor, Ridge
from scipy.optimize import nnls


EPS = 1e-9
TRAINING_SPLIT = "training"


@dataclass(frozen=True)
class PanelSpec:
    unit_col: str
    time_col: str
    target_col: str
    target_type: str
    split_col: str = "split"
    exposure_col: str | None = None
    covariate_cols: tuple[str, ...] = ()
    force_ratio_col: str | None = None
    prior_rows: float = 8.0
    adjacency: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.target_type not in {"binary", "count", "continuous"}:
            raise ValueError("target_type must be binary, count, or continuous")
        if self.prior_rows <= 0:
            raise ValueError("prior_rows must be positive")


def _required_columns(spec: PanelSpec) -> set[str]:
    columns = {spec.unit_col, spec.time_col, spec.target_col, spec.split_col}
    columns.update(spec.covariate_cols)
    if spec.exposure_col:
        columns.add(spec.exposure_col)
    if spec.force_ratio_col:
        columns.add(spec.force_ratio_col)
    return columns


def prepare_panel(frame: pd.DataFrame, spec: PanelSpec) -> pd.DataFrame:
    missing = sorted(_required_columns(spec) - set(frame.columns))
    if missing:
        raise ValueError(f"panel missing required columns: {missing}")
    prepared = frame.copy()
    prepared[spec.unit_col] = prepared[spec.unit_col].astype(str)
    prepared[spec.target_col] = pd.to_numeric(prepared[spec.target_col], errors="raise")
    if prepared.duplicated([spec.unit_col, spec.time_col]).any():
        raise ValueError("panel must have at most one row per unit/time")
    if not (prepared[spec.split_col] == TRAINING_SPLIT).any():
        raise ValueError("panel has no training rows")
    if spec.target_type == "binary":
        values = set(prepared[spec.target_col].astype(float).unique())
        if not values <= {0.0, 1.0}:
            raise ValueError("binary target must contain only 0/1")
    if spec.target_type == "count" and (prepared[spec.target_col] < 0).any():
        raise ValueError("count target cannot be negative")
    # Use a stable explicit mapping so mixed string/date/integer time columns
    # remain deterministic without relying on pandas tuple-field renaming.
    ordered_times = sorted(prepared[spec.time_col].unique().tolist())
    time_map = {value: index for index, value in enumerate(ordered_times)}
    prepared["__time_key"] = prepared[spec.time_col].map(time_map).astype(int)
    return prepared.sort_values(["__time_key", spec.unit_col]).reset_index(drop=True)


def _training(frame: pd.DataFrame, spec: PanelSpec) -> pd.DataFrame:
    return frame[frame[spec.split_col] == TRAINING_SPLIT]


def _global_binary_probability(training: pd.DataFrame, spec: PanelSpec) -> float:
    positives = float(training[spec.target_col].sum())
    return (positives + 1.0) / (len(training) + 2.0)


def _unit_binary_probabilities(training: pd.DataFrame, spec: PanelSpec) -> tuple[float, dict[str, float]]:
    global_p = _global_binary_probability(training, spec)
    grouped = training.groupby(spec.unit_col)[spec.target_col].agg(["sum", "count"])
    unit = {
        str(index): float((row["sum"] + spec.prior_rows * global_p) /
                          (row["count"] + spec.prior_rows))
        for index, row in grouped.iterrows()
    }
    return global_p, unit


def _exposure_weights(frame: pd.DataFrame, spec: PanelSpec) -> np.ndarray:
    if spec.exposure_col is None:
        return np.ones(len(frame), dtype=float)
    values = frame[spec.exposure_col].to_numpy(dtype=float)
    if np.any(values < 0):
        raise ValueError("exposure cannot be negative")
    if np.any((values <= EPS) & (frame[spec.target_col].to_numpy(dtype=float) > 0)):
        raise ValueError("positive count cannot have zero exposure")
    return values


def _count_rates(frame: pd.DataFrame, spec: PanelSpec) -> np.ndarray:
    exposure = _exposure_weights(frame, spec)
    counts = frame[spec.target_col].to_numpy(dtype=float)
    if spec.exposure_col is None:
        return counts
    return np.divide(counts, exposure, out=np.zeros_like(counts), where=exposure > EPS)


def _reference_exposure(training: pd.DataFrame, spec: PanelSpec) -> float:
    if spec.exposure_col is None:
        return 1.0
    exposure = _exposure_weights(training, spec)
    positive = exposure[exposure > EPS]
    return max(EPS, float(positive.mean()) if len(positive) else 1.0)


def _unit_count_rates(training: pd.DataFrame, spec: PanelSpec) -> tuple[float, dict[str, float]]:
    exposure = _exposure_weights(training, spec)
    total_exposure = max(EPS, float(exposure.sum()))
    global_rate = float(training[spec.target_col].sum()) / total_exposure
    result: dict[str, float] = {}
    for unit, subset in training.groupby(spec.unit_col):
        unit_exposure = float(_exposure_weights(subset, spec).sum())
        count = float(subset[spec.target_col].sum())
        prior_exposure = spec.prior_rows * (float(np.mean(exposure)) if len(exposure) else 1.0)
        result[str(unit)] = (count + global_rate * prior_exposure) / max(
            EPS, unit_exposure + prior_exposure
        )
    return global_rate, result


def _standardized_training_matrix(training: pd.DataFrame, frame: pd.DataFrame,
                                  columns: list[str]) -> tuple[np.ndarray, np.ndarray]:
    if not columns:
        return np.zeros((len(training), 0)), np.zeros((len(frame), 0))
    train_x = training[columns].astype(float).to_numpy()
    all_x = frame[columns].astype(float).to_numpy()
    mean = train_x.mean(axis=0)
    scale = train_x.std(axis=0)
    scale[scale < EPS] = 1.0
    return (train_x - mean) / scale, (all_x - mean) / scale


def _transition_probabilities(training: pd.DataFrame, spec: PanelSpec) -> tuple[float, float]:
    counts = np.ones((2, 2), dtype=float)  # Laplace smoothing.
    for _, subset in training.groupby(spec.unit_col):
        rows = subset.sort_values("__time_key")
        previous_time = None
        previous_state = None
        for _, row in rows.iterrows():
            time_value = int(row["__time_key"])
            state = int(float(row[spec.target_col]))
            if previous_time is not None and time_value == previous_time + 1:
                counts[previous_state, state] += 1.0
            previous_time, previous_state = time_value, state
    probabilities = counts / counts.sum(axis=1, keepdims=True)
    colonization = float(probabilities[0, 1])
    persistence = float(probabilities[1, 1])
    return colonization, persistence


def _recursive_binary_state(frame: pd.DataFrame, spec: PanelSpec,
                            transition: tuple[float, float],
                            *, neighbor_beta: float = 0.0,
                            force_model: LogisticRegression | None = None,
                            force_columns: list[str] | None = None,
                            force_mean: np.ndarray | None = None,
                            force_scale: np.ndarray | None = None) -> np.ndarray:
    frame = frame.reset_index(drop=True)
    colonization, persistence = transition
    predictions = np.zeros(len(frame), dtype=float)
    last_state: dict[str, float] = {}
    units = sorted(frame[spec.unit_col].unique().astype(str))
    global_p = _global_binary_probability(_training(frame, spec), spec)
    for unit in units:
        last_state[unit] = global_p
    by_time = frame.groupby("__time_key", sort=True)
    for _, rows in by_time:
        prior = dict(last_state)
        current_probabilities: dict[str, float] = {}
        for index, row in rows.iterrows():
            unit = str(row[spec.unit_col])
            prev = float(prior.get(unit, global_p))
            base = prev * persistence + (1.0 - prev) * colonization
            neighbors = spec.adjacency.get(unit, [])
            neighbor_share = (
                float(np.mean([prior.get(str(neighbor), global_p) for neighbor in neighbors]))
                if neighbors else global_p
            )
            if neighbor_beta:
                odds = np.clip(base, EPS, 1 - EPS)
                logit = math.log(odds / (1.0 - odds)) + neighbor_beta * (neighbor_share - global_p)
                base = 1.0 / (1.0 + math.exp(-logit))
            if force_model is not None and force_columns:
                raw = row[force_columns].astype(float).to_numpy()
                x = (raw - force_mean) / force_scale
                # The model includes previous occupancy explicitly as its first
                # feature; recursive prediction is therefore leakage-safe.
                features = np.concatenate([[prev], x]).reshape(1, -1)
                base = float(force_model.predict_proba(features)[0, 1])
            predictions[index] = np.clip(base, EPS, 1 - EPS)
            current_probabilities[unit] = predictions[index]
        # Training outcomes are observable history. Holdout targets never
        # update state, even when an earlier holdout row is temporally prior.
        for index, row in rows.iterrows():
            unit = str(row[spec.unit_col])
            if row[spec.split_col] == TRAINING_SPLIT:
                last_state[unit] = float(row[spec.target_col])
            else:
                last_state[unit] = current_probabilities[unit]
    return predictions


def _local_persistence_only(frame: pd.DataFrame, spec: PanelSpec,
                            persistence: float) -> np.ndarray:
    """No ignition and no propagation: established activity can only persist."""
    frame = frame.reset_index(drop=True)
    training = _training(frame, spec)
    global_p = _global_binary_probability(training, spec)
    last = {str(unit): global_p for unit in frame[spec.unit_col].unique()}
    predictions = np.zeros(len(frame), dtype=float)
    for _, rows in frame.groupby("__time_key", sort=True):
        prior = dict(last); current = {}
        for index, row in rows.iterrows():
            unit = str(row[spec.unit_col])
            value = np.clip(prior.get(unit, global_p) * persistence, EPS, 1-EPS)
            predictions[index] = value; current[unit] = value
        for index, row in rows.iterrows():
            unit = str(row[spec.unit_col])
            last[unit] = float(row[spec.target_col]) if row[spec.split_col] == TRAINING_SPLIT else current[unit]
    return predictions


def _fit_neighbor_beta(training: pd.DataFrame, spec: PanelSpec,
                       transition: tuple[float, float]) -> float:
    if not spec.adjacency:
        return 0.0
    # One-dimensional fixed grid deliberately keeps this competitor simple.
    candidates = (0.0, 0.5, 1.0, 2.0, 3.0)
    best_beta, best_score = 0.0, -float("inf")
    full = training.copy()
    for beta in candidates:
        predictions = _recursive_binary_state(full, spec, transition, neighbor_beta=beta)
        y = full[spec.target_col].to_numpy(dtype=float)
        score = float(np.mean(y * np.log(predictions) + (1 - y) * np.log(1 - predictions)))
        if score > best_score + 1e-12:
            best_beta, best_score = beta, score
    return best_beta


def _hawkes_excitation_features(frame: pd.DataFrame, spec: PanelSpec,
                                beta: float) -> tuple[np.ndarray, np.ndarray]:
    """Exact exponentially decayed training-history states in linear time.

    All rows at a time step are scored before that time step's training events
    update the state, preserving the strict ``prior < time`` Hawkes convention.
    Holdout outcomes never update state.
    """
    frame = frame.reset_index(drop=True)
    self_excitation = np.zeros(len(frame), dtype=float)
    neighbor_excitation = np.zeros(len(frame), dtype=float)
    state: dict[str, float] = {}
    last_time: dict[str, int] = {}

    def decayed(unit: str, time_key: int) -> float:
        value = state.get(unit, 0.0)
        previous = last_time.get(unit)
        if previous is None or value <= 0.0:
            return 0.0
        return value * math.exp(-beta * max(0, time_key - previous))

    for time_key, rows in frame.groupby("__time_key", sort=True):
        time_key = int(time_key)
        cache: dict[str, float] = {}

        def at_time(unit: str) -> float:
            if unit not in cache:
                cache[unit] = decayed(unit, time_key)
            return cache[unit]

        for index, row in rows.iterrows():
            unit = str(row[spec.unit_col])
            self_excitation[index] = at_time(unit)
            neighbors = spec.adjacency.get(unit, [])
            if neighbors:
                neighbor_excitation[index] = float(np.mean([
                    at_time(str(neighbor)) for neighbor in neighbors
                ]))

        additions: dict[str, float] = {}
        for _, row in rows.iterrows():
            if row[spec.split_col] == TRAINING_SPLIT and float(row[spec.target_col]) > 0:
                unit = str(row[spec.unit_col])
                additions[unit] = additions.get(unit, 0.0) + float(row[spec.target_col])
        for unit in set(cache) | set(additions):
            state[unit] = cache.get(unit, decayed(unit, time_key)) + additions.get(unit, 0.0)
            last_time[unit] = time_key
    return self_excitation, neighbor_excitation


def _hawkes_binary_predictions(frame: pd.DataFrame, spec: PanelSpec,
                               base: dict[str, float], global_p: float,
                               *, alpha: float, beta: float,
                               neighbor_alpha: float = 0.0) -> np.ndarray:
    frame = frame.reset_index(drop=True)
    self_excitation, neighbor_excitation = _hawkes_excitation_features(frame, spec, beta)
    base_p = np.clip(
        frame[spec.unit_col].astype(str).map(base).fillna(global_p).to_numpy(dtype=float),
        EPS, 1 - EPS,
    )
    hazard = (
        -np.log(1.0 - base_p)
        + alpha * self_excitation
        + neighbor_alpha * neighbor_excitation
    )
    return np.clip(1.0 - np.exp(-hazard), EPS, 1 - EPS)


def _fit_hawkes_grid(frame: pd.DataFrame, spec: PanelSpec, base: dict[str, float],
                     global_p: float, *, spatial: bool) -> tuple[float, float, float]:
    frame = frame.reset_index(drop=True)
    training_mask = (frame[spec.split_col] == TRAINING_SPLIT).to_numpy()
    y = frame.loc[training_mask, spec.target_col].to_numpy(dtype=float)
    base_p = np.clip(
        frame[spec.unit_col].astype(str).map(base).fillna(global_p).to_numpy(dtype=float),
        EPS, 1 - EPS,
    )
    base_hazard = -np.log(1.0 - base_p)
    best = (0.0, 0.25, 0.0)
    best_score = -float("inf")
    for beta in (0.1, 0.25, 0.5):
        self_excitation, neighbor_excitation = _hawkes_excitation_features(frame, spec, beta)
        for alpha in (0.0, 0.1, 0.2, 0.35):
            neighbor_values = (0.0, 0.1, 0.2) if spatial and spec.adjacency else (0.0,)
            for neighbor_alpha in neighbor_values:
                hazard = base_hazard + alpha * self_excitation + neighbor_alpha * neighbor_excitation
                predictions = np.clip(1.0 - np.exp(-hazard), EPS, 1 - EPS)[training_mask]
                score = float(np.mean(y * np.log(predictions) + (1-y) * np.log(1-predictions)))
                if score > best_score + 1e-12:
                    best_score = score
                    best = (alpha, beta, neighbor_alpha)
    return best


def _training_history_features(frame: pd.DataFrame, spec: PanelSpec,
                               *, windows: tuple[int, ...] = (4, 12)) -> np.ndarray:
    """Causal conflict-history features using training outcomes only.

    Training rows update their unit's history after feature construction.
    Holdout rows never update history, so mutations to held-out targets cannot
    affect later predictions. ``time_since`` increases naturally beyond the
    last observed training event.
    """
    frame = frame.reset_index(drop=True)
    histories: dict[str, list[tuple[int, float]]] = {
        str(unit): [] for unit in frame[spec.unit_col].unique()
    }
    features = np.zeros((len(frame), 1 + len(windows)), dtype=float)
    max_window = max(windows) if windows else 1
    for index, row in frame.iterrows():
        unit = str(row[spec.unit_col]); time_key = int(row["__time_key"])
        history = histories.setdefault(unit, [])
        positive_times = [time for time, value in history if value > 0]
        if positive_times:
            time_since = max(0, time_key - max(positive_times))
        else:
            time_since = max_window + time_key + 1
        values = [math.log1p(time_since)]
        for window in windows:
            recent = sum(
                value for time, value in history
                if 0 < time_key - time <= window
            )
            values.append(math.log1p(max(0.0, recent)))
        features[index] = values
        if row[spec.split_col] == TRAINING_SPLIT:
            histories[unit].append((time_key, float(row[spec.target_col])))
    return features


def binary_predictions(frame: pd.DataFrame, spec: PanelSpec) -> dict[str, np.ndarray]:
    training = _training(frame, spec)
    global_p, unit_p = _unit_binary_probabilities(training, spec)
    result: dict[str, np.ndarray] = {
        "global_rate": np.full(len(frame), global_p),
        "unit_empirical_bayes": frame[spec.unit_col].map(unit_p).fillna(global_p).to_numpy(dtype=float),
    }
    history_features = _training_history_features(frame, spec)
    training_mask = (frame[spec.split_col] == TRAINING_SPLIT).to_numpy()
    training_targets = training[spec.target_col].astype(int).to_numpy()
    if len(set(training_targets)) > 1:
        time_model = LogisticRegression(C=1.0, max_iter=2000).fit(
            history_features[training_mask, :1], training_targets
        )
        result["time_since_last_event_logit"] = time_model.predict_proba(
            history_features[:, :1]
        )[:, 1]
        history_model = LogisticRegression(C=1.0, max_iter=2000).fit(
            history_features[training_mask], training_targets
        )
        result["rolling_conflict_history_logit"] = history_model.predict_proba(
            history_features
        )[:, 1]
    else:
        result["time_since_last_event_logit"] = np.full(len(frame), global_p)
        result["rolling_conflict_history_logit"] = np.full(len(frame), global_p)
    transition = _transition_probabilities(training, spec)
    result["markov_persistence"] = _recursive_binary_state(frame, spec, transition)
    result["dynamic_occupancy"] = result["markov_persistence"].copy()
    result["local_persistence_only"] = _local_persistence_only(
        frame, spec, transition[1]
    )
    if spec.adjacency:
        beta = _fit_neighbor_beta(training, spec, transition)
        result["local_neighbor_diffusion"] = _recursive_binary_state(
            frame, spec, transition, neighbor_beta=beta
        )
    alpha, decay, _ = _fit_hawkes_grid(frame, spec, unit_p, global_p, spatial=False)
    result["temporal_hawkes"] = _hawkes_binary_predictions(
        frame, spec, unit_p, global_p, alpha=alpha, beta=decay
    )
    if spec.adjacency:
        alpha, decay, neighbor_alpha = _fit_hawkes_grid(
            frame, spec, unit_p, global_p, spatial=True
        )
        result["spatiotemporal_hawkes"] = _hawkes_binary_predictions(
            frame, spec, unit_p, global_p,
            alpha=alpha, beta=decay, neighbor_alpha=neighbor_alpha,
        )
    if spec.covariate_cols:
        columns = list(spec.covariate_cols)
        train_x, all_x = _standardized_training_matrix(training, frame, columns)
        if len(set(training[spec.target_col].astype(int))) > 1:
            model = LogisticRegression(C=1.0, max_iter=2000).fit(
                train_x, training[spec.target_col].astype(int)
            )
            result["static_covariate_logit"] = model.predict_proba(all_x)[:, 1]
    if spec.force_ratio_col:
        columns = [spec.force_ratio_col]
        train_values = training[columns].astype(float).to_numpy()
        mean = train_values.mean(axis=0)
        scale = train_values.std(axis=0); scale[scale < EPS] = 1.0
        # Training feature includes previous observed state only.  Fit rows with
        # a consecutive training predecessor.
        feature_rows, targets = [], []
        for _, subset in training.groupby(spec.unit_col):
            subset = subset.sort_values("__time_key")
            prior = None; prior_time = None
            for _, row in subset.iterrows():
                time_key = int(row["__time_key"])
                if prior is not None and time_key == prior_time + 1:
                    x = (row[columns].astype(float).to_numpy() - mean) / scale
                    feature_rows.append(np.concatenate([[prior], x]))
                    targets.append(int(row[spec.target_col]))
                prior = float(row[spec.target_col]); prior_time = time_key
        if len(set(targets)) > 1:
            model = LogisticRegression(C=1.0, max_iter=2000).fit(feature_rows, targets)
            result["persistence_force_logit"] = _recursive_binary_state(
                frame, spec, transition, force_model=model,
                force_columns=columns, force_mean=mean, force_scale=scale,
            )
    return result


def _recursive_count_poisson(frame: pd.DataFrame, spec: PanelSpec,
                             model: PoissonRegressor,
                             columns: list[str], mean: np.ndarray,
                             scale: np.ndarray,
                             *, include_neighbor: bool) -> np.ndarray:
    training = _training(frame, spec)
    global_rate, _ = _unit_count_rates(training, spec)
    reference_exposure = _reference_exposure(training, spec)
    last = {str(unit): global_rate for unit in frame[spec.unit_col].unique()}
    predictions = np.zeros(len(frame), dtype=float)
    for _, rows in frame.groupby("__time_key", sort=True):
        prior = dict(last)
        current = {}
        for index, row in rows.iterrows():
            unit = str(row[spec.unit_col])
            features = [math.log1p(max(0.0, prior.get(unit, global_rate)) * reference_exposure)]
            if include_neighbor:
                neighbors = spec.adjacency.get(unit, [])
                neighbor = (
                    float(np.mean([prior.get(str(n), global_rate) for n in neighbors]))
                    if neighbors else global_rate
                )
                features.append(math.log1p(max(0.0, neighbor) * reference_exposure))
            if columns:
                raw = row[columns].astype(float).to_numpy()
                features.extend(((raw - mean) / scale).tolist())
            standardized_count = max(
                EPS, float(model.predict(np.asarray(features).reshape(1, -1))[0])
            )
            predicted_rate = standardized_count / reference_exposure
            row_exposure = (
                max(0.0, float(row[spec.exposure_col]))
                if spec.exposure_col else 1.0
            )
            predictions[index] = predicted_rate * row_exposure
            current[unit] = predicted_rate
        for index, row in rows.iterrows():
            unit = str(row[spec.unit_col])
            if row[spec.split_col] == TRAINING_SPLIT:
                exposure = (
                    max(EPS, float(row[spec.exposure_col]))
                    if spec.exposure_col else 1.0
                )
                last[unit] = float(row[spec.target_col]) / exposure
            else:
                last[unit] = current[unit]
    return predictions


def _fit_branching_process(training: pd.DataFrame, spec: PanelSpec,
                           *, spatial: bool) -> tuple[float, ...] | None:
    """Fit nonnegative immigration + offspring coefficients on training transitions."""
    rates = _count_rates(training, spec)
    lookup = {
        (str(row[spec.unit_col]), int(row["__time_key"])): float(rate)
        for (_, row), rate in zip(training.iterrows(), rates)
    }
    x: list[list[float]] = []
    y: list[float] = []
    for _, row in training.iterrows():
        unit = str(row[spec.unit_col]); time_key = int(row["__time_key"])
        previous = lookup.get((unit, time_key - 1))
        if previous is None:
            continue
        features = [1.0, previous]
        if spatial:
            neighbors = spec.adjacency.get(unit, [])
            neighbor_values = [lookup[(str(n), time_key - 1)] for n in neighbors
                               if (str(n), time_key - 1) in lookup]
            features.append(float(np.mean(neighbor_values)) if neighbor_values else 0.0)
        exposure = (
            max(EPS, float(row[spec.exposure_col])) if spec.exposure_col else 1.0
        )
        x.append(features); y.append(float(row[spec.target_col]) / exposure)
    if len(x) < 3 or sum(y) <= 0:
        return None
    coefficients, _ = nnls(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
    return tuple(float(value) for value in coefficients)


def _recursive_branching(frame: pd.DataFrame, spec: PanelSpec,
                         coefficients: tuple[float, ...], *, spatial: bool) -> np.ndarray:
    frame = frame.reset_index(drop=True)
    training = _training(frame, spec)
    global_rate, _ = _unit_count_rates(training, spec)
    last = {str(unit): global_rate for unit in frame[spec.unit_col].unique()}
    predictions = np.zeros(len(frame), dtype=float)
    immigration, reproduction = coefficients[:2]
    neighbor_coefficient = coefficients[2] if spatial else 0.0
    for _, rows in frame.groupby("__time_key", sort=True):
        prior = dict(last); current = {}
        for index, row in rows.iterrows():
            unit = str(row[spec.unit_col])
            previous = max(0.0, prior.get(unit, global_rate))
            neighbor = 0.0
            if spatial:
                neighbors = spec.adjacency.get(unit, [])
                neighbor = (
                    float(np.mean([max(0.0, prior.get(str(n), global_rate)) for n in neighbors]))
                    if neighbors else 0.0
                )
            predicted_rate = max(
                EPS, immigration + reproduction * previous + neighbor_coefficient * neighbor
            )
            row_exposure = (
                max(0.0, float(row[spec.exposure_col])) if spec.exposure_col else 1.0
            )
            predictions[index] = predicted_rate * row_exposure
            current[unit] = predicted_rate
        for index, row in rows.iterrows():
            unit = str(row[spec.unit_col])
            if row[spec.split_col] == TRAINING_SPLIT:
                exposure = (
                    max(EPS, float(row[spec.exposure_col])) if spec.exposure_col else 1.0
                )
                last[unit] = float(row[spec.target_col]) / exposure
            else:
                last[unit] = current[unit]
    return predictions


def count_predictions(frame: pd.DataFrame, spec: PanelSpec) -> dict[str, np.ndarray]:
    training = _training(frame, spec)
    global_rate, unit_rate = _unit_count_rates(training, spec)
    exposure = _exposure_weights(frame, spec)
    result: dict[str, np.ndarray] = {
        "pooled_poisson": np.maximum(EPS, global_rate * exposure),
        "unit_shrunk_poisson": np.maximum(
            EPS,
            frame[spec.unit_col].map(unit_rate).fillna(global_rate).to_numpy(dtype=float) * exposure,
        ),
    }
    training_total = float(training[spec.target_col].sum())
    if spec.adjacency:
        spatial_rate = {}
        for unit in frame[spec.unit_col].unique().astype(str):
            neighbors = spec.adjacency.get(unit, [])
            neighbor_rate = (
                float(np.mean([unit_rate.get(str(n), global_rate) for n in neighbors]))
                if neighbors else global_rate
            )
            spatial_rate[unit] = 0.5 * unit_rate.get(unit, global_rate) + 0.5 * neighbor_rate
        result["spatial_lag_poisson"] = np.maximum(
            EPS,
            frame[spec.unit_col].map(spatial_rate).fillna(global_rate).to_numpy(dtype=float) * exposure,
        )
    branching = _fit_branching_process(training, spec, spatial=False)
    if branching is not None:
        result["branching_immigration"] = _recursive_branching(
            frame, spec, branching, spatial=False
        )
    if spec.adjacency:
        spatial_branching = _fit_branching_process(training, spec, spatial=True)
        if spatial_branching is not None:
            result["branching_spatial_immigration"] = _recursive_branching(
                frame, spec, spatial_branching, spatial=True
            )

    columns = list(spec.covariate_cols)
    train_matrix, _ = _standardized_training_matrix(training, training, columns)
    if columns and training_total > 0:
        train_x, all_x = _standardized_training_matrix(training, frame, columns)
        reference_exposure = _reference_exposure(training, spec)
        static_target = _count_rates(training, spec) * reference_exposure
        static_model = PoissonRegressor(alpha=1.0, max_iter=1000).fit(
            train_x, static_target
        )
        static_rate = np.maximum(EPS, static_model.predict(all_x)) / reference_exposure
        static_prediction = static_rate * exposure
        result["static_covariate_poisson"] = static_prediction
    elif columns:
        result["static_covariate_poisson"] = np.maximum(EPS, global_rate * exposure)

    history_features = _training_history_features(frame, spec)
    if training_total > 0:
        training_mask = (frame[spec.split_col] == TRAINING_SPLIT).to_numpy()
        reference_exposure = _reference_exposure(training, spec)
        standardized_target = _count_rates(training, spec) * reference_exposure
        history_model = PoissonRegressor(alpha=1.0, max_iter=1000).fit(
            history_features[training_mask], standardized_target
        )
        history_rate = np.maximum(
            EPS, history_model.predict(history_features)
        ) / reference_exposure
        result["rolling_conflict_history_poisson"] = history_rate * exposure
    else:
        result["rolling_conflict_history_poisson"] = np.maximum(EPS, global_rate * exposure)
    # Build training lag features only from consecutive training rows.
    def lag_training(include_neighbor: bool) -> tuple[list[list[float]], list[float]]:
        reference_exposure = _reference_exposure(training, spec)
        rates = _count_rates(training, spec)
        features, targets = [], []
        target_lookup = {
            (str(row[spec.unit_col]), int(row["__time_key"])): float(rate)
            for (_, row), rate in zip(training.iterrows(), rates)
        }
        for _, row in training.iterrows():
            unit = str(row[spec.unit_col]); time_key = int(row["__time_key"])
            prior_key = (unit, time_key - 1)
            if prior_key not in target_lookup:
                continue
            values = [math.log1p(target_lookup[prior_key] * reference_exposure)]
            if include_neighbor:
                neighbors = spec.adjacency.get(unit, [])
                available = [target_lookup[(str(n), time_key - 1)] for n in neighbors
                             if (str(n), time_key - 1) in target_lookup]
                neighbor_rate = float(np.mean(available)) if available else 0.0
                values.append(math.log1p(neighbor_rate * reference_exposure))
            if columns:
                raw = row[columns].astype(float).to_numpy()
                train_values = training[columns].astype(float).to_numpy()
                mean = train_values.mean(axis=0); scale = train_values.std(axis=0)
                scale[scale < EPS] = 1.0
                values.extend(((raw - mean) / scale).tolist())
            exposure_value = (
                max(EPS, float(row[spec.exposure_col])) if spec.exposure_col else 1.0
            )
            target_rate = float(row[spec.target_col]) / exposure_value
            features.append(values); targets.append(target_rate * reference_exposure)
        return features, targets

    train_values = training[columns].astype(float).to_numpy() if columns else np.zeros((len(training), 0))
    mean = train_values.mean(axis=0) if columns else np.zeros(0)
    scale = train_values.std(axis=0) if columns else np.ones(0)
    if columns:
        scale[scale < EPS] = 1.0
    for name, include_neighbor in (
        ("count_ar1_poisson", False),
        ("count_spatial_ar_poisson", True),
    ):
        if include_neighbor and not spec.adjacency:
            continue
        features, targets = lag_training(include_neighbor)
        if len(features) >= 3 and sum(targets) > 0:
            model = PoissonRegressor(alpha=1.0, max_iter=1000).fit(features, targets)
            result[name] = _recursive_count_poisson(
                frame, spec, model, columns, mean, scale,
                include_neighbor=include_neighbor,
            )
    return result


def continuous_predictions(frame: pd.DataFrame, spec: PanelSpec) -> dict[str, np.ndarray]:
    training = _training(frame, spec)
    global_mean = float(training[spec.target_col].mean())
    grouped = training.groupby(spec.unit_col)[spec.target_col].agg(["mean", "count"])
    unit_mean = {
        str(index): float((row["count"] * row["mean"] + spec.prior_rows * global_mean) /
                          (row["count"] + spec.prior_rows))
        for index, row in grouped.iterrows()
    }
    result: dict[str, np.ndarray] = {
        "global_training_mean": np.full(len(frame), global_mean),
        "unit_shrunk_mean": frame[spec.unit_col].map(unit_mean).fillna(global_mean).to_numpy(dtype=float),
    }
    # Fit pooled AR(1) on consecutive training observations.
    x, y = [], []
    for _, subset in training.groupby(spec.unit_col):
        subset = subset.sort_values("__time_key")
        prior = None; prior_time = None
        for _, row in subset.iterrows():
            time_key = int(row["__time_key"])
            if prior is not None and time_key == prior_time + 1:
                x.append([prior]); y.append(float(row[spec.target_col]))
            prior = float(row[spec.target_col]); prior_time = time_key
    ar = Ridge(alpha=1e-6).fit(x, y) if len(x) >= 2 else None
    last = {str(unit): unit_mean.get(str(unit), global_mean) for unit in frame[spec.unit_col].unique()}
    locf = np.zeros(len(frame)); ar_pred = np.zeros(len(frame))
    for _, rows in frame.groupby("__time_key", sort=True):
        prior = dict(last); current = {}
        for index, row in rows.iterrows():
            unit = str(row[spec.unit_col]); previous = prior.get(unit, global_mean)
            locf[index] = previous
            ar_value = float(ar.predict([[previous]])[0]) if ar is not None else previous
            ar_pred[index] = ar_value; current[unit] = ar_value
        for index, row in rows.iterrows():
            unit = str(row[spec.unit_col])
            last[unit] = float(row[spec.target_col]) if row[spec.split_col] == TRAINING_SPLIT else current[unit]
    result["last_observation_carried_forward"] = locf
    result["control_ar1"] = ar_pred
    if spec.covariate_cols:
        train_x, all_x = _standardized_training_matrix(
            training, frame, list(spec.covariate_cols)
        )
        static = Ridge(alpha=1.0).fit(
            train_x, training[spec.target_col].to_numpy(dtype=float)
        )
        result["static_covariate_ridge"] = static.predict(all_x)
    if spec.force_ratio_col:
        columns = [spec.force_ratio_col]
        train_x, all_x = _standardized_training_matrix(training, frame, columns)
        force = Ridge(alpha=1.0).fit(train_x, training[spec.target_col].to_numpy(dtype=float))
        result["force_ratio_only"] = force.predict(all_x)
        # Persistence + force ratio uses observed previous training state for
        # fitting and recursive predictions in holdout.
        feature_rows, targets = [], []
        mean = training[columns].astype(float).to_numpy().mean(axis=0)
        scale = training[columns].astype(float).to_numpy().std(axis=0); scale[scale < EPS] = 1.0
        for _, subset in training.groupby(spec.unit_col):
            subset = subset.sort_values("__time_key")
            prior = None; prior_time = None
            for _, row in subset.iterrows():
                time_key = int(row["__time_key"])
                if prior is not None and time_key == prior_time + 1:
                    force_x = (row[columns].astype(float).to_numpy() - mean) / scale
                    feature_rows.append(np.concatenate([[prior], force_x]))
                    targets.append(float(row[spec.target_col]))
                prior = float(row[spec.target_col]); prior_time = time_key
        if len(feature_rows) >= 2:
            model = Ridge(alpha=1.0).fit(feature_rows, targets)
            last = {str(unit): unit_mean.get(str(unit), global_mean) for unit in frame[spec.unit_col].unique()}
            predictions = np.zeros(len(frame))
            for _, rows in frame.groupby("__time_key", sort=True):
                prior_state = dict(last); current = {}
                for index, row in rows.iterrows():
                    unit = str(row[spec.unit_col]); previous = prior_state.get(unit, global_mean)
                    force_x = (row[columns].astype(float).to_numpy() - mean) / scale
                    value = float(model.predict(np.concatenate([[previous], force_x]).reshape(1,-1))[0])
                    predictions[index] = value; current[unit] = value
                for index, row in rows.iterrows():
                    unit = str(row[spec.unit_col])
                    last[unit] = float(row[spec.target_col]) if row[spec.split_col] == TRAINING_SPLIT else current[unit]
            result["persistence_plus_force_ratio"] = predictions
    return result


def predictions_for_panel(frame: pd.DataFrame, spec: PanelSpec) -> tuple[pd.DataFrame, dict[str, Any]]:
    prepared = prepare_panel(frame, spec)
    if spec.target_type == "binary":
        predictions = binary_predictions(prepared, spec)
    elif spec.target_type == "count":
        predictions = count_predictions(prepared, spec)
    else:
        predictions = continuous_predictions(prepared, spec)
    output = prepared[[spec.unit_col, spec.time_col, spec.split_col, spec.target_col]].copy()
    for name, values in predictions.items():
        output[name] = np.asarray(values, dtype=float)
    metadata = {
        "spec": asdict(spec),
        "training_rows": int((prepared[spec.split_col] == TRAINING_SPLIT).sum()),
        "total_rows": int(len(prepared)),
        "models": list(predictions),
        "holdout_target_updates": False,
        "fit_scope": "training_only",
    }
    return output, metadata


def _binary_score(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    p = np.clip(p, EPS, 1-EPS)
    return {
        "log_score": float(np.mean(y*np.log(p) + (1-y)*np.log(1-p))),
        "brier": float(np.mean((y-p)**2)),
        "observed_mean": float(np.mean(y)),
        "predicted_mean": float(np.mean(p)),
    }


def _count_score(y: np.ndarray, mu: np.ndarray) -> dict[str, float]:
    mu = np.maximum(mu, EPS)
    log_score = y*np.log(mu) - mu - np.asarray([math.lgamma(v+1) for v in y])
    active_p = 1-np.exp(-mu)
    return {
        "mean_poisson_log_score": float(np.mean(log_score)),
        "mae": float(np.mean(np.abs(y-mu))),
        "rmse": float(np.sqrt(np.mean((y-mu)**2))),
        "active_brier": float(np.mean(((y>0).astype(float)-active_p)**2)),
        "observed_mean": float(np.mean(y)),
        "predicted_mean": float(np.mean(mu)),
    }


def _continuous_score(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    return {
        "mae": float(np.mean(np.abs(y-p))),
        "rmse": float(np.sqrt(np.mean((y-p)**2))),
        "bias": float(np.mean(p-y)),
        "observed_mean": float(np.mean(y)),
        "predicted_mean": float(np.mean(p)),
    }


def score_predictions(predictions: pd.DataFrame, spec: PanelSpec) -> pd.DataFrame:
    identity = {spec.unit_col, spec.time_col, spec.split_col, spec.target_col, "__time_key"}
    model_columns = [column for column in predictions.columns if column not in identity]
    rows: list[dict[str, Any]] = []
    for split, subset in predictions.groupby(spec.split_col, sort=False):
        y = subset[spec.target_col].to_numpy(dtype=float)
        for model in model_columns:
            p = subset[model].to_numpy(dtype=float)
            if spec.target_type == "binary":
                metrics = _binary_score(y, p)
            elif spec.target_type == "count":
                metrics = _count_score(y, p)
            else:
                metrics = _continuous_score(y, p)
            rows.append({"split": split, "model": model, "n": len(subset), **metrics})
    return pd.DataFrame(rows)


def competitor_registry() -> list[dict[str, Any]]:
    """Machine-readable benchmark purpose, ordered from weakest to stronger."""
    return [
        {"model": "global_rate", "targets": ["binary"], "tests": "case-wide prevalence"},
        {"model": "unit_empirical_bayes", "targets": ["binary"], "tests": "static local propensity"},
        {"model": "markov_persistence", "targets": ["binary"], "tests": "local persistence/constant ignition"},
        {"model": "dynamic_occupancy", "targets": ["binary"], "tests": "constant site colonization and extinction"},
        {"model": "local_persistence_only", "targets": ["binary"], "tests": "persistence without ignition/propagation"},
        {"model": "local_neighbor_diffusion", "targets": ["binary"], "tests": "persistence plus adjacency diffusion"},
        {"model": "temporal_hawkes", "targets": ["binary"], "tests": "generic temporal self-excitation"},
        {"model": "spatiotemporal_hawkes", "targets": ["binary"], "tests": "generic spatial self-excitation"},
        {"model": "time_since_last_event_logit", "targets": ["binary"], "tests": "recency since local conflict"},
        {"model": "rolling_conflict_history_logit", "targets": ["binary"], "tests": "short/medium local conflict history"},
        {"model": "static_covariate_logit", "targets": ["binary"], "tests": "static geography/covariates"},
        {"model": "persistence_force_logit", "targets": ["binary"], "tests": "persistence plus force balance"},
        {"model": "pooled_poisson", "targets": ["count"], "tests": "global event rate"},
        {"model": "unit_shrunk_poisson", "targets": ["count"], "tests": "static local event propensity"},
        {"model": "spatial_lag_poisson", "targets": ["count"], "tests": "static spatial smoothing"},
        {"model": "count_ar1_poisson", "targets": ["count"], "tests": "count persistence"},
        {"model": "count_spatial_ar_poisson", "targets": ["count"], "tests": "count persistence plus neighbors"},
        {"model": "branching_immigration", "targets": ["count"], "tests": "offspring reproduction plus exogenous ignition"},
        {"model": "branching_spatial_immigration", "targets": ["count"], "tests": "offspring plus neighboring reproduction and immigration"},
        {"model": "static_covariate_poisson", "targets": ["count"], "tests": "static geography/manpower/capacity covariates"},
        {"model": "rolling_conflict_history_poisson", "targets": ["count"], "tests": "short/medium count history"},
        {"model": "global_training_mean", "targets": ["continuous"], "tests": "global control mean"},
        {"model": "unit_shrunk_mean", "targets": ["continuous"], "tests": "static local control propensity"},
        {"model": "last_observation_carried_forward", "targets": ["continuous"], "tests": "control persistence"},
        {"model": "control_ar1", "targets": ["continuous"], "tests": "mean-reverting/persistent control"},
        {"model": "force_ratio_only", "targets": ["continuous"], "tests": "force-balance control"},
        {"model": "persistence_plus_force_ratio", "targets": ["continuous"], "tests": "control persistence plus force balance"},
        {"model": "static_covariate_ridge", "targets": ["continuous"], "tests": "static geography/manpower/capacity covariates"},
    ]
