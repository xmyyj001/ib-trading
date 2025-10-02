from ib_insync import MarketOrder

from intents.intent import Intent
from lib.trading import Trade
from strategies.strategy import Strategy


class CloseAll(Intent):

    _dry_run = False
    _order_properties = {}

    def __init__(self, env, **kwargs):
        super().__init__(env=env, **kwargs)

        self._dry_run = kwargs.get('dryRun', self._dry_run) if kwargs is not None else self._dry_run
        self._order_properties = kwargs.get('orderProperties', self._order_properties) if kwargs is not None else self._order_properties
        self._activity_log.update(dryRun=self._dry_run, orderProperties=self._order_properties)

    async def _core_async(self):
        self._env.logging.info('Cancelling open orders...')
        if not self._dry_run:
            for o in self._env.ibgw.openOrders():
                await self._env.ibgw.cancelOrderAsync(o)
                await self._env.db.collection(f'positions/{self._env.trading_mode}/openOrders/{o.permId}').delete()
                self._env.logging.info(f'Cancelled {o.permId}, deleted /positions/{self._env.trading_mode}/openOrders/{o.permId}')

        self._env.logging.info('Closing all positions...')
        strategies = [Strategy(doc.id)
                      for doc in self._env.db.collection(f'positions/{self._env.trading_mode}/holdings').get()]
        self._activity_log.update(**{
            'holdings': {s.id: {s.contracts[k].local_symbol: v for k, v in s.holdings.items()} for s in strategies},
            'contractIds': {v.contract.localSymbol: k for s in strategies for k, v in s.contracts.items()},
            'trades': {s.id: {s.contracts[k].local_symbol: v for k, v in s.trades.items()} for s in strategies}
        })
        self._env.logging.info(f"Trades: {self._activity_log['trades']}")

        trades = Trade(strategies)
        trades.consolidate_trades()
        self._activity_log.update(consolidatedTrades={v['contract'].local_symbol: v['quantity']
                                                      for v in trades.trades.values()})
        self._env.logging.info(f"Consolidated trades: {self._activity_log['consolidatedTrades']}")
        # double-check w/ IB potfolio
        portfolio = {item.contract.conId: item.position for item in self._env.ibgw.portfolio()}
        if {k: -v for k, v in portfolio.items()} != {k: v['quantity'] for k, v in trades.trades.items()}:
            self._env.logging.warning(f"Consolidated trade and IB portfolio don't match - portfolio: {portfolio}")

        if not self._dry_run:
            self._activity_log.update(orders=await trades.place_orders_async(MarketOrder,
                                                                 order_properties=self._order_properties))
            self._env.logging.info(f"Orders placed: {self._activity_log['orders']}")


if __name__ == '__main__':
    from lib.environment import Environment

    env = Environment()
    env.ibgw.connect(port=4001)
    try:
        close_all = CloseAll(dryRun=True)
        close_all._core()
    except Exception as e:
        raise e
    finally:
        env.ibgw.disconnect()
