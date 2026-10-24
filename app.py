"""Portfolio Risk Analyzer — Streamlit app.

Run:  streamlit run app.py
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st

from analyzer import charts
from analyzer import data_sources as ds
from analyzer import metrics as m

st.set_page_config(page_title="Portfolio Risk Analyzer", page_icon="📊", layout="wide")

DEFAULT_HOLDINGS = pd.DataFrame({"Ticker": ["AAPL", "MSFT", "SPY"], "Amount": [4000.0, 3500.0, 2500.0]})
LOOKBACKS = {"1 year": 1, "2 years": 2, "3 years": 3, "5 years": 5}
MIN_HOLDINGS = 3
MIN_DAYS = 60


# ---------------------------------------------------------------------------
# Cached data loaders (avoid hitting APIs on every widget change)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner="Downloading price history…")
def load_live_prices(tickers: tuple[str, ...], start: date, end: date):
    return ds.fetch_price_history(list(tickers), start, end)


@st.cache_data(ttl=3600, show_spinner=False)
def load_risk_free():
    return ds.fetch_risk_free_rate("DGS3MO")


@st.cache_data(ttl=300, show_spinner=False)
def load_quote(symbol: str, key: str):
    return ds.finnhub_quote(symbol, key)


@st.cache_data(ttl=86400, show_spinner=False)
def load_profile(symbol: str, key: str):
    return ds.finnhub_profile(symbol, key)


@st.cache_data(show_spinner=False)
def load_demo():
    return ds.load_sample_prices()


def pct(x: float, digits: int = 1) -> str:
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{digits}%}"


def num(x: float, digits: int = 2) -> str:
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{digits}f}"


# ---------------------------------------------------------------------------
# Sidebar — settings
# ---------------------------------------------------------------------------
st.sidebar.title("Settings")
source = st.sidebar.radio(
    "Data source", ["Live market data", "Demo dataset (offline)"],
    help="Live: Yahoo Finance prices, Finnhub quotes/profiles, FRED risk-free rate. "
         "Demo: bundled synthetic prices so the app works with no internet or API key.")
demo = source.startswith("Demo")

benchmark_raw = st.sidebar.text_input("Benchmark", "SPY", help="Market index ETF to compare against, e.g. SPY, QQQ, IWM.")
lookback_label = st.sidebar.selectbox("Lookback period", list(LOOKBACKS), index=2)
method_label = st.sidebar.radio(
    "Rebalancing", ["Buy and hold", "Rebalance daily"],
    help="Buy and hold: weights drift with prices. Rebalance daily: weights reset to target every day.")
method = "buy_and_hold" if method_label == "Buy and hold" else "rebalanced"

st.sidebar.subheader("Risk-free rate")
rf_auto = st.sidebar.checkbox("Use latest 3-month T-bill (FRED)", value=not demo, disabled=demo)
rf_note = ""
risk_free = None
if rf_auto and not demo:
    try:
        risk_free, rf_date = load_risk_free()
        rf_note = f"FRED DGS3MO: {risk_free:.2%} as of {rf_date}"
        st.sidebar.caption(rf_note)
    except ds.DataSourceError as e:
        st.sidebar.warning(f"{e} Using the manual rate below.")
if risk_free is None:
    risk_free = st.sidebar.number_input("Annual risk-free rate (%)", 0.0, 20.0, 4.0, 0.1) / 100
    rf_note = f"Manual input: {risk_free:.2%}"

finnhub_key = ds.get_finnhub_key()
if not demo:
    st.sidebar.caption("Finnhub key: " + ("found ✅" if finnhub_key else "not set (quotes tab disabled)"))

st.sidebar.divider()
st.sidebar.caption("Educational tool. Past performance doesn't predict future results. Not investment advice.")

# ---------------------------------------------------------------------------
# Header + holdings input
# ---------------------------------------------------------------------------
st.title("📊 Portfolio Risk Analyzer")
st.markdown(
    "Investors often underestimate how much risk comes from **one or two positions** or from holdings that "
    "**move together**. Enter a portfolio below to see its return, volatility, Sharpe ratio, drawdowns and "
    "where its risk actually comes from, compared with a market benchmark."
)
if demo:
    st.info("**Demo mode:** prices are *synthetic* (simulated, not real market data) and bundled with the app. "
            "Switch to **Live market data** in the sidebar for real prices.", icon="🧪")

col_in, col_help = st.columns([3, 2])
with col_in:
    mode = st.radio("Enter holdings as", ["Dollar amounts", "Percent weights"], horizontal=True)
    label = "Amount ($)" if mode == "Dollar amounts" else "Weight (%)"
    seed = DEFAULT_HOLDINGS.copy()
    if mode == "Percent weights":
        seed["Amount"] = [40.0, 35.0, 25.0]
    edited = st.data_editor(
        seed, num_rows="dynamic", width="stretch", key=f"holdings_{mode}", hide_index=True,
        column_config={
            "Ticker": st.column_config.TextColumn("Ticker", help="Stock or ETF symbol", required=True),
            "Amount": st.column_config.NumberColumn(label, min_value=0.0, step=100.0 if mode == "Dollar amounts" else 1.0,
                                                    format="$%.0f" if mode == "Dollar amounts" else "%.1f%%"),
        })
with col_help:
    st.markdown("**How to use**")
    st.markdown(
        "- Add at least **3** stocks or ETFs (click the empty last row to add one).\n"
        "- Weights don't need to add to 100. They're scaled automatically.\n"
        "- Try the **What-if** tab to see how changing the mix changes the risk.")
    if demo:
        st.caption("Demo tickers: " + ", ".join(load_demo().columns))

# ---------------------------------------------------------------------------
# Validate inputs
# ---------------------------------------------------------------------------
amounts, errors = ds.parse_holdings(edited)

try:
    benchmark = ds.clean_ticker(benchmark_raw)
except ds.DataSourceError as e:
    st.error(f"Benchmark: {e}")
    st.stop()

for e in errors:
    st.warning(e)
if len(amounts) < MIN_HOLDINGS:
    st.error(f"Add at least {MIN_HOLDINGS} holdings with a positive amount or weight (you have {len(amounts)}).")
    st.stop()

# ---------------------------------------------------------------------------
# Load prices
# ---------------------------------------------------------------------------
years = LOOKBACKS[lookback_label]
needed = list(dict.fromkeys(list(amounts) + [benchmark]))
try:
    if demo:
        all_px = load_demo()
        end = all_px.index.max()
        start = end - pd.DateOffset(years=years)
        missing = [t for t in needed if t not in all_px.columns]
        prices = all_px.loc[all_px.index >= start, [t for t in needed if t in all_px.columns]]
        if all_px.index.min() > start:
            st.caption(f"Demo data starts {all_px.index.min():%b %Y}, so the {lookback_label} window is shorter.")
    else:
        end = date.today()
        start = end - timedelta(days=int(365.25 * years))
        prices, missing = load_live_prices(tuple(needed), start, end)
except ds.DataSourceError as e:
    st.error(f"**Couldn't load price data.** {e}")
    st.info("You can switch to **Demo dataset (offline)** in the sidebar to explore the app without a connection.")
    st.stop()

if benchmark in missing:
    st.error(f"No price data for benchmark **{benchmark}**. Pick a different benchmark.")
    st.stop()
dropped = [t for t in missing if t in amounts]
if dropped:
    st.warning(f"No price history found for **{', '.join(dropped)}**, so they were left out. "
               "Check the symbol" + (" (demo mode only includes the tickers listed above)." if demo else "."))
    for t in dropped:
        amounts.pop(t)
if len(amounts) < MIN_HOLDINGS:
    st.error(f"Only {len(amounts)} holdings have data. At least {MIN_HOLDINGS} are needed.")
    st.stop()

holdings = list(amounts)
aligned = prices[holdings + ([benchmark] if benchmark not in holdings else [])].dropna()
if len(aligned) < MIN_DAYS:
    st.error(f"Only {len(aligned)} days where every holding has a price (need {MIN_DAYS}). "
             "A holding may have started trading recently. Try removing it or shortening the lookback.")
    st.stop()
short_history = [t for t in holdings if prices[t].first_valid_index() > prices.index.min() + pd.Timedelta(days=10)]
if short_history:
    st.caption(f"Note: {', '.join(short_history)} has a shorter history, so all stats start "
               f"{aligned.index.min():%b %d, %Y} when every holding has data.")

# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------
weights = m.normalize_weights(amounts)
start_amount = sum(amounts.values()) if mode == "Dollar amounts" else 10_000.0
try:
    port_val = m.portfolio_value(aligned, weights, method)
    bench_val = aligned[benchmark] / aligned[benchmark].iloc[0]
    port = m.summarize(port_val, risk_free, bench_val)
    bench = m.summarize(bench_val, risk_free, bench_val)
    asset_rets = m.daily_returns(aligned[holdings])
    rc = m.risk_contributions(asset_rets, weights)
    corr = asset_rets.corr()
    stats = m.asset_table(aligned, weights, risk_free)
    div_ratio = m.diversification_ratio(asset_rets, weights)
except m.MetricsError as e:
    st.error(f"Calculation problem: {e}")
    st.stop()

period_text = f"{aligned.index.min():%b %d, %Y} – {aligned.index.max():%b %d, %Y} ({len(aligned)} trading days)"
st.caption(f"Analysis window: {period_text} · {method_label} · Risk-free: {rf_note}")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_over, tab_risk, tab_hold, tab_whatif, tab_method = st.tabs(
    ["Overview", "Risk", "Holdings", "What-if", "Methodology"])

with tab_over:
    k = st.columns(5)
    k[0].metric("Annualized return", pct(port["Annualized return"]),
                f"{port['Annualized return'] - bench['Annualized return']:+.1%} vs {benchmark}")
    k[1].metric("Annualized volatility", pct(port["Annualized volatility"]),
                f"{port['Annualized volatility'] - bench['Annualized volatility']:+.1%} vs {benchmark}",
                delta_color="inverse")
    k[2].metric("Sharpe ratio", num(port["Sharpe ratio"]),
                f"{port['Sharpe ratio'] - bench['Sharpe ratio']:+.2f} vs {benchmark}")
    k[3].metric("Max drawdown", pct(port["Max drawdown"]),
                f"{port['Max drawdown'] - bench['Max drawdown']:+.1%} vs {benchmark}")
    k[4].metric("Beta", num(port["Beta"]), help=f"Sensitivity to {benchmark}. 1.0 = moves with the market.")

    c1, c2 = st.columns([1, 2])
    with c1:
        st.plotly_chart(charts.allocation_donut(weights, amounts if mode == "Dollar amounts" else None),
                        width="stretch")
    with c2:
        st.plotly_chart(charts.growth_chart(port_val, bench_val, benchmark, start_amount), width="stretch")

    st.subheader("What the numbers say")
    for note in m.plain_language_assessment(port, bench, weights, rc, benchmark, corr):
        st.markdown(f"- {note}")

    st.subheader(f"Portfolio vs {benchmark}")
    keys = ["Total return", "Annualized return", "Annualized volatility", "Sharpe ratio", "Sortino ratio",
            "Max drawdown", "1-day VaR (95%)", "Beta", "Tracking error"]
    ratio_keys = {"Sharpe ratio", "Sortino ratio", "Beta"}
    comp = pd.DataFrame({
        "Metric": keys,
        "Portfolio": [num(port[x]) if x in ratio_keys else pct(port[x]) for x in keys],
        benchmark: [num(bench[x]) if x in ratio_keys else ("—" if x == "Tracking error" else pct(bench[x]))
                    for x in keys],
    })
    st.dataframe(comp, hide_index=True, width="stretch")

with tab_risk:
    dd = port["_drawdown"]
    rec = f"recovered {dd.recovery_date:%b %d, %Y}" if dd.recovery_date is not None else "not yet recovered"
    st.markdown(f"**Worst drawdown:** {dd.depth:.1%}, from the peak on {dd.peak_date:%b %d, %Y} to the low on "
                f"{dd.trough_date:%b %d, %Y} ({rec}).")
    st.plotly_chart(charts.drawdown_chart(m.drawdown_series(port_val), m.drawdown_series(bench_val), benchmark),
                    width="stretch")
    st.plotly_chart(charts.rolling_vol_chart(m.rolling_volatility(m.series_returns(port_val)),
                                             m.rolling_volatility(m.series_returns(bench_val)), benchmark),
                    width="stretch")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(charts.risk_vs_weight_chart(weights, rc), width="stretch")
        st.caption("A holding whose blue bar is taller than its grey bar adds more risk than its dollar weight suggests.")
    with c2:
        st.plotly_chart(charts.correlation_heatmap(corr), width="stretch")
        st.caption("Values near +1 move together (little diversification). Near 0 or negative diversify.")
    c3, c4 = st.columns(2)
    c3.metric("Effective number of holdings", f"{m.effective_holdings(weights):.1f}",
              help="1 / sum of squared weights. 3 equal positions = 3.0; one dominant position pushes it toward 1.")
    c4.metric("Diversification ratio", f"{div_ratio:.2f}",
              help="Weighted average of each holding's volatility ÷ portfolio volatility. Higher = more benefit "
                   "from combining assets. 1.0 = none.")

with tab_hold:
    st.plotly_chart(charts.risk_return_scatter(
        stats, (port["Annualized volatility"], port["Annualized return"]),
        (bench["Annualized volatility"], bench["Annualized return"]), benchmark), width="stretch")
    st.subheader("Holding statistics")
    show = stats.copy()
    for col in ["Weight", "Risk share", "Annualized return", "Annualized volatility", "Max drawdown"]:
        show[col] = show[col].map(pct)
    show["Sharpe ratio"] = stats["Sharpe ratio"].map(num)
    if mode == "Dollar amounts":
        show.insert(0, "Amount", [f"${amounts[t]:,.0f}" for t in show.index])
    st.dataframe(show, width="stretch")

    st.subheader("Live quotes and company info (Finnhub)")
    if demo:
        st.caption("Not shown in demo mode. Switch to live market data and set a Finnhub key to see quotes.")
    elif not finnhub_key:
        st.info("Set a free Finnhub API key to see live quotes. See the README: add `FINNHUB_API_KEY` to "
                "`.streamlit/secrets.toml` or your environment.")
    else:
        rows, problems = [], []
        for t in holdings:
            try:
                q = load_quote(t, finnhub_key)
            except ds.DataSourceError as e:
                problems.append(f"{t}: {e}")
                continue
            try:
                p = load_profile(t, finnhub_key)
            except ds.DataSourceError:
                p = {}
            rows.append({
                "Ticker": t, "Name": p.get("name") or "—", "Industry": p.get("industry") or "ETF / not listed",
                "Price": f"${q['price']:,.2f}",
                "Change": f"{q['change']:+.2f} ({q['change_pct']:+.2f}%)" if q.get("change") is not None else "—",
                "Day range": f"{q['low']:,.2f} – {q['high']:,.2f}" if q.get("low") else "—",
                "Market cap": f"${p['market_cap_m'] / 1000:,.1f}B" if p.get("market_cap_m") else "—",
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            st.caption("Quote = latest price from Finnhub /quote; change is vs previous close. Profiles from /stock/profile2.")
        for pmsg in problems:
            st.warning(pmsg)

with tab_whatif:
    st.markdown("Move the sliders to try a different mix of the **same holdings**. The weights are rescaled to "
                "100% automatically. Everything else (dates, rebalancing, risk-free rate) stays the same.")
    sig = "|".join(holdings)
    cols = st.columns(min(len(holdings), 4))
    raw_new = {}
    for i, t in enumerate(holdings):
        with cols[i % len(cols)]:
            raw_new[t] = st.slider(t, 0, 100, int(round(weights[t] * 100)), key=f"wi_{sig}_{t}")
    if sum(raw_new.values()) == 0:
        st.warning("Give at least one holding a weight above zero.")
    else:
        new_w = m.normalize_weights(raw_new)
        new_val = m.portfolio_value(aligned, new_w, method)
        new = m.summarize(new_val, risk_free, bench_val)
        new_rc = m.risk_contributions(asset_rets, new_w)
        keys = ["Annualized return", "Annualized volatility", "Max drawdown"]
        st.plotly_chart(charts.whatif_bars(port, new, keys), width="stretch")
        c = st.columns(4)
        c[0].metric("Sharpe ratio", num(new["Sharpe ratio"]), f"{new['Sharpe ratio'] - port['Sharpe ratio']:+.2f}")
        c[1].metric("Volatility", pct(new["Annualized volatility"]),
                    f"{new['Annualized volatility'] - port['Annualized volatility']:+.1%}", delta_color="inverse")
        c[2].metric("Max drawdown", pct(new["Max drawdown"]), f"{new['Max drawdown'] - port['Max drawdown']:+.1%}")
        c[3].metric("Beta", num(new["Beta"]), f"{new['Beta'] - port['Beta']:+.2f}", delta_color="off")
        st.plotly_chart(charts.growth_chart(new_val, bench_val, benchmark, start_amount).update_layout(
            title_text=f"What-if growth of ${start_amount:,.0f} vs {benchmark}"), width="stretch")
        st.dataframe(pd.DataFrame({
            "Current weight": [pct(weights[t]) for t in holdings], "What-if weight": [pct(new_w[t]) for t in holdings],
            "Current risk share": [pct(rc[t]) for t in holdings], "What-if risk share": [pct(new_rc[t]) for t in holdings],
        }, index=holdings), width="stretch")

with tab_method:
    st.markdown(r"""
