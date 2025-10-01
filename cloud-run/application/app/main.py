from contextlib import asynccontextmanager
from datetime import datetime
import json
import logging
from os import environ
from fastapi import FastAPI, Request, Response

from intents.allocation import Allocation
from intents.cash_balancer import CashBalancer
from intents.close_all import CloseAll
from intents.collect_market_data import CollectMarketData
from intents.intent import Intent
from intents.summary import Summary
from intents.trade_reconciliation import TradeReconciliation
from intents.reconcile import Reconcile
from lib.environment import Environment

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Lifespan: Startup - Initializing application...")
    TRADING_MODE = environ.get('TRADING_MODE', 'paper')
    TWS_VERSION = environ.get('TWS_VERSION')
    if not TWS_VERSION:
        raise ValueError("FATAL: TWS_VERSION environment variable is not set!")
    logging.info(f"Lifespan: Startup - Starting in {TRADING_MODE} mode for TWS version {TWS_VERSION}.")
    ibc_config = {'gateway': True, 'twsVersion': TWS_VERSION}
    app.state.env = Environment(TRADING_MODE, ibc_config)
    try:
        logging.info("Lifespan: Startup - Connecting to IB Gateway...")
        await app.state.env.ibgw.start_and_connect_async()
        logging.info("Lifespan: Startup - Successfully connected to IB Gateway.")
    except Exception as e:
        logging.critical(f"FATAL: Lifespan connection failed: {e}", exc_info=True)
    yield
    logging.info("Lifespan: Shutdown - Disconnecting from IB Gateway...")
    if hasattr(app.state, 'env') and app.state.env.ibgw.isConnected():
        app.state.env.ibgw.disconnect()
    logging.info("Lifespan: Shutdown - Disconnection complete.")

logging.basicConfig(level=logging.INFO)
app = FastAPI(lifespan=lifespan)

INTENTS = {
    'allocation': Allocation,
    'cash-balancer': CashBalancer,
    'close-all': CloseAll,
    'collect-market-data': CollectMarketData,
    'summary': Summary,
    'trade-reconciliation': TradeReconciliation,
    'reconcile': Reconcile
}

@app.get("/{intent}")
@app.post("/{intent}")
async def handle_intent(intent: str, request: Request):
    body = {}
    if request.method == 'POST' and request.headers.get('content-length'):
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return Response(content=json.dumps({"error": "Invalid JSON body"}), media_type="application/json", status_code=400)
    result = {}
    status_code = 500
    try:
        if intent not in INTENTS:
            raise ValueError(f"Unknown intent received: {intent}")
        intent_instance = INTENTS[intent](env=request.app.state.env, **body)
        result = await intent_instance.run()
        status_code = 200
    except Exception as e:
        logging.exception("An error occurred while processing the intent:")
        error_str = f'{e.__class__.__name__}: {e}'
        result = {'error': error_str}
    result['utcTimestamp'] = datetime.utcnow().isoformat()
    return Response(content=json.dumps(result) + '\n', media_type="application/json", status_code=status_code)