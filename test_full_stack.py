import asyncio
import logging
import os
from lib.environment import Environment
from intents.intent import Intent
from intents.summary import Summary

logging.basicConfig(level=logging.INFO)

# --- 1. The Corrected Intent __init__ Logic ---
def patched_init(self, env: Environment, **kwargs):
    self._env = env  # Directly set the environment via dependency injection
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

# --- 2. Main Test Execution Block ---
async def main():
    logging.info("--- Starting Full Stack Test (Connection + Intent) ---")
    
    # 3. Patch the class before we use it
    Intent.__init__ = patched_init
    logging.info("Intent class has been patched for this test.")

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

        # 6. Instantiate Intent with Dependency Injection
        logging.info("Instantiating Summary intent...")
        summary_intent = Summary(env=env)
        logging.info("Summary intent created successfully.")

        # 7. Run Intent
        logging.info("Running summary_intent.run()...")
        result = await summary_intent.run()
        
        logging.info(f">>> SUCCESS: Intent executed successfully. Result: {result}")

    except Exception as e:
        logging.critical(f">>> FAILURE: Test failed: {e}", exc_info=True)
    finally:
        # 8. Disconnect
        if hasattr(env, 'ibgw') and env.ibgw and env.ibgw.isConnected():
            env.ibgw.disconnect()
            logging.info("Disconnected cleanly.")

    logging.info("--- Full Stack Test Finished ---")

if __name__ == "__main__":
    print("Running full stack validation...")
    asyncio.run(main())
