"""Synthetic curves only: no experimental performance assertions."""

import numpy as np
import pytest
from scipy.optimize._numdiff import approx_derivative

from tumortwin.baselines.models import MODELS, curve, fit_model, jacobian


@pytest.mark.parametrize("model,parameters", [
    ("exponential", [20., .1]), ("exponential", [20., -.1]),
    ("logistic", [20., .15, 200.]), ("logistic", [200., .15, 20.]),
    ("gompertz", [20., .15, 200.]), ("gompertz", [200., .15, 20.]),
])
def test_analytic_curves_derivatives_and_forecasts(model, parameters):
    days = np.array([0., 2, 5, 8, 12, 18, 25, 35])
    p = np.asarray(parameters)
    y = curve(model, days, p)
    assert y[0] == pytest.approx(p[0])
    np.testing.assert_allclose(jacobian(model, days, p),
                               approx_derivative(lambda q: curve(model, days, q), p),
                               rtol=2e-5, atol=1e-5)
    fit = fit_model(model, days+7, y)
    assert fit.success
    np.testing.assert_allclose(fit.predict(np.array([47., 57.])), curve(model, np.array([40., 50.]), p),
                               rtol=2e-3, atol=1e-3)
    shifted = fit_model(model, days+100, y)
    np.testing.assert_allclose(shifted.predict(np.array([140., 150.])),
                               fit.predict(np.array([47., 57.])), rtol=1e-8)


@pytest.mark.parametrize("model", MODELS)
def test_constant_history(model):
    fit = fit_model(model, np.arange(8.), np.full(8, 20.))
    assert fit.success
    assert fit.predict(np.array([10.]))[0] == pytest.approx(20., rel=1e-4)


def test_persistence_zero_and_unidentifiable_zeros():
    for model in MODELS:
        fit = fit_model(model, np.arange(6.), np.zeros(6))
        if model == "persistence":
            assert fit.predict(np.array([9.]))[0] == 0
        else:
            assert not fit.success
            assert fit.status == "all_zero_unidentifiable"
            assert np.isnan(fit.predict(np.array([9.]))[0])


def test_partial_zeros_are_not_imputed():
    y = np.array([0., 1., 2., 3., 4., 5.])
    before = y.copy()
    fit = fit_model("exponential", np.arange(6.), y)
    assert fit.success
    np.testing.assert_array_equal(y, before)


def test_failed_solver_is_not_silently_persistence():
    fit = fit_model("gompertz", np.arange(6.), np.arange(6.)+1, {"max_nfev": 1})
    assert not fit.success
    assert np.isnan(fit.predict(np.array([9.]))[0])
    assert len(fit.starts) == 12


def test_flat_curve_identifiability_and_extreme_forecast():
    fit = fit_model("logistic", np.arange(8.), np.full(8, 10.))
    assert fit.success and fit.ill_conditioned
    fit = fit_model("exponential", np.arange(6.), 10*np.exp(.2*np.arange(6.)))
    pred = fit.predict(np.array([8., 10000.]))
    assert np.isfinite(pred[0]) and np.isnan(pred[1])


@pytest.mark.parametrize("days,volumes", [([0, 0, 2], [1, 2, 3]),
    ([2, 1, 0], [1, 2, 3]), ([0, 1, 2], [1, -1, 3]), ([0, 1, 2], [1, np.nan, 3])])
def test_invalid_contexts_fail_explicitly(days, volumes):
    with pytest.raises(ValueError):
        fit_model("exponential", np.array(days), np.array(volumes))
