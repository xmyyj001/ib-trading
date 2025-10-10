from datetime import datetime
import json
from fastapi import FastAPI, Request, Response
import asyncio

from intents.allocation import Allocation
from intents.cash_balancer import CashBalancer
from intents.close_all import CloseAll
from intents.collect_market_data import CollectMarketData
from intents.intent import Intent
from intents.summary import Summary
from intents.trade_reconciliation import TradeReconciliation
from intents.reconcile import Reconcile
from lib.environment import Environment

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

# This function will run in a separate thread, not in the main event loop
def get_body_sync(request: Request):
    # Starlette's Request object provides a sync way to get the body
    return request.scope.get('_body')

async def set_body(request: Request):
    # We need to run this once to populate the scope with the body
    request.scope['_body'] = await request.body()

@app.post("/{intent}", response_class=Response)
def handle_post_intent(intent: str, request: Request):
    # Run the async part to get the body
    asyncio.run(set_body(request))
    # Now handle the logic synchronously
    return handle_intent_logic(intent, request, is_post=True)

@app.get("/{intent}", response_class=Response)
def handle_get_intent(intent: str, request: Request):
    return handle_intent_logic(intent, request, is_post=False)

def handle_intent_logic(intent: str, request: Request, is_post: bool):
    body = {}
    if is_post:
        try:
            raw_body = get_body_sync(request)
            if raw_body:
                body = json.loads(raw_body)
        except Exception:
            pass

    result = {}
    status_code = 500
    
    env = Environment()
    try:
        if intent not in INTENTS:
            raise ValueError(f"Unknown intent received: {intent}")
        
        intent_instance = INTENTS[intent](env=env, **body)
        
        result = intent_instance.run()
        status_code = 200
    except Exception as e:
        env.logging.exception("An error occurred while processing the intent:")
        error_str = f'{e.__class__.__name__}: {e}'
        result = {'error': error_str}

    result['utcTimestamp'] = datetime.utcnow().isoformat()
    return Response(
        content=json.dumps(result, default=str) + '\n',
        media_type="application/json",
        status_code=status_code
    )