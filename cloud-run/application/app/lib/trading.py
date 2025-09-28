import asyncio
import logging
from abc import ABC
from datetime import datetime, timedelta, timezone
import ib_insync
from google.cloud.firestore_v1 import DELETE_FIELD
from lib.environment import Environment
from lib.gcp import GcpModule

class Instrument(ABC):
    IB_CLS = None
    _contract = None
    _details = None
    _local_symbol = None
    _tickers = None

    def __init__(self, get_tickers=False, **kwargs):
        self._ib_contract = self.IB_CLS(**kwargs)
        self._env = Environment()
        self.get_contract_details()
        if get_tickers:
            self.get_tickers()

    @property
    def contract(self):
        return self._contract

    @property
    def details(self):
        return self._details

    @property
    def local_symbol(self):
        return self._local_symbol

    @property
    def tickers(self):
        return self._tickers

    def get_contract_details(self):
        if self._ib_contract and hasattr(self._ib_contract, 'symbol'):
            try:
                details_list = self._env.ibgw.reqContractDetails(self._ib_contract)
                if details_list:
                    details = details_list[0].nonDefaults()
                    self._contract = details.pop('contract')
                    self._local_symbol = self._contract.localSymbol
                    self._details = details
            except Exception as e:
                self._env.logging.error(f"Error fetching contract details for {self._ib_contract.symbol}: {e}")

    def get_tickers(self):
        if self._contract:
            self._env.logging.info(f'Requesting tick data for {self._local_symbol}...')
            try:
                tickers = self._env.ibgw.reqTickers(self._contract)
                if tickers:
                    self._tickers = tickers[0]
            except Exception as e:
                self._env.logging.error(f"Error fetching tickers for {self._local_symbol}: {e}")

class Contract(Instrument):
    IB_CLS = ib_insync.Contract
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

class Forex(Instrument):
    IB_CLS = ib_insync.Forex
    def __init__(self, pair, **kwargs):
        super().__init__(pair=pair, **kwargs)

class Stock(Instrument):
    IB_CLS = ib_insync.Stock
    def __init__(self, symbol, exchange, currency, **kwargs):
        super().__init__(symbol=symbol, exchange=exchange, currency=currency, **kwargs)

class InstrumentSet:
    def __init__(self, *args):
        if not all(isinstance(a, Instrument) for a in args):
            raise TypeError('Not all arguments are of type Instrument')
        self._constituents = args
        self._env = Environment()
    
    @property
    def contracts(self):
        return [c.contract for c in self._constituents if c.contract]

    def get_tickers(self):
        valid_contracts = self.contracts
        if valid_contracts:
            pass

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
        from strategies.strategy import Strategy
        self._trades = {}
        for strategy in self._strategies:
            if not isinstance(strategy, Strategy):
                logging.warning(f"Item provided to Trade class is not a Strategy instance: {type(strategy)}")
                continue
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
        try:
            async for trade in self._env.ibgw.tradesAsync():
                if trade.order.permId == order.permId and trade.orderStatus.status in target_status:
                    logging.info(f"Order {order.permId} reached status: {trade.orderStatus.status}")
                    return trade
        except asyncio.TimeoutError:
            logging.error(f"Timeout ({timeout}s) waiting for order {order.permId} to reach status {target_status}.")
            return None

    async def place_orders_async(self, order_type=ib_insync.MarketOrder, order_params=None, order_properties=None):
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
        log_entries = {}
        for t in trades:
            log_entries[t.contract.localSymbol] = {'permId': t.order.permId, 'status': t.orderStatus.status}
        return log_entries
