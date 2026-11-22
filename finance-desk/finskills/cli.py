"""Command line: python3 fin.py <command> ... [--json]"""

import argparse
import json
import os
import sys

from . import __version__, options, reports
from .http import DataError


def money(x, dp=2):
    if x is None:
        return "n/a"
    a = abs(x)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if a >= div:
            return "%s$%.2f%s" % ("-" if x < 0 else "", a / div, suf)
    return "%s$%s" % ("-" if x < 0 else "", format(round(a, dp), ",." + str(dp) + "f"))


def pct(x, dp=1, already=False):
    if x is None or x != x:
        return "n/a"
    return ("%+." + str(dp) + "f%%") % (x if already else x * 100)


def num(x, dp=2):
    return "n/a" if x is None or x != x else ("%." + str(dp) + "f") % x


def line(k, v):
    print("  %-26s %s" % (k, v))


# ------------------------------------------------------------------ printers


def p_quote(r):
    for q in r["quotes"]:
        if "error" in q:
            print("%s: ERROR %s" % (q["symbol"], q["error"]))
            continue
        print("%s  %s  (%s, %s)" % (q["symbol"], q["name"], q.get("exchange"), q.get("currency")))
        line("price", "%s  %s (%s)" % (num(q["price"]), num(q.get("change")), pct(q.get("change_pct"), 2, True)))
        line("data", "%s, as of %s" % (q.get("label"), q.get("as_of")))
        line("day range", "%s - %s" % (num(q.get("day_low")), num(q.get("day_high"))))
        line("52-week range", "%s - %s  (%.0f%% of range, %s from high)" % (
            num(q.get("week52_low")), num(q.get("week52_high")), q.get("week52_position_pct") or 0, pct(q.get("off_52w_high_pct"), 1, True)))
        if q.get("volume"):
            line("volume", "{:,}".format(int(q["volume"])) + ("  (%.2fx 3-month avg)" % q["relative_volume"] if q.get("relative_volume") else ""))
        rt = q.get("realtime_trade")
        if rt and "price" in rt:
            line("real-time last trade", "%s x %s at %s (%s)" % (num(rt["price"]), rt.get("size"), rt.get("time"), rt.get("source")))
        elif rt and "error" in rt:
            line("real-time feed", "error: " + rt["error"])
        print()


def p_tech(t):
    print("%s technicals  (price %s, %s, bars to %s)" % (t["symbol"], num(t["price"]), t.get("label"), t["as_of"]))
    line("trend", t["trend"])
    line("SMA 20 / 50 / 200", "%s / %s / %s" % (num(t["sma20"]), num(t["sma50"]), num(t["sma200"])))
    line("RSI(14)", num(t["rsi14"], 1))
    line("MACD / signal / hist", "%s / %s / %s" % (num(t["macd"]), num(t["macd_signal"]), num(t["macd_hist"])))
    line("ATR(14)", "%s (%s of price)" % (num(t["atr14"]), pct(t.get("atr_pct"), 2, True)))
    line("Bollinger 20,2", "%s - %s" % (num(t["bb_lower"]), num(t["bb_upper"])))
    line("returns 1m/3m/6m/12m", " / ".join(pct(t.get(k)) for k in ("ret_1m", "ret_3m", "ret_6m", "ret_12m")))
    if t.get("benchmark"):
        line("vs %s 3m / 12m" % t["benchmark"], "%s / %s" % (pct(t.get("rel_3m")), pct(t.get("rel_12m"))))
    line("volatility 20d / 1y", "%s / %s ann." % (pct(t.get("vol_20d_ann"), 0).lstrip("+"), pct(t.get("vol_1y_ann"), 0).lstrip("+")))
    line("max drawdown (1y)", pct(t.get("max_drawdown_1y")))
    line("support", ", ".join("%s (%dx)" % (num(x["level"]), x["touches"]) for x in t["support"]) or "none nearby")
    line("resistance", ", ".join("%s (%dx)" % (num(x["level"]), x["touches"]) for x in t["resistance"]) or "none nearby")
    if t["signals"]:
        print("  signals:")
        for s in t["signals"]:
            print("    - " + s)


