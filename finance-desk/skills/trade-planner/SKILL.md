---
name: trade-planner
description: Plan a trade before taking it. Risk-based position sizing (fixed fraction of the account, stop from price or ATR, max-position cap, R-multiple targets), and history-based odds that the target is hit before the stop: a seeded Monte Carlo replay of the stock's own daily bars, giving win rate, breakeven win rate and expected R. Use when the user asks how many shares to buy, where to put a stop, what the odds are of reaching a price, or whether a setup's risk/reward is worth it.
---

# Trade planner

The two questions to answer before entering: how much, and is it worth it.

## Run

```bash
FIN="<this skill's base directory>/fin.py"
# Size from explicit levels
python3 "$FIN" size --account 50000 --risk 1 --entry 100 --stop 95 --target 112
# Size from the live price, stop = 2 x ATR(14) below it
python3 "$FIN" size AAPL --account 50000 --risk 1 --atr-mult 2
# Odds: target before stop within N sessions (10,000 replays, seed 7)
python3 "$FIN" odds AAPL --entry 342 --stop 325 --target 375 --days 15
python3 "$FIN" odds AAPL --entry 342 --stop 325 --target 375 --days 15 --years 5 --seed 11
# Levels to anchor entry and stop
python3 "$FIN" tech AAPL
```

Short trades: stop above entry, target below. The engine detects the side.

## Method

- **Sizing:** shares = (account × risk%) / |entry - stop|. The result is
  capped by `--max-position` (default 25% of the account). The default risk
  is 1% per trade. Suggest 0.25-0.5% while learning or in a RISK-OFF
  regime.
- **Odds:** the engine replays random 5-day blocks of the stock's real daily
  bars (open, high, low, close relative to the prior close) from the entry
  price. For each path it records which level is touched first. When a
  single bar spans both levels, it counts the stop, which is the
  pessimistic choice because daily bars hide the order of touches. The same
  seed and data always give the same numbers.
- **Expected R** is the average result in units of risk. It is only
  attractive when the win rate clears the **breakeven win rate**
  (risk / (risk + reward)) by a margin.

## Presenting it

Give a compact plan:

| | |
|---|---|
| Entry / stop / target | ... |
| Shares, $ at risk, % of account | ... |
| Odds: target first / stop first / neither | ... |
| Expected R, breakeven win rate | ... |

Then give a verdict: "positive expectancy on this history", "marginal" or
"negative: improve the entry or widen the target". Name the main caveat:
earnings inside the window (check `market-pulse` news), regime change, or
gap risk. A stop doesn't protect against overnight gaps.

Never place orders. This pack has no trading capability. End with:
history-based estimate, not financial advice.
