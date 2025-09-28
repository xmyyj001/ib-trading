import pandas as pd
from ib_insync import util
from strategies.strategy import Strategy

class SpyMacdVixy(Strategy):
    """
    A trading strategy based on the MACD indicator for SPY, with a hedge using VIXY.
    - When MACD is above the signal line (bullish), go long SPY.
    - When MACD is below the signal line (bearish), go short SPY.
    """

    def _setup(self):
        """
        Define the instruments required for this strategy.
        """
        from lib.trading import Stock
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

        # 3. Generate signals based on state (modified for frequent testing)
        if macd.iloc[-1] > signal.iloc[-1]:
            # Bullish State: MACD is above the signal line
            self._env.logging.info(f"Bullish state detected at price {last_price}: Long SPY.")
            self._signals = {
                self.spy.contract.conId: (1.0, last_price),   # Target 100% allocation to long SPY
                self.vixy.contract.conId: (0.0, 0.0)      # Target 0% allocation to VIXY
            }
        elif macd.iloc[-1] < signal.iloc[-1]:
            # Bearish State: MACD is below the signal line
            self._env.logging.info(f"Bearish state detected at price {last_price}: Short SPY.")
            self._signals = {
                self.spy.contract.conId: (-1.0, last_price), # Target 100% allocation to short SPY
                self.vixy.contract.conId: (0.0, 0.0)  # Hedge is removed for simplicity in this test
            }
        else:
            # No clear signal (lines are equal), maintain current positions
            self._env.logging.info("No clear bullish/bearish state. No change in signals.")
            self._signals = { k: (0, 0) for k in self._holdings.keys() }