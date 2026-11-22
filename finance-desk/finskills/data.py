"""Data providers.

Keyless (default):
  * Yahoo Finance chart endpoint: quotes, intraday and daily OHLCV
  * Yahoo Finance RSS: headlines
  * SEC EDGAR XBRL company facts: fundamentals from 10-K / 10-Q filings
  * FRED: 10-year Treasury yield (risk-free rate)

Optional, only when the user sets keys in the environment:
  * Alpaca market data (ALPACA_API_KEY_ID + ALPACA_API_SECRET_KEY): real-time IEX trades
  * Financial Modeling Prep (FMP_API_KEY): analyst estimates and price targets

This module only reads data. It contains no code that places orders.
"""

import datetime as dt
import os
import urllib.parse
import xml.etree.ElementTree as ET

from .http import DataError, fetch, fetch_json

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?{qs}"
YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
ALPACA_TRADE = "https://data.alpaca.markets/v2/stocks/{sym}/trades/latest?feed={feed}"
FMP_BASE = "https://financialmodelingprep.com/stable/"

INTRADAY = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}


def norm_symbol(sym):
    s = sym.strip().upper()
    if not s or len(s) > 15 or any(c.isspace() for c in s):
        raise DataError("invalid symbol: %r" % sym)
    return s


# --------------------------------------------------------------------- Yahoo


class Bars:
    """OHLCV series with the chart metadata Yahoo returns."""

    def __init__(self, symbol, meta, t, o, h, l, c, adj, v):
        self.symbol, self.meta = symbol, meta
        self.t, self.o, self.h, self.l, self.c, self.adj, self.v = t, o, h, l, c, adj, v

    def __len__(self):
        return len(self.c)

    @property
    def tz(self):
        return dt.timezone(dt.timedelta(seconds=int(self.meta.get("gmtoffset") or 0)))

    def dates(self):
        tz = self.tz
        return [dt.datetime.fromtimestamp(x, tz).date().isoformat() for x in self.t]


