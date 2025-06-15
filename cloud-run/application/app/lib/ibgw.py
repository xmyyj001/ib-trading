# --- START OF FULLY REVISED lib/ibgw.py ---

from ib_insync import IB, IBC, util

from lib.gcp import logger as logging

import socket
import time

class IBGW(IB):

    IB_CONFIG = {'host': '127.0.0.1', 'port': 4001, 'clientId': 1}

    def __init__(self, ibc_config, ib_config=None, connection_timeout=120, timeout_sleep=5):
        super().__init__()
        util.patchAsyncio()
        
        ib_config = ib_config or {}
        self.ib_config = {**self.IB_CONFIG, **ib_config}
        self.connection_timeout = connection_timeout
        self.timeout_sleep = timeout_sleep

        self.ibc_config = ibc_config
        
        # --- THE FINAL FIX (Option 2) ---
        # This makes the __init__ method robust.
        # It only builds the explicit command if the 'script' key is not already
        # provided (e.g., by a test fixture that passes an empty config).
        if 'script' not in self.ibc_config:
            # Explicitly build the command to avoid any ambiguity
            ibc_path = self.ibc_config.get('ibcPath', '/opt/ibc')
            tws_path = self.ibc_config.get('twsPath', '/root/ibgateway')
            ini_file = self.ibc_config.get('ibcIni', '/root/ibc/config.ini')
            
            explicit_script_command = (
                f"{ibc_path}/scripts/ibcstart.sh -g "
                f"--tws-path={tws_path} --ibc-ini={ini_file}"
            )
            
            logging.info(f"Using explicit IBC command: {explicit_script_command}")
            self.ibc_config['script'] = explicit_script_command
        # --- END OF FINAL FIX ---

        self.ibc = IBC(**self.ibc_config)


    def start_and_connect(self):
        if self.isConnected():
            logging.info('Already connected to IB gateway.')
            return

        logging.info('Starting IBC process in the background...')
        self.ibc.start()

        host = self.ib_config.get('host', '127.0.0.1')
        port = self.ib_config.get('port', 4001)
        
        logging.info(f"Probing for API port {host}:{port} to open...")
        start_time = time.time()
        port_is_open = False
        
        while time.time() - start_time < self.connection_timeout:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                try:
                    s.connect((host, port))
                    port_is_open = True
                    logging.info(f"Success! API port {port} is now open.")
                    break
                except (socket.timeout, ConnectionRefusedError):
                    logging.info(f"Port not open yet. Waiting... (elapsed: {int(time.time() - start_time)}s)")
                    time.sleep(self.timeout_sleep)
        
        if not port_is_open:
            error_msg = f"Health check failed: API port {port} did not open within {self.connection_timeout}s."
            logging.error(error_msg)
            self.stop_and_terminate()
            raise TimeoutError(error_msg)

        logging.info('Port is open, proceeding with ib_insync connection...')
        try:
            self.connect(**self.ib_config, timeout=30)
            logging.info('Successfully connected to IB gateway.')
        except Exception as e:
            logging.error(f"Connection failed even after port was open: {e}")
            self.stop_and_terminate()
            raise e

    def stop_and_terminate(self, wait=0):
        logging.info('Disconnecting from IB gateway...')
        if self.isConnected():
            self.disconnect()
        
        logging.info('Terminating IBC...')
        try:
            util.run(self.ibc.terminateAsync())
        except Exception as e:
            logging.error(f"Error during IBC termination: {e}")

        if wait > 0:
            time.sleep(wait)

# --- END OF FULLY REVISED lib/ibgw.py ---