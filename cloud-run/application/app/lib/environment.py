import json
import os
from ib_insync import util
import logging
from os import environ

# 导入 Secret Manager 客户端库
from google.cloud import secretmanager

from lib.gcp import GcpModule
from lib.ibgw import IBGW


class Environment:
    """Singleton class"""

    class __Implementation(GcpModule):

        ACCOUNT_VALUE_TIMEOUT = 60
        ENV_VARS = ['K_REVISION', 'PROJECT_ID']

        def __init__(self, trading_mode, ibc_config):
            self._env = {k: v for k, v in environ.items() if k in self.ENV_VARS}
            self._trading_mode = trading_mode

            # --- 全新的、与您的 Secret 配置匹配的凭据获取逻辑 ---
            self._logging.info(f"Fetching credentials from a single secret named '{self._trading_mode}'...")
            secrets = {}
            try:
                # 初始化客户端
                client = secretmanager.SecretManagerServiceClient()
                project_id = self._env['PROJECT_ID']

                # 根据交易模式构建密钥名称 (例如 'paper' 或 'live')
                secret_name = f"projects/{project_id}/secrets/{self._trading_mode}/versions/latest"

                # 访问密钥，获取其内容 (这是一个 JSON 字符串)
                response = client.access_secret_version(request={"name": secret_name})
                credentials_json = response.payload.data.decode("UTF-8")

                # 解析 JSON 字符串
                credentials = json.loads(credentials_json)

                # 从解析后的字典中提取 userid 和 password
                # IBC 库需要 'userid' 和 'password' 这两个键
                secrets['userid'] = credentials.get('userid')
                secrets['password'] = credentials.get('password')

                if not secrets['userid'] or not secrets['password']:
                    raise ValueError("JSON content from secret is missing 'userid' or 'password' keys.")

                self._logging.info(f"Successfully fetched and parsed credentials from secret '{self._trading_mode}'.")

            except Exception as e:
                # 如果获取或解析失败，这是致命错误
                self._logging.critical(f"FATAL: Could not fetch or parse credentials from secret '{self._trading_mode}'. Error: {e}")
                raise ValueError("Failed to load IB credentials from Secret Manager.") from e
            # --- 凭据获取逻辑结束 ---


            # 优先使用环境变量中的 TWS_PATH
            if 'TWS_PATH' in os.environ:
                ibc_config['twsPath'] = os.environ['TWS_PATH']

            # 将获取到的 secrets 合并到最终配置中
            config = {
                **ibc_config,
                'tradingMode': self._trading_mode,
                **secrets
            }

            # 确保关键路径是从环境变量中设置的
            config['ibcPath'] = environ.get('IBC_PATH', config.get('ibcPath'))
            config['ibcIni'] = environ.get('IBC_INI', config.get('ibcIni'))
            config['twsPath'] = environ.get('TWS_PATH', config.get('twsPath'))

            self._logging.debug({**config, 'password': 'xxx'}) # 打印前隐藏密码

            # query config from Firestore
            common_doc = self._db.document('config/common').get()
            mode_doc = self._db.document(f'config/{self._trading_mode}').get()

            if not common_doc.exists:
                raise ValueError("Critical configuration document 'config/common' not found in Firestore.")
            if not mode_doc.exists:
                raise ValueError(f"Critical configuration document 'config/{self._trading_mode}' not found in Firestore.")

            common_config = common_doc.to_dict()
            mode_config = mode_doc.to_dict()

            self._config = {
                **common_config,
                **mode_config
            }

            # instantiate IB Gateway
            self._ibgw = IBGW(config)
            # set IB logging level
            util.logToConsole(level=logging.ERROR)

        # ... (后续的 @property 和其他方法保持不变) ...
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
            account_summary = {}
            account_value = []
            timeout = self.ACCOUNT_VALUE_TIMEOUT
            while not len(account_value) and timeout:
                self._ibgw.sleep(1)
                account_value = self._ibgw.accountValues(account)
                timeout -= 1
            if len(account_value):
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
            self.__dict__['_Environment__instance'] = Environment.__instance

    def __getattr__(self, attr):
        return getattr(self.__instance, attr)

    def __setattr__(self, attr, value):
        return setattr(self.__instance, attr, value)

    def destroy(self):
        Environment.__instance = None
        self.__dict__.pop('_Environment__instance', None)