"""Offline tests: no network. Run with  python3 -m unittest discover -s tests"""

import io
import math
import os
import random
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from finskills import data, fundamentals, indicators as ind, options, portfolio, risk, technical, valuation  # noqa: E402
from finskills.cli import main  # noqa: E402
from finskills.http import redact  # noqa: E402


def synthetic_bars(symbol="TEST", n=300, drift=0.0005, vol=0.015, seed=1, start=100.0):
    rng = random.Random(seed)
    t0 = 1_700_000_000
    t, o, h, l, c, v = [], [], [], [], [], []
    px = start
    for i in range(n):
        op = px
        px = px * math.exp(drift + vol * rng.gauss(0, 1))
        hi, lo = max(op, px) * (1 + abs(rng.gauss(0, vol / 3))), min(op, px) * (1 - abs(rng.gauss(0, vol / 3)))
        t.append(t0 + i * 86400)
        o.append(op), h.append(hi), l.append(lo), c.append(px), v.append(1_000_000 + i)
    meta = {"symbol": symbol, "regularMarketPrice": c[-1], "gmtoffset": 0, "regularMarketTime": t[-1]}
    return data.Bars(symbol, meta, t, o, h, l, c, list(c), v)


class TestIndicators(unittest.TestCase):
    def test_sma_ema(self):
        xs = [1, 2, 3, 4, 5]
        self.assertEqual(ind.sma(xs, 3), [None, None, 2.0, 3.0, 4.0])
        e = ind.ema(xs, 3)
        self.assertAlmostEqual(e[2], 2.0)
        self.assertAlmostEqual(e[3], 3.0)

    def test_rsi_extremes(self):
        self.assertEqual(ind.rsi(list(range(1, 40)), 14)[-1], 100.0)
        self.assertLess(ind.rsi(list(range(40, 1, -1)), 14)[-1], 1e-9)

    def test_atr_constant_range(self):
        h, l, c = [11.0] * 30, [9.0] * 30, [10.0] * 30
        self.assertAlmostEqual(ind.atr(h, l, c, 14)[-1], 2.0)

    def test_drawdown_beta_corr(self):
        self.assertAlmostEqual(ind.max_drawdown([100, 120, 60, 130])[0], -0.5)
        r = [0.01, -0.02, 0.015, 0.0, 0.03, -0.01]
        self.assertAlmostEqual(ind.beta(r, r), 1.0)
        self.assertAlmostEqual(ind.beta([2 * x for x in r], r), 2.0)
        self.assertAlmostEqual(ind.correlation(r, r), 1.0)

    def test_percentile(self):
        self.assertEqual(ind.percentile([1, 2, 3, 4, 5], 50), 3)
        self.assertAlmostEqual(ind.percentile([0, 10], 25), 2.5)


class TestValuation(unittest.TestCase):
    def test_gordon_closed_form(self):
        # constant growth equal to terminal growth reduces to FCF1 / (r - g)
        ev, _ = valuation.dcf_ev(100.0, 0.03, 0.09, 0.03)
        self.assertAlmostEqual(ev, 100.0 * 1.03 / (0.09 - 0.03), places=6)

    def test_reverse_dcf_round_trip(self):
        v, _ = valuation.per_share(50.0, 0.12, 0.09, 0.025, 100.0, 10.0)
        g = valuation.implied_growth(v, 50.0, 0.09, 100.0, 10.0)
        self.assertAlmostEqual(g, 0.12, places=5)

    def test_wacc_guard(self):
        with self.assertRaises(ValueError):
            valuation.dcf_ev(100, 0.05, 0.03, 0.03)

    def test_scenarios_ordered(self):
        sc = valuation.scenarios(100.0, 0.06, 0.09, 0.0, 10.0)
        self.assertLess(sc["bear"]["value_per_share"], sc["base"]["value_per_share"])
        self.assertLess(sc["base"]["value_per_share"], sc["bull"]["value_per_share"])

    def test_capm_clamps(self):
        w, parts = valuation.capm_wacc(0.04, 5.0, 1e9, 0.0)
        self.assertAlmostEqual(parts["adj_beta"], 2.0)
        self.assertAlmostEqual(w, 0.04 + 2.0 * 0.05)


