"""Financial calculations for the Portfolio Risk Analyzer.

Every function here is pure (no network, no Streamlit) so it can be unit-tested
and checked by hand. Prices are daily adjusted closes; returns are simple
(arithmetic) daily returns. Annualization assumes 252 trading days per year.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252


class MetricsError(ValueError):
    """Raised when inputs are not usable for a calculation."""


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
def normalize_weights(amounts: dict[str, float]) -> dict[str, float]:
    """Turn dollar amounts (or raw weights) into weights that sum to 1.

    Works for either input mode: $4,000 / $3,500 / $2,500 and 40 / 35 / 25
    both become 0.40 / 0.35 / 0.25.
    """
    clean = {}
    for ticker, value in amounts.items():
        if value is None or (isinstance(value, float) and np.isnan(value)):
            continue
        value = float(value)
        if value < 0:
            raise MetricsError(f"{ticker}: amounts and weights can't be negative (no short positions).")
        if value > 0:
            clean[ticker] = value
    total = sum(clean.values())
    if total <= 0:
        raise MetricsError("Enter a positive amount or weight for at least one holding.")
    return {t: v / total for t, v in clean.items()}


def daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Simple daily returns: r_t = P_t / P_{t-1} - 1."""
    return prices.sort_index().pct_change().dropna(how="all")


# ---------------------------------------------------------------------------
# Portfolio construction
# ---------------------------------------------------------------------------
def portfolio_value(prices: pd.DataFrame, weights: dict[str, float], method: str = "buy_and_hold",
                    start_value: float = 1.0) -> pd.Series:
    """Growth of a portfolio over time.

    method="buy_and_hold": buy the starting weights once and let them drift.
    method="rebalanced":   reset to the target weights every day.
    """
    tickers = list(weights)
    px = prices[tickers].dropna()
    if len(px) < 2:
        raise MetricsError("Not enough overlapping price history for these holdings.")
    w = np.array([weights[t] for t in tickers])

    if method == "buy_and_hold":
        rel = px / px.iloc[0]                      # each asset's growth of $1
        value = (rel * w).sum(axis=1) * start_value
    elif method == "rebalanced":
        rets = px.pct_change().dropna()
        port = rets.to_numpy() @ w
        value = pd.Series(np.concatenate([[1.0], np.cumprod(1 + port)]) * start_value, index=px.index)
    else:
        raise MetricsError(f"Unknown rebalancing method: {method}")
    value.name = "Portfolio"
    return value


def series_returns(value: pd.Series) -> pd.Series:
    return value.pct_change().dropna()


# ---------------------------------------------------------------------------
# Return and risk measures
# ---------------------------------------------------------------------------
def total_return(value: pd.Series) -> float:
    return float(value.iloc[-1] / value.iloc[0] - 1)


def annualized_return(value: pd.Series) -> float:
    """Compound annual growth rate (CAGR)."""
    periods = len(value) - 1
    if periods <= 0:
        raise MetricsError("Need at least two prices to compute a return.")
    return float((value.iloc[-1] / value.iloc[0]) ** (TRADING_DAYS / periods) - 1)


def annualized_volatility(returns: pd.Series) -> float:
    """Sample standard deviation of daily returns x sqrt(252)."""
    return float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS))


def sharpe_ratio(returns: pd.Series, risk_free_rate: float) -> float:
    """Annualized Sharpe ratio = mean daily excess return / daily std x sqrt(252)."""
    excess = returns - risk_free_rate / TRADING_DAYS
    sd = excess.std(ddof=1)
    if np.isnan(sd) or sd < 1e-12:
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(TRADING_DAYS))


def sortino_ratio(returns: pd.Series, risk_free_rate: float) -> float:
    """Like Sharpe, but only penalizes downside deviation (returns below the risk-free rate)."""
    excess = returns - risk_free_rate / TRADING_DAYS
    downside = np.minimum(excess, 0)
    dd = np.sqrt((downside ** 2).mean())
    if np.isnan(dd) or dd < 1e-12:
        return float("nan")
    return float(excess.mean() / dd * np.sqrt(TRADING_DAYS))


def drawdown_series(value: pd.Series) -> pd.Series:
    """Percent below the running peak at each date (0 at new highs, negative otherwise)."""
    return value / value.cummax() - 1


@dataclass
class Drawdown:
    depth: float            # e.g. -0.23 for a 23% drawdown
    peak_date: pd.Timestamp
    trough_date: pd.Timestamp
    recovery_date: pd.Timestamp | None   # None = not recovered by end of sample


def max_drawdown(value: pd.Series) -> Drawdown:
    dd = drawdown_series(value)
    trough = dd.idxmin()
    peak = value.loc[:trough].idxmax()
    after = value.loc[trough:]
    recovered = after[after >= value.loc[peak]]
    return Drawdown(float(dd.min()), peak, trough, recovered.index[0] if len(recovered) else None)


