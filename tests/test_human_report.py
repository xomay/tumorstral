"""All frames below are synthetic examples, not patient observations."""

import numpy as np
import pandas as pd
import pytest

from tumortwin.evaluation.human_report import comparison_support, write_human_report


def synthetic_frames():
    observations, predictions, quantiles = [], [], []
    for study in ["Synthetic A", "Synthetic B"]:
        for visit, value in [(0, .1), (1, .2), (2, .4), (3, .5)]:
            observations.append(dict(study=study, patient_id="001", day=visit, tumour_volume=value))
        origin = study+"-001"
        for target, truth in [(2, .4), (3, .5)]:
            for model, pred in [("persistence", .2), ("timestral", truth+.02)]:
                predictions.append(dict(study=study, patient_id="001", origin_id=origin,
                                        t0=1, target_day=target, model=model, prediction=pred,
                                        target_volume=truth))
            for level, value in [(.05, truth-.2), (.1, truth-.1), (.5, truth+.02),
                                  (.9, truth+.1), (.95, truth+.2)]:
                quantiles.append(dict(origin_id=origin, target_day=target, level=level, value=value))
    return pd.DataFrame(predictions), pd.DataFrame(quantiles), pd.DataFrame(observations)


def test_offline_report_compares_patient_predictions_and_truth(tmp_path):
    predictions, quantiles, observations = synthetic_frames()
    result = write_human_report(predictions, quantiles, observations, None, tmp_path,
        dict(volume_label="Volume publié normalisé", time_label="Numéro de visite",
             horizon_label="Nombre de visites", partition="test synthétique"))
    for key, path in result.items():
        assert path.exists()
        if key != "report":
            assert path.stat().st_size > 1000
    text = result["report"].read_text()
    assert "Volume publié normalisé" in text and "Numéro de visite" in text
    assert "[MAE](glossary.md#mae)" in text
    assert (tmp_path/"glossary.md").exists()
    examples = pd.read_csv(tmp_path/"report_examples.csv", dtype={"animal_id": str})
    assert len(examples) == 2 and examples.animal_id.eq("001").all()
    scores = pd.read_csv(tmp_path/"report_point_scores.csv")
    assert scores.n_patients.eq(2).all()  # Same ID in two studies must remain distinct.
    np.testing.assert_allclose(scores.loc[scores.model == "timestral", "mean_absolute_error"], .02)
    intervals = pd.read_csv(tmp_path/"report_interval_scores.csv")
    assert intervals.empirical_coverage.eq(1).all()


def test_common_support_never_compares_different_target_sets():
    predictions, _, _ = synthetic_frames()
    bad = (predictions.model == "timestral") & (predictions.target_day == 3)
    predictions.loc[bad, "prediction"] = np.nan
    common = comparison_support(predictions)
    assert common.target_day.eq(2).all()
    assert common.groupby("model").size().eq(2).all()


def test_units_are_required_and_conflicting_truth_is_rejected(tmp_path):
    predictions, quantiles, observations = synthetic_frames()
    with pytest.raises(ValueError, match="volume_label"):
        write_human_report(predictions, quantiles, observations, None, tmp_path, {})
    predictions.loc[0, "target_volume"] = 99
    with pytest.raises(ValueError, match="Different observed truths"):
        comparison_support(predictions)


def test_report_without_timestral_intervals_or_usable_targets(tmp_path):
    predictions, _, observations = synthetic_frames()
    predictions["target_volume"] = np.nan
    write_human_report(predictions, pd.DataFrame(), observations, {}, tmp_path,
                       dict(volume_label="Mesure sans dimension", time_label="Visite"))
    assert (tmp_path/"report.md").exists()


def test_example_selection_uses_identity_not_error(tmp_path):
    predictions, quantiles, observations = synthetic_frames()
    examples = pd.DataFrame([dict(study="Synthetic B", patient_id="001")])
    write_human_report(predictions, quantiles, observations, None, tmp_path,
                       dict(volume_label="Mesure sans dimension", time_label="Visite"), examples)
    selected = pd.read_csv(tmp_path/"report_examples.csv")
    assert selected.study.tolist() == ["Synthetic B"]
