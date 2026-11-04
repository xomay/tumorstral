"""Patient-weighted point and quantile scores on explicit common supports."""

from __future__ import annotations

import numpy as np
import pandas as pd

PATIENT = ["study", "animal_id"]
PAIR = ["origin_id", "target_day"]


def point_scores(predictions: pd.DataFrame, expected_models: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep negative finite raw forecasts in scores; report them as domain warnings."""
    frame = predictions.copy()
    frame["valid"] = np.isfinite(frame.prediction) & frame.target_volume.notna() & frame.fit_success
    rows, individuals = [], []
    for (context, horizon), group in frame.groupby(["n_context", "horizon"], sort=True):
        valid_keys = (group.groupby(PAIR).agg(n_models=("model", "nunique"), valid=("valid", "all"))
                      .loc[lambda d: d.valid & d.n_models.eq(len(expected_models))].reset_index()[PAIR])
        common = group.merge(valid_keys, on=PAIR, how="inner")
        for model in expected_models:
            own = group.loc[group.model == model]
            denominator = int(own.target_volume.notna().sum())
            for support, subset in [("common", common.loc[common.model == model]),
                                     ("native", own.loc[own.valid])]:
                subset = subset.copy()
                error = subset.prediction-subset.target_volume
                subset["absolute_error"] = error.abs()
                subset["squared_error"] = error**2
                subset["signed_error"] = error
                subset["relative_error"] = error.abs()/subset.target_volume.where(subset.target_volume > 0)
                by_patient = subset.groupby(PATIENT).agg(
                    mae=("absolute_error", "mean"), mse=("squared_error", "mean"),
                    bias=("signed_error", "mean"), relative=("relative_error", "median"),
                    n_pairs=("origin_id", "size")).reset_index()
                by_patient = by_patient.assign(model=model, n_context=context, horizon=horizon, support=support)
                individuals.append(by_patient)
                rows.append(dict(model=model, n_context=context, horizon=horizon, support=support,
                    n_patients=len(by_patient), n_pairs=len(subset), n_available=denominator,
                    coverage=float(own.valid.sum()/denominator) if denominator else np.nan,
                    common_fraction=len(subset)/denominator if denominator and support == "common" else np.nan,
                    mae=float(by_patient.mae.mean()), rmse=float(np.sqrt(by_patient.mse.mean())),
                    bias=float(by_patient.bias.mean()), median_relative=float(by_patient.relative.median()),
                    negative_predictions=int(own.prediction.lt(0).sum())))
    return pd.DataFrame(rows), pd.concat(individuals, ignore_index=True) if individuals else pd.DataFrame()


def quantile_scores(quantiles: pd.DataFrame, truth: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pinball averaged over levels, then origins per patient, then patients."""
    joined = quantiles.merge(truth[PAIR+PATIENT+["n_context", "horizon", "target_volume"]].drop_duplicates(),
                             on=PAIR, how="left", validate="many_to_one")
    joined["level"] = joined.level.round(6)
    joined = joined.sort_values(PAIR+["level"])
    valid_cases = joined.groupby(PAIR).value.agg(
        lambda v: len(v) == 21 and np.isfinite(v).all() and (np.diff(v.to_numpy()) >= 0).all())
    keys = valid_cases[valid_cases].reset_index()[PAIR]
    joined = joined.merge(keys, on=PAIR, how="inner")
    joined = joined.loc[joined.target_volume.notna()].copy()
    error = joined.target_volume-joined.value
    joined["pinball"] = np.maximum(joined.level*error, (joined.level-1)*error)
    by_level = joined.groupby(["n_context", "horizon", "level", *PATIENT]).pinball.mean().reset_index()
    per_level = by_level.groupby(["n_context", "horizon", "level"]).agg(
        pinball=("pinball", "mean"), n_patients=("animal_id", "size")).reset_index()
    rows = []
    for (context, horizon), group in joined.groupby(["n_context", "horizon"]):
        cases = group.pivot(index=PAIR+PATIENT+["target_volume"], columns="level", values="value")
        for low, high in [(.1, .9), (.05, .95)]:
            if low not in cases or high not in cases:
                continue
            subset = cases[[low, high]].dropna().reset_index()
            subset["covered"] = subset.target_volume.ge(subset[low]) & subset.target_volume.le(subset[high])
            subset["width"] = subset[high]-subset[low]
            individual = subset.groupby(PATIENT).agg(coverage=("covered", "mean"), width=("width", "mean"))
            pin = group.groupby(PATIENT).pinball.mean()
            rows.append(dict(n_context=context, horizon=horizon, nominal=high-low,
                n_patients=len(individual), n_pairs=len(subset), pinball=float(pin.mean()),
                interval_coverage=float(individual.coverage.mean()), mean_width=float(individual.width.mean()),
                negative_quantile_fraction=float(group.value.lt(0).mean())))
    return pd.DataFrame(rows), per_level


def paired_patient_bootstrap(individual: pd.DataFrame, samples: int, seed: int,
                             minimum: int = 10) -> pd.DataFrame:
    records = []
    for (context, horizon), group in individual.loc[individual.support == "common"].groupby(["n_context", "horizon"]):
        wide = group.pivot(index=PATIENT, columns="model", values="mae").dropna()
        if "persistence" not in wide or wide.empty:
            continue
        rng = np.random.default_rng(seed+100*int(context)+int(horizon))
        studies = wide.index.get_level_values("study")
        draws = None
        if len(wide) >= minimum:
            draws = np.concatenate([rng.choice(np.flatnonzero(studies == s),
                                    size=(samples, int((studies == s).sum())), replace=True)
                                    for s in sorted(set(studies))], axis=1)
        for model in wide:
            delta = (wide[model]-wide.persistence).to_numpy()
            boot = delta[draws].mean(axis=1) if draws is not None else None
            records.append(dict(n_context=context, horizon=horizon, model=model, n_patients=len(wide),
                                delta_mae=float(delta.mean()),
                                lower=float(np.quantile(boot,.025)) if boot is not None else np.nan,
                                upper=float(np.quantile(boot,.975)) if boot is not None else np.nan))
    return pd.DataFrame(records)