def p_fund(f):
    print("%s  (CIK %s)  source: %s" % (f.get("company"), f.get("cik"), f["source"]))
    if f.get("price"):
        line("price / market cap", "%s / %s" % (num(f["price"]), money(f.get("market_cap"))))
        line("enterprise value", money(f.get("enterprise_value")))
    line("revenue TTM", "%s (to %s)" % (money(f.get("revenue_ttm")), f.get("revenue_ttm_end")))
    line("net income TTM", money(f.get("net_income_ttm")))
    line("free cash flow TTM", money(f.get("fcf_ttm")))
    line("margins op / net / FCF", " / ".join(pct(f.get(k)).lstrip("+") for k in ("operating_margin", "net_margin", "fcf_margin")))
    line("revenue CAGR 3y", pct(f.get("revenue_cagr_3y")))
    line("ROE", pct(f.get("roe")))
    line("cash+ST inv / debt", "%s / %s" % (money((f.get("cash") or 0) + (f.get("short_term_investments") or 0)), money(f.get("total_debt"))))
    line("debt / equity", num(f.get("debt_to_equity")))
    line("shares", "{:,.0f} ({})".format(f["shares_outstanding"], f.get("shares_source")) if f.get("shares_outstanding") else "n/a")
    if f.get("price"):
        line("P/E  P/S  P/FCF  EV/EBIT", "  ".join(num(f.get(k), 1) for k in ("pe", "ps", "p_fcf", "ev_ebit")))
        line("FCF yield / earnings yld", "%s / %s" % (pct(f.get("fcf_yield")), pct(f.get("earnings_yield"))))
    hist = f.get("history", {})
    if hist.get("revenue"):
        print("  annual (fiscal year end: revenue | net income | FCF):")
        for end, rev in list(hist["revenue"].items())[-5:]:
            print("    %s  %10s | %10s | %10s" % (end, money(rev), money(hist["net_income"].get(end)), money(hist["fcf"].get(end))))


def p_value(v):
    i = v["inputs"]
    print("%s DCF estimate  (price %s)" % (v["symbol"], num(v["price"])))
    line("starting FCF", "%s  [%s]" % (money(i["fcf0"]), i["fcf_source"]))
    line("growth / terminal", "%s / %s" % (pct(i["growth"]), pct(i["terminal_growth"])))
    line("discount rate (WACC)", "%s  [rf %s from %s, beta %s]" % (
        pct(i["wacc"]).lstrip("+"), pct(i["risk_free"]).lstrip("+"), i["risk_free_source"], num(i.get("raw_beta"))))
    line("net cash", money(i["net_cash"]))
    print("  scenario   growth   WACC    value/share   vs price   TV share")
    for name in ("bear", "base", "bull"):
        s = v["scenarios"][name]
        print("  %-8s %7s %7s %13s %9s %8s" % (name, pct(s["growth"]), pct(s["wacc"]).lstrip("+"), num(s["value_per_share"]),
                                              pct(s["upside_pct"], 0, True), pct(s["terminal_value_share"], 0).lstrip("+")))
    ig = v.get("implied_growth")
    line("reverse DCF", "price implies %s/yr FCF growth for 5 yrs" % pct(ig) if ig is not None else "implied growth outside -50%..100%")
    sens = v["sensitivity"]
    print("  sensitivity (value/share): rows = WACC, cols = terminal growth")
    print("           " + "".join("%9s" % pct(t).lstrip("+") for t in sens["terminal_growth"]))
    for row in sens["rows"]:
        print("    %6s " % pct(row["wacc"]).lstrip("+") + "".join("%9s" % num(x) for x in row["values"]))
    for n in v.get("notes", []):
        print("  note: " + n)
    print("  " + v["disclaimer"])


def p_check(c):
    print("%s health check  price %s  (%s, %s)" % (c["symbol"], num(c["price"]), c.get("freshness"), c.get("as_of")))
    for k, s in c["scores"].items():
        print("  %-10s %5.0f  %s" % (k, s, "#" * int(s / 5)))
    print("  %-10s %5.0f  (%s)" % ("OVERALL", c["overall"], c["coverage"]))
    print("  -> " + c["stance"])
    for p in c["positives"]:
        print("   + " + p)
    for n in c["negatives"]:
        print("   - " + n)
    pl = c.get("levels_plan") or {}
    if pl:
        print("  levels: entry zone near %s, idea invalid below %s, first resistance %s" % (
            num(pl.get("entry_zone_near")), num(pl.get("invalidation_below")), num(pl.get("first_resistance"))))
    if c.get("valuation_base"):
        line("base DCF value/share", num(c["valuation_base"]["value_per_share"]))
    for k, e in c.get("missing", {}).items():
        print("  (%s skipped: %s)" % (k, e))
    print("  " + c["disclaimer"])


