from lib.environment import Environment
from lib.trading import Contract, Forex, Instrument, InstrumentSet

class Strategy:
    _contracts = {}
    _fx = {}
    _holdings = {}
    _instruments = {}
    _signals = {}
    _target_positions = {}
    _trades = {}
    _open_orders = {}

    def __init__(self, _id=None, open_orders=None, **kwargs):
        self._id = _id or self.__class__.__name__.lower()
        self._env = Environment()
        self._base_currency = kwargs.get('base_currency', None)
        self._exposure = kwargs.get('exposure', 0)
        self._open_orders = open_orders or {}

        self._setup()
        self._get_holdings()
        self._get_signals()

        contract_ids = set([*self._signals.keys()] + [*self._holdings.keys()] + [*self._open_orders.keys()])
        
        virtual_holdings = {**self._holdings}
        for conId, order in self._open_orders.items():
            qty = order.totalQuantity if order.action == 'BUY' else -order.totalQuantity
            virtual_holdings[conId] = virtual_holdings.get(conId, 0) + qty

        self._holdings = {**{cid: 0 for cid in contract_ids}, **self._holdings}
        self._signals = {**{cid: (0, 0) for cid in contract_ids}, **self._signals}
        
        self._calculate_target_positions()
        self._calculate_trades(virtual_holdings)

    @property
    def contracts(self):
        return self._contracts

    @property
    def fx(self):
        return self._fx

    @property
    def holdings(self):
        return self._holdings

    @property
    def id(self):
        return self._id

    @property
    def signals(self):
        return self._signals

    @property
    def target_positions(self):
        return self._target_positions

    @property
    def trades(self):
        return self._trades

    def _calculate_target_positions(self):
        if self._base_currency is not None and self._exposure:
            for k, v_tuple in self._signals.items():
                if (c := self._contracts[k]).tickers is None:
                    c.get_tickers()
            self._get_currencies(self._base_currency)

            self._target_positions = {}
            for k, v_tuple in self._signals.items():
                weight, price = v_tuple
                if weight != 0 and price > 0:
                    self._target_positions[k] = round(self._exposure * weight
                                     / (price * int(self._contracts[k].contract.multiplier) * self._fx[self._contracts[k].contract.currency]))
                else:
                    self._target_positions[k] = 0
        else:
            self._target_positions = {k: 0 for k in self._signals.keys()}

    def _calculate_trades(self, virtual_holdings):
        self._trades = {}
        for k, v in self._target_positions.items():
            trade_qty = v - virtual_holdings.get(k, 0)
            if trade_qty != 0:
                self._trades[k] = {'quantity': trade_qty, 'lmtPrice': self._signals[k][1]}
        self._env.logging.info(f"Trades for {self._id}: { {self._contracts[k].local_symbol: v['quantity'] for k, v in self._trades.items()} }")

    def _get_currencies(self, base_currency):
        """
        Gets the FX rates for all involved contracts.
        :param base_currency: base currency of IB account in ISO format (str)
        """
        # 1. 初始化 FX 字典，基础货币对自身的汇率永远是 1.0
        self._fx = {base_currency: 1.0}
        
        # 2. 找出所有需要查询汇率的、非基础货币的币种
        currencies_to_fetch = {c.contract.currency for c in self._contracts.values() if c.contract and c.contract.currency != base_currency}

        if not currencies_to_fetch:
            self._env.logging.info("All instruments are in the base currency. No FX rates needed.")
            return

        # 3. 只为非基础货币创建 Forex 合约
        self._env.logging.info(f"Fetching FX rates for: {currencies_to_fetch}")
        forex_instruments = InstrumentSet(*[Forex(pair=c + base_currency) for c in currencies_to_fetch])
        forex_instruments.get_tickers()

        # 4. 健壮地填充汇率字典
        for instrument in forex_instruments:
            # 从 'EURUSD' 中提取 'EUR'
            currency = instrument.contract.symbol
            if instrument.tickers:
                # 使用 nan-safe 的方式获取中间价
                rate = instrument.tickers.midpoint() if instrument.tickers.midpoint() == instrument.tickers.midpoint() else instrument.tickers.close
                self._fx[currency] = rate
                self._env.logging.info(f"Fetched FX rate for {currency}{base_currency}: {rate}")
            else:
                self._env.logging.error(f"Could not fetch FX rate for {currency}{base_currency}. It will be missing from the FX map.")

    def _get_holdings(self):
        """
        Gets current portfolio holdings from Firestore.
        """
        doc = self._env.db.document(f'positions/{self._env.trading_mode}/holdings/{self._id}').get()
        self._holdings = {
            int(k): v
            for k, v in doc.to_dict().items()
        } if doc.exists else {}
        self._register_contracts(*self._holdings.keys())

    def _get_signals(self):
        # This method must now return a dict of {conId: (weight, price)}
        # Example: return {12345: (1.0, 450.50)} for long SPY at 450.50
        self._signals = { k: (0, 0) for k in self._holdings.keys() }

    def _register_contracts(self, *contracts):
        if not all(isinstance(c, (int, Instrument)) for c in contracts):
            raise TypeError('Not all contracts are of type int or Instrument')

        # add to _contracts if not in it yet
        to_add = {
            k: v
            for k, v in {
                c if isinstance(c, int) else c.contract.conId: Contract(conId=c) if isinstance(c, int) else c
                for c in contracts
            }.items()
            if k not in self._contracts.keys()
        }
        self._contracts = {**self._contracts, **to_add}

    def _setup(self):
        pass