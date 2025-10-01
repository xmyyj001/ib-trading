from intents.intent import Intent
import asyncio

class Summary(Intent):
    def __init__(self, env, **kwargs):
        super().__init__(env=env, **kwargs)
        self._activity_log = {}  # don't log summary requests

    async def _core(self):
        portfolio, open_trades, fills, account_summary = await asyncio.gather(
            self._get_positions(),
            self._get_trades(),
            self._get_fills(),
            self._env.ibgw.reqAccountValuesAsync(self._env.config['account'])
        )
        return {
            'accountSummary': account_summary,
            'portfolio': portfolio,
            'openTrades': open_trades,
            'fills': fills
        }

    async def _get_fills(self):
        fills = await self._env.ibgw.reqFillsAsync()
        return {f.contract.localSymbol: [{'side': f.execution.side, 'shares': int(f.execution.shares)}] for f in fills}

    async def _get_positions(self):
        portfolio_items = await self._env.ibgw.reqPortfolioAsync()
        return {item.contract.localSymbol: {'position': int(item.position)} for item in portfolio_items}

    async def _get_trades(self):
        trades = await self._env.ibgw.reqOpenTradesAsync()
        return {t.contract.localSymbol: [{'isActive': t.isActive(), 'isDone': t.isDone()}] for t in trades}
