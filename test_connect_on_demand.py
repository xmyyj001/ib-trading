import asyncio
import logging
import os
from lib.environment import Environment
from intents.intent import Intent
from intents.summary import Summary

logging.basicConfig(level=logging.INFO)

# --- 1. Patched Intent and Summary Classes for the Test ---

class PatchedIntent(Intent):
    def __init__(self, env: Environment, **kwargs):
        self._env = env
        # Simplified init for the test
        self._activity_log = {}

    async def _core_async(self):
        # This is the async part of the logic
        await self._env.ibgw.start_and_connect_async()
        logging.info("Connection successful inside _core_async.")
        server_time = await self._env.ibgw.reqCurrentTimeAsync()
        self._env.ibgw.disconnect()
        return server_time

    def run_sync(self):
        # This is the synchronous wrapper that will be called by the web server.
        # It creates a new event loop just for the ib_insync logic.
        logging.info("Running ib_insync logic in a new, isolated event loop...")
        result = asyncio.run(self._core_async())
        return {"server_time": result.isoformat()}

class PatchedSummary(PatchedIntent):
    pass # Inherits the new run_sync method

# --- 2. Main Test Execution Block ---
def main():
    logging.info("--- Starting Final Connect-on-Demand Test ---")
    
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
        result = summary_intent.run_sync()
        
        logging.info(f">>> SUCCESS: Intent executed successfully. Result: {result}")

    except Exception as e:
        logging.critical(f">>> FAILURE: Test failed: {e}", exc_info=True)

if __name__ == "__main__":
    print("Running final connect-on-demand validation...")
    main()
