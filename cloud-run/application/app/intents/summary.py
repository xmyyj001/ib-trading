from intents.intent import Intent
import asyncio

class Summary(Intent):
    def __init__(self, env, **kwargs):
        super().__init__(env=env, **kwargs)
        self._activity_log = {}  # don't log summary requests

    async def _core_async(self):
        # Run all requests in parallel for efficiency
        # CORRECTED: Changed reqAccountValuesAsync to reqAccountSummaryAsync
        portfolio, open_trades, fills, account_summary = await asyncio.gather(
            self._get_positions(),
            self._get_trades(),
            self._get_fills(),
            self._env.ibgw.reqAccountSummaryAsync()
        )
        return {
            # CORRECTED: account_summary is a list of AccountValue objects
            'accountSummary': {v.tag: v.value for v in account_summary if v.value},
            'portfolio': portfolio,
            'openTrades': open_trades,
            'fills': fills
        }

    async def _get_fills(self):
        # CORRECTED: Changed reqFillsAsync() to reqExecutionsAsync()
        # reqExecutionsAsync returns a list of Fill objects
        fills = await self._env.ibgw.reqExecutionsAsync()
        # The Fill object has a 'contract' and 'execution' attribute
        return {f.contract.localSymbol: [{'side': f.execution.side, 'shares': int(f.execution.shares)}] for f in fills}

    async def _get_positions(self):
        # CORRECTED: portfolio() is a synchronous method that returns a list.
        # It does not need to be awaited.
        portfolio_items = self._env.ibgw.portfolio()
        return {item.contract.localSymbol: {'position': int(item.position)} for item in portfolio_items}

    async def _get_trades(self):
        # CORRECTED: openTrades() is a synchronous method that returns a list.
        trades = self._env.ibgw.openTrades()
        return {t.contract.localSymbol: [{'isActive': t.isActive(), 'isDone': t.isDone()}] for t in trades}
