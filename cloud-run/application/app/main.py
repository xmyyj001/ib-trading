# ===================================================================
# == FINAL, COMPLETE main.py
# ===================================================================

from datetime import datetime
import falcon
import json
import logging
from os import environ, listdir
import re

# --- 1. 导入 ib_insync.util ---
from ib_insync import util

from intents.allocation import Allocation
from intents.cash_balancer import CashBalancer
from intents.close_all import CloseAll
from intents.collect_market_data import CollectMarketData
from intents.intent import Intent
from intents.summary import Summary
from intents.trade_reconciliation import TradeReconciliation
from lib.environment import Environment

# --- 2. 在所有代码的最开始，打上 asyncio 补丁 ---
# 这是解决所有运行时事件循环问题的关键，它必须在任何 ib_insync 代码被调用之前执行。
util.patchAsyncio()
logging.info("Asyncio patched for ib_insync.")


# --- 您现有的、健壮的代码逻辑 (保持原样) ---

# get environment variables
TRADING_MODE = environ.get('TRADING_MODE', 'paper')
TWS_INSTALL_LOG = environ.get('TWS_INSTALL_LOG')

if TRADING_MODE not in ['live', 'paper']:
    raise ValueError('Unknown trading mode')

# set constants
INTENTS = {
    'allocation': Allocation,
    'cash-balancer': CashBalancer,
    'close-all': CloseAll,
    'collect-market-data': CollectMarketData,
    'summary': Summary,
    'trade-reconciliation': TradeReconciliation
}

# build IBC config from environment variables
env = {
    key: environ.get(key) for key in
    ['ibcIni', 'ibcPath', 'javaPath', 'twsPath', 'twsSettingsPath']
}
# env['javaPath'] += f"/{listdir(env['javaPath'])[0]}/bin"

# 优先从环境变量获取 TWS 版本号，这是最可靠的方式
tws_version = environ.get('TWS_VERSION')

# 如果环境变量不存在，则尝试从日志文件中解析
if not tws_version:
    logging.warning("TWS_VERSION environment variable not set. Falling back to parsing log file.")
    try:
        # 确保 TWS_INSTALL_LOG 变量存在
        if not TWS_INSTALL_LOG:
             raise ValueError("TWS_VERSION and TWS_INSTALL_LOG environment variables are both not set.")

        with open(TWS_INSTALL_LOG, 'r') as fp:
            install_log = fp.read()
        
        match = re.search('IB Gateway ([0-9]{3})', install_log)
        
        if not match:
            # 抛出一个包含所有调试信息的清晰错误
            raise ValueError(
                f"Could not find version pattern 'IB Gateway ([0-9]{3})' in log file '{TWS_INSTALL_LOG}'. "
                f"Log content was: '{install_log}'"
            )
        
        # 如果解析成功，则使用解析出的版本
        tws_version = match.group(1)
        logging.info(f"Extracted TWS version '{tws_version}' from log file: {TWS_INSTALL_LOG}")

    except FileNotFoundError:
        # 如果日志文件不存在，也抛出一个清晰的错误
        raise FileNotFoundError(
            f"TWS_INSTALL_LOG file not found at path: '{TWS_INSTALL_LOG}'"
        )
else:
    logging.info(f"Using TWS version '{tws_version}' from environment variable.")

# 经过以上逻辑，tws_version 必须有值，否则程序已经因异常而停止
# 现在可以安全地构建配置字典
ibc_config = {
    'gateway': True,
    'twsVersion': tws_version,
    **env
}

# 实例化 Environment，这将触发所有初始化，包括凭据获取和 IBGW 实例化
Environment(TRADING_MODE, ibc_config)


class Main:
    """
    Main route.
    """

    def on_get(self, request, response, intent):
        self._on_request(request, response, intent)

    def on_post(self, request, response, intent):
        body = json.load(request.stream) if request.content_length else {}
        self._on_request(request, response, intent, **body)

    @staticmethod
    def _on_request(_, response, intent, **kwargs):
        """
        Handles HTTP request.

        :param _: Falcon request (not used)
        :param response: Falcon response
        :param intent: intent (str)
        :param kwargs: HTTP request body (dict)
        """

        try:
            if intent is None or intent not in INTENTS.keys():
                logging.warning('Unknown intent')
                intent_instance = Intent()
            else:
                intent_instance = INTENTS[intent](**kwargs)
            result = intent_instance.run()
            response.status = falcon.HTTP_200
        except Exception as e:
            # 打印完整的 traceback 以便调试
            logging.exception("An error occurred while processing the intent:")
            error_str = f'{e.__class__.__name__}: {e}'
            result = {'error': error_str}
            response.status = falcon.HTTP_500

        result['utcTimestamp'] = datetime.utcnow().isoformat()
        response.content_type = falcon.MEDIA_JSON
        response.text = json.dumps(result) + '\n'


# instantiante Falcon App and define route for intent
app = falcon.App()
app.add_route('/{intent}', Main())