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

The number that got me was 45%. That's how much of the portfolio's risk comes from AAPL in the default example, even though AAPL is only 40% of the money. I honestly expected those two to be the same. SPY goes the other way: 25% of the money, under 19% of the risk. If you only look at the allocation pie, you'd never know AAPL was carrying more than its share.

That's basically why I picked Project 2 out of the ten. People split their money by percent and assume the risk splits the same way, and I wanted something that would show whether that's true.

How it actually got built: I gave Claude the assignment sheet and said "finish this project." Before writing anything it asked me which project I wanted, and once I picked the portfolio risk analyzer it built the app, the tests and the docs. I didn't write the Python. My part was picking the project, deciding what it needed to do, and checking that the results made sense, like comparing the AAPL and SPY numbers above against the charts.

Heads up on the screenshots, since they look worse than you'd expect: they're from demo mode, which runs on simulated prices. That's why AAPL shows a loss. Claude's workspace couldn't reach Yahoo Finance or Finnhub, so it made a fake dataset to test with and labeled it as fake everywhere instead of passing it off as real market data. I still want to see if the 40/45 gap shows up the same way on real prices.

- **Live data test:** [fill in after running it: date, tickers tried, whether the AAPL risk gap held up, anything that broke]
- **Changes I asked for:** [fill in if you change anything]
