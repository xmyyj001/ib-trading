# Original IBKR market-data provenance & snapshot availability
Evidence inventory as of 2026-11-02. **Historical documentation only; no data was fetched to create this record.**

## Snapshot existence and disposition

**原始快照不可恢复** (within the currently accessible conversation/tool state and GitHub project). This statement means the exact arrays consumed by the original JS execution have no preserved, readable copy or content hash in the accessible material; it does not rule out uninspected independent backups on the user's machines or private cloud.

- Original JS obtained the stock OHLCV arrays directly using 12 IBKR connector calls, held them in a per-invocation in-memory V8 array named \`fetched\`, and wrote only aggregates, per-trade ledger, and six-symbol coverage metadata to \`preliminary_results.json\`.
- No raw IBKR HTTP/MCP response bodies, frozen input JSON, bytes checksum, materialization path, offline execution log, provider request ID, or upstream extraction timestamp were recorded.
- This branch is in a **public GitHub repository**, and no raw market-data arrays were committed. The trade-ledger estimates already in the historical commit are unchanged.
- Re-fetching current/historical bars would be a **new** acquisition, NOT a reconstruction of the exact original input. This request forbids it; no new market-data request has been made in this evidence-completion turn.
- **Original execution status: NOT_REPRODUCED.**

### Private delivery if a separate authentic historical snapshot is later found
No actual original snapshot exists in the checked material, therefore there is **nothing to transfer now**. If an *independently preserved, provably original* copy already exists in a user-controlled private location, its licensed/authorized transmission could use an existing access-controlled private channel or locally transferred encrypted attachment after confirming IBKR redistribution and access rules. Record the original storage URI privately and publish only a **non-sensitive checksum and manifest** to the research branch; do **not** place the raw bars in public GitHub. This note neither establishes a new storage service nor authorizes upload, export, or cloud writes.

## Original executed production-like research request contract (one batch, not a live trade)
Exactly the following request arguments appear in the archived original JS invocation, per symbol:

\`\`\`json
{
  "security_type": "STK",
  "history_daily": {"period":"ONE_YEAR", "step":"ONE_DAY", "outside_rth":false},
  "history_intraday": {"period":"ONE_MONTH", "step":"FIFTEEN_MINS", "outside_rth":false},
  "exchange": "OMITTED",
  "include_corporate_actions": "OMITTED",
  "step_count": "OMITTED"
}
\`\`\`

| Ticker | IBKR contract_id | Returned daily bars | Daily first bar UTC | Daily last bar UTC | Returned 15-min bars | Intraday first bar UTC | Intraday last bar UTC |
|---|---:|---:|---|---|---:|---|---|
| GOOG | 208813720 | 251 | 2025-11-03T14:30:00Z | 2026-11-02T14:30:00Z | 521 | 2026-10-05T13:30:00Z | 2026-11-02T14:30:00Z |
| NVDA | 4815747 | 251 | 2025-11-03T14:30:00Z | 2026-11-02T14:30:00Z | 521 | 2026-10-05T13:30:00Z | 2026-11-02T14:30:00Z |
| TSLA | 76792991 | 501 | 2024-11-01T13:30:00Z | 2026-11-02T14:30:00Z | 547 | 2026-10-02T13:30:00Z | 2026-11-02T14:30:00Z |
| AMD | 4391 | 251 | 2025-11-03T14:30:00Z | 2026-11-02T14:30:00Z | 521 | 2026-10-05T13:30:00Z | 2026-11-02T14:30:00Z |
| META | 107113386 | 251 | 2025-11-03T14:30:00Z | 2026-11-02T14:30:00Z | 521 | 2026-10-05T13:30:00Z | 2026-11-02T14:30:00Z |
| PLTR | 444857009 | 251 | 2025-11-03T14:30:00Z | 2026-11-02T14:30:00Z | 521 | 2026-10-05T13:30:00Z | 2026-11-02T14:30:00Z |

Source for this table: **unchanged** \`preliminary_results.json.coverage\` committed at \`38d20262c6259b19fc07c075ae08a6e5e13cf408\`. It is metadata, not raw-market-data evidence. The daily request nominally used ONE_YEAR, but TSLA returned 501 bars spanning two years; **reason UNKNOWN**. Neither truncate nor silently normalize.

## Ingestion/request circumstances
- Caller: \`functions.exec\` isolated JS using \`tools.mcp__Interactive_Brokers__IBKR___get_price_history\` in \`Promise.all\`.
- Exact network call completion times / request IDs / provider revision ID: **UNKNOWN**.
- Known commit timestamp when resulting ledger was saved: 2026-11-02T14:35:57Z UTC. This is **NOT** the quote acquisition time; it establishes only a later artifact commit.
- \`source\` field logged in coverage: \`"Last"\`; exact exchange routing and real-time-versus-delayed status for all bars: **UNKNOWN**.
- Bar timestamps: UTC strings returned by IBKR connector; whether they designate **bar open, bar close, or service normalization**: **UNKNOWN** (original script assumed date grouping by UTC date, without timezone-calendar verification).
- Adjusted / unadjusted / splits / dividends / back-adjustment: **UNKNOWN**. The original executed request did **not** request the optional corporate-action listing.
- Missing bars, duplicates, session gaps, halted sessions, zero-volume, volume unit, half-days, DST, completed regular sessions: **UNKNOWN**; no integrity checks were recorded. No claim of completeness.
- Incomplete or still-forming last bar: **UNKNOWN**. The input included a 2026-11-02 timestamp, and there was **no explicit completed-bar exclusion**. That may affect daily or intraday inputs.
- Historical signal dates in ledger: 2026-10-07 through 2026-10-29. **This differs from the raw input coverage** through 2026-11-02. The exposure window and the trade-output window are not interchangeable.

## Separate earlier read-only data feasibility probes (NOT the actual JS input)
1. GOOG STK \`ONE_YEAR/ONE_DAY/outside_rth=false/include_corporate_actions=true\`: returned **251 bars** with **4 corporate-action entries** in that separate response; covered approximately late Oct 2025–Oct 2026.
2. GOOG STK \`TWO_WEEKS/FIVE_MINS/outside_rth=false\`: error — \`Combination of period and step will provide more then allowed 1000 data points\`. **Failed data-availability query, not a strategy backtest.**
3. GOOG STK \`ONE_WEEK/FIVE_MINS/outside_rth=false\`: returned **390 bars**; tested API practicality, **not used as actual JS input**.
4. A preliminary six-symbol batch fetched the above ONE_YEAR/ONE_MONTH requests before the Python source was committed; responses were displayed only as coverage counts, **not** snapshotted. The later JS execution fetched the 12 requests again in its own invocation, so these are different acquisitions.

**No earlier raw result arrays are retained in the research repository.** Absence of a recoverable frozen snapshot prevents evidentiary exact replay.
