"""Discounted cash flow estimates: scenarios, sensitivity grid, reverse DCF.

Model: two-stage free-cash-flow DCF. Growth `g` holds for `stage1` years,
then fades linearly to the terminal rate by year `years`; a Gordon-growth
terminal value is added at the end. All inputs are explicit and reported.
"""


def project(fcf0, g, tg, years=10, stage1=5):
    flows, f = [], fcf0
    for y in range(1, years + 1):
        if y <= stage1:
            rate = g
        else:
            k = (y - stage1) / float(years - stage1)
            rate = g + (tg - g) * k
        f *= 1 + rate
        flows.append(f)
    return flows


def dcf_ev(fcf0, g, wacc, tg, years=10, stage1=5):
    if wacc <= tg:
        raise ValueError("discount rate (%.2f%%) must exceed terminal growth (%.2f%%)" % (wacc * 100, tg * 100))
    flows = project(fcf0, g, tg, years, stage1)
    pv = sum(f / (1 + wacc) ** (i + 1) for i, f in enumerate(flows))
    tv = flows[-1] * (1 + tg) / (wacc - tg)
    pv_tv = tv / (1 + wacc) ** years
    return pv + pv_tv, pv_tv / (pv + pv_tv)


def per_share(fcf0, g, wacc, tg, net_cash, shares, years=10, stage1=5):
    ev, tv_share = dcf_ev(fcf0, g, wacc, tg, years, stage1)
    return (ev + net_cash) / shares, tv_share


def capm_wacc(rf, beta, market_cap, debt, erp=0.05, credit_spread=0.015, tax=0.21):
    """WACC from CAPM. Beta is Blume-adjusted toward 1 and clamped to [0.6, 2.0]."""
    b = min(2.0, max(0.6, 0.67 * beta + 0.33)) if beta == beta else 1.0
    re = rf + b * erp
    rd = (rf + credit_spread) * (1 - tax)
    d = max(debt or 0.0, 0.0)
    e = max(market_cap, 1.0)
    w = e / (e + d) * re + d / (e + d) * rd
    return max(w, rf + 0.02), {"adj_beta": b, "cost_of_equity": re, "after_tax_cost_of_debt": rd, "debt_weight": d / (e + d)}


def scenarios(fcf0, base_g, wacc, net_cash, shares, tg=0.025, spread_g=0.05, spread_w=0.01):
    cases = {
        "bear": (base_g - spread_g, wacc + spread_w, tg - 0.005),
        "base": (base_g, wacc, tg),
        "bull": (base_g + spread_g, wacc - spread_w, tg + 0.005),
    }
    out = {}
    for name, (g, w, t) in cases.items():
        v, tvs = per_share(fcf0, g, w, t, net_cash, shares)
        out[name] = {"growth": g, "wacc": w, "terminal_growth": t, "value_per_share": v, "terminal_value_share": tvs}
    return out


def sensitivity(fcf0, g, wacc, net_cash, shares, tgs=(0.015, 0.02, 0.025, 0.03, 0.035), wacc_steps=(-0.02, -0.01, 0.0, 0.01, 0.02)):
    rows = []
    for dw in wacc_steps:
        w = wacc + dw
        row = {"wacc": w, "values": []}
        for t in tgs:
            row["values"].append(per_share(fcf0, g, w, t, net_cash, shares)[0] if w > t + 0.005 else None)
        rows.append(row)
    return {"terminal_growth": list(tgs), "rows": rows}


def implied_growth(price, fcf0, wacc, net_cash, shares, tg=0.025, lo=-0.5, hi=1.0):
    """Reverse DCF: stage-1 growth the market price implies. None if outside [lo, hi]."""
    def f(g):
        return per_share(fcf0, g, wacc, tg, net_cash, shares)[0] - price
    flo, fhi = f(lo), f(hi)
    if flo > 0 or fhi < 0:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2
