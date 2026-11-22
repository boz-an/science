"""Position sizing, trade odds (Monte Carlo bar replay) and Value-at-Risk."""

import math
import random

from . import indicators as ind


def position_size(account, risk_pct, entry, stop, max_position_pct=25.0, target=None):
    """Fixed-fractional sizing: risk `risk_pct`% of the account between entry and stop."""
    if account <= 0 or entry <= 0 or stop <= 0:
        raise ValueError("account, entry and stop must be positive")
    if entry == stop:
        raise ValueError("entry and stop must differ")
    side = "long" if stop < entry else "short"
    per_share = abs(entry - stop)
    risk_budget = account * risk_pct / 100.0
    shares = math.floor(risk_budget / per_share)
    cap = math.floor(account * max_position_pct / 100.0 / entry)
    capped = shares > cap
    shares = min(shares, cap)
    out = {
        "side": side, "shares": shares, "position_value": shares * entry,
        "position_pct": shares * entry / account * 100, "risk_per_share": per_share,
        "dollar_risk": shares * per_share, "risk_pct_actual": shares * per_share / account * 100,
        "stop_distance_pct": per_share / entry * 100, "capped_by_max_position": capped,
        "r_targets": {"1R": entry + (per_share if side == "long" else -per_share),
                      "2R": entry + (2 * per_share if side == "long" else -2 * per_share),
                      "3R": entry + (3 * per_share if side == "long" else -3 * per_share)},
    }
    if target:
        out["reward_risk"] = abs(target - entry) / per_share
    return out


def kelly_fraction(win_prob, reward_risk):
    """Full Kelly fraction for a binary bet; callers should use a fraction of it."""
    if reward_risk <= 0:
        return 0.0
    return max(0.0, win_prob - (1 - win_prob) / reward_risk)


def bar_shapes(bars, lookback=504):
    """Each daily bar as (open, high, low, close) relative to the prior close."""
    o, h, l, c = bars.o, bars.h, bars.l, bars.c
    n = len(c)
    out = []
    for i in range(max(1, n - lookback), n):
        p = c[i - 1]
        if p and h[i] >= l[i]:
            out.append((o[i] / p, h[i] / p, l[i] / p, c[i] / p))
    return out


def trade_odds(shapes, entry, stop, target, days, paths=10000, seed=7, block=5):
    """Replay random blocks of real daily bars from `entry` for `days` sessions.

    Counts which level is touched first. If stop and target are both inside one
    bar, the stop is assumed first (pessimistic: daily bars hide the order).
    """
    if not shapes:
        raise ValueError("no historical bars to replay")
    long = target > entry
    if long and not stop < entry < target:
        raise ValueError("for a long trade use stop < entry < target")
    if not long and not target < entry < stop:
        raise ValueError("for a short trade use target < entry < stop")
    rng = random.Random(seed)
    n = len(shapes)
    hit_t = hit_s = 0
    ambiguous = 0
    days_to = []
    finals = []
    for _ in range(paths):
        px = entry
        outcome = None
        d = 0
        while d < days and outcome is None:
            start = rng.randrange(0, max(1, n - block + 1))
            for k in range(block):
                if d >= days:
                    break
                o, hi, lo, cl = shapes[min(start + k, n - 1)]
                bar_hi, bar_lo = px * hi, px * lo
                touch_t = bar_hi >= target if long else bar_lo <= target
                touch_s = bar_lo <= stop if long else bar_hi >= stop
                d += 1
                if touch_s:
                    outcome = "stop"
                    ambiguous += 1 if touch_t else 0
                    break
                if touch_t:
                    outcome = "target"
                    break
                px *= cl
        if outcome == "target":
            hit_t += 1
            days_to.append(d)
            finals.append(target)
        elif outcome == "stop":
            hit_s += 1
            finals.append(stop)
        else:
            finals.append(px)
    risk = abs(entry - stop)
    r_mult = [((f - entry) if long else (entry - f)) / risk for f in finals]
    p_t, p_s = hit_t / paths, hit_s / paths
    return {
        "paths": paths, "days": days, "seed": seed, "block_days": block, "history_bars": n,
        "p_target_first": p_t, "p_stop_first": p_s, "p_neither": 1 - p_t - p_s,
        "ambiguous_bars_pct": ambiguous / paths * 100,
        "expected_R": sum(r_mult) / paths,
        "median_days_to_target": ind.percentile(days_to, 50) if days_to else None,
        "R_percentiles": {q: ind.percentile(r_mult, q) for q in (5, 25, 50, 75, 95)},
        "breakeven_win_rate": risk / (risk + abs(target - entry)),
    }


def var_historical(returns, conf=0.95):
    """One-period historical VaR and expected shortfall, as positive loss fractions."""
    if len(returns) < 30:
        raise ValueError("need at least 30 returns for VaR")
    cut = ind.percentile(returns, (1 - conf) * 100)
    tail = [r for r in returns if r <= cut]
    return -cut, -(sum(tail) / len(tail))