class TestOptions(unittest.TestCase):
    def test_put_call_parity(self):
        s, k, d, v, r = 100.0, 105.0, 60, 0.3, 0.04
        c = options.bs(s, k, d, v, r, kind="call")["price"]
        p = options.bs(s, k, d, v, r, kind="put")["price"]
        self.assertAlmostEqual(c - p, s - k * math.exp(-r * d / 365), places=8)

    def test_implied_vol_round_trip(self):
        px = options.bs(100, 95, 45, 0.37, 0.045, kind="put")["price"]
        self.assertAlmostEqual(options.implied_vol(px, 100, 95, 45, 0.045, kind="put"), 0.37, places=5)

    def test_bull_call_spread(self):
        legs = [options.parse_leg("long call 100 5"), options.parse_leg("short call 110 2")]
        p = options.payoff(legs)
        self.assertAlmostEqual(p["max_profit"], 700.0)
        self.assertAlmostEqual(p["max_loss"], -300.0)
        self.assertEqual(len(p["breakevens"]), 1)
        self.assertAlmostEqual(p["breakevens"][0], 103.0, places=1)

    def test_unlimited(self):
        self.assertEqual(options.payoff([options.parse_leg("short call 100 3")])["max_loss"], "unlimited")
        self.assertEqual(options.payoff([options.parse_leg("long call 100 3")])["max_profit"], "unlimited")

    def test_bad_leg(self):
        with self.assertRaises(ValueError):
            options.parse_leg("buy something")


class TestRisk(unittest.TestCase):
    def test_position_size(self):
        r = risk.position_size(50_000, 1.0, 100.0, 95.0)
        self.assertEqual(r["shares"], 100)
        self.assertAlmostEqual(r["dollar_risk"], 500.0)
        self.assertEqual(r["side"], "long")
        self.assertAlmostEqual(r["r_targets"]["2R"], 110.0)

    def test_position_cap(self):
        r = risk.position_size(10_000, 2.0, 100.0, 99.5, max_position_pct=25)
        self.assertEqual(r["shares"], 25)
        self.assertTrue(r["capped_by_max_position"])

    def test_short_side(self):
        r = risk.position_size(10_000, 1.0, 50.0, 52.0)
        self.assertEqual(r["side"], "short")
        self.assertAlmostEqual(r["r_targets"]["1R"], 48.0)

    def test_trade_odds_deterministic(self):
        shapes = risk.bar_shapes(synthetic_bars())
        a = risk.trade_odds(shapes, 100, 95, 110, 20, paths=2000, seed=3)
        b = risk.trade_odds(shapes, 100, 95, 110, 20, paths=2000, seed=3)
        self.assertEqual(a, b)
        self.assertAlmostEqual(a["p_target_first"] + a["p_stop_first"] + a["p_neither"], 1.0)

    def test_trade_odds_monotone_market(self):
        up = [(1.0, 1.02, 0.999, 1.02)] * 50
        r = risk.trade_odds(up, 100, 95, 105, 10, paths=200)
        self.assertEqual(r["p_target_first"], 1.0)
        with self.assertRaises(ValueError):
            risk.trade_odds(up, 100, 105, 110, 10)

    def test_var(self):
        rets = [-0.05] + [0.001] * 99
        var, es = risk.var_historical(rets, 0.95)
        self.assertGreater(var, -0.002)
        self.assertGreaterEqual(es, var)


class TestData(unittest.TestCase):
    def test_parse_chart_skips_nulls(self):
        payload = {"chart": {"result": [{
            "meta": {"symbol": "X", "regularMarketPrice": 3.0},
            "timestamp": [1, 2, 3],
            "indicators": {"quote": [{"open": [1, None, 3], "high": [1, None, 3], "low": [1, None, 3],
                                      "close": [1, None, 3], "volume": [10, None, 30]}],
                           "adjclose": [{"adjclose": [0.5, None, 1.5]}]},
        }], "error": None}}
        b = data.parse_chart(payload, "X")
        self.assertEqual(b.c, [1, 3])
        self.assertEqual(b.adj, [0.5, 1.5])

    def test_parse_chart_error(self):
        with self.assertRaises(data.DataError):
            data.parse_chart({"chart": {"result": None, "error": {"description": "No data"}}}, "X")

    def test_freshness(self):
        meta = {"regularMarketTime": 1000, "currentTradingPeriod": {"regular": {"start": 900, "end": 5000}}}
        self.assertEqual(data.freshness(meta, now=1060)["label"], "real-time")
        self.assertTrue(data.freshness(meta, now=1000 + 600)["label"].startswith("delayed"))
        self.assertIn("closed", data.freshness(meta, now=6000)["label"])

    def test_symbol_validation(self):
        with self.assertRaises(data.DataError):
            data.norm_symbol("AA PL")

    def test_redact(self):
        self.assertNotIn("SECRET", redact("https://x.test/a?symbol=AAPL&apikey=SECRET"))


