import asyncio
import logging
import os
from lib.environment import Environment

# Configure logging to see output
logging.basicConfig(level=logging.INFO)

async def main():
    logging.info("--- Starting Direct Application Test (bypassing Falcon/Uvicorn) ---")
    
    TRADING_MODE = os.environ.get('TRADING_MODE', 'paper')
    TWS_VERSION = os.environ.get('TWS_VERSION')
    
    logging.info(f"Direct Test - Starting in {TRADING_MODE} mode for TWS version {TWS_VERSION}.")
    
    ibc_config = {'gateway': True, 'twsVersion': TWS_VERSION}
    
    # 1. Instantiate the Environment. This does NOT create the IBGW object yet.
    env = Environment(TRADING_MODE, ibc_config)
    
    try:
        # 2. Access the .ibgw property, which will now create the IBGW instance.
        #    Then, call the connection method.
        logging.info("Direct Test - Attempting to connect...")
        await env.ibgw.start_and_connect_async()
        logging.info(">>> SUCCESS: Direct application connection to IB Gateway was successful.")
        
        # 3. Cleanly disconnect
        env.ibgw.disconnect()
        logging.info("Disconnected cleanly.")

    except Exception as e:
        logging.critical(f">>> FAILURE: Direct application test failed: {e}", exc_info=True)
    
    logging.info("--- Direct Application Test Finished ---")

if __name__ == "__main__":
    print("Running direct application startup test...")
    asyncio.run(main())
