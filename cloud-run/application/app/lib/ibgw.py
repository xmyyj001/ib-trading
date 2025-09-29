import asyncio
from ib_insync import IB, IBC
from lib.gcp import logger as logging

class IBGW(IB):

    IB_CONFIG = {'host': '127.0.0.1', 'port': 4002, 'clientId': 1}

    def __init__(self, ibc_config, ib_config=None, connection_timeout=120, timeout_sleep=10):
        super().__init__()
        ib_config = ib_config or {}
        self.ibc_config = ibc_config
        self.ib_config = {**self.IB_CONFIG, **ib_config}
        self.connection_timeout = connection_timeout
        self.timeout_sleep = timeout_sleep
        self.ibc = IBC(**self.ibc_config)

    async def start_and_connect_async(self):
        """Asynchronously connects to an already running IB gateway with robust retries."""
        wait = self.connection_timeout
        while not self.isConnected():
            if wait <= 0:
                logging.error("Final timeout reached while trying to connect to IB gateway.")
                raise TimeoutError('Timeout reached while trying to connect to IB gateway')
            
            logging.info(f'Attempting to connect to IB gateway... Time remaining: {wait}s')
            try:
                # The connectAsync has its own internal timeout, we'll use a short one
                await asyncio.wait_for(self.connectAsync(**self.ib_config), timeout=self.timeout_sleep)
            except (ConnectionRefusedError, OSError, asyncio.TimeoutError) as e:
                logging.warning(f"Connection attempt failed: {e}. Retrying in {self.timeout_sleep}s...")
                wait -= self.timeout_sleep
                # No need to sleep here as wait_for already handled the delay
        logging.info('Successfully connected to IB Gateway.')

    async def stop_and_terminate_async(self):
        """Asynchronously closes the connection and terminates the gateway."""
        logging.info('Disconnecting from IB gateway...')
        self.disconnect()
        logging.info('Terminating IBC...')
        # In a container, we might not need to terminate IBC, but it's good practice
        # await self.ibc.terminateAsync()
