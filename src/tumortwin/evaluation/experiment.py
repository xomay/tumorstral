"""Separate development, explicit freeze and final test, with immutable manifests."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from importlib import metadata
from importlib.resources import files
import json
from pathlib import Path
import platform
import subprocess
import sys
import tomllib

import numpy as np
import pandas as pd

from ..baselines import MODELS, FitResult, fit_model
from ..data.inspectumours import IDENTITY, load_raw, sha256
from .design import Origin, build_origins, digest, join_targets, make_split, target_registry
from .metrics import coverage, paired_bootstrap, summarize, supports


def clean(value: object) -> object:
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def json_text(value: object) -> str:
    return json.dumps(clean(value), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+"\n"


def immutable(path: Path, content: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError(f"Immutable artifact differs: {path}")
        return
    with path.open("x", encoding="utf-8") as stream:
        stream.write(content)


def verify_stage(folder: Path) -> dict:
    marker = folder / "complete.json"
    if not marker.exists():
        raise ValueError(f"Stage incomplete: {folder}. Preserve it for audit; use a new output root to retry.")
    record = json.loads(marker.read_text())
    for name, expected in record["artifacts"].items():
        if not (folder/name).exists() or sha256(folder/name) != expected:
            raise ValueError(f"Stage artifact changed: {folder/name}")
    return record


def load_experiment(config_path: Path) -> tuple[dict, Path, Path, pd.DataFrame, dict]:
    with config_path.open("rb") as stream:
        cfg = tomllib.load(stream)
    root = (config_path.resolve().parent/cfg.get("project_root", "..")).resolve()
    source = (root/cfg["input"]).resolve()
    output = (root/cfg["output"]).resolve()
    if source.is_relative_to(output):
        raise ValueError("Output directory must not contain the source data")
    if cfg["horizons"] != [3, 7, 14] or cfg["primary_horizon"] != 7 or cfg["short_histories"] != [3, 4, 5]:
        raise ValueError("This preclinical protocol requires horizons 3/7/14 and short contexts 3/4/5")
    if not 1 <= cfg["workers"] <= 32 or cfg["min_history"] < 3:
        raise ValueError("Invalid workers or context size")
    source_hash = sha256(source)
    manifest = source.parent/"provenance.json"
    upstream = None
    if manifest.exists():
        upstream = json.loads(manifest.read_text())
        matches = [f for f in upstream.get("files", []) if f["file"] == source.name]
        if not matches or matches[0]["sha256"] != source_hash:
            raise ValueError("Source checksum differs from upstream manifest")
    protocol = root/cfg["protocol"]
    src = Path(__file__).resolve().parents[1]
    code = {str(p.relative_to(src)): sha256(p) for p in sorted(src.rglob("*"))
            if p.is_file() and p.suffix in {".py", ".md"}}
    lock = root/"uv.lock"
    if lock.exists():
        code["uv.lock"] = sha256(lock)
    try:
        commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                         text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True))
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = "unversioned", True
    provenance = dict(source_sha256=source_hash, upstream=upstream, config=cfg,
                      config_sha256=digest(cfg), protocol_sha256=sha256(protocol),
                      code_sha256=digest(code), git_commit=commit, working_tree_dirty=dirty,
                      python=platform.python_version(),
                      packages={p: metadata.version(p) for p in
                                ["tumortwin", "numpy", "pandas", "scipy", "matplotlib"]})
    identity = {k: provenance[k] for k in ["source_sha256", "config_sha256", "protocol_sha256",
                                         "code_sha256", "git_commit", "working_tree_dirty", "packages", "python"]}
    run = output/digest(identity)[:20]
    raw = load_raw(source).reset_index(drop=True)
    raw["_source_row"] = np.arange(1, len(raw)+1)
    return cfg, root, run, raw, provenance


def prepare(config_path: Path) -> tuple[dict, Path, pd.DataFrame, pd.DataFrame, dict]:
    cfg, root, run, raw, provenance = load_experiment(config_path)
    run.mkdir(parents=True, exist_ok=True)
    split = make_split(raw, cfg["seed"], cfg["test_fraction"])
    immutable(run/"split.csv", split.to_csv(index=False))
    immutable(run/"provenance.json", json_text(provenance))
    immutable(run/"protocol.md", (root/cfg["protocol"]).read_text(encoding="utf-8").replace(
        "../src/tumortwin/glossary.md", "glossary.md"))
    immutable(run/"config.toml", config_path.read_text(encoding="utf-8"))
    immutable(run/"glossary.md", files("tumortwin").joinpath("glossary.md").read_text(encoding="utf-8"))
    # Choose examples using identity and allocation hash before calculating any errors.
    examples = (split.sort_values("allocation_hash").groupby(["partition", "study", "treatment"])
                .head(1).sort_values(["partition", *IDENTITY]))
    immutable(run/"examples.csv", examples.to_csv(index=False))
    immutable(run/"design_manifest.json", json_text({
        name: sha256(run/name) for name in ["split.csv", "provenance.json", "protocol.md",
                                            "config.toml", "glossary.md", "examples.csv"]}))
    return cfg, run, raw, split, provenance


def forecast_origin(job: tuple[Origin, dict]) -> tuple[list[dict], list[dict]]:
    origin, cfg = job
    diagnostics, predictions = [], []
    target_days = origin.t0+np.asarray(cfg["horizons"], float)
    for model in MODELS:
        if origin.status == "ok":
            fit = fit_model(model, origin.days, origin.volumes, cfg["fit"])
        else:
            fit = FitResult(model, False, "ineligible_prefix", origin.t0, np.nan)
        diagnostics.append(origin.record() | fit.record())
        pred = fit.predict(target_days)
        for h, target, value in zip(cfg["horizons"], target_days, pred, strict=True):
            predictions.append(origin.record() | dict(
                origin_status=origin.status, model=model, horizon_days=h, target_day=float(target),
                prediction=float(value), fit_success=fit.success, fit_status=fit.status,
                forecast_status="ok" if fit.success and np.isfinite(value) else "forecast_failed",
                last_volume=fit.last_volume, near_bound=fit.near_bound, ill_conditioned=fit.ill_conditioned))
    return diagnostics, predictions


def _export_scores(joined: pd.DataFrame, folder: Path, cfg: dict) -> None:
    coverage(joined).to_csv(folder/"coverage.csv", index=False)
    for analysis in sorted(joined.analysis.unique()):
        frames = supports(joined.loc[joined.analysis == analysis], cfg["horizons"])
        for name, frame in frames.items():
            if name == "short_matched":
                continue
            summary, individual = summarize(frame)
            summary.to_csv(folder/f"{analysis}_{name}_scores.csv", index=False)
            individual.to_csv(folder/f"{analysis}_{name}_animals.csv", index=False)
            if name in {"common", "fallback", "common_horizons"}:
                paired_bootstrap(individual, cfg["bootstrap_samples"], cfg["seed"],
                                 cfg["bootstrap_min_animals"]).to_csv(
                    folder/f"{analysis}_{name}_bootstrap.csv", index=False)
        subgroup_rows = []
        for (study, treatment), sub in frames["common"].groupby(["study", "treatment"]):
            scores, _ = summarize(sub)
            scores["study"], scores["treatment"] = study, treatment
            subgroup_rows.append(scores)
        (pd.concat(subgroup_rows, ignore_index=True) if subgroup_rows else pd.DataFrame(
            columns=["study", "treatment", "model", "horizon_days", "n_animals"])).to_csv(
                folder/f"{analysis}_subgroups.csv", index=False)
    matched = supports(joined, cfg["horizons"])["short_matched"]
    for analysis, frame in matched.groupby("analysis"):
        scores, individual = summarize(frame)
        scores.to_csv(folder/f"{analysis}_matched_scores.csv", index=False)
        individual.to_csv(folder/f"{analysis}_matched_animals.csv", index=False)


def run_partition(config_path: Path, partition: str) -> Path:
    cfg, run, raw, split, provenance = prepare(config_path)
    if partition not in {"development", "test"}:
        raise ValueError("Unknown partition")
    if partition == "test":
        if not (run/"freeze.json").exists():
            raise ValueError("Run development and freeze before opening test scores")
        freeze(config_path, check_only=True)
    folder = run/partition
    if folder.exists():
        verify_stage(folder)
        return folder
    selected = split.loc[split.partition == partition, IDENTITY]
    from ..data.quality import normalize

    identity = normalize(raw)[IDENTITY]
    indices = identity.merge(selected.assign(selected=True), how="left", on=IDENTITY).selected.fillna(False)
    subset = raw.loc[indices.to_numpy(bool)].reset_index(drop=True)
    origins = build_origins(subset, cfg["min_history"], tuple(cfg["short_histories"]))
    if not origins:
        raise ValueError("No prediction origins in partition")
    folder.mkdir()
    pd.DataFrame([o.record() for o in origins]).to_csv(folder/"origins.csv", index=False)
    all_predictions = []
    jobs = [(o, cfg) for o in origins]
    executor = ProcessPoolExecutor(max_workers=cfg["workers"]) if cfg["workers"] > 1 else None
    stream = executor.map(forecast_origin, jobs, chunksize=1) if executor else map(forecast_origin, jobs)
    try:
        with (folder/"fits.jsonl").open("x", encoding="utf-8") as output:
            for index, (fits, predictions) in enumerate(stream, start=1):
                for fit in fits:
                    output.write(json.dumps(clean(fit), ensure_ascii=False, allow_nan=False)+"\n")
                all_predictions.extend(predictions)
                if index % 25 == 0 or index == len(origins):
                    print(f"{partition}: {index}/{len(origins)} origins", file=sys.stderr, flush=True)
    finally:
        if executor:
            executor.shutdown(wait=True, cancel_futures=True)
    forecasts = pd.DataFrame(all_predictions)
    # Persist forecasts before constructing or joining any future target volumes.
    forecasts.to_csv(folder/"predictions.csv", index=False)
    targets = target_registry(subset)
    targets.to_csv(folder/"targets.csv", index=False)
    joined = join_targets(forecasts, targets)
    joined.to_csv(folder/"scored_registry.csv", index=False)
    _export_scores(joined, folder, cfg)
    from .report import write_report

    write_report(joined, subset, folder, run, cfg, partition)
    artifacts = {str(p.relative_to(folder)): sha256(p) for p in sorted(folder.rglob("*")) if p.is_file()}
    immutable(folder/"complete.json", json_text(dict(partition=partition, n_animals=len(selected),
                                                   n_origins=len(origins), artifacts=artifacts)))
    return folder


def freeze(config_path: Path, check_only: bool = False) -> Path:
    cfg, run, _, _, provenance = prepare(config_path)
    development = verify_stage(run/"development")
    if provenance["working_tree_dirty"] or provenance["git_commit"] == "unversioned":
        raise ValueError("Freeze requires a clean committed working tree")
    record = dict(provenance_sha256=sha256(run/"provenance.json"),
                  design_sha256=sha256(run/"design_manifest.json"),
                  development_sha256=digest(development), git_commit=provenance["git_commit"],
                  statement="Settings fixed before evaluation of test targets")
    if check_only and not (run/"freeze.json").exists():
        raise ValueError("No freeze marker")
    immutable(run/"freeze.json", json_text(record))
    return run/"freeze.json"
