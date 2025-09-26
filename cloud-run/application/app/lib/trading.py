from abc import ABC
from datetime import datetime, timedelta, timezone
import ib_insync
import asyncio
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

    def as_instrumentset(self):
        return InstrumentSet(self)

    def get_contract_details(self):
        """
        Requests contract details from IB.
        """
        if self._ib_contract and hasattr(self._ib_contract, 'symbol'): # Add a check for valid contract
            try:
                contract_details_list = self._env.ibgw.reqContractDetails(self._ib_contract)
                if contract_details_list:
                    contract_details = contract_details_list[0].nonDefaults()
                    self._contract = contract_details.pop('contract')
                    self._local_symbol = self._contract.localSymbol
                    self._details = contract_details
            except Exception as e:
                self._env.logging.error(f"Error fetching contract details for {self._ib_contract.symbol}: {e}")

    def get_tickers(self):
        """
        Requests price data for contract from IB.
        """
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


class Future(Instrument):

    CONTRACT_SPECS = {
        'MNQ': {
            'currency': 'USD',
            'exchange': 'GLOBEX',
            'expiry_scheme': 'q'
        }
    }
    IB_CLS = ib_insync.Future
    EXPIRY_SCHEMES = {
        'm': ['F', 'G', 'H', 'J', 'K', 'M', 'N', 'Q', 'U', 'V', 'X', 'Z'],
        'q': ['H', 'M', 'U', 'Z']
    }

    def __init__(self, symbol, lastTradeDateOrContractMonth, exchange, **kwargs):
        super().__init__(symbol=symbol, lastTradeDateOrContractMonth=lastTradeDateOrContractMonth, exchange=exchange, **kwargs)

    @classmethod
    def get_contract_series(cls, n, ticker, rollover_days_before_expiry=1):
        logging = GcpModule.get_logger()

        current_year = datetime.now().year
        contract_years = [str(current_year + i)[-1] for i in range(3)]

        contract_symbols = [ticker + m + y for y in contract_years for m in cls.EXPIRY_SCHEMES[cls.CONTRACT_SPECS[ticker]['expiry_scheme']]]

        logging.info(f"Requesting contract for {', '.join(contract_symbols)}...")
        
        valid_contracts = []
        for s in contract_symbols:
            try:
                future_instrument = cls(symbol=ticker, lastTradeDateOrContractMonth=s, exchange=cls.CONTRACT_SPECS[ticker]['exchange'], currency=cls.CONTRACT_SPECS[ticker]['currency'])
                if future_instrument.contract and future_instrument.contract.lastTradeDateOrContractMonth > (datetime.now() + timedelta(days=rollover_days_before_expiry)).strftime('%Y%m%d'):
                    valid_contracts.append(future_instrument)
            except Exception as e:
                logging.warning(f"Could not resolve contract for {s}: {e}")

        contracts = InstrumentSet(*valid_contracts)
        
        if len(contracts) < n:
            logging.warning(f"Only {len(contracts)} contracts found, but {n} were requested. Consider adjusting rollover_days_before_expiry or contract generation logic.")

        return contracts[:n]


class Index(Instrument):

    IB_CLS = ib_insync.Index
    def __init__(self, symbol, exchange, currency, **kwargs):
        super().__init__(symbol=symbol, exchange=exchange, currency=currency, **kwargs)


class Stock(Instrument):

    IB_CLS = ib_insync.Stock
    def __init__(self, symbol, exchange, currency, **kwargs):
        super().__init__(symbol=symbol, exchange=exchange, currency=currency, **kwargs)


