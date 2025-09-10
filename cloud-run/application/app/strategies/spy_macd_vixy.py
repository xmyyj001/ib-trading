
import pandas as pd
from ib_insync import util
from strategies.strategy import Strategy
from lib.trading import Stock

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
        self.spy = Stock('SPY', 'ARCA', 'USD')
        self.vixy = Stock('VIXY', 'BATS', 'USD')
        self._register_contracts(self.spy, self.vixy)

    def _get_signals(self):
        """
        Calculate MACD for SPY and generate trading signals for SPY and VIXY.
        Returns signals in the format {conId: (weight, price)}.
        """
        self._env.logging.info("Generating signals for SpyMacdVixy...")
        
        # 1. Fetch historical data for SPY
        self._env.logging.info("Fetching historical data for SPY...")
        bars = self._env.ibgw.reqHistoricalData(
            self.spy.contract,
            endDateTime='',
            durationStr='100 D',
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True
        )

        if not bars:
            self._env.logging.error("Could not fetch historical data for SPY. Aborting.")
            self._signals = { k: (0, 0) for k in self._holdings.keys() }
            return

        df = util.df(bars)
        if df.empty:
            self._env.logging.error("Historical data for SPY is empty. Aborting.")
            self._signals = { k: (0, 0) for k in self._holdings.keys() }
            return
            
        # 2. Calculate MACD
        self._env.logging.info("Calculating MACD...")
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal = macd.ewm(span=9, adjust=False).mean()

        # Get latest closing price for limit orders
        last_price = df.iloc[-1]['close']

        # 3. Generate signals based on crossover
        if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] < signal.iloc[-2]:
            # Bullish crossover (Golden Cross)
            self._env.logging.info(f"Bullish Crossover detected at price {last_price}: Long SPY, Close VIXY.")
            self._signals = {
                self.spy.id: (1.0, last_price),   # Target 100% allocation to long SPY
                self.vixy.id: (0.0, 0.0)      # Target 0% allocation to VIXY
            }
        elif macd.iloc[-1] < signal.iloc[-1] and macd.iloc[-2] > signal.iloc[-2]:
            # Bearish crossover (Death Cross)
            self._env.logging.info(f"Bearish Crossover detected at price {last_price}: Short SPY, Long VIXY.")
            self._signals = {
                self.spy.id: (-1.0, last_price), # Target 100% allocation to short SPY
                self.vixy.id: (1.0, last_price)  # Target 100% allocation to long VIXY (as hedge)
            }
        else:
            # No new signal, maintain current positions by returning zero signals
            self._env.logging.info("No new crossover detected. No change in signals.")
            self._signals = { k: (0, 0) for k in self._holdings.keys() }
