"""Fundamentals from SEC EDGAR XBRL company facts (US-GAAP filers).

Annual figures come from 10-K full-year facts. Trailing-twelve-month (TTM)
figures are built as: last fiscal year + current year-to-date - prior
year-to-date, the standard way to roll 10-Q cumulative figures forward.
"""

import datetime as dt

from .http import DataError

REVENUE = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
           "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet"]
NET_INCOME = ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"]
OPERATING_INCOME = ["OperatingIncomeLoss"]
OCF = ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]
CAPEX = ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]
CASH = ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "Cash"]
SHORT_INVEST = ["MarketableSecuritiesCurrent", "ShortTermInvestments", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"]
LT_DEBT_TOTAL = ["LongTermDebt"]
LT_DEBT_NONCURRENT = ["LongTermDebtNoncurrent"]
LT_DEBT_CURRENT = ["LongTermDebtCurrent"]
ST_DEBT = ["ShortTermBorrowings", "CommercialPaper"]
EQUITY = ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]
EPS_DILUTED = ["EarningsPerShareDiluted"]
DILUTED_SHARES = ["WeightedAverageNumberOfDilutedSharesOutstanding"]


def _d(s):
    return dt.date.fromisoformat(s)


def _units(facts, concept, unit="USD", ns="us-gaap"):
    node = ((facts.get("facts") or {}).get(ns) or {}).get(concept) or {}
    return (node.get("units") or {}).get(unit) or []


def _rows(facts, concept, unit, forms=("10-K", "10-Q", "10-K/A", "10-Q/A")):
    out = []
    for r in _units(facts, concept, unit):
        if r.get("form") in forms and r.get("val") is not None and r.get("end"):
            out.append(r)
    return out


def _dedupe_latest_filed(rows, key):
    best = {}
    for r in rows:
        k = key(r)
        if k not in best or r.get("filed", "") > best[k].get("filed", ""):
            best[k] = r
    return best


def annual_series(facts, concepts, unit="USD"):
    """{fiscal_year_end: value} of full-year 10-K figures, merging concepts by priority."""
    series = {}
    for concept in concepts:
        rows = [r for r in _rows(facts, concept, unit, ("10-K", "10-K/A")) if r.get("start")]
        rows = [r for r in rows if 340 <= (_d(r["end"]) - _d(r["start"])).days <= 380]
        for end, r in _dedupe_latest_filed(rows, lambda r: r["end"]).items():
            series.setdefault(end, float(r["val"]))
    return dict(sorted(series.items()))


def ttm(facts, concepts, unit="USD"):
    """Trailing twelve months for a flow item. Returns (value, period_end, method) or None."""
    for concept in concepts:
        rows = [r for r in _rows(facts, concept, unit) if r.get("start")]
        if not rows:
            continue
        annual = [r for r in rows if r["form"].startswith("10-K") and 340 <= (_d(r["end"]) - _d(r["start"])).days <= 380]
        if not annual:
            continue
        fy = max(_dedupe_latest_filed(annual, lambda r: r["end"]).values(), key=lambda r: r["end"])
        fy_end = _d(fy["end"])
        ytd = [r for r in rows if _d(r["end"]) > fy_end and abs((_d(r["start"]) - fy_end).days - 1) <= 5]
        if not ytd:
            return float(fy["val"]), fy["end"], "fiscal year (%s)" % concept
        cur = max(_dedupe_latest_filed(ytd, lambda r: r["end"]).values(), key=lambda r: r["end"])
        cur_end, cur_len = _d(cur["end"]), (_d(cur["end"]) - _d(cur["start"])).days
        prior = [
            r for r in rows
            if abs((_d(r["end"]) - (cur_end - dt.timedelta(days=364))).days) <= 8
            and abs((_d(r["end"]) - _d(r["start"])).days - cur_len) <= 8
        ]
        if not prior:
            return float(fy["val"]), fy["end"], "fiscal year (%s; prior-year YTD missing)" % concept
        pr = max(prior, key=lambda r: r.get("filed", ""))
        value = float(fy["val"]) + float(cur["val"]) - float(pr["val"])
        return value, cur["end"], "TTM = FY + YTD - prior YTD (%s)" % concept
    return None


def latest_instant(facts, concepts, unit="USD"):
    best = None
    for concept in concepts:
        rows = _rows(facts, concept, unit)
        if not rows:
            continue
        r = max(rows, key=lambda r: (r["end"], r.get("filed", "")))
        if best is None or r["end"] > best[1]:
            best = (float(r["val"]), r["end"], concept)
    return best


def shares_outstanding(facts):
    """Cover-page share count (summing share classes), cross-checked with diluted weighted shares."""
    rows = [r for r in _units(facts, "EntityCommonStockSharesOutstanding", "shares", ns="dei") if r.get("val")]
    cover = None
    if rows:
        last = max(rows, key=lambda r: (r.get("filed", ""), r["end"]))
        same = {(r["val"]) for r in rows if r.get("accn") == last.get("accn") and r["end"] == last["end"]}
        cover = (float(sum(same)), last["end"], "dei:EntityCommonStockSharesOutstanding")
    diluted = ttm_like_latest(facts, DILUTED_SHARES)
    if cover and diluted and not (0.7 <= cover[0] / diluted[0] <= 1.3):
        return diluted  # class mix-ups on the cover page: trust the income-statement count
    return cover or diluted


