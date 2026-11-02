# Original experiment disclosure: parameters, exposures, failed attempts, freeze claims
Evidence completion only, dated 2026-11-02. **No new run, no new market-data query, no code/config/results mutation.**

## Original candidate variants (all were calculated in one recorded JS execution)
- \`M0\`: daily trend filter; intraday drawdown/pullback; breakout confirmation.
- \`M1\`: M0 plus EMA21 proximity and close-above-EMA signal.
- \`M2\`: M1 plus a causally selected rolling-high AVWAP proximity/reclaim condition.
These are **three nested signal variants**, not three independently verified backtests. They are research choices, not proven replicas of Martin Luk's discretionary method. Same underlying tickers, date span, and cost assumption for all.

## All strategy parameters visibly used in the original JS tool-call body
| Mechanism | Exact value / operator in original JS | Source |
|---|---|---|
| Symbol universe | GOOG, NVDA, TSLA, AMD, META, PLTR | hardcoded ticker list |
| Daily trend | Prior session \`close > EMA50 > EMA150\`; EMA exponential multiplier \`2/(n+1)\`, seeded with first price | code |
| Intraday bars | 15 minutes, RTH flag \`outside_rth=false\` | IBKR arguments |
| Intraday lookback warm-up | \`i=45\` global starting loop index | code, **not true per-session start** |
| Signal time limit | \`ords[day] <= 14\` (incorrect session count when loop starts mid-data) | code |
| Pullback | \`max(high[i-26:i]) - min(low[i-8:i]) >= 0.01*max(high[i-26:i])\` | code |
| Breakout | \`close[i] > max(high[i-4:i])\` | code |
| EMA support for M1 | \`min(low[i-5:i+1]) <= EMA21[i-1]*1.005\` and \`close[i] > EMA21[i]\` | code |
| Rolling AVWAP anchor for M2 | highest high over \`[i-40, i-3)\`, choose earliest index on ties | code |
| AVWAP formula | \`sum(close[k]*volume[k])/sum(volume[k])\` for \`k=anchor..i-1\` | code |
| AVWAP signal | \`min(low[i-5:i+1]) <= AVWAP*1.005\` and \`close[i] >= AVWAP\` | code |
| ATR | 14 trailing 15-minute true-range bars; seed from first bar / previous close | code |
| Entry | next 15-minute bar open, only when next bar's UTC date is same | code |
| Stop / target | long stop \`open - ATR14\`; target \`open + 1.5*ATR14\` | code |
| Exit horizon | up to 8 bars or session end; bar low trigger checked before bar high | code |
| Gap/slippage assumption | stop/target filled exactly at threshold when touched; **no gap-through stop protection** | code |
| Transaction cost | \`0.0014\` decimal round-trip, 7 bps each side assumed | code |
| Position limit | at most one accepted trade per symbol / model / UTC date | code |
| Equity/portfolio allocation | **NONE**; per-trade returns only | code |

Parameter differences beyond M0/M1/M2 filters: **no such run is recorded in available conversation-level evidence**. Not a verified exhaustive account of experiments performed elsewhere. There is no documented grid search, optimizer, alternative risk/stop levels, price threshold sweep, OOS cross-validation, or alternative bar interval **strategy backtest**.

## Read / exposure / experiment chronology
| Order | Event | Evidence and limits |
|---|---|---|
| Prior research conversation | User-supplied Grok strategy package and Scite literature screening | Theory/idea review, not blind data evidence |
| Feasibility probe | GOOG 1y daily including corporate-action listing | Historical data **viewed before** the experimental configuration commit; separate query |
| Failed data feasibility probe | GOOG 2w 5m | >1000 bars error; **NOT a failed strategy hypothesis** |
| Successful data feasibility probe | GOOG 1w 5m | 390 bars, data-access probe, not a strategy run |
| 2026-11-02 14:33:24Z | \`experiment_config.json\` commit \`e9aa57d0aea649ff7910d3d58ffd260327862473\` | File records one fixed rule set before the result commit; not proof of blinded preregistration |
| After config and before prototype commit | Six-ticker initial 1y daily / 1mo 15m batch, with counts and coverage examined | Original arrays not archived; first of two acquisitions |
| 2026-11-02 14:34:48Z | \`prototype_backtest.py\` commit \`fe44d93b2e324f9cb02a2ccde4ebc15d1a4c490a\` | Code committed before the later JS results, but not executed against a frozen input snapshot |
| After prototype commit | Second 12-IBKR-call acquisition and actual JS signal/return calculation | Original exact source transcribed separately; exact run/market fetch timestamps **UNKNOWN** |
| 2026-11-02 14:35:57Z | \`preliminary_results.json\` commit \`38d20262c6259b19fc07c075ae08a6e5e13cf408\` | Trade ledger and metrics created, no raw bars persisted |
| 2026-11-02 14:37:13Z | \`README.md\` commit \`ce9f44f3dc189da36cba1f80e8c31e4b938b06ba\` | The first independently inspected evidence-bundle reference |

The full original input-time coverage includes **2026-10-02/05 through 2026-11-02** at 15m, plus prior daily windows (mostly 2025-11-03 through 2026-11-02, TSLA 2024-11-01 through 2026-11-02). Signals with recorded trades are only **2026-10-07 through 2026-10-29**. All input dates and trade dates already inspected must be treated as **exploratory / seen**, not as new OOS test data.

### Freezing assessment
- **Verified:** \`experiment_config.json\` existed on GitHub at **14:33:24Z**, before \`preliminary_results.json\` at **14:35:57Z**, and the Python prototype at 14:34:48Z also predates the results file. Commit ancestry/order corroborates the file-level ordering.
- **Not verified:** A cryptographically hashed configuration frozen *before any price-history exposure*, a read-only immutable original market snapshot, exact configuration binding to the JS runtime, any automated lock/hypothesis preregistration, or a complete all-attempts notebook/history.
- **Important:** The JS did **not** read \`experiment_config.json\`; parameters were hardcoded in both code bodies. Therefore the committed config is descriptive, not proven consumed by the executed program. Call this **pre-result commit chronology**, not rigorously verified preregistration.

## Known static defects identified by independent Codex review (NOT corrected here)
1. \`ords\` starts counting at global bar index 45, so its first day need not start at session ordinal 1.
2. \`eod\` can label both actual end of session and the 8-bar time exit.
3. JS and Python use hardcoded constants; no config-reading contract.
4. Gap-through-stop fills use the stop price and do not model a worse market execution.
5. Even-number median was computed using upper-middle observation; by conventional midpoint median, original ledger gives M0 **-0.1903875%**, M1 **-0.2957425%**, M2 **-0.283538%**. The archived original \`preliminary_results.json\` retains its historically reported medians unchanged.
6. Data-snapshot completeness, bar semantics, time-of-day, and adjusted/unadjusted history status are not proven.

These limitations affect fidelity; the historical log is evidence of what was originally calculated, **not** a corrected/validated trading result.

## Failed runs and negative results
- Only explicit **failed tool request** recoverable in this evidence: GOOG 2w / 5m exceeded 1000-bar return limit.
- No separate failed model-run transcript or alternative optimization trial is available; **UNKNOWN** whether the user or any independent external environment tried other tests.
- The actual single JS experiment produced: **M0 34 trades, mean net -0.0700%; M1 24, -0.0242%; M2 23, -0.0118%**. The result was not successful and must remain **HOLD / NOT_REPRODUCED**.
- The first six-ticker data preview is not counted as an additional full backtest; it only displayed coverage, whereas the subsequent run produced trade rows.

## Record invariants
- Original \`prototype_backtest.py\`, \`experiment_config.json\`, \`preliminary_results.json\`, \`preliminary_results.md\`, \`codex_handoff.md\`, and earlier commits are unchanged.
- No paper promotion, data re-download, dependency change, execution or new strategy test follows from this disclosure.
