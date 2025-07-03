# ===================================================================
# == FINAL GOLDEN CODE: environment.py
# == Correctly inherits from the refactored GcpModule.
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
            # 关键修复：必须先调用父类的构造函数
            super().__init__()
            
            self._env = {k: v for k, v in environ.items() if k in self.ENV_VARS}
            self._trading_mode = trading_mode
            
            # --- 凭据获取逻辑 ---
            self._logging.info(f"Fetching credentials from a single secret named '{self._trading_mode}'...")
            secrets = {}
            try:
                # 使用 GcpModule 提供的、延迟初始化的 Secret Manager 客户端
                # self.sm 会在第一次被访问时才创建实例
                secret_name = f"projects/{self._project_id}/secrets/{self._trading_mode}/versions/latest"
                response = self.sm.access_secret_version(request={"name": secret_name})
                credentials = json.loads(response.payload.data.decode("UTF-8"))
                secrets['userid'] = credentials.get('userid')
                secrets['password'] = credentials.get('password')

                if not secrets.get('userid') or not secrets.get('password'):
                    raise ValueError("JSON content from secret is missing 'userid' or 'password' keys.")

                self._logging.info(f"Successfully fetched and parsed credentials from secret '{self._trading_mode}'.")
            except Exception as e:
                self._logging.critical(f"FATAL: Could not fetch credentials from secret '{self._trading_mode}'. Error: {e}")
                raise ValueError("Failed to load IB credentials from Secret Manager.") from e

            # --- 配置合并 ---
            config = {**ibc_config, 'tradingMode': self._trading_mode, **secrets}
            # 从环境变量中获取路径，如果不存在则为 None
            config['ibcPath'] = environ.get('IBC_PATH')
            config['twsPath'] = environ.get('TWS_PATH')
            config['ibcIni'] = environ.get('IBC_INI')
            
            self._logging.debug({**config, 'password': 'xxx'})

            # --- Firestore 调用 ---
            # self.db 会在第一次被访问时才创建实例，并使用正确的 project_id
            self._logging.info("Fetching configuration from Firestore...")
            common_doc = self.db.document('config/common').get()
            mode_doc = self.db.document(f'config/{self._trading_mode}').get()

            if not common_doc.exists:
                raise ValueError("Critical configuration document 'config/common' not found in Firestore.")
            if not mode_doc.exists:
                raise ValueError(f"Critical configuration document 'config/{self._trading_mode}' not found in Firestore.")

            self._config = {**common_doc.to_dict(), **mode_doc.to_dict()}
            self._logging.info("Successfully loaded configuration from Firestore.")

            # --- IB Gateway 实例化 ---
            self._ibgw = IBGW(config)
            util.logToConsole(logging.ERROR)

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
            # This method's logic remains the same
            account_summary = {}
            # ... (rest of the method)
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