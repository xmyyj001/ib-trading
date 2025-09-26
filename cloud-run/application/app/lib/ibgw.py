import asyncio
from ib_insync import IB, IBC
from lib.gcp import logger as logging

class IBGW(IB):

    IB_CONFIG = {'host': '127.0.0.1', 'port': 4002, 'clientId': 1}

    def __init__(self, ibc_config, ib_config=None, connection_timeout=60, timeout_sleep=5):
        super().__init__()
        try:
            self.loop = asyncio.get_running_loop()
            logging.info("IBGW: Successfully got running event loop from get_running_loop().")
        except RuntimeError:
            logging.warning("IBGW: No running loop found, falling back to get_event_loop().")
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
            logging.info('Connecting to IB gateway...')
            try:
                self._run_in_loop(self.connectAsync(**self.ib_config))
            except (ConnectionRefusedError, OSError) as e:
                logging.warning(f"Connection attempt failed: {e}. Retrying...")
                self.sleep(self.timeout_sleep)
                wait -= self.timeout_sleep
        logging.info('Connected.')

    def stop_and_terminate(self):
        """Closes the connection with the IB gateway and terminates it."""
        logging.info('Disconnecting from IB gateway...')
        self.disconnect()
        logging.info('Terminating IBC...')
        self._run_in_loop(self.ibc.terminateAsync())
