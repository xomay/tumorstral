"""Bounded multi-start fits in volume space with analytic derivatives."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import product
from time import perf_counter

import numpy as np
from scipy.optimize import least_squares

MODELS = ("persistence", "exponential", "logistic", "gompertz")
DEFAULTS = dict(max_nfev=2000, tolerance=1e-8, volume_lower=1e-6,
                volume_upper_factor=1000., rate_bound=2.,
                exponential_starts=[-.1, 0., .1], rate_starts=[.01, .1, .5],
                capacity_factors=[.5, 1., 2., 10.],
                condition_threshold=1e8, boundary_threshold=1e-4)


def curve(model: str, tau: np.ndarray, parameters: np.ndarray) -> np.ndarray:
    """Evaluate in mm³ at elapsed days; no clipping of large finite volumes."""
    t = np.asarray(tau, dtype=float)
    if model not in MODELS or model == "persistence":
        raise ValueError("curve requires a mechanistic model")
    if not np.isfinite(t).all() or (t < 0).any():
        raise ValueError("Elapsed times must be finite and nonnegative")
    v0, r = parameters[:2]
    if v0 <= 0 or not np.isfinite(parameters).all():
        raise ValueError("Invalid parameters")
    with np.errstate(over="raise", invalid="raise", divide="ignore", under="ignore"):
        if model == "exponential":
            return np.exp(np.log(v0) + r * t)
        k = parameters[2]
        if k <= 0 or r < 0:
            raise ValueError("Capacity must be positive and rate nonnegative")
        q = np.exp(-r * t)
        if model == "gompertz":
            return np.exp(np.log(k) + (np.log(v0) - np.log(k)) * q)
        # 1-q + (K/V0)q avoids cancellation when K < V0.
        log_denom = np.logaddexp(np.log(-np.expm1(-r * t)), np.log(k/v0) - r*t)
        return np.exp(np.log(k) - log_denom)


def jacobian(model: str, tau: np.ndarray, parameters: np.ndarray) -> np.ndarray:
    t = np.asarray(tau, dtype=float)
    v = curve(model, t, parameters)
    v0, r = parameters[:2]
    if model == "exponential":
        return np.column_stack([v/v0, t*v])
    k = parameters[2]
    q = np.exp(-r*t)
    if model == "gompertz":
        return np.column_stack([v*q/v0, -t*(np.log(v0)-np.log(k))*q*v, v*(1-q)/k])
    w = (v/v0)*q
    return np.column_stack([v*w/v0, t*v*(1-v/k), v*(1-w)/k])


@dataclass
class FitResult:
    model: str
    success: bool
    status: str
    t_start: float
    last_volume: float
    parameters: list[float] = field(default_factory=list)
    message: str = ""
    cost: float | None = None
    nfev: int = 0
    elapsed_seconds: float = 0.
    selected_start: int | None = None
    near_bound: bool = False
    ill_conditioned: bool = False
    jacobian_condition: float | None = None
    singular_values: list[float] = field(default_factory=list)
    starts: list[dict] = field(default_factory=list)

    def predict(self, days: np.ndarray) -> np.ndarray:
        days = np.asarray(days, dtype=float)
        if not np.isfinite(days).all() or (days < self.t_start).any():
            raise ValueError("Prediction dates must be finite and follow context start")
        if not self.success:
            return np.full(days.shape, np.nan)
        if self.model == "persistence":
            return np.full(days.shape, self.last_volume)
        try:
            result = curve(self.model, days-self.t_start, np.asarray(self.parameters))
            return np.where(np.isfinite(result) & (result >= 0), result, np.nan)
        except (FloatingPointError, ValueError):
            # Evaluate separately so one overflowing horizon does not erase others.
            result = np.full(days.shape, np.nan)
            for index in np.ndindex(days.shape):
                try:
                    result[index] = curve(self.model, np.array([days[index]-self.t_start]),
                                          np.asarray(self.parameters))[0]
                except (FloatingPointError, ValueError):
                    pass
            return result

    def record(self) -> dict:
        return asdict(self)


def fit_model(model: str, days: np.ndarray, volumes: np.ndarray,
              options: dict | None = None) -> FitResult:
    """Only explicit prefix arrays enter the fitter; no future values or covariates."""
    if model not in MODELS:
        raise ValueError(f"Unknown model: {model}")
    days, y = np.asarray(days, float), np.asarray(volumes, float)
    if (days.ndim != 1 or y.shape != days.shape or not len(days)
            or not np.isfinite(days).all() or not np.isfinite(y).all()
            or (y < 0).any() or (np.diff(days) <= 0).any()):
        raise ValueError("Context requires ordered unique dates and finite nonnegative volumes")
    cfg = DEFAULTS | (options or {})
    result = FitResult(model, False, "fit_failed", float(days[0]), float(y[-1]))
    start_time = perf_counter()
    if model == "persistence":
        result.success, result.status = True, "ok"
        return result
    npar = 2 if model == "exponential" else 3
    if len(days) < npar or not (y > 0).any():
        result.status = "insufficient_context" if len(days) < npar else "all_zero_unidentifiable"
        return result
    tau = days-days[0]
    s = max(float(np.median(y[y > 0])), 1.)
    upper_v = cfg["volume_upper_factor"] * max(float(y.max()), 1.)
    low = np.array([cfg["volume_lower"], -cfg["rate_bound"] if npar == 2 else 0.]
                   + ([] if npar == 2 else [cfg["volume_lower"]]))
    high = np.array([upper_v, cfg["rate_bound"]] + ([] if npar == 2 else [upper_v]))
    initial_v = float(y[y > 0][0])
    starts = ([np.array([initial_v, r]) for r in cfg["exponential_starts"]] if npar == 2
              else [np.array([initial_v, r, factor*y.max()]) for r, factor in
                    product(cfg["rate_starts"], cfg["capacity_factors"])])
    best = None
    for index, initial in enumerate(starts):
        initial = np.clip(initial, np.nextafter(low, high), np.nextafter(high, low))
        try:
            fit = least_squares(lambda p: (curve(model, tau, p)-y)/s, initial,
                                jac=lambda p: jacobian(model, tau, p)/s,
                                bounds=(low, high), method="trf", loss="linear", x_scale="jac",
                                max_nfev=cfg["max_nfev"], ftol=cfg["tolerance"],
                                xtol=cfg["tolerance"], gtol=cfg["tolerance"])
            valid = bool(fit.success and np.isfinite(fit.cost) and np.isfinite(fit.x).all())
            result.nfev += int(fit.nfev)
            result.starts.append(dict(index=index, success=valid, nfev=int(fit.nfev),
                                      status=int(fit.status), message=str(fit.message),
                                      cost=float(fit.cost) if np.isfinite(fit.cost) else None))
            if valid and (best is None or fit.cost < best.cost):
                best, result.selected_start = fit, index
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
            result.starts.append(dict(index=index, success=False, message=str(error)))
    result.elapsed_seconds = perf_counter()-start_time
    if best is not None:
        result.success, result.status = True, "ok"
        result.parameters, result.cost = best.x.tolist(), float(best.cost)
        result.message = str(best.message)
        distance = np.minimum((best.x-low)/(high-low), (high-best.x)/(high-low))
        result.near_bound = bool((distance < cfg["boundary_threshold"]).any())
        sv = np.linalg.svd(best.jac*(high-low)[None, :], compute_uv=False)
        result.singular_values = sv.tolist()
        condition = float(sv[0]/sv[-1]) if sv[-1] > 0 else float("inf")
        result.jacobian_condition = condition if np.isfinite(condition) else None
        result.ill_conditioned = bool(not np.isfinite(condition) or
                                      condition > cfg["condition_threshold"] or
                                      np.linalg.matrix_rank(best.jac*(high-low)[None, :]) < npar)
    return result
