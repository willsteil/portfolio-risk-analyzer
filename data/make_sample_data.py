"""Generate the synthetic demo dataset in data/sample_prices.csv.

The prices are NOT real market data. They are simulated with a one-factor
model so the app can be launched and graded without an internet connection or
API key:

    r_i,t = beta_i * market_t + idio_i,t      (daily)

with market volatility and two calm/stressed regimes so drawdowns look
realistic. Each ticker's drift, beta and idiosyncratic volatility are rough,
hand-picked approximations of how that kind of asset tends to behave. A fixed
random seed makes the file reproducible.

Run:  python data/make_sample_data.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
START, END = "2022-01-03", "2026-09-30"

# ticker: (annual drift, market beta, annual idiosyncratic vol, start price)
ASSETS = {
    "SPY":  (0.10, 1.00, 0.00, 470.0),
    "QQQ":  (0.13, 1.20, 0.05, 400.0),
    "AAPL": (0.14, 1.15, 0.18, 180.0),
    "MSFT": (0.15, 1.10, 0.17, 330.0),
    "NVDA": (0.40, 1.70, 0.38, 300.0),
    "AMZN": (0.13, 1.25, 0.24, 170.0),
    "GOOGL": (0.13, 1.10, 0.21, 145.0),
    "META": (0.20, 1.30, 0.30, 330.0),
    "TSLA": (0.18, 1.60, 0.45, 390.0),
    "JPM":  (0.12, 0.95, 0.16, 160.0),
    "XOM":  (0.09, 0.60, 0.22, 62.0),
    "JNJ":  (0.05, 0.50, 0.13, 170.0),
    "KO":   (0.06, 0.55, 0.11, 60.0),
    "TLT":  (0.00, -0.20, 0.13, 140.0),
    "GLD":  (0.07, 0.10, 0.13, 170.0),
    "IWM":  (0.07, 1.10, 0.10, 220.0),
}


def main() -> None:
    rng = np.random.default_rng(SEED)
    dates = pd.bdate_range(START, END)
    n = len(dates)

    # Market factor with volatility regimes (calm ~14%, stressed ~28% annualized).
    regime = np.zeros(n, dtype=bool)
    i = 0
    while i < n:
        length = rng.integers(60, 250)
        stressed = rng.random() < 0.3
        regime[i:i + length] = stressed
        i += length
    mkt_vol = np.where(regime, 0.28, 0.14) / np.sqrt(252)
    mkt_drift = np.where(regime, -0.10, 0.16) / 252
    market = mkt_drift + mkt_vol * rng.standard_normal(n)

    prices = {}
    for t, (mu, b, idio, p0) in ASSETS.items():
        eps = idio / np.sqrt(252) * rng.standard_t(df=5, size=n) * np.sqrt(3 / 5)  # fat tails, unit variance
        alpha = mu / 252 - b * market.mean()
        r = alpha + b * market + eps
        prices[t] = p0 * np.cumprod(1 + r)

    df = pd.DataFrame(prices, index=dates).round(2)
    df.index.name = "Date"
    out = Path(__file__).resolve().parent / "sample_prices.csv"
    df.to_csv(out)
    print(f"Wrote {out} ({n} days x {len(ASSETS)} tickers)")


if __name__ == "__main__":
    main()
