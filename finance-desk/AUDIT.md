# Source audit: GitHub finance skill packs

How trustworthy the candidate skill packs are, and what `finance-desk` took
from each. Reviewed 2026-11-22 against each repository's default branch.

## Method

Static review only. None of the reviewed code was executed. For each repo we:

1. Cloned shallow into an isolated folder, then fetched commit metadata
   (`--filter=blob:none`) to see the history.
2. Listed plugin manifests, `.mcp.json`, hooks, settings files and install
   scripts.
3. Extracted every network host the code contacts.
4. Grepped non-test code for `eval`/`exec`, `os.system`, `shell=True`,
   `subprocess`, `child_process`, `pickle`, base64 decoding, `.ssh`,
   keychain, cron and `curl | sh`.
5. Located all order-placement code and checked how it is gated.
6. Scanned every `SKILL.md` for prompt-injection or permission-escalation
   wording ("ignore previous", "without asking", "silently", "bypass"),
   for install commands, and for live-trading switches.
7. Checked dependency pinning and lockfiles, tests, and maintainer history.

**What this does not cover:** a line-by-line review of all code (one repo
has 370k lines of Python), the transitive dependencies, or runtime
behaviour. Treat the result as "no red flags found", not a guarantee.

## Summary

| Repo | Trust | Why |
|---|---|---|
| [tradermonty/claude-trading-skills](https://github.com/tradermonty/claude-trading-skills) | **High** | 13 months of history, 1,152 commits, 43 contributors, 547 test files, `uv.lock`, its own secret-leak and `shell=True` checks. No hooks. Alpaca defaults to paper. |
| [staskh/trading_skills](https://github.com/staskh/trading_skills) | **Medium-high** | 306 commits, 7 contributors, tests, `uv.lock`. IB orders are dry-run by default on a read-only connection, but the skill text includes `--execute` commands that place **live** orders. |
| [himself65/finance-skills](https://github.com/himself65/finance-skills) | **Medium** | Clean repo (109 commits, mostly one author), but several skills pull in third-party tools: an unpinned global npm CLI plus a Chrome extension that reuses logged-in sessions, a `uvx` MCP server from another author's git repo, and TradingView launched with a debugging port open. |
| [Jakeschincariol/day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) / [trader-skill](https://github.com/Jakeschincariol/trader-skill) | **Medium (code good, provenance weak)** | Well-written stdlib-only Python with tests. However, each repo is a **single commit** with no reviewable history, and gained 9.2k / 2.0k stars and 2.2k / 423 forks in about 5 weeks, which is unusually fast. |

None of the five repos contained hooks, obfuscated code, `eval`/`exec`,
`shell=True`, credential harvesting, or hidden network destinations. No
SKILL.md contained instructions to hide actions from the user or to skip
confirmation.

## Details

### tradermonty/claude-trading-skills (MIT)
- **Scale:** 94 skills, 1,115 Python files, created 2025-10-19.
- **Hosts:** financialmodelingprep.com, finviz.com, Alpaca (paper and live
  APIs), cmegroup.com, sec.gov, raw.githubusercontent.com (docs).
  Everything expected.
- **Subprocess:** only in dev tooling, the example dashboard, and two
  meta-skills that run `uv`. All use argument lists and timeouts.
- **Keys:** FMP keys travel in the URL query (FMP requires that). 73
  files apply redaction, and a repo script audits for key leaks.
- **Orders:** the portfolio-manager skill uses Alpaca through MCP, with
  `ALPACA_PAPER=true` in the docs.
- **Caveats:**
  - Many skills require paid or keyed data (FMP, Finviz Elite).
  - Python dependencies are lower-bound pins (`requests>=2.31`) for
    standalone installs. The repo itself has a lockfile.

### staskh/trading_skills (MIT)
- **Hosts:** Yahoo (via yfinance), IB Gateway on 127.0.0.1, Massive
  (formerly Polygon), nasdaq.com, federalreserve.gov. All expected.
- **Orders:** `stop_loss.py` and `trailing_stop.py` call `ib.placeOrder`
  only with `--execute`. Without it they connect with `readonly=True`.
  This is good design. Still, port 7496 is the *live* account, and the
  skill documents `--execute --forced`. Only use it if you want Claude to
  be able to manage real stops.
- **Dependencies:** 17 runtime dependencies with `>=` bounds (pandas-ta,
  ib-async, massive, mcp, reportlab and others), locked by `uv.lock`
  when you use `uv`.

### himself65/finance-skills (MIT)
- **Code:** mostly SKILL.md instructions (3 Python files, 41 JS files for
  opencli plugins).
- **Third-party execution:**
  - `plugins/data-providers/.mcp.json` runs
    `uvx --from git+https://github.com/atilaahmettaner/tradingview-mcp@<commit>`,
    third-party code pinned to a commit. Pinning is good, but that code
    is outside this repo.
  - Social-reader skills tell the agent to run
    `npm install -g @jackwener/opencli`. The package is unpinned and
    installed globally. It also requires a Chrome "Browser Bridge"
    extension that **reuses your logged-in browser sessions** (X, Discord,
    LinkedIn). That is a large grant of trust.
  - `tradingview/launch.js` relaunches the TradingView desktop app with
    `--remote-debugging-port`. While it runs, any local process can drive
    your logged-in TradingView session through that port.
- **Valuation skills:** pure instructions plus yfinance
  (`pip install yfinance`, unpinned).

### Jakeschincariol/day-trader-skill and trader-skill (MIT)
- **Code quality:** stdlib only (`urllib`), 20-second timeouts, seeded
  RNG, writes confined to a local `trader/` folder. One `subprocess.run`
  call runs `pdftotext` with an argument list (no shell). Tests included.
- **Hosts:** Yahoo chart and RSS, sec.gov, data.sec.gov, the House Clerk,
  nasdaqtrader.com, nyse.com, stooq.com, api.openfigi.com. All expected.
- **Orders:** through Alpaca's MCP server (`uvx alpaca-mcp-server`,
  unpinned). The example config forces `ALPACA_PAPER_TRADE=true`, and the
  skill says it never switches to live.
- **Provenance concern:** a single squashed commit per repo, so the
  code's history can't be reviewed. Star and fork counts grew very fast.
  The code we read is clean, but pin to a commit you have reviewed if you
  install it.

## What finance-desk took (ideas, not code)

finance-desk is a clean-room rewrite. No code was copied. These ideas
were adopted:

| Idea | From |
|---|---|
| Stdlib-only engine; public keyless data; seeded, reproducible Monte Carlo; pessimistic rule when stop and target fall in the same bar | day-trader-skill |
| Fail-closed data handling (never fill gaps with guesses); R-multiple position sizing; market-regime and breadth scoring; FMP as the optional estimates source | claude-trading-skills |
| Bull/base/bear DCF with a WACC x terminal-growth sensitivity grid | finance-skills |
| Read-only by default; Black-Scholes Greeks; portfolio risk report | trading_skills |

## Design choices that follow from the audit

1. **No order placement anywhere.** The engine has no broker write code,
   so no prompt can make it trade.
2. **Zero third-party packages.** Python standard library only. There is
   nothing to `pip install`, so there is no transitive supply chain.
3. **No MCP servers, hooks, browser extensions or global installs.**
4. **Keys are optional and stay in env vars:**
   - `FMP_API_KEY` for estimates.
   - `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY` for real-time IEX
     trades. These are read-only market-data calls.
   - Keys are redacted from errors. Cache files are named by SHA-256 hash
     and created with `0600` permissions.
5. **Only public endpoints.** Yahoo's cookie- and crumb-gated endpoints
   (quoteSummary, option chains) are not used.
6. **Headlines are labelled as untrusted text** in output and in the
   skill instructions.
