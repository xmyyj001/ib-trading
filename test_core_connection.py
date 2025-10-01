import asyncio
import logging
import os
from lib.environment import Environment

logging.basicConfig(level=logging.INFO)

async def main():
    logging.info("--- Starting Core Connection Test ---")
    
    # 1. Set up environment
    TRADING_MODE = os.environ.get('TRADING_MODE', 'paper')
    TWS_VERSION = os.environ.get('TWS_VERSION')
    ibc_config = {'gateway': True, 'twsVersion': TWS_VERSION}
    
    # 2. Create the Environment instance using the eager-loading pattern
    env = Environment(TRADING_MODE, ibc_config)
    logging.info("Environment object and IBGW instance created.")

    try:
        # 3. Connect
        logging.info("Attempting to connect...")
        await env.ibgw.start_and_connect_async()
        logging.info("Connection successful.")

        # 4. Perform a simple, direct API call
        logging.info("Requesting current server time...")
        server_time = await env.ibgw.reqCurrentTimeAsync()
        
        # 5. Check the result
        if server_time:
            logging.info(f">>> SUCCESS: Received server time: {server_time}")
        else:
            logging.error(">>> FAILURE: API call returned no data.")

    except Exception as e:
        logging.critical(f">>> FAILURE: Test failed during connection or API call: {e}", exc_info=True)
    finally:
        # 6. Disconnect
        if hasattr(env, 'ibgw') and env.ibgw and env.ibgw.isConnected():
            env.ibgw.disconnect()
            logging.info("Disconnected cleanly.")

    logging.info("--- Core Connection Test Finished ---")

if __name__ == "__main__":
    print("Running core connection validation...")
    asyncio.run(main())