def p_portfolio(r):
    print("Portfolio  NAV %s  (invested %s, cash %s)" % (money(r["nav"]), money(r["invested"]), money(r["cash"])))
    print("  %-7s %10s %10s %12s %7s %8s %9s %6s" % ("symbol", "shares", "price", "value", "weight", "day", "P&L", "riskC"))
    for p in r["positions"]:
        print("  %-7s %10s %10s %12s %6.1f%% %8s %9s %6s" % (
            p["symbol"], "{:,.4g}".format(p["shares"]), num(p["price"]), money(p["value"]), p["weight"],
            pct(p.get("day_change_pct"), 1, True), pct(p.get("unrealized_pct"), 0, True),
            ("%.0f%%" % p["risk_contribution_pct"]) if p.get("risk_contribution_pct") is not None else "n/a"))
    k = r["risk"]
    if "ann_vol" in k:
        line("volatility (ann.)", pct(k["ann_vol"], 1).lstrip("+"))
        line("beta vs " + r["benchmark"], num(k["beta"]))
        line("1-day 95% VaR", "%s (%s); expected shortfall %s" % (money(k["var95_1d_usd"], 0), pct(k["var95_1d_pct"], 2, True).lstrip("+"), money(k["es95_1d_usd"], 0)))
        line("1y return / max drawdown", "%s / %s  (benchmark %s)" % (
            pct(k["return_1y_pct"], 1, True), pct(k["max_drawdown_1y_pct"], 1, True), pct(k["benchmark_return_1y_pct"], 1, True)))
    print("  suggestions:")
    for s in r["suggestions"]:
        print("    - " + s)
    print("  " + r["disclaimer"])


def p_size(s):
    print("Position size  (%s, account %s, risk %.2f%%)" % (s["side"], money(s["account"], 0), s["risk_pct"]))
    if s.get("atr"):
        line("stop from ATR", "%s x ATR(14) %s on %s" % (s["atr"]["atr_mult"], num(s["atr"]["atr14"]), s["atr"]["symbol"]))
    line("entry / stop", "%s / %s  (%s away)" % (num(s["entry"]), num(s["stop"]), pct(s["stop_distance_pct"], 2, True).lstrip("+")))
    line("shares", "{:,}".format(s["shares"]) + ("  (capped by max position size)" if s["capped_by_max_position"] else ""))
    line("position", "%s = %.1f%% of account" % (money(s["position_value"]), s["position_pct"]))
    line("money at risk", "%s = %.2f%% of account" % (money(s["dollar_risk"]), s["risk_pct_actual"]))
    line("targets 1R / 2R / 3R", " / ".join(num(s["r_targets"][k]) for k in ("1R", "2R", "3R")))
    if s.get("reward_risk"):
        line("your target", "%.2fR" % s["reward_risk"])


def p_odds(o):
    print("%s trade odds  entry %s  stop %s  target %s  over %d sessions" % (o["symbol"], num(o["entry"]), num(o["stop"]), num(o["target"]), o["days"]))
    line("replayed", "%s paths from %d real daily bars (%s to %s), %d-day blocks, seed %d" % (
        "{:,}".format(o["paths"]), o["history_bars"], o["history_from"], o["history_to"], o["block_days"], o["seed"]))
    line("target hit first", "%.1f%%" % (o["p_target_first"] * 100))
    line("stop hit first", "%.1f%%" % (o["p_stop_first"] * 100))
    line("neither by the deadline", "%.1f%%" % (o["p_neither"] * 100))
    line("breakeven win rate", "%.1f%%" % (o["breakeven_win_rate"] * 100))
    line("expected result", "%+.2fR per trade" % o["expected_R"])
    line("R at 5/25/50/75/95 pct", " / ".join("%+.2f" % o["R_percentiles"][q] for q in (5, 25, 50, 75, 95)))
    if o.get("median_days_to_target"):
        line("median days to target", num(o["median_days_to_target"], 0))
    line("same-bar stop+target", "%.1f%% of paths (counted as stop)" % o["ambiguous_bars_pct"])
    print("  History-based odds; news, earnings and regime changes can break them. " + o["disclaimer"])


