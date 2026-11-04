"""Synthetic fake-model tests; no network access or model weights required."""

from types import SimpleNamespace
import sys

import numpy as np
import pytest

from tumortwin.timestral import QUANTILE_LEVELS, TimestralAdapter, prepare_grid


class FakeForecaster:
    def __init__(self):
        self.calls = []

    def forecast(self, context, prediction_length, **kwargs):
        self.calls.append((context.copy(), prediction_length, kwargs))
        # Depend only on the supplied prefix, to make target leakage detectable.
        start = float(context[np.isfinite(context)][-1])
        quantiles = start+np.arange(1, prediction_length+1)[:, None]+QUANTILE_LEVELS[None, :]
        return SimpleNamespace(quantiles=quantiles[None, None], quantile_levels=QUANTILE_LEVELS)


def test_regular_grid_preserves_real_dates_missingness_and_zero():
    dates = np.array([7., 9., 12., 14.])
    values = np.array([0., 12., np.nan, 20.])
    grid = prepare_grid(dates, values)
    np.testing.assert_array_equal(grid.times, np.arange(7, 15))
    np.testing.assert_array_equal(grid.observation_mask, [True, False, True, False, False, False, False, True])
    assert grid.values[0] == 0
    assert grid.values[2] == 12
    assert np.isnan(grid.values[5])
    assert grid.density == 3/8
    assert np.isnan(values[2])  # input was not modified


def test_exact_future_alignment_and_full_quantile_output():
    model = FakeForecaster()
    adapter = TimestralAdapter(model, model_revision="synthetic-weights")
    result = adapter.forecast(np.array([0., 2., 5.]), np.array([10., 11., 15.]),
                              np.array([7., 12., 19.]))
    assert result.quantiles.shape == (3, 21)
    assert result.full_quantiles.shape == (14, 21)
    np.testing.assert_allclose(result.median, [17.5, 22.5, 29.5])
    np.testing.assert_allclose(result.quantile(.1), [17.1, 22.1, 29.1])
    context, horizon, options = model.calls[0]
    assert horizon == 14 and context.shape == (1, 1, 6)
    assert options["clip_nonnegative"] is False
    assert options["symmetric_averaging"] is True
    np.testing.assert_array_equal(options["observation_mask"], np.isfinite(context))
    assert result.diagnostics["internal_forward_fill"] is True


def test_week_grid_is_explicit_and_context_rank_is_not_time():
    model = FakeForecaster()
    adapter = TimestralAdapter(model, model_revision="synthetic")
    result = adapter.forecast(np.array([0., 7., 21.]), np.array([1., 2., 3.]), np.array([35.]), step=7.)
    assert len(result.context.values) == 4
    assert model.calls[0][1] == 2
    assert np.isnan(result.context.values[2])


@pytest.mark.parametrize("dates,values,step", [
    ([0., 1.5], [1., 2.], 1.), ([0., 0.], [1., 2.], 1.),
    ([1., 0.], [1., 2.], 1.), ([0., 1.], [np.nan, np.nan], 1.),
    ([0., 1.], [1., np.inf], 1.), ([0., 1.], [1., -2.], 1.),
    ([0., 1.], [1., 2.], 0.),
])
def test_invalid_grid_never_silently_interpolates(dates, values, step):
    with pytest.raises(ValueError):
        prepare_grid(np.array(dates), np.array(values), step)


def test_context_limit_does_not_silently_drop_history():
    with pytest.raises(ValueError, match="no silent truncation"):
        prepare_grid(np.array([0., 32768.]), np.array([1., 2.]))


@pytest.mark.parametrize("target", [[5.], [4.], [6.5], []])
def test_invalid_future_dates_are_explicit(target):
    adapter = TimestralAdapter(FakeForecaster(), model_revision="synthetic")
    with pytest.raises(ValueError):
        adapter.forecast(np.array([0., 5.]), np.array([1., 2.]), np.array(target))


def test_quantile_diagnostics_keep_negative_crossing_and_nonfinite_outputs():
    class Broken(FakeForecaster):
        def forecast(self, *args, **kwargs):
            output = super().forecast(*args, **kwargs)
            output.quantiles[0, 0, 0, :] = -2.
            output.quantiles[0, 0, 1, 0] = np.inf
            output.quantiles[0, 0, 2, 5] = 1000
            return output

    result = TimestralAdapter(Broken(), model_revision="synthetic").forecast(
        np.array([0., 1.]), np.array([1., 2.]), np.array([2., 3., 4.]))
    assert (result.quantiles[0] == -2).all()  # no clipping
    assert result.diagnostics["negative_medians"] == 1
    assert result.diagnostics["nonfinite_targets"] == 1
    assert result.diagnostics["crossed_targets"] >= 1
    assert result.diagnostics["valid_quantiles"] == [True, False, False]


def test_forecast_has_no_future_value_argument_and_is_translation_invariant():
    model = FakeForecaster()
    adapter = TimestralAdapter(model, model_revision="synthetic")
    a = adapter.forecast(np.array([0., 5.]), np.array([1., 2.]), np.array([7., 12.]))
    b = adapter.forecast(np.array([100., 105.]), np.array([1., 2.]), np.array([107., 112.]))
    np.testing.assert_array_equal(a.quantiles, b.quantiles)


def test_weight_revision_must_be_immutable_before_import_or_download():
    with pytest.raises(ValueError, match="immutable"):
        TimestralAdapter.from_pretrained("main")


def test_optional_loading_pins_weights_and_disables_upstream_quantile_cap(monkeypatch, tmp_path):
    calls = []

    class Loader:
        @staticmethod
        def from_pretrained(model, **kwargs):
            calls.append((model, kwargs))
            return FakeForecaster()

    monkeypatch.setitem(sys.modules, "timestral", SimpleNamespace(TimestralForecaster=Loader))
    revision = "a"*40
    adapter = TimestralAdapter.from_pretrained(revision, cache_dir=tmp_path, local_files_only=True)
    model, options = calls[0]
    assert model == "mistralai/Timestral-5M"
    assert options["revision"] == revision
    assert options["quantile_real_cap_k"] == 0.
    assert options["local_files_only"] is True
    assert options["cache_dir"] == tmp_path
    assert adapter.model_revision == revision


def test_unexpected_levels_are_not_relabelled():
    class Wrong(FakeForecaster):
        def forecast(self, *args, **kwargs):
            output = super().forecast(*args, **kwargs)
            output.quantile_levels = np.linspace(.01, .99, 21)
            return output

    with pytest.raises(ValueError, match="21 quantile levels"):
        TimestralAdapter(Wrong(), model_revision="synthetic").forecast(
            np.array([0., 1.]), np.array([1., 2.]), np.array([2.]))
