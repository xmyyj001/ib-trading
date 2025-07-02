# main.py
from datetime import datetime
import falcon
import json
import logging
from os import environ
from ib_insync import util

# --- 1. 关键修复：在所有代码的最开始，打上 asyncio 补丁 ---
util.patchAsyncio()
logging.info("Asyncio patched for ib_insync.")

# --- 2. 导入 ---
from intents.allocation import Allocation
from intents.cash_balancer import CashBalancer
from intents.close_all import CloseAll
from intents.collect_market_data import CollectMarketData
from intents.intent import Intent
from intents.summary import Summary
from intents.trade_reconciliation import TradeReconciliation
from lib.environment import Environment

# --- 3. 关键修复：简化并加固环境变量处理 ---
TRADING_MODE = environ.get('TRADING_MODE', 'paper')
TWS_VERSION = environ.get('TWS_VERSION') 

if not TWS_VERSION:
    raise ValueError("FATAL: TWS_VERSION environment variable is not set!")
if TRADING_MODE not in ['live', 'paper']:
    raise ValueError('Unknown trading mode')

logging.info(f"Starting application in {TRADING_MODE} mode for TWS version {TWS_VERSION}.")

# --- 4. 简化 ibc_config 构建 ---
ibc_config = {
    'gateway': True,
    'twsVersion': TWS_VERSION
}

# --- 5. 实例化 Environment ---
Environment(TRADING_MODE, ibc_config)

# --- 6. 定义 Intents 和 Falcon App ---
INTENTS = {
    'allocation': Allocation,
    'cash-balancer': CashBalancer,
    'close-all': CloseAll,
    'collect-market-data': CollectMarketData,
    'summary': Summary,
    'trade-reconciliation': TradeReconciliation
}

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