def p_option(o):
    print("%s  strike %s, %d days  spot %s  vol %s  rate %s" % (
        o["kind"].upper(), num(o["strike"]), o["days"], num(o["spot"]), pct(o["vol"]).lstrip("+"), pct(o["rate"]).lstrip("+")))
    if o.get("implied_vol") is not None:
        line("implied vol", pct(o["implied_vol"]).lstrip("+"))
    for k in ("price", "delta", "gamma", "theta_per_day", "vega_per_pt", "rho_per_pt"):
        line(k, num(o[k], 4))
    line("P(ITM) risk-neutral", "%.1f%%" % (o["prob_itm_riskneutral"] * 100))
    line("1-sd expected move", "+/- %s" % num(o["expected_move_1sd"]))
    for k, v in o.get("sources", {}).items():
        line("source: " + k, v)


def p_payoff(p):
    print("Strategy payoff at expiry (per 1 contract = %s shares)" % p["multiplier"])
    line("net premium", "%s %s" % (money(abs(p["net_debit"])), "debit" if p["net_debit"] > 0 else "credit"))
    line("max profit", p["max_profit"] if isinstance(p["max_profit"], str) else money(p["max_profit"]))
    line("max loss", p["max_loss"] if isinstance(p["max_loss"], str) else money(p["max_loss"]))
    line("breakevens", ", ".join(num(b) for b in p["breakevens"]) or "none")
    for s, v in p["table"]:
        print("    at %10s  %12s" % (num(s), money(v)))


def p_regime(r):
    print("Market regime: %s  (score %d of %d)" % (r["regime"], r["score"], r["max_score"]))
    for w in r["reasons"]:
        print("  - " + w)
    line("10y yield", num(r.get("ten_year_yield")) + "%")
    line("sector leaders (1m)", ", ".join(r["leaders_1m"]))
    line("sector laggards (1m)", ", ".join(r["laggards_1m"]))
    for s in ("SPY", "QQQ", "IWM", "DIA"):
        x = r["rows"].get(s)
        if x:
            line(s, "%s  1m %s  %s 50d  %s 200d" % (num(x["price"]), pct(x["ret_1m"]), "above" if x["above_50d"] else "below", "above" if x["above_200d"] else "below"))
    for s, e in r["errors"].items():
        print("  (%s unavailable: %s)" % (s, e))


def p_news(n):
    print("%s headlines  (%s)" % (n["symbol"], n["note"]))
    for it in n["items"]:
        print("  - %s  [%s]\n    %s" % (it["title"], it["published"], it["link"]))


def p_json_only(x):
    print(json.dumps(x, indent=2, default=str))


# ---------------------------------------------------------------------- main


