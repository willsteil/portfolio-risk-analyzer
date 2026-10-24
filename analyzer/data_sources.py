"""Data access: Finnhub (quotes + company profiles), Yahoo Finance via yfinance
(historical prices), FRED (risk-free rate), and a bundled demo dataset.

Why three sources: Finnhub's free tier covers real-time quotes and company
profiles, but its historical candle endpoint (/stock/candle) is a premium
feature. The assignment allows "a permitted free historical-price source", so
historical prices come from Yahoo Finance through the open-source yfinance
library. The 3-month Treasury bill rate comes from FRED's public CSV endpoint,
which needs no API key.

Every function raises DataSourceError with a readable message instead of
crashing, so the app can show a warning and keep running.
"""

from __future__ import annotations

import io
import os
from datetime import date
from pathlib import Path

import pandas as pd
import requests

FINNHUB_BASE = "https://finnhub.io/api/v1"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
SAMPLE_FILE = Path(__file__).resolve().parent.parent / "data" / "sample_prices.csv"
TIMEOUT = 10


class DataSourceError(RuntimeError):
    """Raised when a data provider can't return usable data."""


def clean_ticker(raw: str) -> str:
    """Upper-case, strip spaces; reject anything that can't be a ticker."""
    t = (raw or "").strip().upper()
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-^")
    if not t or len(t) > 10 or any(ch not in allowed for ch in t):
        raise DataSourceError(f"'{raw}' doesn't look like a valid ticker symbol.")
    return t


def parse_holdings(table: pd.DataFrame) -> tuple[dict[str, float], list[str]]:
    """Read the holdings editor table into {ticker: amount}.

    Skips blank rows, merges duplicate tickers, drops zero amounts and collects a
    readable message for every row it can't use (bad symbol, negative or
    non-numeric amount) instead of raising.
    """
    amounts: dict[str, float] = {}
    errors: list[str] = []
    for _, row in table.iterrows():
        raw_t = row.get("Ticker")
        if raw_t is None or (isinstance(raw_t, float) and pd.isna(raw_t)) or str(raw_t).strip() == "":
            continue
        try:
            t = clean_ticker(str(raw_t))
        except DataSourceError as e:
            errors.append(str(e))
            continue
        val = row.get("Amount")
        try:
            val = 0.0 if val is None or pd.isna(val) else float(val)
        except (TypeError, ValueError):
            errors.append(f"{t}: amount '{val}' isn't a number.")
            continue
        if val < 0:
            errors.append(f"{t}: negative amounts aren't supported (no short positions), so it was skipped.")
            continue
        amounts[t] = amounts.get(t, 0.0) + val
    return {t: v for t, v in amounts.items() if v > 0}, errors


# ---------------------------------------------------------------------------
# Finnhub
# ---------------------------------------------------------------------------
def get_finnhub_key() -> str | None:
    """API key from Streamlit secrets or the FINNHUB_API_KEY environment variable. Never hard-coded."""
    try:
        import streamlit as st
        key = st.secrets.get("FINNHUB_API_KEY")  # type: ignore[attr-defined]
        if key:
            return str(key)
    except Exception:
        pass
    return os.environ.get("FINNHUB_API_KEY") or None


