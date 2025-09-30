from intents.intent import Intent
import asyncio

class Summary(Intent):

    def __init__(self, env, **kwargs):
        super().__init__(env=env, **kwargs)
        self._activity_log = {}  # don't log summary requests

    async def _core(self):
        # Run all requests in parallel for efficiency
        portfolio, open_trades, fills, account_summary = await asyncio.gather(
            self._get_positions(),
            self._get_trades(),
            self._get_fills(),
            self._env.get_account_values_async(self._env.config['account'])
        )
        return {
            'accountSummary': account_summary,
            'portfolio': portfolio,
            'openTrades': open_trades,
            'fills': fills
        }

    async def _get_fills(self):
        fills = await self._env.ibgw.reqFillsAsync()
        return {
            fill.contract.localSymbol: [{
                'side': fill.execution.side,
                'shares': int(fill.execution.shares),
                'price': fill.execution.price,
                'cumQuantity': int(fill.execution.cumQty),
                'avgPrice': fill.execution.avgPrice,
                'time': fill.execution.time.isoformat(),
                'commission': round(fill.commissionReport.commission, 2),
                'rPnL': round(fill.commissionReport.realizedPNL, 2)
            }] for fill in fills
        }

    async def _get_positions(self):
        portfolio_items = await self._env.ibgw.reqPortfolioAsync()
        return {
            item.contract.localSymbol: {
                'position': int(item.position),
                'exposure': round(item.marketValue, 2),
                'uPnL': round(item.unrealizedPNL, 2)
            } for item in portfolio_items
        }

    async def _get_trades(self):
        trades = await self._env.ibgw.reqOpenTradesAsync()
        return {
            trade.contract.localSymbol: [{
                'isActive': trade.isActive(),
                'isDone': trade.isDone(),
                'orderStatus': trade.orderStatus.status,
                'whyHeld': trade.orderStatus.whyHeld,
                'action': trade.order.action,
                'totalQuantity': int(trade.order.totalQuantity),
                'orderType': trade.order.orderType,
                'limitPrice': trade.order.lmtPrice,
                'timeInForce': trade.order.tif,
                'goodAfterTime': trade.order.goodAfterTime,
                'goodTillDate': trade.order.goodTillDate
            }] for trade in trades
        }
