import pandas as pd
from ib_insync import Stock, util
from strategies.strategy import Strategy

class SpyMacdVixy(Strategy):
    def __init__(self, **kwargs):
        self.spy = Stock('SPY', 'SMART', 'USD')
        self.vixy = Stock('VIXY', 'BATS', 'USD')
        super().__init__(**kwargs)

    def _get_signals(self):
        spy_contract = self._instruments['spy'][0].contract
        vixy_contract = self._instruments['vixy'][0].contract
        if not spy_contract or not vixy_contract:
            self._env.logging.error("SPY or VIXY contract details not available.")
            self._signals = {}
            return

        bars = self._env.ibgw.reqHistoricalData(
            spy_contract, endDateTime='', durationStr='100 D',
            barSizeSetting='1 day', whatToShow='TRADES', useRTH=True)
        if not bars:
            self._env.logging.error("Could not fetch historical data for SPY.")
            self._signals = {}
            return

        df = util.df(bars)
        if df.empty:
            self._env.logging.error("SPY data is empty.")
            self._signals = {}
            return

        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal = macd.ewm(span=9, adjust=False).mean()

        if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] < signal.iloc[-2]:
            self._signals = {spy_contract.conId: 1.0, vixy_contract.conId: 0.0}
        elif macd.iloc[-1] < signal.iloc[-1] and macd.iloc[-2] > signal.iloc[-2]:
            self._signals = {spy_contract.conId: -1.0, vixy_contract.conId: 1.0}
        else:
            self._signals = {}

    def _setup(self):
        from lib.trading import InstrumentSet
        self._instruments = {
            'spy': InstrumentSet(self.spy),
            'vixy': InstrumentSet(self.vixy)
        }
        for key in self._instruments:
            inst = self._instruments[key].constituents[0]
            inst.get_contract_details()
            if inst.contract:
                inst.get_tickers()
            else:
                self._env.logging.error(f"Failed to get contract details for {key.upper()}.")
                self._instruments[key] = None