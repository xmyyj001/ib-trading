import asyncio
from datetime import datetime, timezone
import ib_insync
from google.cloud.firestore_v1 import DELETE_FIELD
from lib.environment import Environment
import logging

# (Instrument, Contract, Forex, Future, Index, Stock, InstrumentSet 类的代码保持不变)
# ...

class Trade:
    _trades = {}
    _trade_log = {}

    def __init__(self, strategies=()):
        self._env = Environment()
        self._strategies = strategies

    @property
    def trades(self):
        return self._trades

    def consolidate_trades(self):
        """
        Consolidates trades from all strategies.
        This logic remains synchronous as it's pure computation.
        """
        self._trades = {}
        for strategy in self._strategies:
            for k, v in strategy.trades.items():
                if k not in self._trades:
                    self._trades[k] = {}
                    self._trades[k]['contract'] = strategy.contracts[k]
                    if 'lmtPrice' in v:
                        self._trades[k]['lmtPrice'] = v['lmtPrice']

                self._trades[k]['quantity'] = self._trades[k].get('quantity', 0) + v['quantity']
                self._trades[k]['source'] = self._trades[k].get('source', {})
                self._trades[k]['source'][strategy.id] = v['quantity']

        self._trades = {k: v for k, v in self._trades.items() if v['quantity'] != 0}

    async def _wait_for_order_status(self, order, target_status, timeout=15):
        """Asynchronously waits for an order to reach a target status."""
        try:
            async for trade in self._env.ibgw.tradesAsync():
                if trade.order.permId == order.permId and trade.orderStatus.status in target_status:
                    logging.info(f"Order {order.permId} reached status: {trade.orderStatus.status}")
                    return trade
        except asyncio.TimeoutError:
            logging.error(f"Timeout ({timeout}s) waiting for order {order.permId} to reach status {target_status}.")
            return None

    async def place_orders_async(self, order_type=ib_insync.MarketOrder, order_params=None, order_properties=None):
        """
        Fully asynchronously places orders and waits for broker confirmation.
        Assumes the ibgw connection is already established.
        """
        order_properties = order_properties or {}
        order_params = order_params or {}
        
        place_order_coros = []
        for v in self._trades.values():
            order_args = {
                'action': 'BUY' if v['quantity'] > 0 else 'SELL',
                'totalQuantity': abs(v['quantity']),
                **order_params
            }
            if order_type == ib_insync.LimitOrder:
                if 'lmtPrice' in v and v['lmtPrice'] > 0:
                    order_args['lmtPrice'] = v['lmtPrice']
                else:
                    logging.error(f"LimitOrder requested but no valid lmtPrice for {v['contract'].contract.localSymbol}. Skipping.")
                    continue
            
            order_obj = order_type(**order_args)
            if 'orderRef' not in order_properties and 'source' in v:
                order_properties['orderRef'] = list(v['source'].keys())[0]
            order_obj.update(**order_properties)

            place_order_coros.append(self._env.ibgw.placeOrderAsync(v['contract'].contract, order_obj))

        if not place_order_coros:
            return {}

        placed_trades = await asyncio.gather(*place_order_coros)
        logging.info(f"Successfully placed {len(placed_trades)} orders.")

        confirm_coros = [self._wait_for_order_status(trade.order, {'Submitted', 'Filled', 'PreSubmitted'}) for trade in placed_trades]
        confirmed_trades = await asyncio.gather(*confirm_coros)
        
        valid_trades = [t for t in confirmed_trades if t is not None]
        
        self._trade_log = await self._log_trades_async(valid_trades)
        return self._trade_log

    async def _log_trades_async(self, trades):
        """Asynchronously logs trades to Firestore."""
        log_entries = {}
        for t in trades:
            log_entries[t.contract.localSymbol] = {'permId': t.order.permId, 'status': t.orderStatus.status}
        return log_entries
