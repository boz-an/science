"""Portfolio check: live valuation, P&L, risk, concentration and rebalancing."""

import csv

from . import indicators as ind
from .risk import var_historical

CASH_SYMBOLS = {"CASH", "USD", "$CASH"}


def read_holdings(path):
    """CSV with columns: symbol, shares, [cost_basis per share], [target_weight in %]."""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fields = {f.strip().lower(): f for f in (reader.fieldnames or [])}
        if "symbol" not in fields or not ({"shares", "quantity", "qty"} & set(fields)):
            raise ValueError("holdings CSV needs 'symbol' and 'shares' columns")
        qcol = fields.get("shares") or fields.get("quantity") or fields.get("qty")

        def num(row, name):
            col = fields.get(name)
            v = (row.get(col) or "").strip().replace(",", "").replace("$", "").replace("%", "") if col else ""
            return float(v) if v else None

        for row in reader:
            sym = (row.get(fields["symbol"]) or "").strip().upper()
            if not sym or sym.startswith("#"):
                continue
            rows.append({
                "symbol": sym,
                "shares": float((row.get(qcol) or "0").replace(",", "")),
                "cost_basis": num(row, "cost_basis") if "cost_basis" in fields else num(row, "cost"),
                "target_weight": num(row, "target_weight") if "target_weight" in fields else num(row, "target"),
            })
    if not rows:
        raise ValueError("no holdings found in %s" % path)
    return rows


def analyze(holdings, bars_by_symbol, bench_bars, max_weight=20.0, corr_flag=0.85):
    positions, total, cash = [], 0.0, 0.0
    for h in holdings:
        if h["symbol"] in CASH_SYMBOLS:
            cash += h["shares"]
            continue
        b = bars_by_symbol[h["symbol"]]
        price = b.meta.get("regularMarketPrice") or b.c[-1]
        value = price * h["shares"]
        p = {"symbol": h["symbol"], "shares": h["shares"], "price": price, "value": value,
             "day_change_pct": (b.c[-1] / b.c[-2] - 1) * 100 if len(b.c) > 1 else None}
        if h.get("cost_basis"):
            p["cost_value"] = h["cost_basis"] * h["shares"]
            p["unrealized_pnl"] = value - p["cost_value"]
            p["unrealized_pct"] = (price / h["cost_basis"] - 1) * 100
        if h.get("target_weight") is not None:
            p["target_weight"] = h["target_weight"]
        positions.append(p)
        total += value
    nav = total + cash
    for p in positions:
        p["weight"] = p["value"] / nav * 100 if nav else 0.0

    # Align daily returns on common dates
    date_sets = [set(bars_by_symbol[p["symbol"]].dates()) for p in positions] + [set(bench_bars.dates())]
    common = sorted(set.intersection(*date_sets))[-253:]
    series = {}
    for p in positions:
        b = bars_by_symbol[p["symbol"]]
        m = dict(zip(b.dates(), b.adj))
        series[p["symbol"]] = [m[d] for d in common]
    bm = dict(zip(bench_bars.dates(), bench_bars.adj))
    bench_px = [bm[d] for d in common]
    rets = {s: ind.pct_returns(px) for s, px in series.items()}
    bench_r = ind.pct_returns(bench_px)
    w = {p["symbol"]: p["value"] / nav for p in positions} if nav else {}
    n = len(bench_r)
    port_r = [sum(w[s] * rets[s][i] for s in rets) for i in range(n)]

    risk = {"days_used": n}
    if n >= 30:
        var95, es95 = var_historical(port_r, 0.95)
        risk.update({
            "ann_vol": ind.ann_vol(port_r), "beta": ind.beta(port_r, bench_r),
            "var95_1d_pct": var95 * 100, "var95_1d_usd": var95 * nav,
            "es95_1d_usd": es95 * nav,
        })
        eq = [1.0]
        for r in port_r:
            eq.append(eq[-1] * (1 + r))
        risk["max_drawdown_1y_pct"] = ind.max_drawdown(eq)[0] * 100
        risk["return_1y_pct"] = (eq[-1] - 1) * 100
        risk["benchmark_return_1y_pct"] = (bench_px[-1] / bench_px[0] - 1) * 100
        var_p = ind.stdev(port_r) ** 2
        for p in positions:
            r = rets[p["symbol"]]
            p["risk_contribution_pct"] = (w[p["symbol"]] * ind.covariance(r, port_r) / var_p * 100) if var_p else None
            p["beta"] = ind.beta(r, bench_r)

    pairs = []
    syms = list(rets)
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            c = ind.correlation(rets[syms[i]], rets[syms[j]])
            if c == c and c >= corr_flag:
                pairs.append((syms[i], syms[j], c))
    pairs.sort(key=lambda x: -x[2])

    return {"nav": nav, "invested": total, "cash": cash, "positions": sorted(positions, key=lambda p: -p["value"]),
            "risk": risk, "high_correlation_pairs": pairs, "benchmark": bench_bars.symbol,
            "suggestions": suggestions(positions, risk, pairs, nav, cash, max_weight)}


def suggestions(positions, risk, pairs, nav, cash, max_weight):
    out = []
    for p in positions:
        tw = p.get("target_weight")
        if p["weight"] > max_weight and (tw is None or p["weight"] > tw + 1):
            trim = (p["weight"] - max_weight) / 100 * nav
            out.append("%s is %.1f%% of the portfolio (limit %.0f%%): trimming ~$%s would bring it to the limit"
                       % (p["symbol"], p["weight"], max_weight, format(round(trim), ",")))
        if p.get("unrealized_pct") is not None and p["unrealized_pct"] <= -25:
            out.append("%s is %.0f%% below cost: re-check the thesis; in a taxable account a loss harvest may be worth a look"
                       % (p["symbol"], p["unrealized_pct"]))
        rc = p.get("risk_contribution_pct")
        if rc is not None and rc > 1.75 * p["weight"] and rc > 15:
            out.append("%s supplies %.0f%% of portfolio risk on a %.0f%% weight" % (p["symbol"], rc, p["weight"]))
    top3 = sum(sorted((p["weight"] for p in positions), reverse=True)[:3])
    if len(positions) > 3 and top3 > 60:
        out.append("top 3 holdings are %.0f%% of the portfolio: concentrated" % top3)
    for a, b, c in pairs[:5]:
        out.append("%s and %s move together (correlation %.2f): they diversify each other little" % (a, b, c))
    beta = risk.get("beta")
    if beta is not None and beta > 1.3:
        out.append("portfolio beta %.2f: a 10%% market drop implies roughly a %.0f%% drop" % (beta, beta * 10))
    if nav and cash / nav > 0.25:
        out.append("%.0f%% in cash: deliberate, or idle?" % (cash / nav * 100))
    targets = [p for p in positions if p.get("target_weight") is not None]
    for p in targets:
        diff = (p["target_weight"] - p["weight"]) / 100 * nav
        if abs(diff) >= max(0.01 * nav, 1):
            shares = diff / p["price"]
            out.append("rebalance %s to %.1f%%: %s %d shares (~$%s)"
                       % (p["symbol"], p["target_weight"], "buy" if shares > 0 else "sell", abs(int(shares)), format(abs(round(diff)), ",")))
    if not out:
        out.append("no concentration, correlation or drift flags at the current thresholds")
    return out