### Data
| What | Source | Notes |
|---|---|---|
| Daily adjusted close prices | Yahoo Finance via the `yfinance` library | Adjusted for splits and dividends, so returns include dividends. Finnhub's historical candles are a paid feature. |
| Latest quote and company profile | Finnhub `/quote` and `/stock/profile2` | Free tier, 60 calls/min. Needs a free API key. |
| Risk-free rate | FRED series **DGS3MO** (3-month Treasury bill) | Public CSV, no key needed. Falls back to a manual rate. |
| Demo data | `data/sample_prices.csv` | **Synthetic**, generated by `data/make_sample_data.py`. Not real prices. |

### Calculations (252 trading days per year)
- **Daily return:** $r_t = P_t / P_{t-1} - 1$
- **Portfolio value:** buy-and-hold $V_t = \sum_i w_i \, P_{i,t}/P_{i,0}$, or daily-rebalanced $V_t = \prod (1 + \sum_i w_i r_{i,t})$
- **Annualized return (CAGR):** $(V_T / V_0)^{252/N} - 1$
- **Annualized volatility:** $\sigma_{daily} \times \sqrt{252}$
- **Sharpe ratio:** $\dfrac{\overline{r - r_f/252}}{\sigma(r - r_f/252)} \times \sqrt{252}$
- **Sortino ratio:** same numerator, divided by downside deviation (only days below the risk-free rate)
- **Maximum drawdown:** $\min_t \left( V_t / \max_{s \le t} V_s - 1 \right)$
- **Beta:** $\mathrm{Cov}(r_p, r_b) / \mathrm{Var}(r_b)$; **tracking error:** $\sigma(r_p - r_b)\sqrt{252}$
- **1-day historical VaR (95%):** 5th percentile of daily returns
- **Risk contribution:** $RC_i = w_i (\Sigma w)_i / w^\top \Sigma w$, where the shares add up to 100%
- **Effective number of holdings:** $1 / \sum w_i^2$ (inverse Herfindahl index)
- **Diversification ratio:** $\sum w_i \sigma_i / \sigma_p$

### Limitations
- History is not a forecast. Volatility and correlations change, especially in crises.
- Volatility and Sharpe assume returns are roughly normal. Real returns have fatter tails, which is why max drawdown and VaR are shown too.
- No trading costs, taxes or bid/ask spreads. "Rebalance daily" would be expensive in practice.
- The risk-free rate is today's T-bill yield applied to the whole period, not the rate that applied each day.
- Yahoo Finance data comes through an unofficial library and can be rate-limited or change without notice.
""")
