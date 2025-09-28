import pandas as pd
from ib_insync import util
from strategies.strategy import Strategy

class SpyMacdVixy(Strategy):
    def _setup(self):
        from lib.trading import Stock, InstrumentSet
        self._env.logging.info("Setting up SpyMacdVixy strategy instruments...")
        self._instruments = {
            'spy': InstrumentSet(Stock('SPY', 'ARCA', 'USD')),
            'vixy': InstrumentSet(Stock('VIXY', 'BATS', 'USD'))
        }
        for key in self._instruments:
            if self._instruments[key].constituents:
                inst = self._instruments[key].constituents[0]
                inst.get_contract_details()
                if not inst.contract:
                    self._env.logging.error(f"Failed to get contract details for {key.upper()}.")
                    self._instruments[key] = None

    def _get_signals(self):
        self._env.logging.info("Generating signals for SpyMacdVixy...")
        
        spy_instrument_set = self._instruments.get('spy')
        vixy_instrument_set = self._instruments.get('vixy')

        if not spy_instrument_set or not spy_instrument_set.constituents or not vixy_instrument_set or not vixy_instrument_set.constituents:
            self._env.logging.error("SPY or VIXY instrument not properly set up. Skipping signal generation.")
            self._signals = {}
            return

        spy_instrument = spy_instrument_set.constituents[0]
        vixy_instrument = vixy_instrument_set.constituents[0]

        if not spy_instrument.contract or not vixy_instrument.contract:
            self._env.logging.error("SPY or VIXY contract details not available. Skipping signal generation.")
            self._signals = {}
            return

        self._env.logging.info("Fetching historical data for SPY...")
        bars = self._env.ibgw.reqHistoricalData(
            spy_instrument.contract,
            endDateTime='',
            durationStr='100 D',
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True
        )

        if not bars:
            self._env.logging.error("Could not fetch historical data for SPY. Aborting.")
            self._signals = {}
            return

        df = util.df(bars)
        if df.empty:
            self._env.logging.error("Historical data for SPY is empty. Aborting.")
            self._signals = {}
            return
            
        self._env.logging.info("Calculating MACD...")
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal = macd.ewm(span=9, adjust=False).mean()

        last_price_spy = df['close'].iloc[-1]
        
        vixy_instrument.get_tickers()
        last_price_vixy = vixy_instrument.tickers.close if vixy_instrument.tickers else 0

        if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] < signal.iloc[-2]:
            self._env.logging.info("Bullish Crossover detected: Long SPY, Close VIXY.")
            self._signals = {
                spy_instrument.contract.conId: (1.0, last_price_spy),
                vixy_instrument.contract.conId: (0.0, last_price_vixy)
            }
        elif macd.iloc[-1] < signal.iloc[-1] and macd.iloc[-2] > signal.iloc[-2]:
            self._env.logging.info("Bearish Crossover detected: Short SPY, Long VIXY.")
            self._signals = {
                spy_instrument.contract.conId: (-1.0, last_price_spy),
                vixy_instrument.contract.conId: (1.0, last_price_vixy)
            }
        else:
            self._env.logging.info("No new crossover detected. No change in signals.")
            self._signals = {}

        self._register_contracts(spy_instrument, vixy_instrument)