def ttm_like_latest(facts, concepts):
    for concept in concepts:
        rows = [r for r in _rows(facts, concept, "shares") if r.get("start")]
        if rows:
            r = max(rows, key=lambda r: (r["end"], r.get("filed", "")))
            return float(r["val"]), r["end"], concept
    return None


def cagr(series, years=3):
    vals = list(series.values())
    if len(vals) < 2:
        return None
    n = min(years, len(vals) - 1)
    start, end = vals[-1 - n], vals[-1]
    if start <= 0 or end <= 0:
        return None
    return (end / start) ** (1.0 / n) - 1


def summarize(facts):
    """Normalized fundamentals dict. Missing items are None, never guessed."""
    if not (facts.get("facts") or {}).get("us-gaap"):
        raise DataError("no US-GAAP facts for this company (foreign IFRS filer?)")
    out = {"company": facts.get("entityName") or facts.get("_title"), "cik": facts.get("_cik"), "source": "SEC EDGAR XBRL company facts"}

    def flow(name, concepts):
        r = ttm(facts, concepts)
        out[name + "_ttm"] = r[0] if r else None
        out[name + "_ttm_end"] = r[1] if r else None
        out.setdefault("methods", {})[name] = r[2] if r else "not reported"

    flow("revenue", REVENUE)
    flow("net_income", NET_INCOME)
    flow("operating_income", OPERATING_INCOME)
    flow("operating_cash_flow", OCF)
    flow("capex", CAPEX)
    ocf, capex = out["operating_cash_flow_ttm"], out["capex_ttm"]
    out["fcf_ttm"] = (ocf - capex) if ocf is not None and capex is not None else None

    rev_hist = annual_series(facts, REVENUE)
    ni_hist = annual_series(facts, NET_INCOME)
    ocf_hist = annual_series(facts, OCF)
    capex_hist = annual_series(facts, CAPEX)
    fcf_hist = {k: ocf_hist[k] - capex_hist[k] for k in ocf_hist if k in capex_hist}
    out["history"] = {
        "revenue": dict(list(rev_hist.items())[-6:]),
        "net_income": dict(list(ni_hist.items())[-6:]),
        "fcf": dict(list(fcf_hist.items())[-6:]),
    }
    out["revenue_cagr_3y"] = cagr(rev_hist, 3)
    out["fcf_cagr_3y"] = cagr(fcf_hist, 3)

    def inst(name, concepts):
        r = latest_instant(facts, concepts)
        out[name] = r[0] if r else None
        if r:
            out.setdefault("as_of", {})[name] = r[1]

    inst("cash", CASH)
    inst("short_term_investments", SHORT_INVEST)
    inst("equity", EQUITY)
    lt = latest_instant(facts, LT_DEBT_TOTAL)
    if lt is None:
        nc, cur = latest_instant(facts, LT_DEBT_NONCURRENT), latest_instant(facts, LT_DEBT_CURRENT)
        lt_val = (nc[0] if nc else 0.0) + (cur[0] if cur else 0.0)
        lt = (lt_val, max(x[1] for x in (nc, cur) if x), "noncurrent+current") if (nc or cur) else None
    st = latest_instant(facts, ST_DEBT)
    out["total_debt"] = (lt[0] if lt else 0.0) + (st[0] if st else 0.0) if (lt or st) else None

    sh = shares_outstanding(facts)
    out["shares_outstanding"] = sh[0] if sh else None
    out["shares_source"] = sh[2] if sh else None
    eps = ttm(facts, EPS_DILUTED, unit="USD/shares")
    out["eps_diluted_ttm"] = eps[0] if eps else None

    rev = out["revenue_ttm"]
    if rev:
        for k in ("net_income", "operating_income"):
            v = out[k + "_ttm"]
            out[k.replace("_income", "") + "_margin"] = v / rev if v is not None else None
        out["fcf_margin"] = out["fcf_ttm"] / rev if out["fcf_ttm"] is not None else None
    if out["equity"] and out["equity"] > 0:
        if out["net_income_ttm"] is not None:
            out["roe"] = out["net_income_ttm"] / out["equity"]
        if out["total_debt"] is not None:
            out["debt_to_equity"] = out["total_debt"] / out["equity"]
    return out


def with_price(f, price):
    """Add market-value ratios to a fundamentals summary at the given share price."""
    m = dict(f)
    sh = f.get("shares_outstanding")
    if not sh or not price:
        return m
    mcap = price * sh
    cash = (f.get("cash") or 0.0) + (f.get("short_term_investments") or 0.0)
    ev = mcap + (f.get("total_debt") or 0.0) - cash
    m.update({"price": price, "market_cap": mcap, "enterprise_value": ev, "net_cash": cash - (f.get("total_debt") or 0.0)})

    def ratio(num, den):
        return num / den if num is not None and den not in (None, 0) and den > 0 else None

    m["pe"] = ratio(mcap, f.get("net_income_ttm"))
    m["ps"] = ratio(mcap, f.get("revenue_ttm"))
    m["p_fcf"] = ratio(mcap, f.get("fcf_ttm"))
    m["ev_ebit"] = ratio(ev, f.get("operating_income_ttm"))
    m["fcf_yield"] = (f["fcf_ttm"] / mcap) if f.get("fcf_ttm") is not None else None
    m["earnings_yield"] = (f["net_income_ttm"] / mcap) if f.get("net_income_ttm") is not None else None
    return m
