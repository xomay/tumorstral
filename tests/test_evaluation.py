"""Synthetic animal identities, dates, targets and hand-computed metrics."""

from pathlib import Path
import json
import subprocess

import numpy as np
import pandas as pd
import pytest

from tumortwin.baselines import MODELS
from tumortwin.evaluation.design import build_origins, join_targets, make_split, target_registry
from tumortwin.evaluation.experiment import forecast_origin, freeze, prepare, run_partition, verify_stage
from tumortwin.evaluation.metrics import animal_scores, paired_bootstrap, summarize, supports


def synthetic_animals(n=10):
    rows = []
    for animal in range(n):
        for day in [0., 2., 5., 7., 9., 12., 14., 19., 26.]:
            rows.append(dict(study="Synthetic", group="1", treatment="Synthetic control",
                             animal_id=f"{animal:03d}", day=day,
                             tumour_volume=(10+animal)*np.exp(.03*day)))
    return pd.DataFrame(rows)


def test_split_is_animal_disjoint_and_independent_of_rows_values_and_followup():
    raw = synthetic_animals()
    split = make_split(raw)
    assert split.partition.value_counts().to_dict() == {"development": 8, "test": 2}
    changed = raw.sample(frac=1, random_state=1).copy()
    changed["tumour_volume"] = 99999
    pd.testing.assert_frame_equal(split, make_split(changed))
    shortened = raw.groupby("animal_id").head(1)
    pd.testing.assert_frame_equal(split, make_split(shortened))
    assert split.animal_id.nunique() == 10
    assert split.animal_id.str.startswith("00").all()


def test_future_values_and_metadata_do_not_change_an_earlier_forecast():
    raw = synthetic_animals(1)
    initial = next(o for o in build_origins(raw) if o.analysis == "main")
    changed = raw.copy()
    changed.loc[changed.day > initial.t0, "tumour_volume"] = 99999
    changed.loc[changed.day > initial.t0, "treatment"] = "Future metadata conflict"
    later = next(o for o in build_origins(changed) if o.origin_id == initial.origin_id)
    np.testing.assert_array_equal(initial.days, later.days)
    np.testing.assert_array_equal(initial.volumes, later.volumes)
    assert initial.status == later.status == "ok"
    cfg = {"horizons": [3, 7, 14], "fit": {"max_nfev": 100}}
    a = forecast_origin((initial, cfg))[1]
    b = forecast_origin((later, cfg))[1]
    np.testing.assert_allclose([r["prediction"] for r in a], [r["prediction"] for r in b], equal_nan=True)


def test_exact_targets_gaps_and_original_source_rows():
    raw = synthetic_animals(1)
    raw["_source_row"] = np.arange(len(raw))+100
    origins = build_origins(raw)
    origin = next(o for o in origins if o.analysis == "main")
    assert origin.t0 == 12 and origin.source_rows == list(range(100, 106))
    assert origin.context_days == 12
    targets = target_registry(raw)
    predictions = pd.DataFrame([dict(study=origin.study, animal_id=origin.animal_id,
                                     treatment=origin.treatment, target_day=day)
                                for day in [15., 19., 26.]])
    joined = join_targets(predictions, targets)
    assert joined.target_status.tolist() == ["no_exact_target", "observed", "observed"]
    assert json.loads(targets.iloc[0].target_source_rows) == [100]
    assert {o.analysis for o in origins} >= {"short_3", "short_4", "short_5", "main"}


def test_duplicates_and_missing_targets_are_retained_but_not_scored():
    raw = synthetic_animals(1)
    raw = pd.concat([raw, raw.iloc[[7]]], ignore_index=True)
    raw.loc[8, "tumour_volume"] = np.nan
    targets = target_registry(raw)
    assert targets.loc[targets.target_day.isin([19., 26.]), "target_status"].eq("invalid_target").all()
    assert len(targets) == 9
    origin = next(o for o in build_origins(raw) if o.analysis == "main" and o.t0 == 12)
    assert len(origin.days) == 6


def metric_frame():
    rows = []
    for animal, errors in [("001", [1., 3.]), ("002", [10.])]:
        for index, error in enumerate(errors):
            for model in MODELS:
                rows.append(dict(study="S", animal_id=animal, treatment="T", analysis="main",
                    origin_id=f"{animal}-{index}", model=model, horizon_days=7, target_volume=10.,
                    prediction=10.+(error if model == "persistence" else error/2),
                    last_volume=10.+error, origin_status="ok", target_status="observed",
                    fit_success=True, near_bound=False, ill_conditioned=False))
    return pd.DataFrame(rows)


def test_macro_metrics_match_hand_calculation():
    frame = metric_frame()
    summary, individual = summarize(frame)
    row = summary.loc[summary.model == "persistence"].iloc[0]
    assert row.mae == 6  # mean((1+3)/2, 10), not mean(1,3,10)
    assert row.rmse == pytest.approx(np.sqrt((5+100)/2))
    assert row.n_animals == 2 and row.n_pairs == 3
    assert animal_scores(frame).query("model == 'persistence'").mae.tolist() == [2, 10]


