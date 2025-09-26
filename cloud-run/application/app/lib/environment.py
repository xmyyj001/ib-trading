# ===================================================================
# == FINAL CORRECTED CODE: environment.py
# == Removes secret fetching logic to align with new architecture.
# ===================================================================

import json
from os import environ
from ib_insync import util
import logging
from google.cloud import secretmanager

from lib.gcp import GcpModule
from lib.ibgw import IBGW

class Environment:
    """Singleton class to manage the application environment."""

    class __Implementation(GcpModule):
        ACCOUNT_VALUE_TIMEOUT = 60
        ENV_VARS = ['K_REVISION', 'PROJECT_ID']

        def __init__(self, trading_mode, ibc_config):
            super().__init__()
            
            self._env = {k: v for k, v in environ.items() if k in self.ENV_VARS}
            self._trading_mode = trading_mode
            
            self._logging.info("IB Gateway authentication is handled by the startup script using environment variables.")

            config = {**ibc_config, 'tradingMode': self._trading_mode}
            config['ibcPath'] = environ.get('IBC_PATH')
            config['twsPath'] = environ.get('TWS_PATH')
            config['ibcIni'] = environ.get('IBC_INI')
            
            self._logging.debug(f"IBGW config (password omitted as it's handled externally): {config}")

            self._logging.info("Fetching configuration from Firestore...")
            common_doc = self.db.document('config/common').get()
            mode_doc = self.db.document(f'config/{self._trading_mode}').get()

            if not common_doc.exists:
                raise ValueError("Critical configuration document 'config/common' not found in Firestore.")
            if not mode_doc.exists:
                raise ValueError(f"Critical configuration document 'config/{self._trading_mode}' not found in Firestore.")

            self._config = {**common_doc.to_dict(), **mode_doc.to_dict()}
            self._logging.info("Successfully loaded configuration from Firestore.")

            # Store configs for lazy init, but do not create IBGW instance yet
            self._ibc_config = config
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
                self._logging.info("Lazily initializing IBGW instance...")
                ib_connect_config = {
                    'port': self._config.get('apiPort', 4002)
                }
                self.__ibgw = IBGW(self._ibc_config, ib_config=ib_connect_config)
            return self.__ibgw

        @property
        def logging(self):
            return self._logging

        @property
        def trading_mode(self):
            return self._trading_mode

        def get_account_values(self, account, rows=('NetLiquidation', 'CashBalance', 'MaintMarginReq')):
            account_summary = {}
            
            account_value = self.ibgw.accountValues(account)
            self._logging.debug(f"Raw account_value from IBGW: {account_value}")

            if not account_value:
                self._logging.warning(f"IB Gateway returned empty account_value for account {account}. Returning empty summary.")
                return account_summary

            try:
                account_values = util.df(account_value).set_index(['tag', 'currency']).loc[list(rows), 'value']
                self._logging.debug(f"Processed account_values DataFrame: {account_values}")
            except KeyError as e:
                self._logging.error(f"KeyError during account_values processing: {e}. Raw data: {account_value}")
                raise e
            
            for (k, c), v in account_values.items():
                if c != 'BASE':
                    if k in account_summary:
                        account_summary[k][c] = float(v)
                    else:
                        account_summary[k] = {c: float(v)}
            return account_summary

    # --- Singleton Wrapper (remains unchanged) ---
    __instance = None
    def __init__(self, trading_mode='paper', ibc_config=None):
        if Environment.__instance is None:
            Environment.__instance = self.__Implementation(trading_mode, ibc_config or {})
    def __getattr__(self, attr):
        return getattr(self.__instance, attr)
    def __setattr__(self, attr, value):
        return setattr(self.__instance, attr, value)
    def destroy(self):
        Environment.__instance = None