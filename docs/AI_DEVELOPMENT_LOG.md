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

I went with Project 2 because it's the closest thing on the list to what I already do. I day trade NQ futures through prop firms, and the number that decides whether I keep an account isn't my win rate, it's my max drawdown. Hit the limit and the account is gone. So a tool that shows you how deep a portfolio can fall before it comes back made sense to me right away.

My first prompt was basically "finish this project" with the assignment sheet attached. Claude asked which of the ten projects I wanted, I picked the portfolio risk analyzer, and it built the whole thing from there. I'm not going to pretend I wrote the Python. What I did was steer it, decide what it should be, and check that it made sense.

The part I didn't expect was the risk contribution chart. In the default AAPL / MSFT / SPY portfolio, AAPL is 40% of the money but about 45% of the risk. I would have guessed those two numbers were the same. They're not, because AAPL swings harder than the other two, so a position can be "only 40%" and still be running most of the show. Honestly that's the same lesson as sizing a futures trade: the contract count isn't the risk, the volatility behind it is.

The other thing I noticed is that the screenshots in this repo are from demo mode, which uses made-up prices. That's why AAPL shows a loss in them. Claude's workspace couldn't reach Yahoo or Finnhub, so it built a fake dataset to test with and labeled it everywhere so nobody confuses it with real data. I like that it did that instead of making numbers up and passing them off as real.

- **Live data test:** [fill in after running it: date, tickers tried, anything that broke]
- **Changes I asked for:** [fill in if you change anything]
