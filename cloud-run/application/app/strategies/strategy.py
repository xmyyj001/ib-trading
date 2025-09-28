from lib.environment import Environment
# The top-level import that causes the circular dependency is removed.
# from lib.trading import Contract, Forex, Instrument, InstrumentSet

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
        """
        Converts signals into target positions (number of contracts).
        """
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
        """
        Converts target positions into trades (subtract virtual holdings).
        """
        self._trades = {}
        for k, v in self._target_positions.items():
            trade_qty = v - virtual_holdings.get(k, 0)
            if trade_qty != 0:
                self._trades[k] = {'quantity': trade_qty, 'lmtPrice': self._signals[k][1]}
        
        if self._trades:
            self._env.logging.info(f"Trades for {self._id}: { {self._contracts[k].local_symbol: v['quantity'] for k, v in self._trades.items()} }")

    def _get_currencies(self, base_currency):
        """
        Gets the FX rates for all involved contracts.
        """
        # Local import to break circular dependency
        from lib.trading import Forex, InstrumentSet

        currencies = {c.contract.currency for c in self._contracts.values()}
        forex_pairs = [c + base_currency for c in currencies if c != base_currency]
        
        if not forex_pairs:
            self._fx = {base_currency: 1.0}
            return

        forex_instruments = InstrumentSet(*[Forex(pair=pair) for pair in forex_pairs])
        forex_instruments.get_tickers()
        
        self._fx = {base_currency: 1.0}
        for inst in forex_instruments:
            if inst.tickers:
                fx_rate = inst.tickers.midpoint() if inst.tickers.midpoint() == inst.tickers.midpoint() else inst.tickers.close
                self._fx[inst.contract.currency] = fx_rate

    def _get_holdings(self):
        """
        Gets current portfolio holdings from Firestore.
        """
        doc = self._env.db.document(f'positions/{self._env.trading_mode}/holdings/{self._id}').get()
        if doc.exists:
            self._holdings = {int(k): v for k, v in doc.to_dict().items()}
            self._register_contracts(*self._holdings.keys())
        else:
            self._holdings = {}

    def _get_signals(self):
        """
        This method must be implemented by subclasses.
        It should return a dict of {conId: (weight, price)}
        """
        raise NotImplementedError

    def _register_contracts(self, *contracts):
        """
        Registers contracts for the strategy.
        """
        # Local import to break circular dependency
        from lib.trading import Contract, Instrument

        if not all(isinstance(c, (int, Instrument)) for c in contracts):
            raise TypeError('Not all contracts are of type int or Instrument')

        to_add = {}
        for c in contracts:
            conId = c if isinstance(c, int) else c.contract.conId
            if conId not in self._contracts:
                to_add[conId] = Contract(conId=c) if isinstance(c, int) else c
        
        self._contracts.update(to_add)

    def _setup(self):
        """
        This method should be implemented by subclasses to define instruments.
        """
        pass
