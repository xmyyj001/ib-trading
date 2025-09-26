import asyncio
import logging
import traceback
from ib_insync import IB, IBC

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Patched IBGW Class for In-Memory Testing ---
# This class contains the proposed fix for the asyncio loop issue.
class PatchedIBGW(IB):
    IB_CONFIG = {'host': '127.0.0.1', 'port': 4002, 'clientId': 1}

    def __init__(self, ibc_config, ib_config=None, connection_timeout=60, timeout_sleep=5):
        super().__init__()
        try:
            self.loop = asyncio.get_running_loop()
            logging.info("PatchedIBGW: Successfully got running event loop.")
        except RuntimeError:
            logging.warning("PatchedIBGW: No running loop, falling back to get_event_loop().")
            self.loop = asyncio.get_event_loop()

        ib_config = ib_config or {}
        self.ibc_config = ibc_config
        self.ib_config = {**self.IB_CONFIG, **ib_config}
        self.connection_timeout = connection_timeout
        self.timeout_sleep = timeout_sleep
        self.ibc = IBC(**self.ibc_config)

    def _run_in_loop(self, coro):
        """Explicitly run a coroutine in the stored event loop."""
        return self.loop.run_until_complete(coro)

    def start_and_connect(self):
        """Connects to an already running IB gateway using the stored event loop."""
        wait = self.connection_timeout
        while not self.isConnected():
            if wait <= 0:
                raise TimeoutError('Timeout reached while trying to connect to IB gateway')
            logging.info('PatchedIBGW: Connecting to IB gateway...')
            try:
                self._run_in_loop(self.connectAsync(**self.ib_config))
            except (ConnectionRefusedError, OSError) as e:
                logging.warning(f"PatchedIBGW: Connection attempt failed: {e}. Retrying...")
                self.sleep(self.timeout_sleep)
                wait -= self.timeout_sleep
        logging.info('PatchedIBGW: Connected successfully.')

    def stop_and_terminate(self):
        logging.info('PatchedIBGW: Disconnecting...')
        self.disconnect()
        logging.info('PatchedIBGW: Terminating IBC...')
        self._run_in_loop(self.ibc.terminateAsync())

# --- Main Debug Logic ---
def run_debug():
    logging.info("--- Starting Debug Script with Patched IBGW ---")
    
    # 1. Patch asyncio globally (as the app does)
    from ib_insync import util
    logging.info("1. Patching asyncio globally...")
    util.patchAsyncio()
    logging.info("   Asyncio patched.")

    # 2. Import Environment (to get config and other dependencies)
    from lib.environment import Environment
    import os
    TRADING_MODE = os.environ.get('TRADING_MODE', 'paper')
    TWS_VERSION = os.environ.get('TWS_VERSION', '1030')
    logging.info("2. Initializing Environment to load config...")
    env = Environment(TRADING_MODE, {'gateway': True, 'twsVersion': TWS_VERSION})
    logging.info("   Environment initialized.")

    # 3. Instantiate our PatchedIBGW instead of the one from the library
    logging.info("3. Initializing PatchedIBGW...")
    patched_ibgw = None
    try:
        # Get connection params from the real environment
        ib_connect_config = {
            'port': env.config.get('apiPort', 4002)
        }
        patched_ibgw = PatchedIBGW(env._ibc_config, ib_config=ib_connect_config)
        logging.info("   PatchedIBGW initialized.")
    except Exception as e:
        logging.error(f"   !!! Error initializing PatchedIBGW: {e}")
        traceback.print_exc()
        return

    # 4. Run the connection test
    try:
        logging.info("4. Attempting to connect using PatchedIBGW...")
        patched_ibgw.start_and_connect()
        
        if patched_ibgw.isConnected():
            logging.info("   CONNECTION SUCCEEDED with patched logic.")
            # Optional: fetch a small piece of data to confirm
            logging.info("   Fetching current time as a test...")
            current_time = patched_ibgw.reqCurrentTime()
            logging.info(f"   Successfully fetched time: {current_time}")
        else:
            logging.error("   !!! CONNECTION FAILED even with patched logic.")

    except Exception as e:
        logging.error(f"   !!! An exception occurred during the patched connection test: {e}")
        traceback.print_exc()
    finally:
        if patched_ibgw and patched_ibgw.isConnected():
            patched_ibgw.stop_and_terminate()

    logging.info("--- Debug script finished ---")

if __name__ == "__main__":
    run_debug()