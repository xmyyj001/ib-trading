import asyncio
import logging
import os
from lib.environment import Environment
from intents.intent import Intent
from intents.summary import Summary

logging.basicConfig(level=logging.INFO)

# --- 1. Patched Intent and Summary Classes for the Test ---
# This simulates the final architecture we will deploy.

class PatchedIntent(Intent):
    def __init__(self, env: Environment, **kwargs):
        self._env = env
        self._activity_log = {}

    async def _core_async(self):
        """The actual async business logic goes here."""
        # In a real scenario, Summary would override this.
        # For this test, we'll just get the server time.
        server_time = await self._env.ibgw.reqCurrentTimeAsync()
        return {"server_time": server_time}

    async def _run_wrapper(self):
        """The async part of the execution, handling the full lifecycle."""
        try:
            await self._env.ibgw.start_and_connect_async()
            logging.info("Connection successful inside _run_wrapper.")
            retval = await self._core_async()
        finally:
            if self._env.ibgw.isConnected():
                self._env.ibgw.disconnect()
        return retval

    def run(self):
        """The synchronous entrypoint that the web server will call."""
        logging.info("Running ib_insync logic in a new, isolated event loop via asyncio.run()...")
        # This is the critical bridge from sync to async.
        result = asyncio.run(self._run_wrapper())
        return result

class PatchedSummary(PatchedIntent):
    pass

# --- 2. Main Test Execution Block ---
def main():
    logging.info("--- Starting Sync-over-Async Architecture Test ---")
    
    # 3. Set up environment
    TRADING_MODE = os.environ.get('TRADING_MODE', 'paper')
    TWS_VERSION = os.environ.get('TWS_VERSION')
    ibc_config = {'gateway': True, 'twsVersion': TWS_VERSION}
    env = Environment(TRADING_MODE, ibc_config)
    logging.info("Environment object created.")

    try:
        # 4. Instantiate the patched intent
        summary_intent = PatchedSummary(env=env)
        logging.info("Patched Summary intent created.")

        # 5. Run the synchronous wrapper method
        # This does NOT use await at the top level.
        result = summary_intent.run()
        
        logging.info(f">>> SUCCESS: Intent executed successfully. Result: {result}")

    except Exception as e:
        logging.critical(f">>> FAILURE: Test failed: {e}", exc_info=True)

if __name__ == "__main__":
    print("Running final Sync-over-Async validation...")
    main()
