import asyncio
import logging
import json
from datetime import datetime

import falcon
import falcon.asgi
from ib_insync import IB, IBC, util

# --- Patched IBGW Class (from previous debug script) ---
class PatchedIBGW(IB):
    IB_CONFIG = {'host': '127.0.0.1', 'port': 4002, 'clientId': 1}

    def __init__(self, ibc_config, ib_config=None):
        super().__init__()
        try:
            self.loop = asyncio.get_running_loop()
            logging.info("PatchedIBGW: Successfully got running event loop.")
        except RuntimeError:
            logging.warning("PatchedIBGW: No running loop, falling back to get_event_loop().")
            self.loop = asyncio.get_event_loop()
        
        self.ib_config = {**self.IB_CONFIG, **(ib_config or {})}
        self.ibc = IBC(**ibc_config)

    def _run_in_loop(self, coro):
        return self.loop.run_until_complete(coro)

    def start_and_connect(self):
        logging.info('PatchedIBGW: Connecting...')
        self._run_in_loop(self.connectAsync(**self.ib_config))
        logging.info('PatchedIBGW: Connected successfully.')

    def stop_and_terminate(self):
        logging.info('PatchedIBGW: Disconnecting...')
        self.disconnect()
        logging.info('PatchedIBGW: Terminating IBC...')
        self._run_in_loop(self.ibc.terminateAsync())

# --- Falcon Test Server ---
class TestConnectResource:
    async def on_get(self, req, resp):
        logging.info("--- Received request for /test-connect ---")
        response_data = {'status': 'UNKNOWN'}
        status_code = falcon.HTTP_500
        
        patched_ibgw = None
        try:
            # Minimal config needed for the test
            import os
            TWS_VERSION = os.environ.get('TWS_VERSION', '1030')
            ibc_config = {'gateway': True, 'twsVersion': TWS_VERSION}
            
            logging.info("Instantiating PatchedIBGW inside server...")
            patched_ibgw = PatchedIBGW(ibc_config)
            
            patched_ibgw.start_and_connect()
            
            if patched_ibgw.isConnected():
                logging.info("CONNECTION SUCCEEDED in server environment!")
                current_time = patched_ibgw.reqCurrentTime()
                response_data = {
                    'status': 'SUCCESS',
                    'ib_time': current_time.isoformat()
                }
                status_code = falcon.HTTP_200
            else:
                logging.error("CONNECTION FAILED in server environment.")
                response_data = {'status': 'FAILED', 'error': 'isConnected() returned False'}

        except Exception as e:
            logging.error(f"Exception in /test-connect: {e}", exc_info=True)
            response_data = {'status': 'ERROR', 'error': f'{e.__class__.__name__}: {e}'}
        finally:
            if patched_ibgw and patched_ibgw.isConnected():
                patched_ibgw.stop_and_terminate()
        
        resp.status = status_code
        resp.text = json.dumps(response_data)

# --- App Setup ---
logging.basicConfig(level=logging.INFO)

# Patch asyncio at the very beginning, as the main app does
util.patchAsyncio()

app = falcon.asgi.App()
app.add_route('/test-connect', TestConnectResource())

logging.info("Debug server started. Waiting for requests at /test-connect")
