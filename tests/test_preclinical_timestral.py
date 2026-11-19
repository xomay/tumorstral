"""Offline synthetic checks of the five-model preclinical extension."""

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from test_evaluation import metric_frame, synthetic_animals
from test_timestral import FakeForecaster
from tumorstral.baselines import MODELS
from tumorstral.evaluation.design import build_origins, join_targets, target_registry
from tumorstral.evaluation.metrics import coverage, paired_bootstrap, summarize, supports
from tumorstral.evaluation.preclinical_timestral import export_quantile_scores, forecast_origin, model_provenance
from tumorstral.timestral import TimestralAdapter
from tumorstral.timestral.download import CODE_REVISION, MODEL_REVISION

MODELS_FIVE = (*MODELS, "timestral")
CFG = {"horizons": [3, 7, 14], "timestral": {"enabled": True, "grid_step_days": 1.}}


def test_prefix_only_daily_mask_exact_horizons_and_no_target_interpolation():
    raw = synthetic_animals(1)
    origin = next(o for o in build_origins(raw) if o.analysis == "main")
    model = FakeForecaster()
    adapter = TimestralAdapter(model, model_revision="synthetic")
    records, result, _ = forecast_origin(origin, CFG, adapter)
    assert [r["target_day"] for r in records] == [15., 19., 26.]
    assert model.calls[0][1] == 14
    assert result.context.times[0] == 0 and result.context.times[-1] == 12
    assert result.context.observation_mask.sum() == 6
    assert np.isnan(result.context.values[1])
    assert all("target_volume" not in r for r in records)
    scored = join_targets(pd.DataFrame(records), target_registry(raw))
    assert scored.target_status.tolist() == ["no_exact_target", "observed", "observed"]
    changed = raw.copy()
    changed.loc[changed.day > origin.t0, "tumour_volume"] = 1e9
    changed.loc[changed.day > origin.t0, "treatment"] = "Synthetic future conflict"
    later = next(o for o in build_origins(changed) if o.origin_id == origin.origin_id)
    repeated = forecast_origin(later, CFG, adapter)[1]
    np.testing.assert_array_equal(result.quantiles, repeated.quantiles)


def test_negative_median_scored_even_with_crossed_other_quantiles():
    class Raw(FakeForecaster):
        def forecast(self, *args, **kwargs):
            out = super().forecast(*args, **kwargs)
            out.quantiles[:] = -2.
            out.quantiles[0, 0, 2, 0] = 1000.  # Invalid distribution, still a finite median.
            return out

    origin = next(o for o in build_origins(synthetic_animals(1)) if o.analysis == "main")
    records, _, diag = forecast_origin(origin, CFG, TimestralAdapter(Raw(), model_revision="synthetic"))
    assert all(r["prediction"] == -2 and r["fit_success"] for r in records)
    assert records[0]["negative_prediction"]
    assert not records[0]["valid_quantiles"]  # crossed quantiles at horizon three days
    assert diag["negative_medians"] == 3


def five_model_frame():
    frame = metric_frame()
    timestral = frame.loc[frame.model == "persistence"].assign(model="timestral", prediction=-2.)
    return pd.concat([frame, timestral], ignore_index=True)


def test_common_five_model_support_negative_scoring_failures_and_reference_comparison():
    frame = five_model_frame()
    views = supports(frame, [3, 7, 14], MODELS_FIVE)
    assert len(views["common"]) == 15
    scores, individual = summarize(views["common"])
    assert scores.loc[scores.model == "timestral", "mae"].item() == 12
    assert coverage(frame).query("model == 'timestral'").coverage.item() == 1
    assert coverage(frame).query("model == 'timestral'").n_negative_predictions.item() == 3
    result = paired_bootstrap(individual, samples=10, models=MODELS_FIVE, reference="gompertz")
    assert result.query("model == 'timestral'").delta_mae.item() == 9
    failure = (frame.model == "timestral") & (frame.origin_id == "001-0")
    frame.loc[failure, "fit_success"] = False
    frame.loc[failure, "prediction"] = np.nan
    views = supports(frame, [3, 7, 14], MODELS_FIVE)
    assert views["common"].groupby("model").size().eq(2).all()
    assert views["fallback"].used_fallback.sum() == 1
    assert views["fallback"].loc[views["fallback"].model == "timestral", "prediction"].tolist() == [11., -2., -2.]


