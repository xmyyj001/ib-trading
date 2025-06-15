from ib_insync import IB, IBC, util

from lib.gcp import logger as logging

import socket
import time

class IBGW(IB):

    IB_CONFIG = {'host': '127.0.0.1', 'port': 4001, 'clientId': 1}

    def __init__(self, ibc_config, ib_config=None, connection_timeout=120, timeout_sleep=5):
        super().__init__()
        # --- CORE FIX ---
        # This is the magic line. It patches asyncio to automatically
        # create event loops in new threads, which is exactly what gunicorn does.
        # This must be one of the first things to run.
        util.patchAsyncio()
        # --- END OF CORE FIX ---

        ib_config = ib_config or {}
        self.ibc_config = ibc_config
        self.ib_config = {**self.IB_CONFIG, **ib_config}
        self.connection_timeout = connection_timeout
        self.timeout_sleep = timeout_sleep

        self.ibc = IBC(**self.ibc_config)

    # def start_and_connect(self):
    #     """
    #     Starts the IB gateway with IBC and connects to it.
    #     """

    #     logging.info('Starting IBC...')
    #     self.ibc.start()
    #     wait = self.connection_timeout

    #     try:
    #         while not self.isConnected():
    #             # retry until connection is established or timeout is reached
    #             self.sleep(self.timeout_sleep)
    #             wait -= self.timeout_sleep
    #             logging.info('Connecting to IB gateway...')
    #             try:
    #                 self.connect(**self.ib_config)
    #             except ConnectionRefusedError:
    #                 if wait <= 0:
    #                     logging.warning('Timeout reached')
    #                     raise TimeoutError('Could not connect to IB gateway')
    #         logging.info('Connected.')
    #     except Exception as e:
    #         logging.error(f'{e.__class__.__name__}: {e}')
    #         # write the launch log to logging (of limited use though as only the first
    #         # phase of the gateway startup process is logged in this non-encrypted log)
    #         try:
    #             with open(f"{self.ibc_config['twsPath']}/launcher.log", 'r') as fp:
    #                 logging.info(fp.read())
    #         except FileNotFoundError:
    #             logging.warning(f"{self.ibc_config['twsPath']}/launcher.log not found")
    #         raise e
# In lib/ibgw.py

    # def start_and_connect(self):
    #     """
    #     Starts the IB gateway with IBC in the background and connects to it.
    #     """
    #     if self.isConnected():
    #         logging.info('Already connected to IB gateway.')
    #         return

    #     logging.info('Starting IBC process in the background...')
    #     # ！！！核心改变：让 IBC 在后台启动，不阻塞 ！！！
    #     # IBC 类的 start 方法本身就是非阻塞的，它会启动一个子进程。
    #     # 我们只需要调用它，然后继续即可。
    #     self.ibc.start()

    #     logging.info('Attempting to connect to IB gateway...')
    #     # ib_insync 的 connect 方法会自己处理重试和等待。
    #     # 我们将连接超时完全交给它。
    #     try:
    #         self.connect(**self.ib_config, timeout=self.connection_timeout)
    #         logging.info('Successfully connected to IB gateway.')
    #     except Exception as e:
    #         logging.error(f"Failed to connect to IB gateway within {self.connection_timeout}s: {e}")
    #         # 即使连接失败，也要尝试终止 IBC 进程，避免留下僵尸进程
    #         self.ibc.terminate()
    #         raise e

    def start_and_connect(self):
        """
        Starts IBC, waits for the API port to open, and then connects.
        """
        if self.isConnected():
            logging.info('Already connected to IB gateway.')
            return

        logging.info('Starting IBC process in the background...')
        self.ibc.start()

        # --- New Health Check Loop ---
        host = self.ib_config.get('host', '127.0.0.1')
        port = self.ib_config.get('port', 4001)
        
        logging.info(f"Probing for API port {host}:{port} to open...")
        start_time = time.time()
        port_is_open = False
        
        while time.time() - start_time < self.connection_timeout:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1) # Set a short timeout for each individual check
                try:
                    s.connect((host, port))
                    port_is_open = True
                    logging.info(f"Success! API port {port} is now open.")
                    break
                except (socket.timeout, ConnectionRefusedError):
                    logging.info(f"Port not open yet. Waiting... (elapsed: {int(time.time() - start_time)}s)")
                    time.sleep(self.timeout_sleep) # Use your timeout_sleep (e.g., 5 seconds)
        
        if not port_is_open:
            error_msg = f"Health check failed: API port {port} did not open within {self.connection_timeout}s."
            logging.error(error_msg)
            self.ibc.terminate()
            raise TimeoutError(error_msg)
        # --- End of Health Check Loop ---

        logging.info('Port is open, proceeding with ib_insync connection...')
        try:
            # Now connect. This should be very fast since we know the port is open.
            # We still use a timeout as a fallback.
            self.connect(**self.ib_config, timeout=30)
            logging.info('Successfully connected to IB gateway.')
        except Exception as e:
            logging.error(f"Connection failed even after port was open: {e}")
            self.ibc.terminate()
            raise e
        

    def stop_and_terminate(self, wait=0):
        """
        Closes the connection with the IB gateway and terminates it.

        :param wait: seconds to wait after terminating (int)
        """

        logging.info('Disconnecting from IB gateway...')
        if self.isConnected():
            self.disconnect()
        
        logging.info('Terminating IBC...')
        # --- CORE FIX 2 ---
        # .terminate() returns an awaitable coroutine. We must run it.
        # util.run() will handle the event loop for this single async task.
        try:
            util.run(self.ibc.terminateAsync())
        except Exception as e:
            logging.error(f"Error during IBC termination: {e}")
        # --- END OF CORE FIX 2 ---

        if wait > 0:
            self.sleep(wait) # self.sleep is synchronous and fine here.