def test_common_support_and_explicit_fallback():
    frame = metric_frame()
    failure = (frame.model == "gompertz") & (frame.origin_id == "001-0")
    frame.loc[failure, "fit_success"] = False
    frame.loc[failure, "prediction"] = np.nan
    views = supports(frame, [3, 7, 14])
    assert len(views["common"]) == 8
    assert views["common"].groupby("model").size().eq(2).all()
    assert len(views["fallback"]) == 12
    assert views["fallback"].used_fallback.sum() == 1
    assert views["fallback"].loc[failure, "prediction"].iloc[0] == 11
    assert views["common_horizons"].empty


def test_zero_denominators_and_bootstrap_clusters():
    frame = metric_frame()
    frame["target_volume"] = 0.
    summary, _ = summarize(frame)
    assert summary.median_relative.isna().all()
    assert summary.positive_target_fraction.eq(0).all()
    records = []
    for animal in range(12):
        for model in MODELS:
            records.append(dict(study="S1" if animal < 6 else "S2", animal_id=str(animal),
                                horizon_days=7, model=model, mae=float(animal+1)+(model != "persistence")))
    individuals = pd.DataFrame(records)
    a = paired_bootstrap(individuals, samples=100)
    b = paired_bootstrap(individuals.sample(frac=1, random_state=2), samples=100)
    pd.testing.assert_frame_equal(a, b)
    np.testing.assert_allclose(a.loc[a.model != "persistence", "delta_low"], 1.)
    np.testing.assert_allclose(a.loc[a.model != "persistence", "delta_high"], 1.)
    assert paired_bootstrap(individuals.iloc[:8], samples=100).mae_low.isna().all()


def test_matched_horizons_and_short_cohorts():
    base = metric_frame()
    expanded = pd.concat([base.assign(horizon_days=h) for h in [3, 7, 14]], ignore_index=True)
    assert len(supports(expanded, [3, 7, 14])["common_horizons"]) == 36
    short = pd.concat([base.assign(analysis=f"short_{k}", origin_id=base.origin_id+str(k))
                       for k in [3, 4, 5]], ignore_index=True)
    assert len(supports(short, [3, 7, 14])["short_matched"]) == 36


def test_miniature_pipeline_freeze_and_integrity(tmp_path):
    raw = synthetic_animals()
    raw.to_csv(tmp_path/"synthetic.csv", index=False)
    (tmp_path/"protocol.md").write_text("Synthetic offline test protocol")
    (tmp_path/".gitignore").write_text("output/\n")
    config = Path("configs/baselines.toml").read_text().replace('project_root = ".."', 'project_root = "."')
    config = config.replace('input = "data/raw/example_data.rda"', 'input = "synthetic.csv"')
    config = config.replace('output = "reports/baselines"', 'output = "output"')
    config = config.replace('protocol = "docs/preclinical_protocol.md"', 'protocol = "protocol.md"')
    config = config.replace('workers = 4', 'workers = 1').replace('bootstrap_samples = 2000', 'bootstrap_samples = 10')
    config = config.replace('exponential_starts = [-0.1, 0.0, 0.1]', 'exponential_starts = [0.1]')
    config = config.replace('rate_starts = [0.01, 0.1, 0.5]', 'rate_starts = [0.1]')
    config = config.replace('capacity_factors = [0.5, 1.0, 2.0, 10.0]', 'capacity_factors = [2.0]')
    config = config.replace('max_nfev = 2000', 'max_nfev = 100')
    path = tmp_path/"baselines.toml"
    path.write_text(config)
    for args in [["init", "-b", "main"], ["add", "."],
                 ["-c", "user.name=Synthetic test", "-c", "user.email=synthetic@example.invalid",
                  "commit", "-m", "Synthetic fixture"]]:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    cfg, run, _, split, _ = prepare(path)
    assert len(split) == 10
    with pytest.raises(ValueError, match="development and freeze"):
        run_partition(path, "test")
    original = (tmp_path/"synthetic.csv").read_bytes()
    develop = run_partition(path, "development")
    marker = freeze(path)
    assert marker.exists()
    final = run_partition(path, "test")
    assert (final/"report.md").exists()
    assert (final/"figures/preselected_examples.png").stat().st_size > 1000
    assert verify_stage(final)["n_animals"] == 2
    assert (tmp_path/"synthetic.csv").read_bytes() == original
    forecasts = pd.read_csv(final/"predictions.csv")
    assert "target_volume" not in forecasts
    assert "target_volume" in pd.read_csv(final/"scored_registry.csv")
    assert run_partition(path, "development") == develop
    (final/"predictions.csv").write_text("tampered")
    with pytest.raises(ValueError, match="artifact changed"):
        verify_stage(final)
