# Codex Research handoff — Martin Luk inspired EMA + AVWAP
Status: **HOLD at ChatGPT exploratory stage** (2026-11-02). This is not authorization to run Paper, deploy, buy data, or modify anything in production.

## What exists
- `idea.json`: user-supplied Grok source hypothesis (noncanonical, provenance incomplete).
- `academic_review.md`: initial Scite research and context/contradictions.
- `hypothesis.json`: M0 / M1 / M2 distinct independent hypotheses.
- `experiment_config.json`: preregistered prototype assumptions.
- `prototype_backtest.py`: prototype consuming input_market_data.json (format below).
- `preliminary_results.json`: actual experimental summaries and trade ledger (from JS execution; no raw bar arrays).
- `preliminary_results.md`: interpretation / limitations.

## Immediate Codex assignment (read-only and offline)
**Do not expand the strategy into Paper.** First validate the pipeline:
1. Read these files on the isolated research branch only, with no merge to `master`.
2. Critique timing / correctness of strategy predicates and potential causality leaks. Test the python prototype with synthetic fixtures before real-data replay.
3. Compare the Python implementation and the prior JS results on a *licensed and archived* identical source dataset; if identical raw bars are not available, report **not reproduced** rather than assert numerical equivalence.
4. Prepare a longer-period data feasibility and quality assessment for US 15m bars; do not subscribe or make large billable data calls without approval.
5. Return **verification findings** and a plan for rigorous OOS, walk-forward, live-candidate prevention and a robust point-in-time universe.
6. Keep deployment/Cloud Run, Scheduler, IAM, credentials, trading and cloud writes untouched.

## Input contract
The Python script takes `input_market_data.json` as its only argument. The JSON is an array where each member has:
```json
{
 "ticker": "GOOG",
 "daily": {"time": ["2026-01-02T14:30:00Z"], "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [100.0]},
 "intra": {"time": ["2026-01-02T14:30:00Z"], "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [100.0]}
}
```
Array fields must be equal-length, UTC ISO format and ascending. Bar timestamps follow IBKR returned bar timestamps, which may represent start-of-bar. The prototype assumes no intraday breaks in the RTH sequence.
Run: `python prototype_backtest.py input_market_data.json`
The above JSON is a format specimen, NOT actual price data.

## Decision escalation
- **No Paper promotion recommended**: negative sample net means; few trades, short window, poor data audit.
- Re-evaluate only after robust sample and independent parity/causality validation.
- An improvement of the research infrastructure can be accepted even if the trading hypothesis fails.
