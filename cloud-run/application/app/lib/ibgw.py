import asyncio
from ib_insync import IB, IBC
from lib.gcp import logger as logging

class IBGW(IB):

    IB_CONFIG = {'host': '127.0.0.1', 'port': 4002, 'clientId': 1}

    def __init__(self, ibc_config, ib_config=None, connection_timeout=60, timeout_sleep=5):
        super().__init__()
        ib_config = ib_config or {}
        self.ibc_config = ibc_config
        self.ib_config = {**self.IB_CONFIG, **ib_config}
        self.connection_timeout = connection_timeout
        self.timeout_sleep = timeout_sleep
        self.ibc = IBC(**self.ibc_config)

    async def start_and_connect_async(self):
        """Asynchronously connects to an already running IB gateway."""
        wait = self.connection_timeout
        while not self.isConnected():
            if wait <= 0:
                raise TimeoutError('Timeout reached while trying to connect to IB gateway')
            logging.info('Connecting to IB gateway...')
            try:
                await self.connectAsync(**self.ib_config)
            except (ConnectionRefusedError, OSError) as e:
                logging.warning(f"Connection attempt failed: {e}. Retrying in {self.timeout_sleep}s...")
                await asyncio.sleep(self.timeout_sleep)
                wait -= self.timeout_sleep
        logging.info('Connected.')

    async def stop_and_terminate_async(self):
        """Asynchronously closes the connection and terminates the gateway."""
        logging.info('Disconnecting from IB gateway...')
        self.disconnect()
        logging.info('Terminating IBC...')
        await self.ibc.terminateAsync()
