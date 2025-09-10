from datetime import datetime, timedelta
import dateparser
from ib_insync import LimitOrder
from intents.intent import Intent
from lib.trading import Trade
from strategies import STRATEGIES

class Allocation(Intent):

    _dry_run = False
    _order_properties = {}
    _strategies = {}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._dry_run = kwargs.get('dryRun', self._dry_run) if kwargs is not None else self._dry_run
        self._order_properties = kwargs.get('orderProperties', self._order_properties) if kwargs is not None else self._order_properties
        strategies = kwargs.get('strategies', [])
        if any([s not in STRATEGIES.keys() for s in strategies]):
            raise KeyError(f"Unknown strategies: {', '.join([s for s in strategies if s not in STRATEGIES.keys()])}")
        self._strategies = {s: STRATEGIES[s] for s in strategies}
        self._activity_log.update(dryRun=self._dry_run, orderProperties=self._order_properties, strategies=strategies)

    def _cancel_stale_orders(self, open_orders, trades):
        for conId, order in open_orders.items():
            trade_for_contract = trades.get(conId)
            if trade_for_contract is None:
                continue

            new_action = 'BUY' if trade_for_contract['quantity'] > 0 else 'SELL'
            if new_action != order.action:
                self._env.logging.warning(f"Cancelling stale GTC order {order.orderId} for {order.action} {order.totalQuantity} of conId {conId}")
                self._env.ibgw.cancelOrder(order)

    def _core(self):
        if (overall_exposure := self._env.config['exposure']['overall']) == 0:
            self._env.logging.info('Aborting allocator as overall exposure is 0')
            return

        all_open_orders = self._env.ibgw.reqOpenOrders()
        self._env.ibgw.sleep(2)

        account_values = self._env.get_account_values(self._env.config['account'])
        base_currency, net_liquidation = list(account_values['NetLiquidation'].items())[0]
        self._activity_log.update(netLiquidation=net_liquidation)

        strategies_instances = []
        for k, v in self._strategies.items():
            if strategy_exposure := self._env.config['exposure']['strategies'].get(k, 0):
                self._env.logging.info(f'Getting signals for {k}...')
                try:
                    strategy_open_orders = {o.contract.conId: o for o in all_open_orders if o.orderRef == k}
                    strategies_instances.append(v(base_currency=base_currency, 
                                        exposure=net_liquidation * overall_exposure * strategy_exposure,
                                        open_orders=strategy_open_orders,
                                        _id=k))
                except Exception as exc:
                    self._env.logging.error(f'{exc.__class__.__name__} running strategy {k}: {exc}')
        
        trades = Trade(strategies_instances)
        trades.consolidate_trades()
        self._activity_log.update(consolidatedTrades={v['contract'].local_symbol: v['quantity'] for v in trades.trades.values()})
        self._env.logging.info(f"Consolidated trades: {self._activity_log['consolidatedTrades']}")

        if not self._dry_run:
            self._cancel_stale_orders({o.contract.conId: o for o in all_open_orders}, trades.trades)
            OrderClass = LimitOrder
            orders = trades.place_orders(OrderClass)
            self._activity_log.update(orders=orders)
            self._env.logging.info(f"Orders placed: {self._activity_log['orders']}")