# /home/app/strategies/test_signal_generator.py

import pandas as pd
from ib_insync import Stock, LimitOrder
from intents.intent import Intent
# --- FINAL FIX 1: Import the correct subclass ---
from lib.trading import Stock as StockInstrument, Trade 
import inspect

class TestSignalGenerator(Intent):
    def __init__(self, env, **kwargs):
        super().__init__(env, **kwargs)
        self._dry_run = False

    async def _core_async(self):
        self._env.logging.info("--- Starting TestSignalGenerator Intent ---")

        # --- Phase 1: Contract Qualification ---
        self._env.logging.info("--- Qualifying contracts...")
        try:
            spy_obj = Stock('SPY', 'ARCA', 'USD')
            vixy_obj = Stock('VIXY', 'BATS', 'USD')
            
            qualified_contracts = await self._env.ibgw.qualifyContractsAsync(spy_obj, vixy_obj)
            
            if not qualified_contracts or len(qualified_contracts) < 2:
                raise ValueError("Contract qualification did not return enough contracts.")

            # --- FINAL FIX 2: Use the StockInstrument subclass and inject env ---
            spy_instrument = StockInstrument(env=self._env, ib_contract=qualified_contracts[0])
            vixy_instrument = StockInstrument(env=self._env, ib_contract=qualified_contracts[1])
            
            if not spy_instrument.contract.conId:
                raise ValueError("SPY contract qualification failed.")
            self._env.logging.info(f"--- SUCCESS: Contracts qualified.")

        except Exception as e:
            self._env.logging.error(f"--- FAILED at contract qualification. Error: {e}", exc_info=True)
            raise e

        # --- Phase 2: Force Signal Generation ---
        self._env.logging.warning("--- FINAL PUSH: FORCING BULLISH SIGNAL ---")
        last_price = 407.0 # Dummy price
        signals = {spy_instrument.contract.conId: (1.0, last_price)}
        
        # --- Phase 3: Mimic Allocation & Trade --- 
        self._env.logging.info("--- FINAL PUSH: Consolidating trades and placing orders... ---")
        
        # Pass env to Trade constructor
        trade_obj = Trade(self._env, []) 
        trade_obj.trades = { 
            conId: {
                'quantity': int(weight * 10), 
                'contract': spy_instrument.contract
            }
            for conId, (weight, price) in signals.items() if weight != 0
        }

        if not self._dry_run:
            order_params = {'lmtPrice': last_price}
            orders = await trade_obj.place_orders_async(LimitOrder, order_params=order_params)
            self._activity_log.update(orders=orders)
            self._env.logging.info(f"--- FINAL PUSH: Orders placed: {self._activity_log['orders']}")
        
        return self._activity_log