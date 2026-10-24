"""Checks the financial math against values worked out by hand."""

import numpy as np
import pandas as pd
import pytest

from analyzer import metrics as m


def make_prices(values: dict[str, list[float]]) -> pd.DataFrame:
    n = len(next(iter(values.values())))
    return pd.DataFrame(values, index=pd.bdate_range("2024-01-01", periods=n))


# --- weights -----------------------------------------------------------------
def test_dollar_amounts_become_weights():
    w = m.normalize_weights({"AAPL": 4000, "MSFT": 3500, "SPY": 2500})
    assert w == pytest.approx({"AAPL": 0.40, "MSFT": 0.35, "SPY": 0.25})


def test_percent_weights_not_summing_to_100_are_rescaled():
    w = m.normalize_weights({"A": 50, "B": 50, "C": 100})
    assert w == pytest.approx({"A": 0.25, "B": 0.25, "C": 0.5})


def test_zero_weights_dropped_and_all_zero_rejected():
    assert m.normalize_weights({"A": 1, "B": 0}) == {"A": 1.0}
    with pytest.raises(m.MetricsError):
        m.normalize_weights({"A": 0, "B": 0})


def test_negative_weight_rejected():
    with pytest.raises(m.MetricsError):
        m.normalize_weights({"A": 10, "B": -5})


# --- returns -----------------------------------------------------------------
def test_buy_and_hold_value_by_hand():
    # A doubles, B stays flat. 50/50 buy-and-hold ends at 0.5*2 + 0.5*1 = 1.5
    px = make_prices({"A": [10, 15, 20], "B": [50, 50, 50]})
    v = m.portfolio_value(px, {"A": 0.5, "B": 0.5}, "buy_and_hold")
    assert v.tolist() == pytest.approx([1.0, 1.25, 1.5])


def test_daily_rebalanced_value_by_hand():
    # Day 1: A +50%, B 0% -> +25%. Day 2: A +33.33%, B 0% -> +16.67%. 1.25 * 1.16667 = 1.458333
    px = make_prices({"A": [10, 15, 20], "B": [50, 50, 50]})
    v = m.portfolio_value(px, {"A": 0.5, "B": 0.5}, "rebalanced")
    assert v.iloc[-1] == pytest.approx(1.25 * (1 + 0.5 * (20 / 15 - 1)))


def test_cagr():
    # 253 prices = 252 daily periods = exactly one year; +10% total -> 10% CAGR
    v = pd.Series(np.linspace(100, 110, 253))
    assert m.annualized_return(v) == pytest.approx(0.10)
    # two years of periods, +21% total -> 10% a year
    v2 = pd.Series(np.linspace(100, 121, 505))
    assert m.annualized_return(v2) == pytest.approx(0.10)


def test_volatility_annualizes_with_sqrt_252():
    r = pd.Series([0.01, -0.01] * 50)
    assert m.annualized_volatility(r) == pytest.approx(r.std(ddof=1) * np.sqrt(252))


def test_sharpe_by_hand():
    r = pd.Series([0.002, 0.0, 0.001, -0.001, 0.003])
    rf = 0.0252  # 0.0001 per day
    excess = r - 0.0001
    expected = excess.mean() / excess.std(ddof=1) * np.sqrt(252)
    assert m.sharpe_ratio(r, rf) == pytest.approx(expected)


def test_sharpe_constant_returns_is_nan_not_crash():
    assert np.isnan(m.sharpe_ratio(pd.Series([0.001] * 10), 0.0))


# --- drawdown ----------------------------------------------------------------
def test_max_drawdown_by_hand():
    # Peak 120 -> trough 90 is -25%; recovers when it gets back to 120
    v = pd.Series([100, 120, 90, 100, 125, 110], index=pd.bdate_range("2024-01-01", periods=6))
    dd = m.max_drawdown(v)
    assert dd.depth == pytest.approx(-0.25)
    assert dd.peak_date == v.index[1]
    assert dd.trough_date == v.index[2]
    assert dd.recovery_date == v.index[4]


def test_drawdown_never_recovered():
    v = pd.Series([100, 80, 90], index=pd.bdate_range("2024-01-01", periods=3))
    assert m.max_drawdown(v).recovery_date is None


def test_drawdown_zero_for_rising_series():
    v = pd.Series([1, 2, 3, 4.0])
    assert m.max_drawdown(v).depth == 0


# --- benchmark relative --------------------------------------------------------
def test_beta_of_scaled_returns():
    rng = np.random.default_rng(0)
    b = pd.Series(rng.normal(0, 0.01, 500))
    assert m.beta(2 * b, b) == pytest.approx(2.0)
    assert m.beta(b, b) == pytest.approx(1.0)
    assert m.tracking_error(b, b) == pytest.approx(0.0)


# --- concentration -------------------------------------------------------------
def test_effective_holdings():
    assert m.effective_holdings({"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}) == pytest.approx(3.0)
    assert m.effective_holdings({"A": 0.4, "B": 0.35, "C": 0.25}) == pytest.approx(1 / (0.16 + 0.1225 + 0.0625))


def test_risk_contributions_sum_to_one_and_match_formula():
    rng = np.random.default_rng(1)
    rets = pd.DataFrame(rng.normal(0, [0.01, 0.02, 0.03], size=(400, 3)), columns=["A", "B", "C"])
    w = {"A": 0.5, "B": 0.3, "C": 0.2}
    rc = m.risk_contributions(rets, w)
    assert rc.sum() == pytest.approx(1.0)
    # Uncorrelated assets: RC_i ≈ w_i² σ_i² / Σ w_j² σ_j²
    var = rets.var().to_numpy()
    wv = np.array(list(w.values()))
    approx = wv ** 2 * var / (wv ** 2 * var).sum()
    assert rc.to_numpy() == pytest.approx(approx, abs=0.05)


def test_equal_vol_uncorrelated_equal_weight_has_equal_risk():
    rng = np.random.default_rng(2)
    rets = pd.DataFrame(rng.normal(0, 0.01, size=(5000, 3)), columns=list("ABC"))
    rc = m.risk_contributions(rets, {t: 1 / 3 for t in "ABC"})
    assert rc.to_numpy() == pytest.approx([1 / 3] * 3, abs=0.03)


def test_diversification_ratio_is_one_for_identical_assets():
    r = pd.Series(np.random.default_rng(3).normal(0, 0.01, 300))
    rets = pd.DataFrame({"A": r, "B": r})
    assert m.diversification_ratio(rets, {"A": 0.5, "B": 0.5}) == pytest.approx(1.0)


def test_var_is_fifth_percentile():
    r = pd.Series(np.arange(-50, 50) / 1000)  # -5.0% .. +4.9%
    assert m.value_at_risk(r, 0.95) == pytest.approx(np.percentile(r, 5))


# --- guard rails ------------------------------------------------------------------
def test_too_little_history_raises():
    px = make_prices({"A": [10], "B": [20]})
    with pytest.raises(m.MetricsError):
        m.portfolio_value(px, {"A": 0.5, "B": 0.5})


def test_unknown_method_raises():
    px = make_prices({"A": [10, 11], "B": [20, 21]})
    with pytest.raises(m.MetricsError):
        m.portfolio_value(px, {"A": 0.5, "B": 0.5}, "monthly")
