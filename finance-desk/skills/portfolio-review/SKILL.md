---
name: portfolio-review
description: Live portfolio check from a holdings CSV. Current value, weights, day change, unrealized P&L, volatility, beta, 1-day 95% Value-at-Risk and expected shortfall, 1-year return and max drawdown vs a benchmark, each position's share of total risk, highly correlated pairs, and concrete suggestions (concentration trims, rebalance-to-target trades, loss reviews). Use when the user shares holdings or asks to review, check, rebalance or de-risk a portfolio.
---

# Portfolio review

## Input

A CSV with at least `symbol,shares`. Optional columns: `cost_basis` (per
share) and `target_weight` (percent). A row with symbol `CASH` holds a cash
balance in `shares`. Example (`examples/holdings.example.csv` in the
plugin):

```csv
symbol,shares,cost_basis,target_weight
AAPL,40,190.00,20
VTI,60,280.00,25
CASH,5000,,5
```

If the user pastes holdings in chat, write them to a CSV in a scratch or
working directory first. Never upload them anywhere.

## Run

```bash
FIN="<this skill's base directory>/fin.py"
python3 "$FIN" portfolio holdings.csv
python3 "$FIN" portfolio holdings.csv --benchmark QQQ --max-weight 15
python3 "$FIN" portfolio holdings.csv --json
```

## Reading the output

- `riskC` is each position's share of total portfolio variance. A position
  whose risk share is much bigger than its weight drives the outcome.
- **VaR 95% (1 day)** is the loss exceeded on about 1 day in 20, judging by
  the last year of returns. **Expected shortfall** is the average loss on
  those bad days.
- Beta above 1.3 means the portfolio amplifies market moves.
- Correlation of 0.85 or more between two holdings means they offer little
  diversification.

## Suggestions

The engine prints rule-based suggestions. Present them, then add judgment:

- Sort them by impact: concentration and risk drivers first, small
  rebalance trades last.
- For trims and sells in taxable accounts, mention tax lots and holding
  periods. Ask before assuming the account type.
- Combine with `market-pulse` `regime`. In a RISK-OFF regime,
  de-risking suggestions deserve more weight.
- For any single name flagged, offer a `stock-checkup`.

This pack only reads data. It never places orders. Present trades as a
list the user can act on in their own broker. End with: rule-based
analysis, not financial advice.
