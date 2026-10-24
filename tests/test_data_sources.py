"""Data-layer tests. Network calls are mocked, so these run offline and never use a real API key."""

from unittest import mock

import pandas as pd
import pytest
import requests

from analyzer import data_sources as ds


class FakeResp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload, text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


# --- tickers and the holdings table --------------------------------------------------
@pytest.mark.parametrize("raw,clean", [(" aapl ", "AAPL"), ("brk.b", "BRK.B"), ("^gspc", "^GSPC")])
def test_clean_ticker(raw, clean):
    assert ds.clean_ticker(raw) == clean


@pytest.mark.parametrize("bad", ["", "  ", "AA PL", "$SPY", "TOOLONGTICKER"])
def test_clean_ticker_rejects_bad_symbols(bad):
    with pytest.raises(ds.DataSourceError):
        ds.clean_ticker(bad)


def test_parse_holdings_merges_skips_and_reports():
    table = pd.DataFrame({
        "Ticker": ["aapl", "AAPL", "msft", None, "", "b@d", "spy", "nvda", "xom"],
        "Amount": [1000, 500, 2000, 300, 300, 100, None, -50, "abc"],
    })
    amounts, errors = ds.parse_holdings(table)
    assert amounts == {"AAPL": 1500.0, "MSFT": 2000.0}   # merged; SPY had no amount so dropped
    assert len(errors) == 3                               # b@d, negative NVDA, non-numeric XOM
    assert any("NVDA" in e for e in errors) and any("XOM" in e for e in errors)


# --- Finnhub ---------------------------------------------------------------------------
def test_finnhub_quote_parses_fields():
    payload = {"c": 230.1, "d": 1.5, "dp": 0.656, "h": 231, "l": 228, "o": 229, "pc": 228.6, "t": 1761250000}
    with mock.patch.object(ds.requests, "get", return_value=FakeResp(200, payload)) as g:
        q = ds.finnhub_quote("AAPL", "test-key")
    assert q["price"] == 230.1 and q["change_pct"] == 0.656
    assert g.call_args.kwargs["params"] == {"symbol": "AAPL", "token": "test-key"}


def test_finnhub_unknown_symbol_all_zeros():
    with mock.patch.object(ds.requests, "get", return_value=FakeResp(200, {"c": 0, "d": None, "dp": None})):
        with pytest.raises(ds.DataSourceError, match="No quote"):
            ds.finnhub_quote("ZZZZ", "k")


@pytest.mark.parametrize("status,msg", [(401, "API key"), (429, "rate limit"), (403, "free plan"), (500, "500")])
def test_finnhub_http_errors(status, msg):
    with mock.patch.object(ds.requests, "get", return_value=FakeResp(status, {})):
        with pytest.raises(ds.DataSourceError, match=msg):
            ds.finnhub_quote("AAPL", "k")


def test_finnhub_network_down():
    with mock.patch.object(ds.requests, "get", side_effect=requests.ConnectionError()):
        with pytest.raises(ds.DataSourceError, match="Couldn't reach"):
            ds.finnhub_quote("AAPL", "k")


def test_finnhub_empty_profile_for_etf():
    with mock.patch.object(ds.requests, "get", return_value=FakeResp(200, {})):
        assert ds.finnhub_profile("SPY", "k") == {}


# --- FRED ---------------------------------------------------------------------------------
def test_fred_skips_holiday_dots():
    csv = "observation_date,DGS3MO\n2026-10-20,4.02\n2026-10-21,4.01\n2026-10-22,.\n"
    with mock.patch.object(ds.requests, "get", return_value=FakeResp(200, text=csv)):
        rate, as_of = ds.fetch_risk_free_rate()
    assert rate == pytest.approx(0.0401) and as_of == "2026-10-21"


def test_fred_down():
    with mock.patch.object(ds.requests, "get", side_effect=requests.Timeout()):
        with pytest.raises(ds.DataSourceError):
            ds.fetch_risk_free_rate()


# --- yfinance -------------------------------------------------------------------------------
def test_price_history_reports_missing_tickers():
    idx = pd.bdate_range("2025-01-01", periods=5)
    cols = pd.MultiIndex.from_product([["Close", "Open"], ["AAPL", "MSFT", "FAKE"]])
    raw = pd.DataFrame(1.0, index=idx, columns=cols)
    raw[("Close", "FAKE")] = float("nan")
    with mock.patch("yfinance.download", return_value=raw):
        prices, missing = ds.fetch_price_history(["AAPL", "MSFT", "FAKE"], idx[0], idx[-1])
    assert list(prices.columns) == ["AAPL", "MSFT"] and missing == ["FAKE"]


def test_price_history_empty_raises():
    with mock.patch("yfinance.download", return_value=pd.DataFrame()):
        with pytest.raises(ds.DataSourceError, match="no price data"):
            ds.fetch_price_history(["AAPL"], "2025-01-01", "2025-02-01")


def test_sample_data_loads():
    df = ds.load_sample_prices()
    assert {"AAPL", "MSFT", "SPY"} <= set(df.columns)
    assert len(df) > 500 and df.notna().all().all()
