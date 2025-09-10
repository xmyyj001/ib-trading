# ===================================================================
# == FINAL GOLDEN CODE: main.py
# == Patches asyncio and uses simplified, robust startup logic.
# ===================================================================

from datetime import datetime
import falcon
import falcon.asgi
import json
import logging
from os import environ
from ib_insync import util

# 1. 在所有代码的最开始，打上 asyncio 补丁
util.patchAsyncio()
# 使用一个初始的 logger，GcpModule 加载后可能会替换 handler
logging.basicConfig(level=logging.INFO)
logging.info("Asyncio patched for ib_insync.")

# 2. 导入其他模块
from intents.allocation import Allocation
from intents.cash_balancer import CashBalancer
from intents.close_all import CloseAll
from intents.collect_market_data import CollectMarketData
from intents.intent import Intent
from intents.summary import Summary
from intents.trade_reconciliation import TradeReconciliation
from intents.reconcile import Reconcile
from lib.environment import Environment

# 3. 简化并加固环境变量处理
TRADING_MODE = environ.get('TRADING_MODE', 'paper')
TWS_VERSION = environ.get('TWS_VERSION') 
if not TWS_VERSION:
    raise ValueError("FATAL: TWS_VERSION environment variable is not set!")
if TRADING_MODE not in ['live', 'paper']:
    raise ValueError('Unknown trading mode')

logging.info(f"Starting application in {TRADING_MODE} mode for TWS version {TWS_VERSION}.")

# 4. 简化 ibc_config 构建
ibc_config = {
    'gateway': True,
    'twsVersion': TWS_VERSION
}

# 5. 实例化 Environment
# 这一行将触发所有初始化，包括 GcpModule 的延迟初始化
Environment(TRADING_MODE, ibc_config)

# 6. 定义 Intents 和 Falcon App
INTENTS = {
    'allocation': Allocation,
    'cash-balancer': CashBalancer,
    'close-all': CloseAll,
    'collect-market-data': CollectMarketData,
    'summary': Summary,
    'trade-reconciliation': TradeReconciliation
}

class Main:
    """Main Falcon route handler."""
    async def on_get(self, request, response, intent):
        await self._on_request(request, response, intent)

    async def on_post(self, request, response, intent):
        body = {}
        if request.content_length:
            body_bytes = await request.stream.read()
            body = json.loads(body_bytes)
        await self._on_request(request, response, intent, **body)

    @staticmethod
    async def _on_request(_, response, intent, **kwargs):
        """Handles the HTTP request by dispatching to the correct intent."""
        try:
            if intent is None or intent not in INTENTS.keys():
                logging.warning(f"Unknown intent received: {intent}")
                intent_instance = Intent()
            else:
                intent_instance = INTENTS[intent](**kwargs)
            
            result = intent_instance.run()
            response.status = falcon.HTTP_200
        except Exception as e:
            # 使用 GcpModule 的 logger，它可能已经配置为 Cloud Logging
            # 如果 GcpModule 未初始化，它会回退到 root logger
            try:
                from lib.gcp import logger as gcp_logger
                gcp_logger.exception("An error occurred while processing the intent:")
            except ImportError:
                logging.exception("An error occurred while processing the intent:")
            
            error_str = f'{e.__class__.__name__}: {e}'
            result = {'error': error_str}
            response.status = falcon.HTTP_500

        result['utcTimestamp'] = datetime.utcnow().isoformat()
        response.content_type = falcon.MEDIA_JSON
        response.text = json.dumps(result) + '\n'

# Instantiate Falcon App
app = falcon.asgi.App()
app.add_route('/{intent}', Main())
