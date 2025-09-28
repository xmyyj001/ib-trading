import asyncio
from datetime import datetime
import falcon
import falcon.asgi
import json
import logging
from os import environ

from ib_insync import util

from intents.allocation import Allocation
from intents.cash_balancer import CashBalancer
from intents.close_all import CloseAll
from intents.collect_market_data import CollectMarketData
from intents.intent import Intent
from intents.summary import Summary
from intents.trade_reconciliation import TradeReconciliation
from intents.reconcile import Reconcile
from lib.environment import Environment

# --- 1. Lifespan Middleware (Official Falcon Pattern) ---
class IBGatewayManager:
    """A middleware class to manage the IB Gateway connection lifecycle."""

    async def process_startup(self, scope, event):
        """
        Called once per worker process when the application starts.
        """
        logging.info("Lifespan: Startup - Initializing application...")
        
        logging.info("Lifespan: Startup - Applying asyncio patch for ib_insync...")
        util.patchAsyncio()

        TRADING_MODE = environ.get('TRADING_MODE', 'paper')
        TWS_VERSION = environ.get('TWS_VERSION')
        if not TWS_VERSION:
            raise ValueError("FATAL: TWS_VERSION environment variable is not set!")
        
        logging.info(f"Lifespan: Startup - Starting in {TRADING_MODE} mode for TWS version {TWS_VERSION}.")
        
        ibc_config = {'gateway': True, 'twsVersion': TWS_VERSION}
        
        # Instantiate the global Environment singleton
        # This also lazily prepares the ibgw instance
        self.env = Environment(TRADING_MODE, ibc_config)
        
        try:
            logging.info("Lifespan: Startup - Connecting to IB Gateway...")
            await self.env.ibgw.start_and_connect_async()
            logging.info("Lifespan: Startup - Successfully connected to IB Gateway.")
        except Exception as e:
            logging.critical(f"FATAL: Lifespan connection to IB Gateway failed: {e}", exc_info=True)
            # In a real scenario, this should cause the service to fail its health check

    async def process_shutdown(self, scope, event):
        """
        Called once per worker process when the application shuts down.
        """
        logging.info("Lifespan: Shutdown - Disconnecting from IB Gateway...")
        if hasattr(self, 'env') and self.env.ibgw.isConnected():
            await self.env.ibgw.stop_and_terminate_async()
        logging.info("Lifespan: Shutdown - Disconnection complete.")

# --- 2. Falcon App Definition ---
logging.basicConfig(level=logging.INFO)

INTENTS = {
    'allocation': Allocation,
    'cash-balancer': CashBalancer,
    'close-all': CloseAll,
    'collect-market-data': CollectMarketData,
    'summary': Summary,
    'trade-reconciliation': TradeReconciliation,
    'reconcile': Reconcile
}

class Main:
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
        result = {}
        try:
            if intent is None or intent not in INTENTS.keys():
                raise ValueError(f"Unknown intent received: {intent}")
            
            intent_instance = INTENTS[intent](**kwargs)
            result = await intent_instance.run()
            response.status = falcon.HTTP_200
        except BaseException as e:
            logging.exception("An error occurred while processing the intent:")
            error_str = f'{e.__class__.__name__}: {e}'
            result = {'error': error_str}
            response.status = falcon.HTTP_500

        result['utcTimestamp'] = datetime.utcnow().isoformat()
        response.content_type = falcon.MEDIA_JSON
        response.text = json.dumps(result) + '\n'

# --- 3. Instantiate the App and Add Middleware ---
app = falcon.asgi.App(middleware=[
    IBGatewayManager()
])
app.add_route('/{intent}', Main())
