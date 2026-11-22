---
name: valuation-estimate
description: Fair-value estimates for a US-listed company. A two-stage DCF on SEC-reported free cash flow with a live risk-free rate and computed beta, bear/base/bull scenarios, a WACC x terminal-growth sensitivity grid, a reverse DCF (the growth the current price implies), multiples (P/E, P/S, P/FCF, EV/EBIT, FCF yield), and optional analyst consensus estimates. Use when the user asks what a stock is worth, whether it is over- or undervalued, for a price target, intrinsic value, DCF, or what growth the price bakes in.
---

# Valuation estimate

Estimates, not facts. Every input is shown so the user can disagree with it.

## Run

```bash
FIN="<this skill's base directory>/fin.py"
python3 "$FIN" value AAPL                                  # defaults from filings + market data
python3 "$FIN" value AAPL --growth 0.10 --terminal 0.03   # user's assumptions
python3 "$FIN" value AAPL --wacc 0.085                    # fixed discount rate
python3 "$FIN" value SNOW --fcf-margin 0.25               # value on revenue x steady-state FCF margin
python3 "$FIN" fundamentals AAPL                          # the reported numbers behind it
python3 "$FIN" estimates AAPL                             # analyst consensus (needs FMP_API_KEY)
```

`SEC_USER_AGENT` must be set (name and email; SEC policy). If it is
missing, ask the user. Don't make one up. `estimates` needs a free
Financial Modeling Prep key in `FMP_API_KEY`. Without one, say consensus
estimates are unavailable and rely on the DCF.

## Model (explain briefly when presenting)

- **Starting FCF:** trailing-12-month operating cash flow minus capex from
  10-K/10-Q filings. If that isn't positive, the engine uses the 3-year
  average. If that also isn't positive, it stops and asks for
  `--fcf-margin`.
- **Growth:** 5 years at the base rate (default: 3-year revenue CAGR,
  clamped between -2% and 20%), then a linear fade to terminal growth by
  year 10.
- **Discount rate:** CAPM cost of equity, with the 10-year Treasury from
  FRED, Blume-adjusted 2-year weekly beta vs SPY, and a 5% equity risk
  premium. It is blended with after-tax cost of debt by market weights.
- **Scenarios:** bear is growth -5pp, WACC +1pp, terminal -0.5pp. Bull is
  the reverse.
- **Reverse DCF:** solves for the 5-year growth that makes the value equal
  today's price. Compare it with the company's actual history; this is often
  the most useful single line.

## Presenting it

1. Value range (bear / base / bull) against the live price, with upside or
   downside.
2. What the price implies (reverse DCF) against what the company has
   delivered (revenue CAGR, FCF history).
3. Which assumption matters most. Use the sensitivity grid: "every 1pp of
   WACC moves value by about $X".
4. If the terminal value is more than 75% of the value, warn that the
   estimate rests mostly on the distant future.
5. If FMP estimates are available, compare consensus revenue/EPS growth
   with the growth input and re-run with `--growth` set to consensus.

Don't call a stock cheap or expensive on one model alone. Present ranges
and the assumptions they rest on, and end with: estimates from public data,
not financial advice.
