import asyncio
import logging
import os
from lib.environment import Environment

logging.basicConfig(level=logging.INFO)

async def main():
    logging.info("--- Starting Eager Loading Validation Test ---")
    
    # 1. Set up environment variables
    TRADING_MODE = os.environ.get('TRADING_MODE', 'paper')
    TWS_VERSION = os.environ.get('TWS_VERSION')
    ibc_config = {'gateway': True, 'twsVersion': TWS_VERSION}
    
    env = None
    try:
        # 2. Create the Environment instance.
        # According to the new design, this will immediately (eagerly)
        # create the IBGW instance within it.
        logging.info("Instantiating Environment (which should trigger eager IBGW instantiation)...")
        env = Environment(TRADING_MODE, ibc_config)
        logging.info("Environment object created successfully.")

        # 3. Connect using the now-existing ibgw object.
        logging.info("Attempting to connect...")
        await env.ibgw.start_and_connect_async()
        logging.info("Connection successful.")

        # 4. Perform a simple API call to be certain.
        logging.info("Requesting current server time...")
        server_time = await env.ibgw.reqCurrentTimeAsync()
        
        if server_time:
            logging.info(f">>> SUCCESS: Eager loading test passed. Received server time: {server_time}")
        else:
            logging.error(">>> FAILURE: API call returned no data.")

    except Exception as e:
        logging.critical(f">>> FAILURE: Test failed: {e}", exc_info=True)
    finally:
        # 6. Disconnect
        if env and hasattr(env, 'ibgw') and env.ibgw and env.ibgw.isConnected():
            env.ibgw.disconnect()
            logging.info("Disconnected cleanly.")

    logging.info("--- Eager Loading Validation Test Finished ---")

if __name__ == "__main__":
    print("Running eager loading validation...")
    asyncio.run(main())
