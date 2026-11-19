"""Synthetic human trajectories, chronological queries and probabilistic scores."""

from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
import pytest

from tumorstral.evaluation.human import landmarks, patient_split, baseline_job, design, run_human, freeze_human
from tumorstral.evaluation.probabilistic import point_scores, quantile_scores, paired_patient_bootstrap
from tumorstral.timestral.adapter import QUANTILE_LEVELS


def synthetic(n=10):
    return pd.DataFrame([dict(study="S", animal_id=f"{i:03d}", patient_id=f"{i:03d}",
        group="A", treatment="A", day=d, tumour_volume=(10+i)*np.exp(.003*d))
        for i in range(n) for d in [-10, 42, 85, 126, 170, 215, 260, 305, 355]])


def test_patient_split_excludes_ambiguous_ids_without_leakage():
    frame = synthetic()
    split = patient_split(frame, 42, .2)
    assert split.partition.value_counts().to_dict() == {"development": 8, "test": 2}
    altered = frame.sample(frac=1, random_state=1).assign(tumour_volume=999)
    pd.testing.assert_frame_equal(split, patient_split(altered, 42, .2))
    repeated = frame.loc[frame.animal_id == "000"].assign(study="S2")
    split = patient_split(pd.concat([frame, repeated]), 42, .2)
    assert split.loc[split.animal_id == "000", "partition"].eq("excluded_ambiguous_identity").all()
    assert not set(split.query("partition == 'test'").animal_id) & set(split.query("partition == 'development'").animal_id)


def test_landmarks_do_not_use_future_values_or_metadata():
    frame = synthetic(1)
    jobs, truth = landmarks(frame, [3, 6], [1, 2, 3])
    first = jobs[0]
    assert first["t0"] == 85 and first["requests"][0]["target_day"] == 126
    future = frame.day > first["t0"]
    changed = frame.copy()
    changed.loc[future, "tumour_volume"] = 999999
    changed.loc[future, "treatment"] = "Different later arm"
    altered, _ = landmarks(changed, [3], [1, 2, 3])
    np.testing.assert_array_equal(first["volumes"], altered[0]["volumes"])
    assert "target_volume" not in first["requests"][0]
    assert truth.target_volume.notna().all()


def test_invalid_next_visit_is_not_replaced_by_later_visit():
    frame = synthetic(1)
    frame.loc[frame.day == 126, "tumour_volume"] = np.nan
    jobs, truth = landmarks(frame, [3], [1, 2, 3])
    assert jobs[0]["requests"][0]["target_day"] == 126
    assert truth.iloc[0].target_status == "invalid_target"
    assert np.isnan(truth.iloc[0].target_volume)
    assert truth.iloc[1].target_day == 170


def test_baseline_scaling_uses_only_prefix_and_preserves_physical_units():
    jobs, _ = landmarks(synthetic(1), [6], [1])
    cfg = dict(baseline_time_scale_days=7., fit={"exponential_starts": [.03],
                                               "rate_starts": [.03], "capacity_factors": [2.]})
    records, fits = baseline_job(jobs[0], cfg)
    prediction = next(r["prediction"] for r in records if r["model"] == "exponential")
    assert prediction == pytest.approx(10*np.exp(.003*260), rel=1e-4)
    assert fits[0]["prefix_volume_scale"] == np.median(jobs[0]["volumes"])


def test_patient_metrics_common_support_hand_errors_and_failures():
    rows = []
    for i, error in enumerate([2., 10.]):
        for model in ["persistence", "timestral"]:
            rows.append(dict(study="S", animal_id=str(i), origin_id=str(i), target_day=42,
                n_context=6, horizon=1, model=model, target_volume=10.,
                prediction=10+error*(1 if model == "persistence" else .5), fit_success=True))
    frame = pd.DataFrame(rows)
    scores, individual = point_scores(frame, ["persistence", "timestral"])
    common = scores.query("support == 'common'").set_index("model")
    assert common.loc["persistence", "mae"] == 6.
    assert common.loc["timestral", "mae"] == 3.
    frame.loc[0, "fit_success"] = False
    scores, _ = point_scores(frame, ["persistence", "timestral"])
    assert scores.query("support == 'common'").n_pairs.eq(1).all()
    assert paired_patient_bootstrap(individual, 100, 42).lower.isna().all()


def test_pinball_and_intervals_on_known_quantiles():
    truth = pd.DataFrame([dict(origin_id="a", target_day=42, study="S", animal_id="P",
                              n_context=6, horizon=1, target_volume=5.)])
    q = pd.DataFrame([dict(origin_id="a", target_day=42, level=x, value=10*x) for x in QUANTILE_LEVELS])
    scores, by_level = quantile_scores(q, truth)
    assert len(by_level) == 21
    assert scores.interval_coverage.eq(1.).all()
    assert scores.loc[np.isclose(scores.nominal, .8), "mean_width"].iloc[0] == 8
    assert by_level.loc[by_level.level == .5, "pinball"].iloc[0] == 0
    q.loc[0, "value"] = np.nan
    scores, by_level = quantile_scores(q, truth)
    assert scores.empty and by_level.empty


def test_human_baseline_pipeline_and_freeze(tmp_path):
    raw = synthetic()
    workbook = pd.DataFrame({"Patient_Anonmyized": raw.animal_id,
        "Treatment_Day": raw.day, "TargetLesionLongDiam_mm": (2*raw.tumour_volume)**(1/3),
        "Study_Arm": raw.treatment})
    with pd.ExcelWriter(tmp_path/"synthetic.xlsx") as writer:
        workbook.to_excel(writer, sheet_name="S", index=False)
    text = Path("configs/human.toml").read_text().replace('project_root = ".."', 'project_root = "."')
    text = text.replace('input = "data/raw/laleh/journal.pcbi.1009822.s006.xlsx"', 'input = "synthetic.xlsx"')
    text = text.replace('output = "reports/human"', 'output = "out"')
    text = text.replace('protocol = "docs/human_protocol.md"', 'protocol = "protocol.md"')
    text = text.replace('enabled = true', 'enabled = false').replace('workers = 4', 'workers = 1')
    text = text.replace('development_patients = 20', 'development_patients = 2')
    text = text.replace('contexts = [3, 4, 5, 6]', 'contexts = [3, 6, 8]')
    text = text.replace('rate_starts = [0.01, 0.1, 0.5]', 'rate_starts = [0.1]')
    text = text.replace('capacity_factors = [0.5, 1.0, 2.0, 10.0]', 'capacity_factors = [2.0]')
    text = text.replace('max_nfev = 2000', 'max_nfev = 40')
    config = tmp_path/"human.toml"; config.write_text(text)
    (tmp_path/"protocol.md").write_text("Synthetic protocol")
    (tmp_path/"uv.lock").write_text("Synthetic lock")
    (tmp_path/".gitignore").write_text("out/\n")
    for args in [["init", "-b", "main"], ["add", "."],
                 ["-c", "user.name=Synthetic", "-c", "user.email=test@example.invalid", "commit", "-m", "Fixture"]]:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    with pytest.raises(ValueError): run_human(config, "test")
    output = run_human(config, "development")
    assert (output/"report.md").exists()
    assert freeze_human(config).exists()
    output = run_human(config, "test")
    assert (output/"figures/patient_forecasts.png").stat().st_size > 1000
    assert "target_volume" not in pd.read_csv(output/"predictions.csv")
    assert pd.read_csv(output/"scored_predictions.csv").target_volume.notna().all()
    assert pd.read_csv(output/"targets.csv").target_status.eq("no_followup_visit").any()
