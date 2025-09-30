import asyncio
import logging
import os
from lib.environment import Environment
from intents.intent import Intent
from intents.summary import Summary

logging.basicConfig(level=logging.INFO)

# --- 1. The Corrected __init__ Logic for Summary ---
def patched_summary_init(self, env: Environment, **kwargs):
    # Call the parent's __init__ method, passing the env
    super(Summary, self).__init__(env=env, **kwargs)
    self._activity_log = {}  # don't log summary requests

# --- 2. Main Test Execution Block ---
async def main():
    logging.info("--- Starting Summary __init__ Fix Test ---")
    
    # 3. Patch the Summary class before we use it
    Summary.__init__ = patched_summary_init
    logging.info("Summary class has been patched for this test.")

    # 4. Set up environment
    TRADING_MODE = os.environ.get('TRADING_MODE', 'paper')
    TWS_VERSION = os.environ.get('TWS_VERSION')
    ibc_config = {'gateway': True, 'twsVersion': TWS_VERSION}
    env = Environment(TRADING_MODE, ibc_config)
    logging.info("Environment object created.")

    try:
        # 5. Connect
        logging.info("Attempting to connect...")
        await env.ibgw.start_and_connect_async()
        logging.info("Connection successful.")

        # 6. Instantiate Summary with Dependency Injection
        logging.info("Instantiating Summary intent with patched __init__...")
        summary_intent = Summary(env=env)
        logging.info(">>> SUCCESS: Summary intent created successfully.")

        # We don't need to run the intent for this test, just creating it is enough.

    except Exception as e:
        logging.critical(f">>> FAILURE: Test failed: {e}", exc_info=True)
    finally:
        # 7. Disconnect
        if hasattr(env, 'ibgw') and env.ibgw and env.ibgw.isConnected():
            env.ibgw.disconnect()
            logging.info("Disconnected cleanly.")

    logging.info("--- Summary __init__ Fix Test Finished ---")

if __name__ == "__main__":
    print("Running __init__ fix validation...")
    asyncio.run(main())