def test_missing_models_or_duplicate_predictions_cannot_form_common_support():
    frame = five_model_frame()
    with pytest.raises(ValueError, match="expected models"):
        supports(frame, [7])
    with pytest.raises(ValueError, match="Duplicate"):
        supports(pd.concat([frame, frame.iloc[[0]]]), [7], MODELS_FIVE)
    # A missing row for one model excludes that pair from every model's common score.
    frame = frame.drop(frame.index[-1])
    assert len(supports(frame, [7], MODELS_FIVE)["common"]) == 10


def test_inference_failures_remain_in_ledger_and_ineligible_prefix_never_called():
    class Failing:
        def forecast(self, *args, **kwargs):
            raise RuntimeError("Synthetic failure")

    origin = next(o for o in build_origins(synthetic_animals(1)) if o.analysis == "main")
    records, result, diagnostic = forecast_origin(origin, CFG, Failing())
    assert result is None and diagnostic["status"] == "failed"
    assert len(records) == 3 and not any(r["fit_success"] for r in records)
    origin.status = "metadata_conflict"
    assert forecast_origin(origin, CFG, Failing())[2]["status"] == "ineligible_prefix"


def test_quantile_scores_keep_negative_values_and_exclude_invalid_distributions(tmp_path):
    # One animal has two origins and another has one: equal animal weighting, not row weighting.
    truth = five_model_frame()
    quantiles = []
    from tumorstral.timestral import QUANTILE_LEVELS

    for origin, prediction in zip(truth.origin_id.unique(), [-2., -6., -10.], strict=True):
        for level in QUANTILE_LEVELS:
            quantiles.append(dict(origin_id=origin, target_day=7., level=level, value=prediction, model="timestral"))
    truth["target_day"] = 7.
    export_quantile_scores(pd.DataFrame(quantiles), truth, tmp_path)
    scores = pd.read_csv(tmp_path/"probabilistic_scores.csv")
    assert scores.n_pairs.eq(3).all() and scores.n_animals.eq(2).all()
    assert scores.negative_quantile_fraction.eq(1).all()
    assert scores.interval_coverage.eq(0).all()
    assert scores.pinball.eq(8.5).all()  # mean(mean(6,8),10), not mean(6,8,10).
    quantiles[0]["value"] = 1000.  # Crossed quantiles invalidate only this distribution.
    export_quantile_scores(pd.DataFrame(quantiles), truth, tmp_path)
    scores = pd.read_csv(tmp_path/"probabilistic_scores.csv")
    assert scores.n_pairs.eq(2).all() and scores.pinball.eq(9).all()
    # No output at all must still produce readable headers for reporting.
    empty = pd.DataFrame(columns=["origin_id", "target_day", "level", "value", "model"])
    export_quantile_scores(empty, truth, tmp_path)
    assert pd.read_csv(tmp_path/"probabilistic_scores.csv").empty


def test_local_weights_and_code_are_checked_without_network(tmp_path, monkeypatch):
    from tumorstral.data.inspectumours import sha256

    artifact = tmp_path/"synthetic.bin"
    artifact.write_bytes(b"explicitly synthetic model fixture")
    hashes = {artifact.name: sha256(artifact)}
    monkeypatch.setattr("tumorstral.evaluation.preclinical_timestral.HASHES", hashes)
    manifest = dict(repository="mistralai/Timestral-5M", model_revision=MODEL_REVISION,
                    code_revision=CODE_REVISION, files=hashes)
    (tmp_path/"provenance.json").write_text(json.dumps(manifest))
    dist = SimpleNamespace(read_text=lambda name: json.dumps({"vcs_info": {"commit_id": CODE_REVISION}}))
    monkeypatch.setattr("tumorstral.evaluation.preclinical_timestral.metadata.distribution", lambda name: dist)
    monkeypatch.setattr("tumorstral.evaluation.preclinical_timestral.metadata.version", lambda name: "synthetic")
    cfg = {"timestral": {"model_revision": MODEL_REVISION, "local_model": ".", "grid_step_days": 1., "threads": 1}}
    assert model_provenance(cfg, tmp_path)["zero_shot"]
    artifact.write_bytes(b"tampered synthetic weights")
    with pytest.raises(ValueError, match="artifact changed"):
        model_provenance(cfg, tmp_path)
    artifact.write_bytes(b"explicitly synthetic model fixture")
    dist.read_text = lambda name: json.dumps({"vcs_info": {"commit_id": "wrong synthetic code"}})
    with pytest.raises(ValueError, match="code differs"):
        model_provenance(cfg, tmp_path)
