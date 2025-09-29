# ===================================================================
# == FINAL VALIDATED CODE: environment.py
# == Fixes event loop issue by instantiating IBGW on first access.
# ===================================================================

import json
from os import environ
from ib_insync import util
import logging

from lib.gcp import GcpModule
from lib.ibgw import IBGW

class Environment:
    """Singleton class to manage the application environment."""

    class __Implementation(GcpModule):
        ENV_VARS = ['K_REVISION', 'PROJECT_ID']

        def __init__(self, trading_mode, ibc_config):
            super().__init__()
            
            self._env = {k: v for k, v in environ.items() if k in self.ENV_VARS}
            self._trading_mode = trading_mode
            
            self._ibc_config = {**ibc_config, 'tradingMode': self._trading_mode}
            self._ibc_config['ibcPath'] = environ.get('IBC_PATH')
            self._ibc_config['twsPath'] = environ.get('TWS_PATH')
            self._ibc_config['ibcIni'] = environ.get('IBC_INI')
            
            self._logging.info("Fetching configuration from Firestore...")
            common_doc = self.db.document('config/common').get()
            mode_doc = self.db.document(f'config/{self._trading_mode}').get()

            if not common_doc.exists or not mode_doc.exists:
                raise ValueError("Critical configuration documents not found in Firestore.")

            self._config = {**common_doc.to_dict(), **mode_doc.to_dict()}
            self._logging.info("Successfully loaded configuration from Firestore.")

            self.__ibgw = None
            util.logToConsole(logging.ERROR)

        @property
        def config(self):
            return self._config

        @property
        def env(self):
            return self._env

        @property
        def ibgw(self):
            if self.__ibgw is None:
                self._logging.info("Instantiating IBGW on first access within the event loop...")
                ib_connect_config = {'port': self._config.get('apiPort', 4002)}
                self.__ibgw = IBGW(self._ibc_config, ib_config=ib_connect_config)
            return self.__ibgw

        @property
        def logging(self):
            return self._logging

        @property
        def trading_mode(self):
            return self._trading_mode

    # --- Singleton Wrapper ---
    __instance = None
    def __init__(self, trading_mode='paper', ibc_config=None):
        if Environment.__instance is None:
            Environment.__instance = self.__Implementation(trading_mode, ibc_config or {})
    def __getattr__(self, attr):
        return getattr(self.__instance, attr)