def build_parser():
    ap = argparse.ArgumentParser(prog="fin.py", description="finance-desk: live market checks, estimates and risk math")
    ap.add_argument("--version", action="version", version="finance-desk " + __version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, help_):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--json", action="store_true", help="machine-readable output")
        p.add_argument("--no-cache", action="store_true", help="bypass the local cache")
        return p

    p = add("quote", "live quote(s) with freshness check")
    p.add_argument("symbols", nargs="+")
    p = add("tech", "technical snapshot")
    p.add_argument("symbol")
    p.add_argument("--benchmark", default="SPY")
    p = add("fundamentals", "fundamentals from SEC filings")
    p.add_argument("symbol")
    p = add("value", "DCF fair-value estimate with scenarios")
    p.add_argument("symbol")
    p.add_argument("--growth", type=float, help="stage-1 annual growth, decimal (0.08 = 8%%)")
    p.add_argument("--wacc", type=float, help="discount rate, decimal")
    p.add_argument("--terminal", type=float, default=0.025)
    p.add_argument("--fcf", type=float, help="starting annual free cash flow in dollars")
    p.add_argument("--fcf-margin", type=float, help="value on revenue x this FCF margin (decimal)")
    p.add_argument("--erp", type=float, default=0.05, help="equity risk premium, decimal")
    p = add("check", "one-shot stock health check and stance")
    p.add_argument("symbol")
    p = add("portfolio", "portfolio check from a holdings CSV")
    p.add_argument("csv")
    p.add_argument("--benchmark", default="SPY")
    p.add_argument("--max-weight", type=float, default=20.0)
    p = add("size", "position size from account risk")
    p.add_argument("symbol", nargs="?")
    p.add_argument("--account", type=float, required=True)
    p.add_argument("--risk", type=float, default=1.0, help="percent of account to risk")
    p.add_argument("--entry", type=float)
    p.add_argument("--stop", type=float)
    p.add_argument("--target", type=float)
    p.add_argument("--atr-mult", type=float, default=2.0)
    p.add_argument("--max-position", type=float, default=25.0, help="max position size, percent of account")
    p = add("odds", "odds a trade hits target before stop (bar replay)")
    p.add_argument("symbol")
    p.add_argument("--entry", type=float, required=True)
    p.add_argument("--stop", type=float, required=True)
    p.add_argument("--target", type=float, required=True)
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--paths", type=int, default=10000)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--years", type=int, default=2, choices=(1, 2, 5, 10))
    p = add("option", "Black-Scholes price, Greeks, implied vol")
    p.add_argument("kind", choices=("call", "put"))
    p.add_argument("--strike", type=float, required=True)
    p.add_argument("--days", type=float, required=True)
    p.add_argument("--symbol")
    p.add_argument("--spot", type=float)
    p.add_argument("--vol", type=float, help="annual volatility, decimal")
    p.add_argument("--price", type=float, help="option market price, to solve implied vol")
    p.add_argument("--rate", type=float)
    p.add_argument("--div", type=float, default=0.0)
    p = add("payoff", "multi-leg option strategy payoff at expiry")
    p.add_argument("legs", nargs="+", help="e.g. 'long call 100 2.5' 'short call 110 0.8'")
    p.add_argument("--multiplier", type=float, default=100)
    add("regime", "market regime: trend, breadth, VIX")
    p = add("news", "latest headlines")
    p.add_argument("symbol")
    p.add_argument("--limit", type=int, default=10)
    p = add("estimates", "analyst estimates and price targets (needs FMP_API_KEY)")
    p.add_argument("symbol")
    return ap


def run(a):
    if a.cmd == "quote":
        return reports.quote_report(a.symbols), p_quote
    if a.cmd == "tech":
        return reports.technical_report(a.symbol, a.benchmark), p_tech
    if a.cmd == "fundamentals":
        return reports.fundamentals_report(a.symbol), p_fund
    if a.cmd == "value":
        return reports.valuation_report(a.symbol, a.growth, a.wacc, a.terminal, a.fcf, a.fcf_margin, a.erp), p_value
    if a.cmd == "check":
        return reports.check_report(a.symbol), p_check
    if a.cmd == "portfolio":
        return reports.portfolio_report(a.csv, a.benchmark, a.max_weight), p_portfolio
    if a.cmd == "size":
        return reports.size_report(a.account, a.risk, a.entry, a.stop, a.symbol, a.atr_mult, a.max_position, a.target), p_size
    if a.cmd == "odds":
        return reports.odds_report(a.symbol, a.entry, a.stop, a.target, a.days, a.paths, a.seed, a.years), p_odds
    if a.cmd == "option":
        return reports.options_report(a.kind, a.strike, a.days, a.spot, a.vol, a.symbol, a.rate, a.div, a.price), p_option
    if a.cmd == "payoff":
        legs = [options.parse_leg(x) for x in a.legs]
        res = options.payoff(legs, a.multiplier)
        res["multiplier"] = a.multiplier
        return res, p_payoff
    if a.cmd == "regime":
        return reports.regime_report(), p_regime
    if a.cmd == "news":
        return reports.news_report(a.symbol, a.limit), p_news
    if a.cmd == "estimates":
        return reports.estimates_report(a.symbol), p_json_only
    raise SystemExit("unknown command")


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.no_cache:
        os.environ["FINDESK_NO_CACHE"] = "1"
    try:
        result, printer = run(a)
    except (DataError, ValueError, OSError) as exc:
        if a.json:
            print(json.dumps({"error": str(exc)}))
        else:
            print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    try:
        if a.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            printer(result)
    except BrokenPipeError:  # output piped into head/less and closed early
        sys.stdout = open(os.devnull, "w")
    return 0
