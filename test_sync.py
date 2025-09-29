import asyncio
import logging
import os
from lib.environment import Environment
from lib.ibgw import IBGW

# Configure logging to see output from all modules
logging.basicConfig(level=logging.INFO)

# --- Define a self-contained test class ---
class PatientIBGW(IBGW):
    """A test version of IBGW with a more patient retry strategy."""
    async def start_and_connect_async(self):
        self.connection_timeout = 120  # Total wait time
        self.timeout_sleep = 10      # Time between retries
        
        wait = self.connection_timeout
        while not self.isConnected():
            if wait <= 0:
                logging.error("Final timeout reached while trying to connect to IB gateway.")
                raise TimeoutError('Timeout reached while trying to connect to IB gateway')
            
            logging.info(f'Attempting to connect to IB gateway... Time remaining: {wait}s')
            try:
                await asyncio.wait_for(self.connectAsync(**self.ib_config), timeout=self.timeout_sleep)
            except (ConnectionRefusedError, OSError, asyncio.TimeoutError) as e:
                logging.warning(f"Connection attempt failed: {e}. Retrying in {self.timeout_sleep}s...")
                wait -= self.timeout_sleep
        logging.info('>>> SUCCESS: Successfully connected to IB Gateway.')

# --- Main Test Execution Block ---
async def main_test():
    print("--- Starting Interactive Test with Corrected Patient Logic ---")
    
    TRADING_MODE = os.environ.get('TRADING_MODE', 'paper')
    TWS_VERSION = os.environ.get('TWS_VERSION')
    
    logging.info(f"Test - Starting in {TRADING_MODE} mode for TWS version {TWS_VERSION}.")
    
    ibc_config = {'gateway': True, 'twsVersion': TWS_VERSION}
    
    # We will instantiate our PatientIBGW directly for this test
    patient_ibgw_instance = PatientIBGW(ibc_config)

    try:
        await patient_ibgw_instance.start_and_connect_async()
    except Exception as e:
        logging.critical(f">>> FAILURE: Test connection to IB Gateway failed: {e}", exc_info=True)
    
    print("--- Interactive Test Script Finished ---")
    print("Please review the log output above for SUCCESS or FAILURE messages.")

if __name__ == "__main__":
    asyncio.run(main_test())