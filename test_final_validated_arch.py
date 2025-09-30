import asyncio
import logging
import os
from types import SimpleNamespace

from lib.environment import Environment
from intents.intent import Intent
from intents.summary import Summary

# Configure logging
logging.basicConfig(level=logging.INFO)

# --- 1. Interactively Patch the Intent Class for the Test ---
# This simulates the final code change we will make.
original_init = Intent.__init__
def patched_init(self, env: Environment, **kwargs):
    self._env = env  # Directly set the environment via dependency injection
    
    # Replicate the rest of the original __init__ logic
    import json
    from hashlib import md5
    hashstr = self._env.env.get('K_REVISION', 'localhost') + self.__class__.__name__ + json.dumps(kwargs, sort_keys=True)
    self._signature = md5(hashstr.encode()).hexdigest()
    self._activity_log = {
        'agent': self._env.env.get('K_REVISION', 'localhost'),
        'config': self._env.config,
        'exception': None,
        'intent': self.__class__.__name__,
        'signature': self._signature,
        'tradingMode': self._env.trading_mode
    }

Intent.__init__ = patched_init
logging.info(">>> Intent class has been interactively patched for this test run.")

# --- 2. Main Test Execution Block ---
async def main():
    logging.info("--- Starting Final Validated Architecture Test ---")
    
    app = SimpleNamespace(state=SimpleNamespace())
    
    # 3. Simulate Lifespan Startup
    TRADING_MODE = os.environ.get('TRADING_MODE', 'paper')
    TWS_VERSION = os.environ.get('TWS_VERSION')
    ibc_config = {'gateway': True, 'twsVersion': TWS_VERSION}
    
    app.state.env = Environment(TRADING_MODE, ibc_config)
    logging.info("Environment object created and stored in app.state.")

    try:
        # 4. Connect to the gateway
        logging.info("Attempting to connect to IB Gateway...")
        await app.state.env.ibgw.start_and_connect_async()
        logging.info("Lifespan simulation: Connection successful.")

        # 5. Simulate an Incoming Request with Dependency Injection
        logging.info("Simulating incoming request to /summary...")
        summary_intent = Summary(env=app.state.env)
        
        # 6. Run the intent
        result = await summary_intent.run()
        logging.info(f">>> SUCCESS: Intent executed successfully. Result: {result}")

    except Exception as e:
        logging.critical(f">>> FAILURE: Final architecture test failed: {e}", exc_info=True)
    finally:
        # 7. Simulate Lifespan Shutdown
        if hasattr(app.state, 'env') and app.state.env.ibgw and app.state.env.ibgw.isConnected():
            app.state.env.ibgw.disconnect()
            logging.info("Disconnected cleanly.")

    logging.info("--- Final Validated Architecture Test Finished ---")

if __name__ == "__main__":
    print("Running final architecture validation test...")
    # Ensure the gateway is running in the background!
    asyncio.run(main())
