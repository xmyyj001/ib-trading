# ChatGPT / Scite initial academic review — Martin Luk inspired EMA + AVWAP
Date: 2026-11-02 (UTC date); **exploratory research, not a profitability certification**.

## What was checked
Scite MCP searches on intraday momentum, moving averages, VWAP/AVWAP, backtest overfitting, and momentum crashes. Exact DOI metadata and Smart Citation tallies were checked for selected papers. Fulltext availability was not universal; some checks relied on abstracts/excerpts. Smart Citation categories apply to *citation statements*, not direct votes on whether a strategy works.

| Mechanism | Literature (DOI) | Initial conclusion | Transferability |
| --- | --- | --- | --- |
| Intraday momentum | *Market intraday momentum*, 2018, [10.1016/j.jfineco.2018.05.009](https://doi.org/10.1016/j.jfineco.2018.05.009) | Empirical intraday momentum in specified index/market windows; Scite snapshot 48 supporting, 5 contrasting, 231 mentioning contexts | **Partial**: not a test of individual-growth-stock 15m pullback entries |
| Out-of-sample counter-evidence | *Understanding intraday momentum strategies*, 2022, [10.1002/fut.22375](https://doi.org/10.1002/fut.22375) | The studied overnight-to-last-half-hour predictability disappears in its out-of-sample period; regime/threshold dependence reported | **Partial**: warns against extrapolation |
| MA trading | *An improved moving average technical trading rule*, 2015, [10.1016/j.physa.2015.01.088](https://doi.org/10.1016/j.physa.2015.01.088) | Illustrates mechanical MA signals combined with adaptive exit thresholds; Scite 0 supporting, 1 contrasting, 16 mentioning contexts | **Indirect**: cannot validate EMA21 support threshold |
| VWAP execution | *A Closed-Form Execution Strategy to Target Volume Weighted Average Price*, 2016, [10.1137/16m1058406](https://doi.org/10.1137/16m1058406) | VWAP as an execution benchmark has a theoretical literature | **Not evidence** that a discretionary anchored VWAP is predictive support |
| Momentum tail risk | *Momentum crashes*, 2016, [10.1016/j.jfineco.2015.12.002](https://doi.org/10.1016/j.jfineco.2015.12.002) | Large tail losses occur in some momentum portfolios; Scite 59 supporting, 12 contrasting, 423 mentioning contexts | **Indirect**: cross-sectional portfolio risks ≠ exact long-only intraday strategy |
| Validation methodology | *The Probability of Backtest Overfitting*, [10.2139/ssrn.2326253](https://doi.org/10.2139/ssrn.2326253) | Multiple testing can lead to false positives; first ~3.5k characters were accessible through Scite as full text | **Directly relevant to experiment design** |

## Preliminary verdict
- The trend/momentum and systematic MA *families* have empirical antecedents; this does **not** prove Martin Luk's approach or these M0–M2 implementations generate positive returns.
- Direct academically verified evidence for *rolling-high-anchored VWAP support improving EMA-pullback returns* was **not established in this screen**.
- Scite's contrasting, supporting and mentioning counts must not be used as an automatic score or Gate 2 profit pass.
- Test M0/M1/M2 as nested incremental hypotheses, preregister parameters, report zero-trade or negative results, and require independent data for any substantive conclusion.
- Literature search coverage is not comprehensive or a systematic review. No paper was claimed retracted merely because an editorial notice was not returned.

## Research decision
**Academic evidence: contextual/partial, sufficient to justify an exploratory hypothesis test**. Not sufficient to claim tradeability or advance to Paper. Source idea captured from user-supplied Grok P1; provenance remains partial.

## Specific research risks
1. Anchor leakage: a future-confirmed pivot cannot be used before confirmation.
2. Survivorship: six currently visible US growth tickers do not represent a historical point-in-time screened universe.
3. Data availability: the IBKR connector has an intraday per-response bar limit; the tested window is short.
4. Trade-to-trade return is not portfolio CAGR; do not treat it as annualized investment performance.
5. Avoid post-hoc parameter selection in this same sample.
