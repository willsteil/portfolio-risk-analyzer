"""End-to-end checks: launch the Streamlit script headless and make sure it never crashes."""

from pathlib import Path
from unittest import mock

import pytest
from streamlit.testing.v1 import AppTest

from analyzer import data_sources as ds

APP = str(Path(__file__).resolve().parent.parent / "app.py")

pytestmark = pytest.mark.filterwarnings("ignore")


def start(demo=True) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90)
    with mock.patch.object(ds, "fetch_risk_free_rate", side_effect=ds.DataSourceError("offline")), \
         mock.patch.object(ds, "fetch_price_history", side_effect=ds.DataSourceError("offline")):
        at.run()
        if demo:
            at.sidebar.radio[0].set_value("Demo dataset (offline)").run()
    return at


def test_demo_mode_renders_everything():
    at = start()
    assert not at.exception and not at.error
    labels = [x.label for x in at.metric]
    for needed in ["Annualized return", "Annualized volatility", "Sharpe ratio", "Max drawdown", "Beta"]:
        assert needed in labels
    assert len(at.tabs) == 5


def test_live_mode_without_network_shows_error_not_crash():
    at = AppTest.from_file(APP, default_timeout=90)
    with mock.patch.object(ds, "fetch_risk_free_rate", side_effect=ds.DataSourceError("offline")), \
         mock.patch.object(ds, "fetch_price_history", side_effect=ds.DataSourceError("network down")):
        at.run()
    assert not at.exception
    assert any("Couldn't load price data" in e.value for e in at.error)


def test_live_mode_with_mocked_prices_drops_missing_ticker():
    demo = ds.load_sample_prices()
    prices = demo[["AAPL", "MSFT", "SPY"]].copy()

    def fake_history(tickers, start, end):
        return prices[[t for t in tickers if t in prices]], [t for t in tickers if t not in prices]

    at = AppTest.from_file(APP, default_timeout=90)
    with mock.patch.object(ds, "fetch_risk_free_rate", return_value=(0.04, "2026-10-22")), \
         mock.patch.object(ds, "fetch_price_history", side_effect=fake_history):
        at.run()
        assert not at.exception and not at.error
        at.sidebar.text_input[0].set_value("QQQ").run()   # benchmark with no data
    assert any("benchmark" in e.value for e in at.error)


def test_unknown_benchmark_in_demo():
    at = start()
    at.sidebar.text_input[0].set_value("ZZZZ").run()
    assert not at.exception
    assert any("ZZZZ" in e.value for e in at.error)


@pytest.mark.parametrize("method", ["Buy and hold", "Rebalance daily"])
@pytest.mark.parametrize("lookback", ["1 year", "5 years"])
def test_settings_combinations(method, lookback):
    at = start()
    at.sidebar.radio[1].set_value(method)
    at.sidebar.selectbox[0].set_value(lookback)
    at.run()
    assert not at.exception and not at.error


def test_whatif_all_zero_warns():
    at = start()
    for s in at.slider:
        s.set_value(0)
    at.run()
    assert not at.exception
    assert any("weight above zero" in w.value for w in at.warning)