def fact(start, end, val, form, filed):
    return {"start": start, "end": end, "val": val, "form": form, "filed": filed, "accn": filed}


class TestFundamentals(unittest.TestCase):
    def facts(self):
        rev = [
            fact("2022-01-01", "2022-12-31", 100.0, "10-K", "2023-02-01"),
            fact("2023-01-01", "2023-12-31", 120.0, "10-K", "2024-02-01"),
            fact("2023-01-01", "2023-06-30", 55.0, "10-Q", "2023-08-01"),
            fact("2024-01-01", "2024-06-30", 70.0, "10-Q", "2024-08-01"),
            fact("2024-04-01", "2024-06-30", 36.0, "10-Q", "2024-08-01"),
        ]
        return {"entityName": "Test Co", "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": rev}},
                "StockholdersEquity": {"units": {"USD": [{"end": "2024-06-30", "val": 500.0, "form": "10-Q", "filed": "2024-08-01"}]}},
                "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [fact("2024-01-01", "2024-06-30", 10.0, "10-Q", "2024-08-01")]}},
            },
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
                {"end": "2024-07-20", "val": 6.0, "form": "10-Q", "filed": "2024-08-01", "accn": "a1"},
                {"end": "2024-07-20", "val": 4.0, "form": "10-Q", "filed": "2024-08-01", "accn": "a1"},
            ]}}},
        }}

    def test_ttm(self):
        val, end, method = fundamentals.ttm(self.facts(), ["Revenues"])
        self.assertAlmostEqual(val, 120 + 70 - 55)
        self.assertEqual(end, "2024-06-30")
        self.assertIn("TTM", method)

    def test_annual_and_cagr(self):
        s = fundamentals.annual_series(self.facts(), ["Revenues"])
        self.assertEqual(list(s.values()), [100.0, 120.0])
        self.assertAlmostEqual(fundamentals.cagr(s, 3), 0.2)

    def test_share_classes_summed(self):
        self.assertEqual(fundamentals.shares_outstanding(self.facts())[0], 10.0)

    def test_summary_and_price(self):
        s = fundamentals.summarize(self.facts())
        self.assertAlmostEqual(s["revenue_ttm"], 135.0)
        self.assertIsNone(s["fcf_ttm"])  # not reported -> None, never guessed
        m = fundamentals.with_price(s, 20.0)
        self.assertAlmostEqual(m["market_cap"], 200.0)
        self.assertAlmostEqual(m["ps"], 200.0 / 135.0)


class TestTechnicalAndPortfolio(unittest.TestCase):
    def test_snapshot(self):
        s = technical.snapshot(synthetic_bars(n=300), synthetic_bars("SPY", n=300, seed=2))
        for k in ("sma200", "rsi14", "atr14", "trend", "signals", "rel_3m"):
            self.assertIn(k, s)
        self.assertTrue(0 <= s["rsi14"] <= 100)

    def test_portfolio(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
            fh.write("symbol,shares,cost_basis,target_weight\nAAA,100,50,30\nBBB,10,100,\nCASH,1000,,\n")
            path = fh.name
        try:
            holdings = portfolio.read_holdings(path)
        finally:
            os.unlink(path)
        bars = {"AAA": synthetic_bars("AAA", seed=3), "BBB": synthetic_bars("BBB", seed=4)}
        rep = portfolio.analyze(holdings, bars, synthetic_bars("SPY", seed=5))
        self.assertAlmostEqual(sum(p["weight"] for p in rep["positions"]) + rep["cash"] / rep["nav"] * 100, 100.0)
        self.assertIn("var95_1d_usd", rep["risk"])
        self.assertTrue(rep["suggestions"])


class TestCli(unittest.TestCase):
    def test_payoff_offline(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["payoff", "long put 95 1.5", "--json"])
        self.assertEqual(rc, 0)
        self.assertIn("breakevens", buf.getvalue())

    def test_size_offline(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["size", "--account", "10000", "--entry", "20", "--stop", "19"])
        self.assertEqual(rc, 0)
        self.assertIn("100", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
