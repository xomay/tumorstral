"""Zero-shot Timestral inference, with no external interpolation or imputation.

Source API inspected at mistralai/timestral revision
a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff, src/timestral/forecaster.py.
The upstream implementation forward-fills missing inputs internally, retains
their observation mask and left-pads partial patches with unobserved zeros.
TumorTwin preserves NaNs and masks in its exported grid and does not create
observations. Raw quantile caps and nonnegative clipping are explicitly disabled;
symmetric averaging remains an explicit, recorded inference option.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

OFFICIAL_CODE_REVISION = "a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff"
QUANTILE_LEVELS = np.array([.01, .05, *[i/100 for i in range(10, 91, 5)], .95, .99])


@dataclass(frozen=True)
class GridContext:
    """A regular time grid whose false mask positions remain unobserved."""

    times: np.ndarray
    values: np.ndarray
    observation_mask: np.ndarray
    step: float

    @property
    def density(self) -> float:
        return float(self.observation_mask.mean())


def _integer_offsets(values: np.ndarray, step: float, name: str) -> np.ndarray:
    scaled = values/step
    rounded = np.rint(scaled)
    if not np.allclose(scaled, rounded, rtol=0, atol=1e-7):
        raise ValueError(f"{name} do not align with the declared grid step; no rounding/interpolation is allowed")
    return rounded.astype(np.int64)


def prepare_grid(days: np.ndarray, volumes: np.ndarray, step: float = 1.,
                 max_context: int = 32768) -> GridContext:
    """Construct the grid in the input time unit; gaps are not assumed missed visits.

    Dates are not treated as equally spaced observation ranks. ``step`` is an
    explicit modeling choice expressed in the same unit as ``days``. Missing
    source values and newly inserted unobserved grid positions both remain NaN.
    """
    days = np.asarray(days, dtype=float)
    values = np.asarray(volumes, dtype=float)
    if (days.ndim != 1 or values.shape != days.shape or len(days) == 0
            or not np.isfinite(days).all() or (np.diff(days) <= 0).any()):
        raise ValueError("Context requires finite strictly increasing unique dates and matching values")
    if not np.isfinite(step) or step <= 0 or max_context < 1:
        raise ValueError("Grid step and max_context must be positive")
    if np.isinf(values).any() or (values[np.isfinite(values)] < 0).any():
        raise ValueError("Volumes must be nonnegative finite values or NaN")
    offsets = _integer_offsets(days-days[0], step, "Context dates")
    length = int(offsets[-1])+1
    if length > max_context:
        raise ValueError(f"Grid context has {length} steps, exceeding {max_context}; no silent truncation")
    grid = np.full(length, np.nan)
    grid[offsets] = values
    mask = np.isfinite(grid)
    if not mask.any():
        raise ValueError("Context must contain at least one observed volume")
    return GridContext(days[0]+np.arange(length)*step, grid, mask, float(step))


def _numpy(value: Any) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value, dtype=float)


@dataclass(frozen=True)
class ForecastResult:
    """Raw 21-quantile outputs, selected targets and full regular-grid forecast."""

    target_days: np.ndarray
    quantile_levels: np.ndarray
    quantiles: np.ndarray
    future_days: np.ndarray
    full_quantiles: np.ndarray
    context: GridContext
    diagnostics: dict

    @property
    def median(self) -> np.ndarray:
        return self.quantiles[:, int(np.flatnonzero(np.isclose(self.quantile_levels, .5))[0])]

    def quantile(self, level: float) -> np.ndarray:
        indices = np.flatnonzero(np.isclose(self.quantile_levels, level, rtol=0, atol=1e-8))
        if len(indices) != 1:
            raise ValueError(f"Quantile level unavailable: {level}")
        return self.quantiles[:, int(indices[0])]


class TimestralAdapter:
    """A lazy optional dependency boundary around the official forecaster."""

    def __init__(self, forecaster: Any, *, model_revision: str,
                 code_revision: str = OFFICIAL_CODE_REVISION,
                 symmetric_averaging: bool = True, max_context: int = 32768) -> None:
        if not model_revision or not code_revision:
            raise ValueError("Model and code revisions must be recorded")
        self.forecaster = forecaster
        self.model_revision = model_revision
        self.code_revision = code_revision
        self.symmetric_averaging = symmetric_averaging
        self.max_context = max_context

    @classmethod
    def from_pretrained(cls, model_revision: str, *, device: str = "cpu",
                        cache_dir: Path | None = None, local_files_only: bool = False,
                        code_revision: str = OFFICIAL_CODE_REVISION,
                        model: str = "mistralai/Timestral-5M",
                        symmetric_averaging: bool = True) -> TimestralAdapter:
        """Pin remote weights to an immutable commit, and preserve raw outputs."""
        if len(model_revision) != 40 or any(c not in "0123456789abcdef" for c in model_revision.lower()):
            raise ValueError("model_revision must be a full immutable 40-character commit SHA")
        try:
            from timestral import TimestralForecaster
        except ImportError as error:
            raise RuntimeError("Timestral is optional; install the project's timestral extra with uv") from error
        forecaster = TimestralForecaster.from_pretrained(
            model, revision=model_revision, device=device, cache_dir=cache_dir,
            local_files_only=local_files_only, quantile_real_cap_k=0.)
        return cls(forecaster, model_revision=model_revision, code_revision=code_revision,
                   symmetric_averaging=symmetric_averaging)

    def forecast(self, days: np.ndarray, volumes: np.ndarray, target_days: np.ndarray,
                 *, step: float = 1.) -> ForecastResult:
        """Forecast exactly requested future grid dates; accepts prefix arrays only."""
        context = prepare_grid(days, volumes, step, self.max_context)
        targets = np.asarray(target_days, dtype=float)
        if targets.ndim != 1 or not len(targets) or not np.isfinite(targets).all():
            raise ValueError("Target dates must be a nonempty finite vector")
        offsets = _integer_offsets(targets-context.times[-1], step, "Target dates")
        if (offsets < 1).any():
            raise ValueError("Target dates must follow the context origin")
        horizon = int(offsets.max())
        forecast = self.forecaster.forecast(
            context.values[None, None, :].copy(), prediction_length=horizon,
            observation_mask=context.observation_mask[None, None, :].copy(),
            symmetric_averaging=self.symmetric_averaging, clip_nonnegative=False)
        levels = _numpy(forecast.quantile_levels)
        raw = _numpy(forecast.quantiles)
        if levels.shape != (21,) or not np.allclose(levels, QUANTILE_LEVELS, rtol=0, atol=1e-7):
            raise ValueError("Timestral must return its documented 21 quantile levels")
        if raw.shape != (1, 1, horizon, 21):
            raise ValueError(f"Unexpected Timestral output shape: {raw.shape}")
        full = raw[0, 0].copy()
        selected = full[offsets-1].copy()
        finite = np.isfinite(selected).all(axis=1)
        crossing = (np.diff(selected, axis=1) < -1e-10).any(axis=1)
        future = context.times[-1]+np.arange(1, horizon+1)*step
        diagnostics = dict(
            model="mistralai/Timestral-5M", model_revision=self.model_revision,
            code_revision=self.code_revision, zero_shot=True,
            symmetric_averaging=self.symmetric_averaging, clip_nonnegative=False,
            quantile_real_cap_k=0., n_grid_steps=len(context.times),
            n_observed=int(context.observation_mask.sum()), observation_density=context.density,
            step=step, n_forecast_steps=horizon, internal_forward_fill=True,
            valid_quantiles=(finite & ~crossing).tolist(),
            nonfinite_targets=int((~finite).sum()), crossed_targets=int(crossing.sum()),
            negative_quantiles=int((selected < 0).sum()),
            negative_medians=int((selected[:, int(np.flatnonzero(np.isclose(levels, .5))[0])] < 0).sum()))
        return ForecastResult(targets.copy(), levels.copy(), selected, future, full, context, diagnostics)
