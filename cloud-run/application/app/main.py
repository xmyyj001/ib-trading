from datetime import datetime
import json
import logging
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

# --- FastAPI App Definition (No Lifespan) ---
logging.basicConfig(level=logging.INFO)
app = FastAPI()

INTENTS = {
    'allocation': Allocation,
    'cash-balancer': CashBalancer,
    'close-all': CloseAll,
    'collect-market-data': CollectMarketData,
    'summary': Summary,
    'trade-reconciliation': TradeReconciliation,
    'reconcile': Reconcile
}

# --- API Routes ---
@app.get("/{intent}")
@app.post("/{intent}")
async def handle_intent(intent: str, request: Request):
    body = {}
    if request.method == 'POST' and request.headers.get('content-length'):
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return Response(
                content=json.dumps({"error": "Invalid JSON body"}),
                media_type="application/json",
                status_code=400
            )

    result = {}
    status_code = 500
    try:
        if intent not in INTENTS:
            raise ValueError(f"Unknown intent received: {intent}")
        
        # Create a new environment and intent for each request.
        # This is the connect-on-demand pattern.
        env = Environment()
        intent_instance = INTENTS[intent](env=env, **body)
        result = await intent_instance.run()
        status_code = 200
    except Exception as e:
        logging.exception("An error occurred while processing the intent:")
        error_str = f'{e.__class__.__name__}: {e}'
        result = {'error': error_str}

    result['utcTimestamp'] = datetime.utcnow().isoformat()
    return Response(
        content=json.dumps(result) + '\n',
        media_type="application/json",
        status_code=status_code
    )