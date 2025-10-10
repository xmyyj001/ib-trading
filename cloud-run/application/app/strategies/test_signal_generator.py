import pandas as pd
from ib_insync import Stock, LimitOrder
from intents.intent import Intent
from lib.trading import Instrument, Trade
import inspect

class TestSignalGenerator(Intent):
    def __init__(self, env, **kwargs):
        super().__init__(env, **kwargs)
        self._dry_run = False

    async def _core_async(self):
        self._env.logging.info("--- ULTIMATE DIAGNOSIS: Starting TestSignalGenerator Intent ---")

        # --- Phase 1: Deep Inspection ---
        self._env.logging.info(f"--- ULTIMATE DIAGNOSIS: Inspecting ibgw object ---")
        try:
            ibgw_obj = self._env.ibgw
            self._env.logging.info(f"    ibgw object: {ibgw_obj}")
            self._env.logging.info(f"    Type of ibgw: {type(ibgw_obj)}")
            
            qualify_method = getattr(ibgw_obj, 'qualifyContractsAsync', 'NOT_FOUND')
            self._env.logging.info(f"    ibgw.qualifyContractsAsync attribute: {qualify_method}")
            self._env.logging.info(f"    Type of qualifyContractsAsync: {type(qualify_method)}")
            
            is_coro_func = inspect.iscoroutinefunction(qualify_method)
            self._env.logging.info(f"    Is it a coroutine function? {is_coro_func}")

            if not is_coro_func:
                raise TypeError("ibgw.qualifyContractsAsync is NOT a valid coroutine function.")

        except Exception as e:
            self._env.logging.error(f"--- ULTIMATE DIAGNOSIS: FAILED at inspection. Error: {e}")
            raise e

        # --- Phase 2: Manual Contract Qualification ---
        self._env.logging.info("--- ULTIMATE DIAGNOSIS: Qualifying contracts...")
        try:
            spy_obj = Stock('SPY', 'ARCA', 'USD')
            vixy_obj = Stock('VIXY', 'BATS', 'USD')
            qualified_contracts = await self._env.ibgw.qualifyContractsAsync(spy_obj, vixy_obj)
            
            spy_instrument = Instrument(qualified_contracts[0])
            vixy_instrument = Instrument(qualified_contracts[1])
            if not spy_instrument.contract.conId:
                raise ValueError("SPY contract qualification failed.")
            self._env.logging.info(f"--- ULTIMATE DIAGNOSIS: SUCCESS: Contracts qualified.")
        except Exception as e:
            self._env.logging.error(f"--- ULTIMATE DIAGNOSIS: FAILED at contract qualification. Error: {e}")
            raise e

        # --- The rest of the logic remains, but is unlikely to be reached if the above fails ---
        # ...
        return {"status": "Debug finished."}