def parse_chart(payload, symbol):
    chart = (payload or {}).get("chart") or {}
    if chart.get("error"):
        err = chart["error"]
        raise DataError("Yahoo: %s (%s)" % (err.get("description") or err, symbol))
    results = chart.get("result") or []
    if not results:
        raise DataError("Yahoo returned no data for %s" % symbol)
    r = results[0]
    meta = r.get("meta") or {}
    ts = r.get("timestamp") or []
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    adj_list = ((r.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose")
    cols = {k: q.get(k) or [None] * len(ts) for k in ("open", "high", "low", "close", "volume")}
    adj_list = adj_list or cols["close"]
    out = {k: [] for k in ("t", "o", "h", "l", "c", "adj", "v")}
    for i, t in enumerate(ts):
        c = cols["close"][i]
        if c is None:
            continue  # Yahoo pads halted / missing bars with nulls
        o, h, l = cols["open"][i], cols["high"][i], cols["low"][i]
        out["t"].append(t)
        out["o"].append(o if o is not None else c)
        out["h"].append(h if h is not None else c)
        out["l"].append(l if l is not None else c)
        out["c"].append(c)
        a = adj_list[i] if i < len(adj_list) else None
        out["adj"].append(a if a is not None else c)
        out["v"].append(cols["volume"][i] or 0)
    return Bars(meta.get("symbol") or symbol, meta, out["t"], out["o"], out["h"], out["l"], out["c"], out["adj"], out["v"])


def chart(symbol, range_="1y", interval="1d", ttl=None):
    sym = norm_symbol(symbol)
    if ttl is None:
        ttl = 20 if interval in INTRADAY else 300
    qs = urllib.parse.urlencode({"range": range_, "interval": interval, "includePrePost": "false", "events": "div|split"})
    url = YAHOO_CHART.format(sym=urllib.parse.quote(sym), qs=qs)
    try:
        payload = fetch_json(url, ttl=ttl)
    except DataError as exc:
        if "HTTP 404" in str(exc):
            raise DataError("Yahoo Finance does not know the symbol %s (indexes start with ^, e.g. ^GSPC; crypto like BTC-USD)" % sym)
        raise
    return parse_chart(payload, sym)


def market_state(meta, now=None):
    now = now or dt.datetime.now(dt.timezone.utc).timestamp()
    ctp = meta.get("currentTradingPeriod") or {}

    def inside(name):
        p = ctp.get(name) or {}
        return p.get("start") is not None and p["start"] <= now < p.get("end", 0)

    if inside("regular"):
        return "OPEN"
    if inside("pre"):
        return "PRE-MARKET"
    if inside("post"):
        return "AFTER-HOURS"
    return "CLOSED"


def freshness(meta, now=None):
    """Classify how current the price is: real-time, delayed or last close."""
    now = now or dt.datetime.now(dt.timezone.utc).timestamp()
    t = meta.get("regularMarketTime")
    if not t:
        return {"label": "unknown", "age_seconds": None}
    age = max(0, int(now - t))
    state = market_state(meta, now)
    if state == "OPEN":
        if age <= 120:
            label = "real-time"
        elif age <= 20 * 60:
            label = "delayed ~%d min" % round(age / 60)
        else:
            label = "stale (%d min old; possible halt or feed issue)" % round(age / 60)
    else:
        label = "last regular-session price (market %s)" % state.lower()
    return {"label": label, "age_seconds": age, "market_state": state}


def fmt_time(epoch, gmtoffset=0):
    tz = dt.timezone(dt.timedelta(seconds=int(gmtoffset or 0)))
    return dt.datetime.fromtimestamp(epoch, tz).strftime("%Y-%m-%d %H:%M %z")


def quote(symbol, now=None):
    sym = norm_symbol(symbol)
    day = chart(sym, "1d", "5m", ttl=15)
    m = day.meta
    price = m.get("regularMarketPrice")
    if price is None:
        raise DataError("no price for %s" % sym)
    prev = m.get("previousClose") or m.get("chartPreviousClose")
    q = {
        "symbol": sym,
        "name": m.get("longName") or m.get("shortName") or sym,
        "exchange": m.get("fullExchangeName") or m.get("exchangeName"),
        "currency": m.get("currency"),
        "type": m.get("instrumentType"),
        "price": price,
        "previous_close": prev,
        "change": (price - prev) if prev else None,
        "change_pct": ((price / prev - 1) * 100) if prev else None,
        "day_high": m.get("regularMarketDayHigh"),
        "day_low": m.get("regularMarketDayLow"),
        "volume": m.get("regularMarketVolume"),
        "week52_high": m.get("fiftyTwoWeekHigh"),
        "week52_low": m.get("fiftyTwoWeekLow"),
        "as_of": fmt_time(m["regularMarketTime"], m.get("gmtoffset")) if m.get("regularMarketTime") else None,
        "source": "Yahoo Finance chart API",
    }
    q.update(freshness(m, now))
    hi, lo = q["week52_high"], q["week52_low"]
    if hi and lo and hi > lo:
        q["week52_position_pct"] = (price - lo) / (hi - lo) * 100
        q["off_52w_high_pct"] = (price / hi - 1) * 100
    try:
        daily = chart(sym, "3mo", "1d")
        vols = [v for v in daily.v[-61:-1] if v]
        if vols:
            q["avg_volume_3m"] = sum(vols) / len(vols)
            if q["volume"]:
                q["relative_volume"] = q["volume"] / q["avg_volume_3m"]
    except DataError:
        pass
    rt = alpaca_latest_trade(sym)
    if rt:
        q["realtime_trade"] = rt
    return q


def news(symbol, limit=10):
    sym = norm_symbol(symbol)
    raw = fetch(YAHOO_RSS.format(sym=urllib.parse.quote(sym)), ttl=300)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise DataError("could not parse news feed for %s: %s" % (sym, exc))
    items = []
    for it in root.iter("item"):
        items.append({
            "title": (it.findtext("title") or "").strip(),
            "published": (it.findtext("pubDate") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
        })
        if len(items) >= limit:
            break
    return items


# -------------------------------------------------------------------- Alpaca


def alpaca_keys():
    kid = os.environ.get("ALPACA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY")
    sec = os.environ.get("ALPACA_API_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY")
    return (kid, sec) if kid and sec else None


def alpaca_latest_trade(symbol):
    """Real-time last trade from Alpaca's free IEX feed. None when no keys are set."""
    keys = alpaca_keys()
    if not keys or "^" in symbol or "=" in symbol:
        return None
    url = ALPACA_TRADE.format(sym=urllib.parse.quote(symbol), feed=os.environ.get("ALPACA_DATA_FEED", "iex"))
    try:
        data = fetch_json(url, headers={"APCA-API-KEY-ID": keys[0], "APCA-API-SECRET-KEY": keys[1]}, ttl=0)
    except DataError as exc:
        return {"error": str(exc)}
    trade = data.get("trade") or {}
    if "p" not in trade:
        return None
    return {"price": trade["p"], "size": trade.get("s"), "time": trade.get("t"), "source": "Alpaca (%s feed)" % data.get("feed", "iex")}


# ---------------------------------------------------------------------- FRED


def fred_latest(series="DGS10"):
    raw = fetch(FRED_CSV.format(series=urllib.parse.quote(series)), ttl=12 * 3600).decode("utf-8", "replace")
    for line in reversed(raw.strip().splitlines()[1:]):
        parts = line.split(",")
        if len(parts) == 2 and parts[1] not in (".", ""):
            try:
                return {"series": series, "date": parts[0], "value": float(parts[1])}
            except ValueError:
                continue
    raise DataError("FRED series %s has no recent value" % series)


def risk_free_rate():
    """10y Treasury yield as a decimal, with its source. Falls back to 4% and says so."""
    try:
        r = fred_latest("DGS10")
        return r["value"] / 100.0, "FRED DGS10 %s" % r["date"]
    except DataError as exc:
        return 0.04, "fallback 4.0%% (FRED unavailable: %s)" % exc


# ----------------------------------------------------------------- SEC EDGAR


def sec_headers():
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        raise DataError(
            "SEC EDGAR asks every client to identify itself. Set SEC_USER_AGENT to your "
            "name and email, e.g.  export SEC_USER_AGENT=\"Jane Doe jane@example.com\""
        )
    return {"User-Agent": ua, "Accept": "application/json"}


def sec_cik(symbol):
    sym = norm_symbol(symbol)
    data = fetch_json(SEC_TICKERS, headers=sec_headers(), ttl=7 * 86400)
    candidates = {sym, sym.replace(".", "-"), sym.replace("-", ".")}
    for row in data.values():
        if str(row.get("ticker", "")).upper() in candidates:
            return int(row["cik_str"]), row.get("title")
    raise DataError("%s is not in SEC's ticker list (non-US issuer, ETF or fund?)" % sym)


def sec_company_facts(symbol):
    cik, title = sec_cik(symbol)
    try:
        facts = fetch_json(SEC_FACTS.format(cik=cik), headers=sec_headers(), ttl=12 * 3600, timeout=40)
    except DataError as exc:
        if "HTTP 404" in str(exc):
            raise DataError("SEC has no XBRL financial statements for %s (ETF, fund or trust?)" % symbol.upper())
        raise
    facts["_cik"], facts["_title"] = cik, title
    return facts


# ----------------------------------------------------------------------- FMP


def fmp_key():
    return os.environ.get("FMP_API_KEY") or None


def fmp(endpoint, **params):
    key = fmp_key()
    if not key:
        raise DataError("FMP_API_KEY is not set (free key: https://site.financialmodelingprep.com/developer/docs)")
    params["apikey"] = key
    return fetch_json(FMP_BASE + endpoint + "?" + urllib.parse.urlencode(params), ttl=3600)


def analyst_estimates(symbol):
    sym = norm_symbol(symbol)
    if not fmp_key():
        raise DataError("analyst estimates need a Financial Modeling Prep key: set FMP_API_KEY "
                        "(free tier at https://site.financialmodelingprep.com/developer/docs)")
    out = {"symbol": sym, "source": "Financial Modeling Prep"}
    for name, ep, extra in (
        ("annual_estimates", "analyst-estimates", {"period": "annual", "limit": 4}),
        ("price_target", "price-target-consensus", {}),
        ("ratings", "grades-consensus", {}),
    ):
        try:
            out[name] = fmp(ep, symbol=sym, **extra)
        except DataError as exc:
            out[name] = {"error": str(exc)}
    return out