def beta(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """Sensitivity to the benchmark: Cov(Rp, Rb) / Var(Rb)."""
    joined = pd.concat([returns, benchmark_returns], axis=1).dropna()
    var_b = joined.iloc[:, 1].var(ddof=1)
    if var_b == 0 or np.isnan(var_b):
        return float("nan")
    return float(joined.iloc[:, 0].cov(joined.iloc[:, 1]) / var_b)


def tracking_error(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    diff = (returns - benchmark_returns).dropna()
    return float(diff.std(ddof=1) * np.sqrt(TRADING_DAYS))


def value_at_risk(returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical one-day VaR: the daily loss not exceeded on `confidence` of days (as a negative return)."""
    return float(np.percentile(returns.dropna(), (1 - confidence) * 100))


def rolling_volatility(returns: pd.Series, window: int = 63) -> pd.Series:
    """Rolling annualized volatility (63 trading days ≈ 3 months)."""
    return returns.rolling(window).std(ddof=1) * np.sqrt(TRADING_DAYS)


# ---------------------------------------------------------------------------
# Concentration and diversification
# ---------------------------------------------------------------------------
def effective_holdings(weights: dict[str, float]) -> float:
    """1 / sum(w^2) — the 'effective number' of equally sized positions (inverse HHI)."""
    w = np.array(list(weights.values()))
    return float(1 / np.sum(w ** 2))


def risk_contributions(asset_returns: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Each holding's share of total portfolio variance (sums to 1).

    RC_i = w_i * (Σw)_i / (wᵀΣw). A holding can carry far more risk than its weight.
    """
    tickers = list(weights)
    cov = asset_returns[tickers].dropna().cov().to_numpy()
    w = np.array([weights[t] for t in tickers])
    port_var = float(w @ cov @ w)
    if port_var == 0:
        raise MetricsError("Portfolio variance is zero; can't split risk.")
    rc = w * (cov @ w) / port_var
    return pd.Series(rc, index=tickers, name="Risk contribution")


def diversification_ratio(asset_returns: pd.DataFrame, weights: dict[str, float]) -> float:
    """Weighted average of individual volatilities / portfolio volatility. 1.0 = no diversification benefit."""
    tickers = list(weights)
    r = asset_returns[tickers].dropna()
    w = np.array([weights[t] for t in tickers])
    port_sd = float(np.sqrt(w @ r.cov().to_numpy() @ w))
    return float((w * r.std(ddof=1).to_numpy()).sum() / port_sd)


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------
def summarize(value: pd.Series, risk_free_rate: float, benchmark_value: pd.Series | None = None) -> dict:
    """All headline statistics for one growth series."""
    r = series_returns(value)
    mdd = max_drawdown(value)
    out = {
        "Total return": total_return(value),
        "Annualized return": annualized_return(value),
        "Annualized volatility": annualized_volatility(r),
        "Sharpe ratio": sharpe_ratio(r, risk_free_rate),
        "Sortino ratio": sortino_ratio(r, risk_free_rate),
        "Max drawdown": mdd.depth,
        "1-day VaR (95%)": value_at_risk(r, 0.95),
        "_drawdown": mdd,
    }
    if benchmark_value is not None:
        br = series_returns(benchmark_value)
        out["Beta"] = beta(r, br)
        out["Tracking error"] = tracking_error(r, br)
    return out


def asset_table(prices: pd.DataFrame, weights: dict[str, float], risk_free_rate: float) -> pd.DataFrame:
    """Per-holding statistics plus each holding's weight and share of portfolio risk."""
    rets = daily_returns(prices[list(weights)].dropna())
    rc = risk_contributions(rets, weights)
    rows = []
    for t in weights:
        v = prices[t].dropna()
        r = rets[t]
        rows.append({
            "Ticker": t,
            "Weight": weights[t],
            "Risk share": rc[t],
            "Annualized return": annualized_return(v),
            "Annualized volatility": annualized_volatility(r),
            "Sharpe ratio": sharpe_ratio(r, risk_free_rate),
            "Max drawdown": max_drawdown(v).depth,
        })
    return pd.DataFrame(rows).set_index("Ticker")


def plain_language_assessment(port: dict, bench: dict, weights: dict[str, float], rc: pd.Series,
                              benchmark: str, corr: pd.DataFrame) -> list[str]:
    """Short, data-backed observations for the user. Educational, not advice."""
    notes = []
    # Return vs benchmark
    gap = port["Annualized return"] - bench["Annualized return"]
    notes.append(
        f"The portfolio returned {port['Annualized return']:.1%} a year versus {bench['Annualized return']:.1%} "
        f"for {benchmark} ({'ahead' if gap >= 0 else 'behind'} by {abs(gap):.1%} a year)."
    )
    # Risk vs benchmark
    vol_ratio = port["Annualized volatility"] / bench["Annualized volatility"]
    notes.append(
        f"Its volatility was {port['Annualized volatility']:.1%}, about {vol_ratio:.2f}x the benchmark's. "
        f"A beta of {port.get('Beta', float('nan')):.2f} means a 1% move in {benchmark} came with a "
        f"{port.get('Beta', float('nan')):.2f}% move in the portfolio on average."
    )
    # Risk-adjusted
    better = port["Sharpe ratio"] > bench["Sharpe ratio"]
    notes.append(
        f"On a risk-adjusted basis (Sharpe {port['Sharpe ratio']:.2f} vs {bench['Sharpe ratio']:.2f}) the portfolio "
        f"was {'more' if better else 'less'} efficient than simply holding {benchmark}."
    )
    # Drawdown
    notes.append(
        f"The worst peak-to-trough loss was {port['Max drawdown']:.1%} (benchmark: {bench['Max drawdown']:.1%})."
    )
    # Concentration
    top = rc.idxmax()
    if rc[top] - weights[top] > 0.05:
        notes.append(
            f"Concentration: {top} is {weights[top]:.0%} of the money but {rc[top]:.0%} of the risk, "
            f"so it drives most of the portfolio's swings."
        )
    eff = effective_holdings(weights)
    notes.append(f"With {len(weights)} holdings the portfolio behaves like {eff:.1f} equally sized positions.")
    # Correlation
    if len(corr) > 1:
        c = corr.where(~np.eye(len(corr), dtype=bool)).stack()
        pair = c.idxmax()
        if c.max() > 0.8:
            notes.append(
                f"{pair[0]} and {pair[1]} moved together closely (correlation {c.max():.2f}), "
                f"so holding both adds less diversification than it seems."
            )
    return notes
