# --- START OF FINAL, GUARANTEED FIX for lib/ibgw.py ---

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

        # --- THE FINAL FIX ---
        # Instead of relying on environment variables or parameters that might not work,
        # we will build the exact, explicit command to run.
        
        # Get the original config
        self.ibc_config = ibc_config
        
        # Get the paths from the config
        ibc_path = self.ibc_config.get('ibcPath', '/opt/ibc')
        tws_path = self.ibc_config.get('twsPath', '/root/ibgateway') # Use our correct path
        ini_file = self.ibc_config.get('ibcIni', '/root/ibc/config.ini')
        
        # Build the explicit command string. This tells the script EXACTLY where to find everything.
        # Format: /path/to/ibcstart.sh TWS_MAJOR_VRSN -g --tws-path=/path/to/ibgateway --ibc-ini=/path/to/config.ini
        # The "-g" flag is for Gateway mode.
        explicit_script_command = (
            f"{ibc_path}/scripts/ibcstart.sh {self.ibc_config['twsVersion']} "
            f"-g --tws-path={tws_path} --ibc-ini={ini_file}"
        )
        
        logging.info(f"Using explicit IBC command: {explicit_script_command}")
        
        # Override the 'script' parameter with our explicit command.
        self.ibc_config['script'] = explicit_script_command

        # Now, instantiate IBC. It will use our custom command instead of its own logic.
        self.ibc = IBC(**self.ibc_config)
        # --- END OF FINAL FIX ---


    def start_and_connect(self):
        """
        Starts IBC, waits for the API port to open, and then connects.
        """
        if self.isConnected():
            logging.info('Already connected to IB gateway.')
            return

        logging.info('Starting IBC process in the background...')
        # When this is called, it will execute our custom script command
        self.ibc.start()

        # The rest of the health check logic is fine and remains unchanged
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
            # Use the async-safe stop method
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
        """
        Closes the connection with the IB gateway and terminates it.
        """
        logging.info('Disconnecting from IB gateway...')
        if self.isConnected():
            self.disconnect()
        
        logging.info('Terminating IBC...')
        try:
            util.run(self.ibc.terminateAsync())
        except Exception as e:
            logging.error(f"Error during IBC termination: {e}")

        if wait > 0:
            # We must use time.sleep here, not self.sleep which is async
            time.sleep(wait)

# --- END OF FINAL, GUARANTEED FIX for lib/ibgw.py ---