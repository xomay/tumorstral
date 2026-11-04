"""Laleh patient holdouts, chronological landmarks and zero-shot comparison."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from importlib import metadata
from pathlib import Path
import json
import csv
import subprocess
import sys
import tomllib

import numpy as np
import pandas as pd

from ..baselines import MODELS, fit_model
from ..data.inspectumours import sha256
from ..data.quality import normalize
from .design import digest
from .experiment import immutable, json_text, verify_stage
from .probabilistic import point_scores, quantile_scores, paired_patient_bootstrap


def patient_split(frame: pd.DataFrame, seed: int, fraction: float) -> pd.DataFrame:
    """Exclude reused anonymous IDs across studies rather than invent patient links."""
    normalized = normalize(frame)
    identities = normalized[["study", "animal_id", "treatment"]].drop_duplicates()
    if identities.isna().any().any():
        raise ValueError("Patient metadata missing")
    if identities.groupby(["study", "animal_id"]).size().gt(1).any():
        raise ValueError("Patient treatment conflict")
    cross = identities.groupby("animal_id").study.nunique()
    ambiguous = set(cross[cross > 1].index)
    identities["allocation_hash"] = [digest([seed, str(i)]) for i in identities.animal_id]
    identities["partition"] = "development"
    for _, group in identities.loc[~identities.animal_id.isin(ambiguous)].groupby(["study", "treatment"]):
        ordered = group.sort_values("allocation_hash")
        ntest = int(np.floor(fraction*len(ordered)))
        identities.loc[ordered.index[:ntest], "partition"] = "test"
    identities.loc[identities.animal_id.isin(ambiguous), "partition"] = "excluded_ambiguous_identity"
    return identities.sort_values(["study", "animal_id"]).reset_index(drop=True)


def landmarks(frame: pd.DataFrame, contexts: list[int], horizons: list[int]) -> tuple[list[dict], pd.DataFrame]:
    """Use first k usable observations; evaluation query dates contain no future volumes."""
    frame = frame.reset_index(drop=True)
    normalized = normalize(frame)
    jobs, truth = [], []
    for (study, patient), rows in normalized.groupby(["study", "animal_id"], sort=True):
        days = sorted(rows.day.dropna().unique())
        for context in contexts:
            selected = None
            for t0 in days:
                indices = rows.index[rows.day.le(t0)]
                prefix = normalize(frame.loc[indices].reset_index(drop=True))
                valid = prefix.loc[prefix.analysis_eligible].sort_values("day")
                if prefix.metadata_conflict.any():
                    break
                if len(valid) == context and valid.day.iloc[-1] == t0:
                    selected = valid
                    break
                if len(valid) > context:
                    break
            if selected is None:
                continue
            origin_id = digest([str(study), str(patient), context, float(t0)])[:24]
            base = dict(study=str(study), animal_id=str(patient), patient_id=str(patient),
                        treatment=str(selected.treatment.iloc[0]), origin_id=origin_id,
                        t0=float(t0), n_context=context,
                        context_duration=float(np.ptp(selected.day)),
                        days=selected.day.to_numpy(float), volumes=selected.tumour_volume.to_numpy(float))
            # Retain every later dated visit; an invalid visit is not silently skipped.
            later = [d for d in days if d > t0]
            requests = []
            for horizon in horizons:
                if len(later) < horizon:
                    truth.append({k: v for k, v in base.items() if k not in {"days", "volumes"}} |
                                 dict(horizon=horizon, target_day=np.nan, target_volume=np.nan,
                                      target_status="no_followup_visit"))
                    continue
                day = later[horizon-1]
                local = normalize(frame.loc[rows.index[rows.day.eq(day)]].reset_index(drop=True))
                ok = len(local) == 1 and bool(local.analysis_eligible.iloc[0])
                requests.append(dict(horizon=horizon, target_day=float(day), elapsed_days=float(day-t0)))
                truth.append({k: v for k, v in base.items() if k not in {"days", "volumes"}} |
                             dict(horizon=horizon, target_day=float(day),
                                  target_volume=float(local.tumour_volume.iloc[0]) if ok else np.nan,
                                  target_status="observed" if ok else "invalid_target"))
            if requests:
                jobs.append(base | dict(requests=requests))
    return jobs, pd.DataFrame(truth)


def baseline_job(job: dict, cfg: dict) -> tuple[list[dict], list[dict]]:
    """Prefix-only scale improves conditioning without global normalization."""
    days, y = job["days"], job["volumes"]
    positive = y[y > 0]
    scale = float(np.median(positive)) if len(positive) else 1.
    time_scale = cfg["baseline_time_scale_days"]
    times = (days-days[0])/time_scale
    queries = np.array([r["target_day"] for r in job["requests"]])
    base = {k: v for k, v in job.items() if k not in {"days", "volumes", "requests"}}
    records, fits = [], []
    for model in MODELS:
        fitted = fit_model(model, times, y/scale, cfg["fit"])
        forecasts = fitted.predict((queries-days[0])/time_scale)*scale
        fits.append(base | fitted.record() | dict(prefix_volume_scale=scale, time_scale_days=time_scale,
                                                  parameter_volume_unit="prefix-relative",
                                                  parameter_rate_unit=f"per {time_scale} days"))
        for request, value in zip(job["requests"], forecasts, strict=True):
            records.append(base | request | dict(model=model, prediction=float(value),
                fit_success=fitted.success, near_bound=fitted.near_bound,
                ill_conditioned=fitted.ill_conditioned))
    return records, fits


def design(config: Path) -> tuple[dict, Path, pd.DataFrame, dict, pd.DataFrame]:
    from ..data.laleh import load_laleh

    cfg = tomllib.loads(config.read_text())
    root = (config.resolve().parent/cfg["project_root"]).resolve()
    if not 0 < cfg["test_fraction"] < 1 or min(cfg["contexts"]) < 3:
        raise ValueError("Invalid patient split or contexts")
    source = root/cfg["input"]
    frame, data_metadata = load_laleh(source)
    try:
        commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        dirty = bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True))
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = "unversioned", True
    src = Path(__file__).resolve().parents[1]
    code_sha = digest({str(p.relative_to(src)): sha256(p) for p in sorted(src.rglob("*"))
                       if p.is_file() and p.suffix in {".py", ".md"}})
    versions = {name: metadata.version(name) for name in ["numpy", "pandas", "scipy", "openpyxl"]}
    if cfg["timestral"]["enabled"]:
        try:
            versions |= {name: metadata.version(name) for name in ["torch", "timestral"]}
        except metadata.PackageNotFoundError as error:
            raise ValueError("Install the inference dependencies with uv sync --locked --extra timestral") from error
        from ..timestral.download import download_model, CODE_REVISION

        model_directory = root/cfg["timestral"]["local_model"]
        # Verify pinned bytes before any expensive patient fits. No network if cached.
        download_model(model_directory)
        direct = json.loads(metadata.distribution("timestral").read_text("direct_url.json") or "{}")
        if direct.get("vcs_info", {}).get("commit_id") != CODE_REVISION:
            raise ValueError("Installed Timestral code differs from pinned revision; sync the locked extra")
        model_provenance = json.loads((model_directory/"provenance.json").read_text())
    else:
        model_provenance, direct = None, None
    provenance = dict(source_sha256=sha256(source), source_metadata=data_metadata, configuration=cfg,
                      code_sha256=code_sha, protocol_sha256=sha256(root/cfg["protocol"]),
                      lock_sha256=sha256(root/"uv.lock"), git_commit=commit, dirty=dirty, packages=versions,
                      model_provenance=model_provenance, timestral_installation=direct)
    run = root/cfg["output"]/digest(provenance)[:20]
    if source.resolve().is_relative_to((root/cfg["output"]).resolve()):
        raise ValueError("Outputs must not contain source data")
    run.mkdir(parents=True, exist_ok=True)
    split = patient_split(frame, cfg["seed"], cfg["test_fraction"])
    immutable(run/"provenance.json", json_text(provenance))
    immutable(run/"split.csv", split.to_csv(index=False))
    immutable(run/"protocol.md", (root/cfg["protocol"]).read_text().replace("../src/tumortwin/glossary.md", "glossary.md"))
    chosen = split.loc[split.partition.isin(["test", "development"])].sort_values("allocation_hash")
    examples = chosen.groupby(["partition", "study", "treatment"], sort=True).head(1)
    immutable(run/"examples.csv", examples.to_csv(index=False))
    quality = normalize(frame)
    quality.to_csv(run/"observations.csv", index=False)
    audit = dict(n_source_rows=len(frame), n_study_patient_pairs=len(split),
                 partitions=split.partition.value_counts().to_dict(),
                 flags={c: int(quality[c].sum()) for c in quality if c.startswith(("missing_", "invalid_"))
                        or c in {"duplicate_time", "negative_volume"}},
                 metadata=data_metadata)
    immutable(run/"audit.json", json_text(audit))
    return cfg, run, frame, provenance, split


def freeze_human(config: Path, check: bool = False) -> Path:
    cfg, run, _, provenance, _ = design(config)
    development = verify_stage(run/"development")
    if provenance["dirty"]:
        raise ValueError("Commit source changes before freezing the experiment")
    if check and not (run/"freeze.json").exists():
        raise ValueError("Development must be frozen before test")
    immutable(run/"freeze.json", json_text(dict(provenance=sha256(run/"provenance.json"),
                  split=sha256(run/"split.csv"), development=digest(development))))
    return run/"freeze.json"


def run_human(config: Path, partition: str) -> Path:
    cfg, run, frame, provenance, split = design(config)
    if partition not in {"development", "test"}:
        raise ValueError("Unknown patient partition")
    if partition == "test":
        freeze_human(config, check=True)
    output = run/partition
    if output.exists():
        verify_stage(output)
        return output
    chosen = split.loc[split.partition == partition]
    # Development pilot is predetermined by hashes, never chosen using target values.
    if partition == "development" and cfg.get("development_patients", 0):
        chosen = chosen.sort_values("allocation_hash").head(cfg["development_patients"])
    normalized = normalize(frame)
    mask = normalized[["study", "animal_id"]].merge(chosen[["study", "animal_id"]].assign(selected=True),
                how="left", on=["study", "animal_id"]).selected.fillna(False).to_numpy(bool)
    subset = frame.loc[mask].reset_index(drop=True)
    jobs, truth = landmarks(subset, cfg["contexts"], cfg["horizons"])
    if not jobs:
        raise ValueError("No human forecast contexts")
    output.mkdir()
    ledger = pd.DataFrame([{k:v for k,v in j.items() if k not in {"days", "volumes", "requests"}} for j in jobs])
    ledger.to_csv(output/"origins.csv", index=False)
    predictions, fits = [], []
    if cfg["workers"] > 1:
        with ProcessPoolExecutor(max_workers=cfg["workers"]) as pool:
            batches = pool.map(baseline_job, jobs, [cfg]*len(jobs))
            for i, (records, diagnostics) in enumerate(batches, 1):
                predictions.extend(records); fits.extend(diagnostics)
                if i % 25 == 0:
                    print(f"{partition} baselines: {i}/{len(jobs)}", file=sys.stderr, flush=True)
    else:
        for job in jobs:
            records, diagnostics = baseline_job(job, cfg)
            predictions.extend(records); fits.extend(diagnostics)
    (output/"fits.json").write_text(json_text(fits))
    quantiles, grids, timestral_diagnostics = [], [], []
    models = list(MODELS)
    if cfg["timestral"]["enabled"]:
        from ..timestral.adapter import TimestralAdapter

        opt = cfg["timestral"]
        root = (config.resolve().parent/cfg["project_root"]).resolve()
        model_path = root/opt["local_model"]
        # Every local model artifact must match its pinned-download manifest.
        manifest = json.loads((model_path/"provenance.json").read_text())
        if manifest["model_revision"] != opt["model_revision"]:
            raise ValueError("Model revision differs from pinned manifest")
        for name, expected in manifest["files"].items():
            if sha256(model_path/name) != expected:
                raise ValueError(f"Model artifact changed: {name}")
        import torch

        torch.set_num_threads(opt["threads"])
        torch.manual_seed(cfg["seed"])
        adapter = TimestralAdapter.from_pretrained(opt["model_revision"], model=str(model_path),
                                                  local_files_only=True)
        models.append("timestral")
        daily_stream = (output/"daily_quantiles.csv").open("x", newline="")
        daily_writer = csv.writer(daily_stream)
        daily_writer.writerow(["origin_id", "day"]+[f"q{level:g}" for level in
                               [.01, .05, *[i/100 for i in range(10, 91, 5)], .95, .99]])
        for i, job in enumerate(jobs, 1):
            base = {k:v for k,v in job.items() if k not in {"days", "volumes", "requests"}}
            queries = np.array([r["target_day"] for r in job["requests"]])
            try:
                result = adapter.forecast(job["days"], job["volumes"], queries, step=opt["grid_step_days"])
                for request, median, values, valid in zip(job["requests"], result.median, result.quantiles,
                                                         result.diagnostics["valid_quantiles"], strict=True):
                    predictions.append(base | request | dict(model="timestral", prediction=float(median), fit_success=bool(valid)))
                    for level, value in zip(result.quantile_levels, values, strict=True):
                        quantiles.append(dict(origin_id=job["origin_id"], target_day=request["target_day"],
                                              level=float(level), value=float(value), model="timestral"))
                grids.extend(dict(origin_id=job["origin_id"], day=float(day), value=float(value), observed=bool(mask))
                             for day, value, mask in zip(result.context.times, result.context.values,
                                                        result.context.observation_mask, strict=True))
                timestral_diagnostics.append(base | dict(status="ok", **result.diagnostics))
                for day, values in zip(result.future_days, result.full_quantiles, strict=True):
                    daily_writer.writerow([job["origin_id"], day, *values])
            except (ValueError, RuntimeError, FloatingPointError) as error:
                for request in job["requests"]:
                    predictions.append(base | request | dict(model="timestral", prediction=np.nan, fit_success=False))
                timestral_diagnostics.append(base | dict(status="failed", error=str(error)))
            if i % 25 == 0 or i == len(jobs):
                print(f"{partition} Timestral: {i}/{len(jobs)}", file=sys.stderr, flush=True)
        daily_stream.close()
    point = pd.DataFrame(predictions)
    point.to_csv(output/"predictions.csv", index=False)  # No future target volumes in this artifact.
    q = pd.DataFrame(quantiles, columns=["origin_id", "target_day", "level", "value", "model"])
    q.to_csv(output/"quantiles.csv", index=False)
    pd.DataFrame(grids).to_csv(output/"grids.csv", index=False)
    (output/"timestral_diagnostics.json").write_text(json_text(timestral_diagnostics))
    truth.to_csv(output/"targets.csv", index=False)
    joined = point.merge(truth[["origin_id", "target_day", "target_volume", "target_status"]],
                         on=["origin_id", "target_day"], how="left", validate="many_to_one")
    joined.to_csv(output/"scored_predictions.csv", index=False)
    scores, individual = point_scores(joined, models)
    scores.to_csv(output/"point_scores.csv", index=False)
    individual.to_csv(output/"patient_scores.csv", index=False)
    paired_patient_bootstrap(individual, cfg["bootstrap_samples"], cfg["seed"]).to_csv(
        output/"paired_bootstrap.csv", index=False)
    if not q.empty:
        probability, levels = quantile_scores(q, truth.loc[truth.target_day.notna()])
        probability.to_csv(output/"probabilistic_scores.csv", index=False)
        levels.to_csv(output/"pinball_by_level.csv", index=False)
    from .human_report import write_human_report

    primary = joined.loc[joined.n_context == cfg["primary_context"]]
    primary_ids = set(primary.origin_id)
    report_metadata = dict(volume_label="Volume estimé de la lésion cible (mm³)",
                           time_label="Jour relatif au traitement", horizon_label="Visite suivante",
                           partition=partition, n_patients=len(chosen),
                           limitations=["Volume proxy calculé par 0,5 × diamètre³ ; pas de segmentation volumétrique.",
                             "Dates réelles conservées ; horizons en visites, avec délais variables.",
                             "Les cas non évaluables et trop petits pour être mesurés ne valent pas zéro.",
                             "Les identifiants anonymes répétés entre études sont exclus du test.",
                             "Le préentraînement de Timestral peut avoir inclus des données publiques apparentées ; absence de recouvrement non démontrée."])
    examples = pd.read_csv(run/"examples.csv", dtype=str)
    plotted_observations = normalize(subset)
    plotted_observations["tumour_volume"] = plotted_observations.tumour_volume.where(plotted_observations.analysis_eligible)
    write_human_report(primary, q.loc[q.origin_id.isin(primary_ids)], plotted_observations,
                       scores.loc[scores.n_context == cfg["primary_context"]], output,
                       report_metadata, examples.loc[examples.partition == partition])
    artifacts = {str(p.relative_to(output)): sha256(p) for p in sorted(output.rglob("*")) if p.is_file()}
    immutable(output/"complete.json", json_text(dict(partition=partition, n_patients=len(chosen),
                                                    n_origins=len(jobs), artifacts=artifacts)))
    return output
