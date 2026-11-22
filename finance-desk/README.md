# finance-desk

Claude skills for live market checks, suggestions and estimates, built on a
small, auditable engine:

- **Python standard library only.** There's nothing to `pip install`.
- **Public data without keys** by default: Yahoo Finance chart API, SEC
  EDGAR filings, FRED rates.
- **Read-only.** There is no code that can place an order.
- **Fail-closed.** Missing data produces an error, never a guess.

It combines the best ideas from four open-source skill packs after a
security and quality review. See [AUDIT.md](AUDIT.md).

## Skills

| Skill | Ask Claude things like | Engine commands |
|---|---|---|
| `market-pulse` | "What's NVDA trading at?", "Is the market risk-off?", "Any news on AAPL?" | `quote`, `regime`, `news` |
| `stock-checkup` | "Should I buy MSFT?", "Check TSLA for me" | `check`, `tech`, `fundamentals` |
| `valuation-estimate` | "What is AAPL worth?", "What growth is priced in?" | `value`, `fundamentals`, `estimates` |
| `portfolio-review` | "Review my portfolio", "How risky are my holdings?", "Rebalance to targets" | `portfolio` |
| `trade-planner` | "How many shares if I risk 1%?", "Odds AAPL hits 375 before 325?" | `size`, `odds` |
| `options-lab` | "Price this call", "What IV is this premium?", "Payoff of my spread?" | `option`, `payoff` |

## What it checks and estimates

- **Real-time checks:**
  - Price, change, day and 52-week range, and relative volume, with a
    freshness label (real-time, delayed ~N min, or last close).
  - Optional exchange-level real-time trades with free Alpaca keys.
- **Technicals:**
  - SMA 20/50/200, RSI, MACD, ATR, Bollinger bands.
  - Returns and relative strength vs SPY, volatility, drawdown.
  - Clustered support and resistance, and plain-English signals.
- **Fundamentals (SEC filings):**
  - Trailing-12-month revenue, earnings and free cash flow.
  - Margins, ROE, leverage, 3-year growth.
  - P/E, P/S, P/FCF, EV/EBIT, FCF yield at the live price.
- **Estimates:**
  - Two-stage DCF with a live risk-free rate and a computed beta.
  - Bear/base/bull scenarios, a sensitivity grid, and a reverse DCF
    (the growth the price implies).
  - Optional analyst consensus via FMP.
- **Suggestions:** a 0-100 scorecard with a stance, entry and invalidation
  levels, portfolio trims and rebalance trades, and risk-driver flags.
- **Risk math:**
  - Fixed-fraction position sizing, using an explicit stop or ATR.
  - Monte Carlo odds of target before stop, replaying the stock's own
    bars.
  - Portfolio VaR and expected shortfall, beta, correlations, and each
    position's share of risk.
- **Options:** Black-Scholes price, Greeks, implied vol, and multi-leg
  payoffs with breakevens.

## Install

**As a Claude Code plugin** (recommended):

```
/plugin marketplace add boz-an/science
/plugin install finance-desk@finance-desk
```

Moved to its own repository? Then use
`/plugin marketplace add <owner>/finance-desk`.

**As personal skills:**

```bash
git clone <this repo> && cd <repo>/finance-desk && ./install.sh
```

This copies the folder to `~/.claude/finance-desk` and symlinks each skill
into `~/.claude/skills/`. It downloads and installs nothing else.

**Configuration** (all optional, read from environment variables):

| Variable | Needed for |
|---|---|
| `SEC_USER_AGENT="Your Name you@example.com"` | fundamentals, valuation and the quality and valuation parts of `check` (SEC requires clients to identify themselves) |
| `FMP_API_KEY` | `estimates`: analyst consensus and price targets ([free tier](https://site.financialmodelingprep.com/developer/docs)) |
| `ALPACA_API_KEY_ID` + `ALPACA_API_SECRET_KEY` | real-time IEX last trade in `quote` (read-only market-data API) |
| `FINDESK_CACHE` / `FINDESK_NO_CACHE=1` | cache location (default `~/.cache/finance-desk`) or disable caching |

## Command line

The skills call this engine. You can also run it directly:

```bash
python3 fin.py quote AAPL ^GSPC BTC-USD
python3 fin.py check MSFT
python3 fin.py value AAPL --growth 0.08
python3 fin.py portfolio examples/holdings.example.csv
python3 fin.py size AAPL --account 50000 --risk 1
python3 fin.py odds AAPL --entry 342 --stop 325 --target 375 --days 15
python3 fin.py option call --symbol AAPL --strike 350 --days 30
python3 fin.py payoff "long call 100 5" "short call 110 2"
python3 fin.py regime
```

Every command accepts `--json` and `--no-cache`.

## Tests

```bash
python3 -m unittest discover -s tests
```

The 34 offline tests use synthetic data and need no network. They cover:
indicators, the DCF closed form, reverse-DCF round trip, put-call parity,
implied-vol round trip, spread payoffs, sizing, seeded Monte Carlo,
SEC TTM math, share-class summing, portfolio weights, and the CLI.

## Limits

- Yahoo's chart API is free but unofficial. Its prices are real-time or
  near real-time for most US listings, and the output always states how
  old the price is.
- Fundamentals cover US-GAAP SEC filers. Foreign IFRS filers and ETFs get
  price-based analysis only.
- A plain FCF DCF undervalues heavy reinvesters, and doesn't fit banks,
  insurers or REITs. The skills tell Claude to say so.
- Odds come from history. Earnings, news and regime shifts can break them.

**Not financial advice.** finance-desk produces rule-based analysis from
public data. Verify the numbers and consider your own situation before
acting.
