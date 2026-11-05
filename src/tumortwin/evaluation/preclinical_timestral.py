"""Optional, pinned Timestral inference on the existing INSPECTumours origins."""

from __future__ import annotations

import csv
from importlib import metadata
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from ..baselines import MODELS
from ..data.inspectumours import sha256
from ..timestral.adapter import ForecastResult, QUANTILE_LEVELS, TimestralAdapter
from ..timestral.download import CODE_REVISION, HASHES, MODEL_REVISION
from .design import Origin
from .probabilistic import quantile_scores


def enabled(cfg: dict) -> bool:
    return bool(cfg.get("timestral", {}).get("enabled", False))


def model_names(cfg: dict) -> tuple[str, ...]:
    return (*MODELS, "timestral") if enabled(cfg) else MODELS


def model_provenance(cfg: dict, root: Path) -> dict:
    """Verify local pinned bytes and installed code; never download during evaluation."""
    opt = cfg["timestral"]
    if opt["grid_step_days"] != 1. or not 1 <= opt["threads"] <= 32:
        raise ValueError("Preclinical Timestral requires a daily grid and 1–32 threads")
    if opt["model_revision"] != MODEL_REVISION:
        raise ValueError("Timestral model revision differs from the pinned protocol")
    directory = root/opt["local_model"]
    expected = dict(repository="mistralai/Timestral-5M", model_revision=MODEL_REVISION,
                    code_revision=CODE_REVISION, files=HASHES)
    if json.loads((directory/"provenance.json").read_text()) != expected:
        raise ValueError("Timestral model manifest differs from pinned artifacts")
    for name, checksum in HASHES.items():
        if sha256(directory/name) != checksum:
            raise ValueError(f"Timestral model artifact changed: {name}")
    try:
        distribution = metadata.distribution("timestral")
        direct = json.loads(distribution.read_text("direct_url.json") or "{}")
        versions = {name: metadata.version(name) for name in ["timestral", "torch"]}
    except metadata.PackageNotFoundError as error:
        raise ValueError("Install optional inference dependencies with uv sync --locked --extra timestral") from error
    if direct.get("vcs_info", {}).get("commit_id") != CODE_REVISION:
        raise ValueError("Installed Timestral code differs from pinned revision")
    return expected | dict(packages=versions, internal_forward_fill=True,
                           symmetric_averaging=True, clip_nonnegative=False, quantile_real_cap_k=0.,
                           zero_shot=True)


def load_adapter(cfg: dict, root: Path) -> TimestralAdapter:
    """Load verified local weights once per partition, independently of baseline workers."""
    import torch

    opt = cfg["timestral"]
    torch.set_num_threads(opt["threads"])
    torch.manual_seed(cfg["seed"])
    return TimestralAdapter.from_pretrained(opt["model_revision"],
        model=str(root/opt["local_model"]), local_files_only=True)


def forecast_origin(origin: Origin, cfg: dict, adapter: TimestralAdapter) -> tuple[list[dict], ForecastResult | None, dict]:
    """The only model inputs are prefix arrays and configured future dates, never truth."""
    target_days = origin.t0+np.asarray(cfg["horizons"], float)
    result = None
    diagnostic = origin.record() | dict(status="ineligible_prefix")
    if origin.status == "ok":
        try:
            result = adapter.forecast(origin.days, origin.volumes, target_days,
                                      step=cfg["timestral"]["grid_step_days"])
            diagnostic = origin.record() | result.diagnostics | dict(status="ok")
        except (ValueError, RuntimeError, FloatingPointError) as error:
            diagnostic = origin.record() | dict(status="failed", error=str(error))
    predictions = []
    for index, (horizon, day) in enumerate(zip(cfg["horizons"], target_days, strict=True)):
        value = float(result.median[index]) if result is not None else np.nan
        valid = bool(np.isfinite(value))
        predictions.append(origin.record() | dict(origin_status=origin.status, model="timestral",
            horizon_days=horizon, target_day=float(day), prediction=value,
            fit_success=valid, fit_status=diagnostic["status"],
            forecast_status="ok" if valid else "forecast_failed",
            last_volume=float(origin.volumes[-1]) if len(origin.volumes) else np.nan,
            near_bound=False, ill_conditioned=False,
            negative_prediction=bool(value < 0),
            valid_quantiles=bool(result.diagnostics["valid_quantiles"][index]) if result is not None else False))
    return predictions, result, diagnostic


def forecast_partition(origins: list[Origin], cfg: dict, root: Path,
                       folder: Path) -> tuple[list[dict], pd.DataFrame]:
    from .experiment import json_text

    adapter = load_adapter(cfg, root)
    predictions, quantiles, diagnostics = [], [], []
    with (folder/"grids.csv").open("x", newline="") as grid_stream, \
            (folder/"daily_quantiles.csv").open("x", newline="") as daily_stream:
        grid_writer, daily_writer = csv.writer(grid_stream), csv.writer(daily_stream)
        grid_writer.writerow(["origin_id", "day", "value", "observed"])
        daily_writer.writerow(["origin_id", "day"]+[f"q{q:g}" for q in QUANTILE_LEVELS])
        for index, origin in enumerate(origins, 1):
            records, result, diagnostic = forecast_origin(origin, cfg, adapter)
            predictions.extend(records)
            diagnostics.append(diagnostic)
            if result is not None:
                for day, value, mask in zip(result.context.times, result.context.values,
                                            result.context.observation_mask, strict=True):
                    grid_writer.writerow([origin.origin_id, day, value, bool(mask)])
                for day, values in zip(result.future_days, result.full_quantiles, strict=True):
                    daily_writer.writerow([origin.origin_id, day, *values])
                for day, values in zip(result.target_days, result.quantiles, strict=True):
                    quantiles.extend(dict(origin_id=origin.origin_id, target_day=float(day),
                        level=float(level), value=float(value), model="timestral")
                        for level, value in zip(result.quantile_levels, values, strict=True))
            if index % 25 == 0 or index == len(origins):
                print(f"{folder.name} Timestral: {index}/{len(origins)} origins", file=sys.stderr, flush=True)
    q = pd.DataFrame(quantiles, columns=["origin_id", "target_day", "level", "value", "model"])
    q.to_csv(folder/"quantiles.csv", index=False)
    (folder/"timestral_diagnostics.json").write_text(json_text(diagnostics), encoding="utf-8")
    return predictions, q


def export_quantile_scores(quantiles: pd.DataFrame, joined: pd.DataFrame, folder: Path) -> None:
    """Reuse the individual-weighted scorer, grouped by analysis and exact day horizon."""
    truth = joined.loc[(joined.model == "timestral") & (joined.origin_status == "ok"),
        ["origin_id", "target_day", "study", "animal_id", "analysis", "horizon_days", "target_volume"]]
    # The generic scorer uses human column names; analysis identifies the main/short cohorts here.
    truth = truth.rename(columns={"analysis": "n_context", "horizon_days": "horizon"})
    scores, levels = quantile_scores(quantiles, truth)
    names = {"n_context": "analysis", "horizon": "horizon_days", "n_patients": "n_animals"}
    score_columns = ["analysis", "horizon_days", "nominal", "n_animals", "n_pairs", "pinball",
                     "interval_coverage", "mean_width", "negative_quantile_fraction"]
    scores.rename(columns=names).reindex(columns=score_columns).to_csv(folder/"probabilistic_scores.csv", index=False)
    levels.rename(columns=names).to_csv(folder/"pinball_by_level.csv", index=False)
