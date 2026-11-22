"""Technical indicators and return statistics on plain Python lists.

Series are aligned to the input: positions without enough history are None.
"""

import math


def sma(xs, n):
    out, s = [None] * len(xs), 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= n:
            s -= xs[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(xs, n):
    out = [None] * len(xs)
    if len(xs) < n:
        return out
    k = 2.0 / (n + 1)
    prev = sum(xs[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(xs)):
        prev = xs[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(closes, n=14):
    """Wilder's RSI."""
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag, al = gains / n, losses / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0.0)) / n
        al = (al * (n - 1) + max(-d, 0.0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def macd(closes, fast=12, slow=26, signal=9):
    ef, es = ema(closes, fast), ema(closes, slow)
    line = [a - b if a is not None and b is not None else None for a, b in zip(ef, es)]
    start = next((i for i, v in enumerate(line) if v is not None), None)
    sig = [None] * len(closes)
    if start is not None:
        tail = ema(line[start:], signal)
        sig[start:] = tail
    hist = [a - b if a is not None and b is not None else None for a, b in zip(line, sig)]
    return line, sig, hist


def true_range(h, l, c):
    tr = [h[0] - l[0]]
    for i in range(1, len(c)):
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return tr


def atr(h, l, c, n=14):
    """Wilder's average true range."""
    tr = true_range(h, l, c)
    out = [None] * len(c)
    if len(c) < n:
        return out
    prev = sum(tr[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(c)):
        prev = (prev * (n - 1) + tr[i]) / n
        out[i] = prev
    return out


def bollinger(closes, n=20, k=2.0):
    mid = sma(closes, n)
    up, lo = [None] * len(closes), [None] * len(closes)
    for i in range(n - 1, len(closes)):
        w = closes[i - n + 1:i + 1]
        sd = math.sqrt(sum((x - mid[i]) ** 2 for x in w) / n)
        up[i], lo[i] = mid[i] + k * sd, mid[i] - k * sd
    return up, mid, lo


def pct_returns(closes):
    return [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1]]


def log_returns(closes):
    return [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0 and closes[i] > 0]


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def stdev(xs):
    if len(xs) < 2:
        return float("nan")
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def ann_vol(rets, periods=252):
    return stdev(rets) * math.sqrt(periods)


def total_return(closes, bars):
    if len(closes) <= bars or not closes[-1 - bars]:
        return None
    return closes[-1] / closes[-1 - bars] - 1


def max_drawdown(closes):
    peak, mdd, peak_i, best = closes[0], 0.0, 0, (0, 0)
    for i, x in enumerate(closes):
        if x > peak:
            peak, peak_i = x, i
        dd = x / peak - 1
        if dd < mdd:
            mdd, best = dd, (peak_i, i)
    return mdd, best[0], best[1]


def covariance(a, b):
    n = min(len(a), len(b))
    a, b = a[-n:], b[-n:]
    ma, mb = mean(a), mean(b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (n - 1)


def correlation(a, b):
    n = min(len(a), len(b))
    sa, sb = stdev(a[-n:]), stdev(b[-n:])
    return covariance(a, b) / (sa * sb) if sa and sb else float("nan")


def beta(asset, market):
    n = min(len(asset), len(market))
    vm = stdev(market[-n:]) ** 2
    return covariance(asset, market) / vm if vm else float("nan")


def percentile(xs, q):
    """Linear-interpolated percentile, q in [0, 100]."""
    s = sorted(xs)
    if not s:
        return float("nan")
    pos = (len(s) - 1) * q / 100.0
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def swing_levels(h, l, window=5, lookback=120):
    """Swing highs/lows over the lookback, clustered within 1.5% into levels."""
    n = len(h)
    start = max(window, n - lookback)
    highs, lows = [], []
    for i in range(start, n - window):
        if h[i] == max(h[i - window:i + window + 1]):
            highs.append(h[i])
        if l[i] == min(l[i - window:i + window + 1]):
            lows.append(l[i])
    return _cluster(highs + lows)


def _cluster(levels, tol=0.015):
    out = []
    for x in sorted(levels):
        if out and abs(x / out[-1][0] - 1) <= tol:
            c, k = out[-1]
            out[-1] = ((c * k + x) / (k + 1), k + 1)
        else:
            out.append((x, 1))
    return [{"level": c, "touches": k} for c, k in out]
