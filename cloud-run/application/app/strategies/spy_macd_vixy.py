
import pandas as pd
from ib_insync import util
from strategies.strategy import Strategy
from lib.trading import Stock
import os

STATE_FILE = '/tmp/trade_state.txt'

class SpyMacdVixy(Strategy):
    """
    A trading strategy that alternates between long and short SPY for testing purposes.
    """

    def _setup(self):
        """
        Define the instruments required for this strategy.
        """
        self._env.logging.info("Setting up SpyMacdVixy strategy instruments...")
        self.spy = Stock('SPY', 'ARCA', 'USD')
        self.vixy = Stock('VIXY', 'BATS', 'USD') # Keep VIXY to avoid breaking other parts
        self._register_contracts(self.spy, self.vixy)

    def _get_signals(self):
        """
        Alternates between buying and selling SPY.
        """
        self._env.logging.info("Generating alternating signals for SpyMacdVixy...")

        # 1. Determine the next action from the state file
        next_action = 'BUY'
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                last_action = f.read().strip()
                if last_action == 'BUY':
                    next_action = 'SELL'

        self._env.logging.info(f"Last action was '{last_action if 'last_action' in locals() else None}'. Next action is '{next_action}'.")

        # 2. Fetch the last price of SPY for the limit order
        bars = self._env.ibgw.reqHistoricalData(
            self.spy.contract,
            endDateTime='',
            durationStr='1 D',
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True
        )

        if not bars:
            self._env.logging.error("Could not fetch historical data for SPY. Aborting.")
            self._signals = { k: (0, 0) for k in self._holdings.keys() }
            return

        last_price = util.df(bars).iloc[-1]['close']

        # 3. Generate the signal and update the state file
        if next_action == 'BUY':
            self._env.logging.info(f"Generating BUY signal for SPY at price {last_price}.")
            self._signals = {
                self.spy.id: (1.0, last_price),   # Target 100% allocation to long SPY
                self.vixy.id: (0.0, 0.0)          # Ensure VIXY is not traded
            }
            with open(STATE_FILE, 'w') as f:
                f.write('BUY')
        else: # SELL
            self._env.logging.info(f"Generating SELL signal for SPY at price {last_price}.")
            self._signals = {
                self.spy.id: (-1.0, last_price), # Target 100% allocation to short SPY
                self.vixy.id: (0.0, 0.0)         # Ensure VIXY is not traded
            }
            with open(STATE_FILE, 'w') as f:
                f.write('SELL')
