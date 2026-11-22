---
name: options-lab
description: Option math. Black-Scholes-Merton price and Greeks (delta, gamma, theta per day, vega and rho per vol/rate point), implied volatility from a market price, risk-neutral probability of finishing in the money, 1-sd expected move, and expiry payoff for multi-leg strategies (spreads, covered calls, straddles, collars) with max profit, max loss and breakevens. Use when the user asks what an option is worth, what its Greeks are, what implied vol a price means, or how a strategy pays off.
---

# Options lab

## Run

```bash
FIN="<this skill's base directory>/fin.py"
# Live spot; vol defaults to 30-day historical; rate = live 10y Treasury
python3 "$FIN" option call --symbol AAPL --strike 350 --days 30
# Solve implied vol from a quoted premium
python3 "$FIN" option put --symbol AAPL --strike 320 --days 45 --price 6.40
# Fully manual
python3 "$FIN" option call --spot 100 --strike 105 --days 60 --vol 0.32 --rate 0.045 --div 0.01
# Strategy payoff at expiry: legs are 'long|short call|put STRIKE PREMIUM [xQTY]' or 'long|short stock PRICE'
python3 "$FIN" payoff "long call 100 5" "short call 110 2"
python3 "$FIN" payoff "long stock 98" "short call 105 2.5" "long put 90 1.2"
```

The engine does not fetch option chains: Yahoo's chain endpoint needs a
session cookie, and this pack only uses public, keyless endpoints. Ask the
user for the premium from their broker, or use historical volatility and
say so.

## Notes when presenting

- Say which volatility was used and where it came from. Historical vol
  isn't implied vol: a model price based on historical vol is a reference
  point, not the market price.
- Theta is per calendar day. Vega and rho are per 1 percentage point.
- `P(ITM) risk-neutral` is not a real-world forecast. Present it as "the
  market-implied probability under Black-Scholes assumptions".
- European-style model. For American options it's a close approximation,
  except deep in-the-money puts and calls just before an ex-dividend date.
- For payoffs, show the table around the strikes and call out undefined
  risk ("unlimited") plainly.

End with: model estimates, not financial advice. Options can lose 100% of
the premium, and short options can lose more than the premium.
