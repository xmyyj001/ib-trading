# Exploratory ChatGPT research screen — 2026-11-02

## Research question
Do trend-pullback breakouts (M0), adding EMA21 (M1), and adding a **causally anchored** volume-weighted price filter (M2) show incremental trading promise? These are **our independent models inspired by** X trader Martin Luk, **not** a replication of his discretionary decisions.

## Data and run
- Read-only IBKR connector, US stocks: GOOG, NVDA, TSLA, AMD, META, PLTR.
- 1-year daily bars (TSLA response returned 501 daily bars, others 251); ~one month of 15m regular-session bars per ticker (521 each; TSLA 547).
- Screen signals dated 2026-10-07 through 2026-10-29. Same-day next-bar-open entry; 1x intraday ATR14 stop, 1.5x ATR14 target, up to 8 bars / end-of-day exit; assume stop hit first when both target/stop in bar. 7bp assumed each side.
- Mean **trade** returns are not portfolio returns. Dataset covers surviving currently selected tickers; not point-in-time universe; no sizing or concurrency portfolio simulation.
- The experiment was run using a JavaScript evaluation implementing the same preregistered logic as the Python prototype. **The Python prototype has not yet been independently replayed against a preserved, exact market-data snapshot.** An important handoff test is parity-checking those two implementations.
- Raw IBKR data not committed to a **public** GitHub repository, so the exact numeric run isn't independently reproducible from repository files alone; data should be retrieved again through licensed provider or transferred via a private approved data store, pinned with hashes.

## Observed results

| Model | Trades | Symbols with trades | Avg net/trade | Median net/trade | Win rate |
|---|---:|---:|---:|---:|---:|
| M0 | 34 | 5 | -0.0700% | -0.1770% | 38.24% |
| M1 | 24 | 5 | -0.0242% | -0.2835% | 41.67% |
| M2 | 23 | 5 | -0.0118% | -0.2835% | 43.48% |

TSLA generated zero qualifying signals. All model means are negative after assumed costs. M1/M2 are stricter nested filters, so different sample composition causes the apparent improvement; the run **does not show statistical or economically significant incremental alpha**. No sample contains an independent out-of-sample holdout. No CAGR, Sharpe, or portfolio maximum drawdown is calculated.

## Scite-backed interpretation
- Momentum/MA families have research history (see academic_review.md), but no credible direct academic demonstration of this specific discretionary support confluence was established.
- Literature also finds instances where intraday predictability fails out of sample.
- A causal AVWAP anchor needs explicit ex-ante definition; this study uses the highest prior-bar high in a fixed historical lookback rather than reconstructing a discretionary chart pattern.
- Backtest overfitting risk is heightened given a one-month window and small trade counts.

## Verdict
**HOLD — not an early positive result.** The *research method* is viable and reusable, but this small sample does **not** support advancing Martin-Luk-inspired M2 to Paper. Continue at most with independent reproducibility/data-quality verification and longer-history feasibility analysis, without parameter tuning on the same one-month window.

## Mandatory validity checks before any Codex deepening
1. Freeze and archive input bar data in permitted private storage; use checksums; clarify adjusted vs unadjusted prices and corporate actions.
2. Correct/verify real session handling (NYSE/Nasdaq calendar, DST, half-days). Check trailing-indicator warm-up and next-open order semantics.
3. Unit-test Python vs JS logic on an identical preserved snapshot. Confirm intrabar stop-first assumption and trading-cost model.
4. Obtain broader historical 5/15m data, point-in-time survivorship-safe liquid-leader universe, and a time-based train/test split.
5. Compare to risk/time-exposure-matched baselines and evaluate tail risks; avoid optimizing based on these observed negative outcomes.

## Security boundary
Read-only public research branch. No changes to Cloud Run, Firestore, IBKR account orders, GCP IAM, Paper/Live or deployed strategies.
