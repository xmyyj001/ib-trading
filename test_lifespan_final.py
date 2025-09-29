import asyncio
import logging
import os
from ib_insync import IB

# Configure logging to see output
logging.basicConfig(level=logging.INFO)

async def main_test():
    print("--- Starting Final Lifespan Connection Test ---")
    
    # 1. Instantiate the IB() object *inside* the async function.
    # This is the critical change we are validating.
    ib_client = IB()
    logging.info("IB() object created inside the async function.")

    try:
        logging.info("Attempting to connect the new IB() instance...")
        # 2. Connect the new instance
        await ib_client.connectAsync(
            host=os.environ.get('IB_HOST', '127.0.0.1'),
            port=4002,
            clientId=1,
            timeout=15  # A reasonable timeout for the test
        )
        logging.info(">>> SUCCESS: Connection to IB Gateway was successful.")
        
        # 3. Cleanly disconnect
        ib_client.disconnect()
        logging.info("Disconnected cleanly.")

    except Exception as e:
        logging.critical(f">>> FAILURE: Connection test failed: {e}", exc_info=True)
    
    print("--- Final Lifespan Connection Test Finished ---")

if __name__ == "__main__":
    print("Running final validation test...")
    asyncio.run(main_test())
