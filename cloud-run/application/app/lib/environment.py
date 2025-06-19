import json
import os
from ib_insync import util
import logging
from os import environ

from lib.gcp import GcpModule
from lib.ibgw import IBGW


class Environment:
    """Singleton class"""

    class __Implementation(GcpModule):

        ACCOUNT_VALUE_TIMEOUT = 60
        ENV_VARS = ['K_REVISION', 'PROJECT_ID']
        SECRET_RESOURCE = 'projects/{}/secrets/{}/versions/latest'

        def __init__(self, trading_mode, ibc_config):
            self._env = {k: v for k, v in environ.items() if k in self.ENV_VARS}
            self._trading_mode = trading_mode
            # get secrets and update config
            # get secrets and update config
            secrets = {}
            if 'IB_CREDENTIALS_JSON' in environ:
                try:
                    credentials = json.loads(environ.get('IB_CREDENTIALS_JSON'))
                    secrets['userid'] = credentials.get('userid')
                    secrets['password'] = credentials.get('password')
                except json.JSONDecodeError:
                    self._logging.critical("Failed to decode IB_CREDENTIALS_JSON environment variable.")
                    raise ValueError("Environment configuration could not be loaded due to invalid JSON.")
            elif 'IB_USERNAME' in environ and 'IB_PASSWORD' in environ:
                secrets['userid'] = environ.get('IB_USERNAME')  # 修复拼写错误
                secrets['password'] = environ.get('IB_PASSWORD')
            else:
                secrets = self.get_secret(self.SECRET_RESOURCE.format(self._env['PROJECT_ID'], self._trading_mode))

            if secrets is None:
                self._logging.critical("Failed to load environment variables from secret manager. They were None.")
                raise ValueError("Environment configuration could not be loaded.")
            
            # 优先使用环境变量中的 TWS_PATH
            if 'TWS_PATH' in os.environ:
                ibc_config['twsPath'] = os.environ['TWS_PATH']

            config = {
                **ibc_config,
                'tradingMode': self._trading_mode,
                **secrets
            }
            self._logging.debug({**config, 'password': 'xxx'})

            # query config
            common_doc = self._db.document('config/common').get()
            mode_doc = self._db.document(f'config/{self._trading_mode}').get()

            if not common_doc.exists:
                raise ValueError("Critical configuration document 'config/common' not found in Firestore.")
            if not mode_doc.exists:
                raise ValueError(f"Critical configuration document 'config/{self._trading_mode}' not found in Firestore.")

            # Now it's safe to call .to_dict()
            common_config = common_doc.to_dict()
            mode_config = mode_doc.to_dict()

            self._config = {
                **common_config,
                **mode_config
            }
            # self._config = {
            #     **self._db.document('config/common').get().to_dict(),
            #     **self._db.document(f'config/{self._trading_mode}').get().to_dict()
            # }


            # instantiate IB Gateway
            self._ibgw = IBGW(config)
            # set IB logging level
            util.logToConsole(level=logging.ERROR)

        @property
        def config(self):
            return self._config

        @property
        def env(self):
            return self._env

        @property
        def ibgw(self):
            return self._ibgw

        @property
        def logging(self):
            return self._logging

        @property
        def trading_mode(self):
            return self._trading_mode

        def get_account_values(self, account, rows=('NetLiquidation', 'CashBalance', 'MaintMarginReq')):
            """
            Requests account data from IB.

            :param account: account identifier (str)
            :param rows: rows to return (list)
            :return: account data (dict)
            """
            account_summary = {}
            account_value = []
            timeout = self.ACCOUNT_VALUE_TIMEOUT
            while not len(account_value) and timeout:
                # needs several attempts sometimes, so let's retry
                self._ibgw.sleep(1)
                account_value = self._ibgw.accountValues(account)
                timeout -= 1
            if len(account_value):
                # filter rows and build dict
                account_values = util.df(account_value).set_index(['tag', 'currency']).loc[list(rows), 'value']
                for (k, c), v in account_values.items():
                    if c != 'BASE':
                        if k in account_summary:
                            account_summary[k][c] = float(v)
                        else:
                            account_summary[k] = {c: float(v)}

            return account_summary

    __instance = None

    def __init__(self, trading_mode='paper', ibc_config=None):
        if Environment.__instance is None:
            Environment.__instance = self.__Implementation(trading_mode, ibc_config or {})
            # store instance reference as the only member in the handle
            self.__dict__['_Environment__instance'] = Environment.__instance

    def __getattr__(self, attr):
        """ Delegate access to implementation """
        return getattr(self.__instance, attr)

    def __setattr__(self, attr, value):
        """ Delegate access to implementation """
        return setattr(self.__instance, attr, value)

    def destroy(self):
        Environment.__instance = None
        self.__dict__.pop('_Environment__instance', None)
