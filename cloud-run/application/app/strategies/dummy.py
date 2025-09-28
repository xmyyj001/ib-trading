from random import randint
from ib_insync import Stock
from strategies.strategy import Strategy

class Dummy(Strategy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _get_signals(self):
        if not self._instruments.get('spy') or not self._instruments['spy'].constituents:
            self._env.logging.warning("No valid 'spy' contracts found. Skipping signal generation.")
            self._signals = {}
            return
        spy_contract = self._instruments['spy'][0].contract
        if not spy_contract:
            self._env.logging.error("SPY contract details not available.")
            self._signals = {}
            return
        weight = randint(-1, 1)
        price = self._instruments['spy'][0].tickers.close if self._instruments['spy'][0].tickers else 0
        self._signals = { spy_contract.conId: (weight, price) }
        self._register_contracts(self._instruments['spy'][0])

    def _setup(self):
        from lib.trading import InstrumentSet
        self._instruments = {
            'spy': InstrumentSet(Stock('SPY', 'ARCA', 'USD'))
        }
        if self._instruments['spy'].constituents:
            spy_inst = self._instruments['spy'].constituents[0]
            spy_inst.get_contract_details()
            if spy_inst.contract:
                 spy_inst.get_tickers()
            else:
                self._env.logging.error("Failed to get contract details for SPY.")
                self._instruments['spy'] = None