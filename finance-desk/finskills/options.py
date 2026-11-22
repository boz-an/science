"""Black-Scholes-Merton pricing, Greeks, implied volatility and multi-leg payoffs."""

import math


def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _npdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def bs(spot, strike, days, vol, rate=0.04, div=0.0, kind="call"):
    """Price and Greeks. vol, rate, div are decimals; theta is per calendar day; vega/rho per 1 point."""
    if spot <= 0 or strike <= 0 or days <= 0 or vol <= 0:
        raise ValueError("spot, strike, days and vol must be positive")
    kind = kind.lower()
    if kind not in ("call", "put"):
        raise ValueError("kind must be call or put")
    t = days / 365.0
    sq = vol * math.sqrt(t)
    d1 = (math.log(spot / strike) + (rate - div + 0.5 * vol * vol) * t) / sq
    d2 = d1 - sq
    dq, dr = math.exp(-div * t), math.exp(-rate * t)
    if kind == "call":
        price = spot * dq * _ncdf(d1) - strike * dr * _ncdf(d2)
        delta = dq * _ncdf(d1)
        theta = (-spot * dq * _npdf(d1) * vol / (2 * math.sqrt(t)) - rate * strike * dr * _ncdf(d2) + div * spot * dq * _ncdf(d1))
        rho = strike * t * dr * _ncdf(d2)
        prob_itm = _ncdf(d2)
    else:
        price = strike * dr * _ncdf(-d2) - spot * dq * _ncdf(-d1)
        delta = -dq * _ncdf(-d1)
        theta = (-spot * dq * _npdf(d1) * vol / (2 * math.sqrt(t)) + rate * strike * dr * _ncdf(-d2) - div * spot * dq * _ncdf(-d1))
        rho = -strike * t * dr * _ncdf(-d2)
        prob_itm = _ncdf(-d2)
    return {
        "price": price, "delta": delta,
        "gamma": dq * _npdf(d1) / (spot * sq),
        "theta_per_day": theta / 365.0,
        "vega_per_pt": spot * dq * _npdf(d1) * math.sqrt(t) / 100.0,
        "rho_per_pt": rho / 100.0,
        "prob_itm_riskneutral": prob_itm,
        "expected_move_1sd": spot * vol * math.sqrt(t),
    }


def implied_vol(market_price, spot, strike, days, rate=0.04, div=0.0, kind="call"):
    lo, hi = 1e-4, 5.0
    if not bs(spot, strike, days, lo, rate, div, kind)["price"] <= market_price <= bs(spot, strike, days, hi, rate, div, kind)["price"]:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if bs(spot, strike, days, mid, rate, div, kind)["price"] > market_price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def parse_leg(text):
    """'long call 100 2.50 [x2]' / 'short put 95 1.10' / 'long stock 98.5 [x100]'."""
    parts = text.lower().replace("@", " ").split()
    qty = 1.0
    if parts and parts[-1].startswith("x"):
        qty = float(parts.pop()[1:])
    if len(parts) == 3 and parts[1] == "stock":
        side, kind, price = parts
        strike = 0.0
    elif len(parts) == 4:
        side, kind, strike, price = parts
        strike = float(strike)
    else:
        raise ValueError("bad leg %r: use 'long|short call|put STRIKE PREMIUM [xQTY]' or 'long|short stock PRICE [xQTY]'" % text)
    if side not in ("long", "short") or kind not in ("call", "put", "stock"):
        raise ValueError("bad leg %r" % text)
    return {"side": side, "kind": kind, "strike": strike, "price": float(price), "qty": qty}


def leg_value_at_expiry(leg, s):
    sign = 1 if leg["side"] == "long" else -1
    if leg["kind"] == "stock":
        pnl = s - leg["price"]
    elif leg["kind"] == "call":
        pnl = max(s - leg["strike"], 0) - leg["price"]
    else:
        pnl = max(leg["strike"] - s, 0) - leg["price"]
    return sign * pnl * leg["qty"]


def payoff(legs, multiplier=100, points=None):
    strikes = [l["strike"] or l["price"] for l in legs]
    lo, hi = min(strikes) * 0.5, max(strikes) * 1.5
    top = max(strikes) * 3
    # Price can't go below zero, so the grid starts there; P&L is piecewise
    # linear, so a still-sloping right edge means unlimited profit or loss.
    grid = points or [top * i / 1200 for i in range(1201)]
    pnl = [sum(leg_value_at_expiry(l, s) for l in legs) * multiplier for s in grid]
    breakevens = []
    for i in range(1, len(grid)):
        a, b = pnl[i - 1], pnl[i]
        if (a < 0 <= b) or (a > 0 >= b):
            x = grid[i - 1] + (grid[i] - grid[i - 1]) * (-a / (b - a)) if b != a else grid[i]
            if not breakevens or abs(x - breakevens[-1]) > 1e-6:
                breakevens.append(x)
    slope_hi = pnl[-1] - pnl[-2]
    max_profit = "unlimited" if slope_hi > 1e-9 else max(pnl)
    max_loss = "unlimited" if slope_hi < -1e-9 else min(pnl)
    table_pts = sorted(set([round(x, 2) for x in strikes] + [round(lo + (hi - lo) * i / 8, 2) for i in range(9)]))
    table = [(s, sum(leg_value_at_expiry(l, s) for l in legs) * multiplier) for s in table_pts]
    net = sum((l["price"] * l["qty"] * (1 if l["side"] == "long" else -1)) for l in legs if l["kind"] != "stock") * multiplier
    return {"breakevens": breakevens, "max_profit": max_profit, "max_loss": max_loss, "net_debit": net, "table": table}
