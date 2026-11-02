# MLUK-EMA-AVWAP — evidence supplement index
Date: 2026-11-02. Branch: `research/martin-luk-chatgpt-20261102`.
Purpose: **only document the original ChatGPT research run**. No new runs, no fresh IBKR market-data queries, no strategy changes, no overwrite of historic results, no new research pipeline.

## Original immutable historical reference
- First Codex-inspected handoff commit: [ce9f44f3dc189da36cba1f80e8c31e4b938b06ba](https://github.com/xmyyj001/ib-trading/commit/ce9f44f3dc189da36cba1f80e8c31e4b938b06ba).
- Original experiment parameter commit: [e9aa57d0aea649ff7910d3d58ffd260327862473](https://github.com/xmyyj001/ib-trading/commit/e9aa57d0aea649ff7910d3d58ffd260327862473), 2026-11-02T14:33:24Z.
- Original Python prototype commit: [fe44d93b2e324f9cb02a2ccde4ebc15d1a4c490a](https://github.com/xmyyj001/ib-trading/commit/fe44d93b2e324f9cb02a2ccde4ebc15d1a4c490a), 2026-11-02T14:34:48Z.
- Original JS results commit: [38d20262c6259b19fc07c075ae08a6e5e13cf408](https://github.com/xmyyj001/ib-trading/commit/38d20262c6259b19fc07c075ae08a6e5e13cf408), 2026-11-02T14:35:57Z.

## Supplemental files only (in this `evidence/` directory)
| New file | Subject | Historical evidence quality |
| --- | --- | --- |
| [original_js_execution_transcript.md](original_js_execution_transcript.md) | Transcribed complete prior tool-call JS body; invocation, runtime class and timestamp limits | Conversation-text recovery, NOT a byte-verified execution artifact |
| [ibkr_data_provenance.md](ibkr_data_provenance.md) | Exact historical request arguments, per-symbol bar coverage, bar metadata unknowns, snapshot disposition | Repository results metadata + prior tool-call transcript |
| [experiment_disclosure.md](experiment_disclosure.md) | Full visible fixed-parameter set, GOOG 2-week/5m failed access probe, earlier data exposure, commit chronology, static defects | Original code + commit dates + independent review |

## Availability & unknowns (do not infer values)
- Original raw response bodies / original exact OHLCV input file: **原始快照不可恢复** within current accessible record. No original input checksum exists. Private transfer **not possible now**, as no authenticated original snapshot is available.
- Exact JS runtime build/V8 version and execution wall-clock start/end: **UNKNOWN**. Result file commit time is not a runtime timestamp.
- Bar timestamp start/close interpretation, adjustments, missing or partial bars, and per-call provider return time: **UNKNOWN**.
- Complete negative attempts / parameter exploration **outside the available ChatGPT transcript**: **UNKNOWN**.
- Config-file-before-results ordering is verified; config lock *before any market-data viewing* is **NOT** established.
- Original run was **not** independently reproduced; no frozen input was available. Status remains **HOLD / NOT_REPRODUCED**.

## Historic file preservation
Following supplemental evidence additions, these original files were read back and their blob SHAs checked **identical** to the pre-supplement readings:
- `experiment_config.json` `836960da092a437e6aea0c470004c69cc35364cf`
- `prototype_backtest.py` `7a2702851f3fd370ce3aec7a7ae2f4da88047c72`
- `preliminary_results.json` `263bdfc5ee72a1bb5de9f6e87226fb2c9912f6b7`
- `preliminary_results.md` `08125fbb5385d97932a2299b6f953b1ffbacbefe`
- `codex_handoff.md` `b7dade3862415ca6d17b7fe4b961db23307a8372`
- `README.md` `44e1fbf98724514d73e081191d41fbb9f3895051`

Independent review identified original median calculation errors; corrected conventional medians are listed **only in the supplemental experiment disclosure**. No historical metric or code was replaced.

**No Paper/Live promotion is authorized.** This is a documentation-only evidence bundle.