def _finnhub_get(path: str, params: dict, api_key: str) -> dict:
    try:
        resp = requests.get(f"{FINNHUB_BASE}{path}", params={**params, "token": api_key}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise DataSourceError(f"Couldn't reach Finnhub ({exc.__class__.__name__}).") from exc
    if resp.status_code == 401:
        raise DataSourceError("Finnhub rejected the API key. Check FINNHUB_API_KEY.")
    if resp.status_code == 429:
        raise DataSourceError("Finnhub rate limit hit (free tier is 60 calls/minute). Wait a minute and retry.")
    if resp.status_code == 403:
        raise DataSourceError("That Finnhub endpoint isn't available on the free plan.")
    if resp.status_code != 200:
        raise DataSourceError(f"Finnhub returned HTTP {resp.status_code}.")
    try:
        return resp.json()
    except ValueError as exc:
        raise DataSourceError("Finnhub sent a response that wasn't valid JSON.") from exc


def finnhub_quote(symbol: str, api_key: str) -> dict:
    """Latest quote. Finnhub fields: c=current, d=change, dp=% change, h/l/o=day high/low/open, pc=prev close."""
    data = _finnhub_get("/quote", {"symbol": symbol}, api_key)
    if not data or not data.get("c"):
        # Finnhub answers unknown symbols with all zeros rather than an error.
        raise DataSourceError(f"No quote found for {symbol}.")
    return {
        "price": data["c"], "change": data.get("d"), "change_pct": data.get("dp"),
        "high": data.get("h"), "low": data.get("l"), "open": data.get("o"), "prev_close": data.get("pc"),
        "timestamp": pd.to_datetime(data.get("t", 0), unit="s") if data.get("t") else None,
    }


def finnhub_profile(symbol: str, api_key: str) -> dict:
    """Company profile (name, industry, market cap). ETFs usually return an empty profile on the free tier."""
    data = _finnhub_get("/stock/profile2", {"symbol": symbol}, api_key)
    if not data:
        return {}
    return {
        "name": data.get("name"), "industry": data.get("finnhubIndustry"), "exchange": data.get("exchange"),
        "market_cap_m": data.get("marketCapitalization"), "country": data.get("country"),
        "ipo": data.get("ipo"), "logo": data.get("logo"), "weburl": data.get("weburl"),
    }


# ---------------------------------------------------------------------------
# Historical prices (Yahoo Finance via yfinance)
# ---------------------------------------------------------------------------
def fetch_price_history(tickers: list[str], start: date, end: date) -> tuple[pd.DataFrame, list[str]]:
    """Daily adjusted close prices. Returns (prices, tickers_with_no_data)."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise DataSourceError("yfinance isn't installed. Run: pip install -r requirements.txt") from exc
    try:
        raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False,
                          group_by="column", threads=True)
    except Exception as exc:  # yfinance raises many different exception types
        raise DataSourceError(f"Yahoo Finance download failed ({exc.__class__.__name__}).") from exc
    if raw is None or raw.empty:
        raise DataSourceError("Yahoo Finance returned no price data. Check the tickers, dates and your connection.")

    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:  # single ticker
        prices = raw[["Close"]].rename(columns={"Close": tickers[0]})
    prices = prices.reindex(columns=tickers)
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    missing = [t for t in tickers if t not in prices or prices[t].dropna().shape[0] < 2]
    prices = prices.drop(columns=missing).ffill(limit=3)  # bridge occasional single missing days
    return prices, missing


# ---------------------------------------------------------------------------
# Risk-free rate (FRED)
# ---------------------------------------------------------------------------
def fetch_risk_free_rate(series: str = "DGS3MO") -> tuple[float, str]:
    """Latest 3-month Treasury yield from FRED, as a decimal. Returns (rate, as_of_date)."""
    try:
        resp = requests.get(FRED_CSV.format(series=series), timeout=TIMEOUT)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
    except Exception as exc:
        raise DataSourceError(f"Couldn't load {series} from FRED ({exc.__class__.__name__}).") from exc
    df.columns = ["date", "value"]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")  # FRED uses "." for holidays
    df = df.dropna()
    if df.empty:
        raise DataSourceError(f"FRED returned no values for {series}.")
    last = df.iloc[-1]
    return float(last["value"]) / 100, str(last["date"])


# ---------------------------------------------------------------------------
# Demo dataset
# ---------------------------------------------------------------------------
def load_sample_prices() -> pd.DataFrame:
    """Bundled synthetic prices (see data/README.md). Lets the app run with no internet or API key."""
    if not SAMPLE_FILE.exists():
        raise DataSourceError("Demo dataset is missing. Run: python data/make_sample_data.py")
    df = pd.read_csv(SAMPLE_FILE, index_col=0, parse_dates=True)
    return df.sort_index()
