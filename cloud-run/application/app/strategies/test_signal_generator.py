import pandas as pd
from ib_insync import util
from strategies.strategy import Strategy

class TestSignalGenerator(Strategy):
    """
    A trading strategy based on the MACD indicator for SPY, with a hedge using VIXY.
    This version is modified to use MOCKED data to guarantee a signal for testing.
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
        
        # --- START: MOCK DATA FOR TESTING ---
        self._env.logging.warning("USING MOCKED DATA FOR SIGNAL GENERATION TEST!")
        mock_data = {
            'date': pd.to_datetime(['2025-10-01', '2025-10-02', '2025-10-03', '2025-10-04', '2025-10-05', '2025-10-06']),
            'open': [400, 402, 401, 403, 400, 405],
            'high': [403, 404, 403, 405, 405, 408],
            'low': [399, 401, 400, 402, 399, 404],
            'close': [402.0, 401.0, 402.5, 401.5, 406.0, 407.0], # A cross-up happens here
            'volume': [1000, 1100, 1050, 1200, 1300, 1400],
            'average': [401.5, 402.5, 401.5, 403.5, 402.5, 406.0],
            'barCount': [100, 100, 100, 100, 100, 100]
        }
        df = pd.DataFrame(mock_data)
        df.set_index('date', inplace=True)
        # The original `reqHistoricalData` returns a list of bars, so we mimic that.
        # In this case, the dataframe itself is treated as the content.
        bars = [df] 
        # --- END: MOCK DATA FOR TESTING ---

        if not bars:
            self._env.logging.error("Mock data is missing. Aborting.")
            self._signals = { k: (0, 0) for k in self._holdings.keys() }
            return

        # The original code uses util.df(bars), which expects a list of BarData objects.
        # Since we created a DataFrame directly, we can just use it.
        # df = util.df(bars) # This line is no longer needed with our mock data structure

        if df.empty:
            self._env.logging.error("Mock DataFrame is empty. Aborting.")
            self._signals = { k: (0, 0) for k in self._holdings.keys() }
            return
            
        # 2. Calculate MACD
        self._env.logging.info("Calculating MACD...")
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal = macd.ewm(span=9, adjust=False).mean()

        # --- ENHANCED LOGGING ---
        self._env.logging.info(f"[Data Check] Last MACD: {macd.iloc[-1]:.4f}, Last Signal: {signal.iloc[-1]:.4f}")

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
