---
name: stock-checkup
description: One-shot stock health check that turns live price data, SEC-filed fundamentals and a DCF into a 0-100 scorecard (trend, timing, risk, quality, valuation), a stance (constructive / neutral / cautious), the reasons for it, and support/resistance levels. Use when the user asks "should I buy X", "is X a good stock", "check X for me", "analyze X", "what do you think of X", or wants technicals or fundamentals for a US-listed stock.
---

# Stock checkup

A transparent, rule-based checkup. The engine computes every score from
fetched data. Your job is to run it, explain it, and add judgment the
numbers can't hold. Don't change the numbers.

## Run

```bash
FIN="<this skill's base directory>/fin.py"
python3 "$FIN" check MSFT            # full scorecard + stance + levels
python3 "$FIN" tech MSFT             # technical snapshot only
python3 "$FIN" fundamentals MSFT     # SEC-filed fundamentals + ratios
```

Fundamentals and valuation come from SEC EDGAR, which requires each client
to identify itself. If you get the `SEC_USER_AGENT` error, ask the user for
the name and email to use (or ask them to run
`export SEC_USER_AGENT="Name email@example.com"`). Never invent an identity.
Without it, `check` still runs trend, timing and risk, and shows coverage
as "3 of 5 components".

## How the scores work

| Component | Weight | Built from |
|---|---|---|
| trend | 25 | price vs 50/200-day averages, 50 vs 200, relative strength vs SPY (3m, 12m) |
| timing | 10 | RSI(14): best near 50, penalized when overbought (70 or more) |
| risk | 15 | 1-year volatility and max drawdown |
| quality | 25 | 3-year revenue growth, operating margin, positive FCF, ROE, debt/equity |
| valuation | 25 | base-case DCF value vs price |

Stance thresholds: 70 or more constructive, 55 or more neutral-positive,
40 or more neutral, below 40 cautious.

## Presenting it

1. Lead with the stance and overall score. Say the data freshness and date.
2. Give the 2-4 strongest positives and negatives the engine listed.
3. Give the levels: the entry zone near support, and where the idea is
   wrong (support minus 1 ATR).
4. Add context the engine can't see, labeled as your judgment: upcoming
   earnings, recent news (run `market-pulse` `news`), sector conditions.
5. For "should I buy", the useful answer is a plan, not yes or no. A plan
   covers where to enter, where you're wrong, and how much to risk. Hand
   off to `trade-planner` for sizing.

## Limits to say out loud when relevant

- The DCF is conservative for heavy-reinvestment compounders, because high
  capex depresses current FCF. If valuation scores near 0 for a quality
  compounder, say so and offer a `valuation-estimate` run with explicit
  growth or FCF-margin assumptions.
- Banks, insurers, REITs and pre-profit companies don't fit an FCF DCF.
  Weight the trend and quality pieces more.
- US-GAAP SEC filers only for fundamentals. Foreign (IFRS) filers and ETFs
  get technicals only.

Close with: rule-based analysis from public data, not financial advice.