class InstrumentSet:

    def __init__(self, *args):
        iter(args)
        if not all(isinstance(a, Instrument) for a in args):
            raise TypeError('Not all arguments are of type Instrument')

        self._constituents = args
        self._env = Environment()

    def __add__(self, other):
        return InstrumentSet(*[*self] + [*other])

    def __getitem__(self, item):
        return self._constituents[item]

    def __iter__(self):
        return iter(self._constituents)

    @property
    def constituents(self):
        return self._constituents

    @property
    def contracts(self):
        return [c.contract for c in self._constituents if c.contract]

    @property
    def tickers(self):
        return [c.tickers for c in self._constituents]

    def get_tickers(self):
        """
        Requests price data for contract from IB.
        """
        valid_contracts = self.contracts
        if valid_contracts:
            self._env.logging.info(f"Requesting tick data for {', '.join([c.localSymbol for c in valid_contracts if c.localSymbol])}...")
            try:
                tickers = self._env.ibgw.reqTickers(*valid_contracts)
                ticker_map = {t.contract.conId: t for t in tickers}
                for c in self._constituents:
                    if c.contract and c.contract.conId in ticker_map:
                        c._tickers = ticker_map[c.contract.conId]
            except Exception as e:
                self._env.logging.error(f"Error fetching tickers: {e}")

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
        Consolidates the trades of all strategies (sum of quantities, grouped by
        contract), remembering which strategy ('source') wants to trade what so
        that we have proper accounting.
        """
        self._trades = {}
        for strategy in self._strategies:
            for k, v in strategy.trades.items():
                if k not in self._trades:
                    self._trades[k] = {}
                    self._trades[k]['contract'] = strategy.contracts[k]
                    # Carry over the limit price from the first strategy that provides it
                    if 'lmtPrice' in v:
                        self._trades[k]['lmtPrice'] = v['lmtPrice']

                self._trades[k]['quantity'] = self._trades[k].get('quantity', 0) + v['quantity']
                self._trades[k]['source'] = self._trades[k].get('source', {})
                self._trades[k]['source'][strategy.id] = v['quantity']

        self._trades = {k: v for k, v in self._trades.items() if v['quantity'] != 0}

    async def _wait_for_order_status(self, order, target_status, timeout=15):
        """Asynchronously waits for an order to reach a target status."""
        try:
            async with asyncio.timeout(timeout):
                async for trade in self._env.ibgw.tradesAsync():
                    if trade.order.permId == order.permId and trade.orderStatus.status in target_status:
                        self._env.logging.info(f"Order {order.permId} reached status: {trade.orderStatus.status}")
                        return trade
        except asyncio.TimeoutError:
            self._env.logging.error(f"Timeout ({timeout}s) waiting for order {order.permId} to reach status {target_status}.")
            return None

    async def _log_trades_async(self, trades):
        """Asynchronously logs trades to Firestore."""
        # This is a simplified version from the review. A full implementation would use async Firestore writes.
        return {t.contract.localSymbol: {'permId': t.order.permId, 'status': t.orderStatus.status} for t in trades if t}

    async def place_orders_async(self, order_type=ib_insync.MarketOrder, order_params=None, order_properties=None):
        """Fully asynchronously places orders and waits for submission confirmation."""
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
                    self._env.logging.error(f"LimitOrder requested but no valid lmtPrice for {v['contract'].local_symbol}. Skipping.")
                    continue
            
            if 'orderRef' not in order_properties and 'source' in v:
                order_properties['orderRef'] = list(v['source'].keys())[0]

            tif = order_properties.get('tif', self._env.config.get('defaultOrderTif', 'GTC'))
            final_order_props = {**order_properties, 'tif': tif}
            order_obj = order_type(**order_args).update(**final_order_props)
            
            place_order_coros.append(self._env.ibgw.placeOrderAsync(v['contract'].contract, order_obj))

        if not place_order_coros:
            return {}

        placed_trades = await asyncio.gather(*place_order_coros)
        self._env.logging.info(f"Successfully placed {len(placed_trades)} orders.")

        confirm_coros = [self._wait_for_order_status(trade.order, {'Submitted', 'Filled', 'PreSubmitted'}) for trade in placed_trades]
        confirmed_trades = await asyncio.gather(*confirm_coros)
        
        valid_trades = [t for t in confirmed_trades if t is not None]
        
        self._trade_log = await self._log_trades_async(valid_trades)
        return self._trade_log