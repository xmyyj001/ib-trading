# X strategy discovery: Martin Luk EMA + AVWAP

**Research use only**; these implementations are independent, simplified testable hypotheses derived from a user-supplied Grok summary, **not** an exact replication of Martin Luk's discretionary trading.

Current verdict: **HOLD** after exploratory one-month IBKR 15m bar backtest. All three M0/M1/M2 model average trade net returns are negative with the fixed 14-bp round-trip cost assumption. See [preliminary_results.md](preliminary_results.md), [preliminary_results.json](preliminary_results.json).

This directory has:
- [idea.json](idea.json) — source and hypothesis provenance.
- [academic_review.md](academic_review.md) — preliminary Scite literature screen.
- [hypothesis.json](hypothesis.json) — three nested testing hypotheses.
- [experiment_config.json](experiment_config.json) — fixed prototype assumptions.
- [prototype_backtest.py](prototype_backtest.py) — baseline Python code; requires locally supplied licensed input data.
- [preliminary_results.json](preliminary_results.json) — exploratory model-level summaries and individual trade estimates.
- [preliminary_results.md](preliminary_results.md) — limitations and decision.
- [codex_handoff.md](codex_handoff.md) — next read-only verification tasks.

**Reproducibility warning:** The numeric run was executed using JS matching the intended Python algorithm, not by executing `prototype_backtest.py` against a frozen accessible input dataset. Do not claim independent reproduction until a pinned private dataset is replayed and results agree. Do not store redistributed IBKR raw bars in a public repository.

**No deployment / Paper / Live authorization.** No current proof of alpha.
