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

    # ... (其他部分不变) ...

    def start_and_connect(self):
        """
        Connects to an already running IB gateway.
        The startup is now handled by cmd.sh.
        """
        # logging.info('Starting IBC...') # <--- 注释掉或删除
        # self.ibc.start() # <--- 注释掉或删除
        wait = self.connection_timeout

        try:
            while not self.isConnected():
                self.sleep(self.timeout_sleep)
                wait -= self.timeout_sleep
                logging.info('Connecting to IB gateway...')
                try:
                    self.connect(**self.ib_config)
                except ConnectionRefusedError:
                    if wait <= 0:
                        logging.warning('Timeout reached')
                        raise TimeoutError('Could not connect to IB gateway')
            logging.info('Connected.')
        except Exception as e:
            logging.error(f'{e.__class__.__name__}: {e}')
            # 日志部分可以保留
            try:
                # 注意：ibc_config 可能不再是 self 的属性，需要确认
                # 假设它仍然被传递并设置
                log_path = self.ibc_config.get('logPath', '/opt/ibc/logs')
                with open(f"{log_path}/twsstart.log", 'r') as fp: # 尝试读取更详细的日志
                    logging.info(fp.read())
            except Exception:
                logging.warning(f"Could not read detailed IBC log.")
            raise e

    # ... (其他部分不变) ...

    def stop_and_terminate(self, wait=0):
        """
        Closes the connection with the IB gateway and terminates it.

        :param wait: seconds to wait after terminating (int)
        """

        logging.info('Disconnecting from IB gateway...')
        self.disconnect()
        logging.info('Terminating IBC...')
        self.ibc.terminate()
        self.sleep(wait)
