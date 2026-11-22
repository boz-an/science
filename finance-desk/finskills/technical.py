"""Technical snapshot: trend, momentum, volatility, levels, rule-based signals."""

from . import indicators as ind


def _last(xs):
    for x in reversed(xs):
        if x is not None:
            return x
    return None


def snapshot(bars, bench=None):
    c, h, l, v = bars.adj, bars.h, bars.l, bars.v
    if len(c) < 60:
        raise ValueError("need at least 60 daily bars for a technical snapshot (got %d)" % len(c))
    # High/low are unadjusted; scale them onto the adjusted close for consistency.
    f = [a / r if r else 1.0 for a, r in zip(bars.adj, bars.c)]
    h = [x * k for x, k in zip(h, f)]
    l = [x * k for x, k in zip(l, f)]
    price = c[-1]
    s20, s50, s200 = _last(ind.sma(c, 20)), _last(ind.sma(c, 50)), _last(ind.sma(c, 200)) if len(c) >= 200 else None
    r = _last(ind.rsi(c, 14))
    m_line, m_sig, m_hist = ind.macd(c)
    a = _last(ind.atr(h, l, c, 14))
    bu, bm, bl = ind.bollinger(c, 20, 2.0)
    rets = ind.pct_returns(c)
    s = {
        "symbol": bars.symbol,
        "price": price,
        "as_of": bars.dates()[-1],
        "sma20": s20, "sma50": s50, "sma200": s200,
        "rsi14": r,
        "macd": _last(m_line), "macd_signal": _last(m_sig), "macd_hist": _last(m_hist),
        "atr14": a, "atr_pct": a / price * 100 if a else None,
        "bb_upper": _last(bu), "bb_lower": _last(bl),
        "vol_20d_ann": ind.ann_vol(rets[-20:]) if len(rets) >= 20 else None,
        "vol_1y_ann": ind.ann_vol(rets[-252:]),
        "ret_1m": ind.total_return(c, 21), "ret_3m": ind.total_return(c, 63),
        "ret_6m": ind.total_return(c, 126), "ret_12m": ind.total_return(c, 252),
        "max_drawdown_1y": ind.max_drawdown(c[-252:])[0],
    }
    hist = [x for x in m_hist if x is not None]
    s["macd_cross"] = None
    if len(hist) >= 2:
        if hist[-2] <= 0 < hist[-1]:
            s["macd_cross"] = "bullish cross today"
        elif hist[-2] >= 0 > hist[-1]:
            s["macd_cross"] = "bearish cross today"
    vols = [x for x in v[-51:-1] if x]
    if vols and v[-1]:
        s["volume_vs_50d"] = v[-1] / (sum(vols) / len(vols))
    hi52, lo52 = max(h[-252:]), min(l[-252:])
    s["off_52w_high_pct"] = (price / hi52 - 1) * 100
    s["above_52w_low_pct"] = (price / lo52 - 1) * 100

    levels = ind.swing_levels(h, l)
    below = [x for x in levels if x["level"] < price * 0.995]
    above = [x for x in levels if x["level"] > price * 1.005]
    s["support"] = sorted(below, key=lambda x: -x["level"])[:3]
    s["resistance"] = sorted(above, key=lambda x: x["level"])[:3]

    if bench is not None and len(bench.adj) > 64:
        bc = bench.adj
        for k, n in (("rel_3m", 63), ("rel_12m", 252)):
            ra, rb = ind.total_return(c, n), ind.total_return(bc, n)
            s[k] = (ra - rb) if ra is not None and rb is not None else None
        s["benchmark"] = bench.symbol

    s["trend"] = classify_trend(price, s20, s50, s200)
    s["signals"] = signals(s)
    return s


def classify_trend(price, s20, s50, s200):
    if s200 is None:
        if s50 is None:
            return "unknown"
        return "up (short history)" if price > s50 else "down (short history)"
    if price > s50 > s200 and (s20 is None or s20 > s50):
        return "strong uptrend"
    if price > s200 and s50 > s200:
        return "uptrend"
    if price < s50 < s200 and (s20 is None or s20 < s50):
        return "strong downtrend"
    if price < s200 and s50 < s200:
        return "downtrend"
    return "sideways / transition"


def signals(s):
    out = []
    r = s.get("rsi14")
    if r is not None:
        if r >= 70:
            out.append("RSI %.0f: overbought, chasing here has poor risk/reward" % r)
        elif r <= 30:
            out.append("RSI %.0f: oversold, watch for a reversal before buying" % r)
    if s.get("macd_cross"):
        out.append("MACD " + s["macd_cross"])
    if s.get("sma50") and s.get("sma200"):
        if s["sma50"] > s["sma200"] and s["sma200"] < s["price"] < s["sma50"]:
            out.append("pullback inside a long-term uptrend (below the 50-day, above the 200-day average)")
        if s["sma50"] > s["sma200"] and s["price"] < s["sma200"]:
            out.append("broke below the 200-day average while the 50-day is still above it: uptrend under threat")
        if abs(s["sma50"] / s["sma200"] - 1) < 0.01:
            out.append("50-day and 200-day averages are converging (possible golden/death cross)")
    if s.get("bb_upper") and s["price"] > s["bb_upper"]:
        out.append("closed above the upper Bollinger band (stretched)")
    if s.get("bb_lower") and s["price"] < s["bb_lower"]:
        out.append("closed below the lower Bollinger band (stretched to the downside)")
    if s.get("volume_vs_50d") and s["volume_vs_50d"] >= 2:
        out.append("volume %.1fx the 50-day average (institutional activity)" % s["volume_vs_50d"])
    if s.get("off_52w_high_pct") is not None and s["off_52w_high_pct"] > -3:
        out.append("within 3% of the 52-week high")
    if s.get("rel_3m") is not None:
        out.append("%s the benchmark by %.1f pts over 3 months" % ("beating" if s["rel_3m"] >= 0 else "lagging", abs(s["rel_3m"]) * 100))
    return out
