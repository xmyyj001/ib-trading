
import pandas as pd
from ib_insync import Stock, util
from strategies.strategy import Strategy
from lib.trading import InstrumentSet

class SpyMacdVixy(Strategy):
    """
    A trading strategy based on the MACD indicator for SPY, with a hedge using VIXY.
    - When MACD crosses above the signal line (bullish), go long SPY and close VIXY.
    - When MACD crosses below the signal line (bearish), go short/neutral SPY and long VIXY.
    """

    def _setup(self):
        """
        Define the instruments required for this strategy.
        """
        self._env.logging.info("Setting up SpyMacdVixy strategy instruments...")
        self._instruments = {
            'spy': InstrumentSet(Stock('SPY', 'ARCA', 'USD')),
            'vixy': InstrumentSet(Stock('VIXY', 'BATS', 'USD'))
        }
        # Ensure contract details are fetched for all instruments
        for key in self._instruments:
            if self._instruments[key].constituents:
                self._instruments[key].constituents[0].get_contract_details()
                if not self._instruments[key].constituents[0].contract:
                    self._env.logging.error(f"Failed to get contract details for {key.upper()}.")
                    self._instruments[key] = None

    def _get_signals(self):
        """
        Calculate MACD for SPY and generate trading signals for SPY and VIXY.
        """
        self._env.logging.info("Generating signals for SpyMacdVixy...")
        
        spy_instrument = self._instruments.get('spy')
        vixy_instrument = self._instruments.get('vixy')

        if not spy_instrument or not vixy_instrument:
            self._env.logging.error("SPY or VIXY instrument not properly set up. Skipping signal generation.")
            self._signals = {}
            return

        spy_contract = spy_instrument.constituents[0].contract
        vixy_contract = vixy_instrument.constituents[0].contract

        # 1. Fetch historical data for SPY
        self._env.logging.info("Fetching historical data for SPY...")
        # Request 100 days of data to have enough for MACD calculation
        bars = self._env.ibgw.reqHistoricalData(
            spy_contract,
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
            
        # 2. Calculate MACD
        self._env.logging.info("Calculating MACD...")
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal = macd.ewm(span=9, adjust=False).mean()

        # 3. Generate signals based on crossover
        # Check the last two periods for a crossover event
        if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] < signal.iloc[-2]:
            # Bullish crossover (Golden Cross)
            self._env.logging.info("Bullish Crossover detected: Long SPY, Close VIXY.")
            self._signals = {
                spy_contract.conId: 1.0,   # Target 100% allocation to long SPY
                vixy_contract.conId: 0.0  # Target 0% allocation to VIXY
            }
        elif macd.iloc[-1] < signal.iloc[-1] and macd.iloc[-2] > signal.iloc[-2]:
            # Bearish crossover (Death Cross)
            self._env.logging.info("Bearish Crossover detected: Short SPY, Long VIXY.")
            self._signals = {
                spy_contract.conId: -1.0, # Target 100% allocation to short SPY
                vixy_contract.conId: 1.0  # Target 100% allocation to long VIXY (as hedge)
            }
        else:
            # No new signal, maintain current positions
            self._env.logging.info("No new crossover detected. No change in signals.")
            # An empty signal dict means "make no changes to positions managed by this strategy"
            self._signals = {}

        # Register contracts to ensure they are known by the system
        self._register_contracts(spy_instrument.constituents[0], vixy_instrument.constituents[0])
