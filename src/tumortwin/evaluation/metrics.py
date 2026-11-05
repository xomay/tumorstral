"""Animal-weighted scores on explicit supports, paired cluster bootstrap."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..baselines import MODELS
from ..data.inspectumours import IDENTITY

KEY = ["origin_id", "horizon_days"]
GROUP = [*IDENTITY, "horizon_days", "model"]


def valid_forecasts(frame: pd.DataFrame) -> pd.Series:
    """Raw negative Timestral medians remain scored, with separate domain warnings."""
    return (frame.fit_success & np.isfinite(frame.prediction)
            & (frame.model.eq("timestral") | frame.prediction.ge(0)))


def supports(joined: pd.DataFrame, horizons: list[int],
             models: tuple[str, ...] = MODELS) -> dict[str, pd.DataFrame]:
    if set(joined.model) != set(models):
        raise ValueError("Forecast registry does not contain the expected models")
    if joined.duplicated(KEY+["model"]).any():
        raise ValueError("Duplicate model forecasts on the same origin and horizon")
    scored = joined.loc[(joined.target_status == "observed") & (joined.origin_status == "ok")].copy()
    scored["valid_prediction"] = valid_forecasts(scored)
    common_keys = (scored.groupby(KEY).agg(valid=("valid_prediction", "all"), n=("model", "nunique"))
                   .loc[lambda s: s.valid & s.n.eq(len(models))].reset_index()[KEY])
    common = scored.merge(common_keys, on=KEY, how="inner", validate="many_to_one")
    fallback = scored.copy()
    fallback["used_fallback"] = ~fallback.valid_prediction
    fallback["prediction"] = fallback.prediction.where(fallback.valid_prediction, fallback.last_volume)
    complete = common.groupby("origin_id").horizon_days.nunique()
    complete = complete[complete == len(horizons)].index
    short = common.loc[common.analysis.str.startswith("short_")]
    # Cohort intersection is defined per horizon across all three context lengths.
    short_count = short.groupby(IDENTITY+["horizon_days"]).analysis.nunique()
    short_keys = short_count[short_count == 3].reset_index()[IDENTITY+["horizon_days"]]
    return dict(native=scored.loc[scored.valid_prediction].copy(), common=common,
                fallback=fallback, common_horizons=common.loc[common.origin_id.isin(complete)].copy(),
                short_matched=short.merge(short_keys, on=IDENTITY+["horizon_days"], how="inner"))


def animal_scores(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=GROUP+["mae", "mse", "bias", "median_relative", "n_pairs",
                                          "n_positive", "n_fallback"])
    frame = frame.copy()
    error = frame.prediction-frame.target_volume
    frame["absolute"] = error.abs()
    with np.errstate(over="ignore", invalid="ignore"):
        frame["squared"] = error**2
    frame["signed"] = error
    frame["relative"] = frame.absolute / frame.target_volume.where(frame.target_volume > 0)
    frame["positive"] = frame.target_volume.gt(0).astype(int)
    if "used_fallback" not in frame:
        frame["used_fallback"] = False
    return frame.groupby(GROUP, sort=True).agg(
        mae=("absolute", "mean"), mse=("squared", "mean"), bias=("signed", "mean"),
        median_relative=("relative", "median"), n_pairs=("origin_id", "size"),
        n_positive=("positive", "sum"), n_fallback=("used_fallback", "sum")).reset_index()


def summarize(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    individual = animal_scores(frame)
    columns = ["horizon_days", "model", "n_animals", "n_pairs", "mae", "rmse", "bias",
               "median_relative", "positive_target_fraction", "fallback_fraction"]
    rows = []
    for (horizon, model), group in individual.groupby(["horizon_days", "model"], sort=True):
        rows.append(dict(horizon_days=horizon, model=model, n_animals=len(group),
                         n_pairs=int(group.n_pairs.sum()), mae=float(group.mae.mean()),
                         rmse=float(np.sqrt(group.mse.mean())), bias=float(group.bias.mean()),
                         median_relative=float(group.median_relative.median()),
                         positive_target_fraction=float(group.n_positive.sum()/group.n_pairs.sum()),
                         fallback_fraction=float(group.n_fallback.sum()/group.n_pairs.sum())))
    return pd.DataFrame(rows, columns=columns), individual


def paired_bootstrap(individual: pd.DataFrame, samples: int = 2000, seed: int = 20261103,
                     min_animals: int = 10, models: tuple[str, ...] = MODELS,
                     reference: str = "persistence") -> pd.DataFrame:
    """Use identical animal draws for all models, stratified by study; preserve all origins."""
    rows = []
    reference_index = models.index(reference)
    for horizon, group in individual.groupby("horizon_days", sort=True):
        wide = group.pivot(index=IDENTITY, columns="model", values="mae").reindex(columns=models).dropna()
        if wide.empty:
            continue
        data = wide.to_numpy()
        rng = np.random.default_rng(seed+int(horizon))
        strata = [np.flatnonzero(wide.index.get_level_values("study") == s)
                  for s in sorted(wide.index.get_level_values("study").unique())]
        boot = None
        if len(wide) >= min_animals and samples > 0:
            indices = np.concatenate([rng.choice(idx, size=(samples, len(idx)), replace=True)
                                      for idx in strata], axis=1)
            boot = data[indices].mean(axis=1)
        for j, model in enumerate(models):
            delta = float(np.mean(data[:, j]-data[:, reference_index]))
            baseline = float(data[:, reference_index].mean())
            rows.append(dict(horizon_days=horizon, model=model, n_animals=len(wide),
                delta_mae=delta, skill=1-float(data[:, j].mean())/baseline if baseline > 0 else np.nan,
                mae_low=float(np.quantile(boot[:, j], .025)) if boot is not None else np.nan,
                mae_high=float(np.quantile(boot[:, j], .975)) if boot is not None else np.nan,
                delta_low=float(np.quantile(boot[:, j]-boot[:, reference_index], .025)) if boot is not None else np.nan,
                delta_high=float(np.quantile(boot[:, j]-boot[:, reference_index], .975)) if boot is not None else np.nan))
    return pd.DataFrame(rows, columns=["horizon_days", "model", "n_animals", "delta_mae", "skill",
                                       "mae_low", "mae_high", "delta_low", "delta_high"])


def coverage(joined: pd.DataFrame) -> pd.DataFrame:
    """Counts include unavailable exact targets; fit and forecast failures stay visible."""
    df = joined.copy()
    df["scorable"] = (df.target_status == "observed") & (df.origin_status == "ok")
    df["valid"] = valid_forecasts(df)
    df["successful_scorable"] = df.scorable & df.valid
    result = df.groupby(["analysis", "horizon_days", "model"], sort=True).agg(
        n_forecasts=("origin_id", "size"), n_scorable=("scorable", "sum"),
        n_valid=("valid", "sum"), n_successful_scorable=("successful_scorable", "sum"),
        n_near_bound=("near_bound", "sum"), n_ill_conditioned=("ill_conditioned", "sum"))
    result["coverage"] = result.n_successful_scorable/result.n_scorable.replace(0, np.nan)
    negatives = df.assign(negative=df.prediction.lt(0)).groupby(["analysis", "horizon_days", "model"]).negative.sum()
    result["n_negative_predictions"] = negatives
    return result.reset_index()
