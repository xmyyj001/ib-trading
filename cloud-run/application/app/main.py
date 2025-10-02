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
@app.get("/{intent}", response_class=Response)
@app.post("/{intent}", response_class=Response)
def handle_intent(intent: str, request: Request):
    # This is now a synchronous function
    body = {}
    # Body parsing in sync functions is more complex, this is a simplified
    # version for GET requests and simple POSTs.

    result = {}
    status_code = 500
    try:
        if intent not in INTENTS:
            raise ValueError(f"Unknown intent received: {intent}")
        
        env = Environment()
        intent_instance = INTENTS[intent](env=env, **body)
        
        # The call to run() is now synchronous
        result = intent_instance.run()
        status_code = 200
    except Exception as e:
        logging.exception("An error occurred while processing the intent:")
        error_str = f'{e.__class__.__name__}: {e}'
        result = {'error': error_str}

    result['utcTimestamp'] = datetime.utcnow().isoformat()
    return Response(
        content=json.dumps(result, default=str) + '\n',
        media_type="application/json",
        status_code=status_code
    )
