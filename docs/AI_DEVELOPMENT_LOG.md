# AI Development Log

**AI coding agent:** Claude (Anthropic), working as an agent that can write files, run code and tests, and screenshot the running app.

Sections 1–6 are what the agent did. The last section is my own notes.

## 1. Choosing the project and data sources
- **Prompt:** build a finished prototype for the FinTech assignment. Project 2, *Investment Portfolio Risk Analyzer*, was chosen from the ten options.
- The agent checked which data was free. Finnhub's free plan covers `/quote` and `/stock/profile2` but not historical candles (`/stock/candle`), so it used Yahoo Finance (`yfinance`) for price history. It added FRED's public CSV for the 3-month T-bill rate, which needs no key.
- Design choice: keep the financial math in pure functions (`analyzer/metrics.py`), separate from the API code and the UI, so each piece can be tested on its own.

## 2. First build
- Wrote `metrics.py` (returns, CAGR, volatility, Sharpe, Sortino, max drawdown, beta, tracking error, VaR, risk contribution, effective holdings, diversification ratio).
- Wrote `data_sources.py`. Every failure raises a readable `DataSourceError` instead of a raw traceback.
- Wrote `charts.py` (Plotly) and `app.py` (Streamlit) with five tabs: Overview, Risk, Holdings, What-if, Methodology.

## 3. Offline demo dataset
- The agent's workspace couldn't reach Yahoo, Finnhub or FRED. Rather than fake API results, it wrote `data/make_sample_data.py`, a seeded one-factor simulation, and added a **Demo dataset (offline)** mode that is labeled as synthetic everywhere it appears.
- It sanity-checked the simulated data. Annualized volatilities came out around 13–50%, and AAPL/SPY correlation was 0.77, in a believable range.

## 4. Testing and the fixes it led to
- Ran the app headless with Streamlit's `AppTest` in demo mode, live mode with no network, a bad benchmark, invalid symbols, percent-weight mode, daily rebalancing and the what-if sliders at zero.
- Found that holdings validation was hard to test inside the UI script, so it moved that logic to `parse_holdings()`. Now duplicates, blanks, bad symbols, negatives and non-numeric amounts are each unit-tested.
- Wrote 52 pytest tests. The first run had 10 failures:
  - The `AppTest` path was relative to the test folder, not the repo. Fixed by using an absolute path.
  - The Sharpe ratio of a constant return series came out huge instead of "n/a". Floating-point error left a tiny non-zero standard deviation. Fixed by treating a standard deviation under 1e-12 as zero, in both Sharpe and Sortino.
- Re-ran: 52/52 passing.

## 5. Visual review from screenshots
- Took full-page screenshots of each tab with a headless browser, then reviewed them:
  - Chart legends overlapped titles in the narrow two-column layout, so legends moved below the plots.
  - The what-if bar chart was titled "allocation" but really showed return and risk, so it was renamed.
  - When the benchmark (SPY) was also a holding, it appeared twice on the risk/return scatter. The duplicate marker is now skipped.
  - The what-if screenshot was re-taken with the sliders actually moved (AAPL 15 / MSFT 35 / SPY 60) so the comparison shows real differences.

## 6. Accuracy check
- Recomputed the default portfolio's headline numbers in plain Python, with no pandas or numpy and separate from `metrics.py`. CAGR −1.9%, volatility 23.3%, Sharpe −0.14, max drawdown −38.2% and total return −5.8% all matched the app exactly.

## My changes and review

I picked Project 2 because it had the clearest problem out of the ten: people look at what percent of their money is in each stock and assume that's how their risk is split too. I wanted to see if that holds up.

My first prompt was the assignment sheet with "finish this project." Claude asked which project I wanted before writing anything, I chose the portfolio risk analyzer, and it built the app from there. I didn't write the Python myself. My part was choosing the project, deciding what it needed to do, and checking that the output made sense.

The result that surprised me was the risk contribution chart. In the default AAPL / MSFT / SPY portfolio, AAPL is 40% of the money but about 45% of the risk. I expected those to match. They don't, because AAPL moves more than the other two, so it pulls more of the portfolio's swings than its weight suggests. SPY goes the other way, 25% of the money but under 19% of the risk.

One thing to know about the screenshots: they come from demo mode, which uses simulated prices, so the returns in them aren't real (that's why AAPL shows a loss). Claude's workspace couldn't reach Yahoo Finance or Finnhub, so it built a synthetic dataset to test with and labeled it as fake everywhere it shows up instead of passing it off as market data.

- **Live data test:** [fill in after running it: date, tickers tried, anything that broke]
- **Changes I asked for:** [fill in if you change anything]
