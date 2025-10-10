# ===================================================================
# == FINAL ARCHITECTURE: main.py
# == Solves the event loop conflict by running ib_insync in a separate thread.
# ===================================================================

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import json
import logging
from os import environ
from fastapi import FastAPI, Request, Response
import threading
import uuid

# 确保所有 intent 类都被导入
from intents.allocation import Allocation
from intents.cash_balancer import CashBalancer
from intents.close_all import CloseAll
from intents.collect_market_data import CollectMarketData
from intents.intent import Intent
from intents.summary import Summary
from intents.trade_reconciliation import TradeReconciliation
from intents.reconcile import Reconcile
from strategies.test_signal_generator import TestSignalGenerator
from lib.environment import Environment

# --- 1. 线程间通信设置 ---
request_queue = asyncio.Queue(maxsize=1)
results = {}

# --- 2. ib_insync 后台线程的目标函数 ---
def ib_thread_loop(env: Environment, loop: asyncio.AbstractEventLoop):
    """
    This function runs in a dedicated background thread.
    It owns its own event loop, specifically for all ib_insync operations.
    """
    asyncio.set_event_loop(loop)
    
    async def main_async_logic():
        try:
            logging.info("IB Thread: Connecting to IB Gateway...")
            await env.ibgw.start_and_connect_async()
            logging.info("IB Thread: Successfully connected to IB Gateway.")

            while True:
                request_id, intent_class, body = await request_queue.get()
                logging.info(f"IB Thread: Received request {request_id} for intent {intent_class.__name__}")
                
                result_data = {}
                error_str = None
                try:
                    intent_instance = intent_class(env=env, **body)
                    result_data = await intent_instance.run()
                except Exception as e:
                    logging.error(f"IB Thread: Error running intent: {e}", exc_info=True)
                    error_str = f'{e.__class__.__name__}: {e}'
                
                results[request_id] = (result_data, error_str)
                request_queue.task_done()

        except Exception as e:
            logging.critical(f"IB Thread: A critical error occurred in the main loop: {e}", exc_info=True)
        finally:
            if env.ibgw.isConnected():
                env.ibgw.disconnect()
            logging.info("IB Thread: Disconnected and shutting down.")

    loop.run_until_complete(main_async_logic())

# --- 3. Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    On application startup, creates the Environment and starts the background thread.
    """
    logging.info("Lifespan: Startup - Initializing application...")
    
    TRADING_MODE = environ.get('TRADING_MODE', 'paper')
    
    # Create Environment instance, which immediately creates the IBGW object
    app.state.env = Environment(TRADING_MODE)
    
    # Create a new, dedicated event loop for the background thread
    ib_loop = asyncio.new_event_loop()
    # Create and start the background thread. daemon=True ensures it exits with the main process.
    thread = threading.Thread(target=ib_thread_loop, args=(app.state.env, ib_loop), daemon=True)
    thread.start()
    logging.info("Lifespan: IB background thread started.")
    
    yield
    
    logging.info("Lifespan: Shutdown - Signaling IB thread to stop (will exit with main process).")

# --- 4. FastAPI App 和路由 ---
logging.basicConfig(level=logging.INFO)
app = FastAPI(lifespan=lifespan)

INTENTS = {
    'allocation': Allocation,
    'cash-balancer': CashBalancer,
    'close-all': CloseAll,
    'collect-market-data': CollectMarketData,
    'summary': Summary,
    'trade-reconciliation': TradeReconciliation,
    'reconcile': Reconcile,
    'testsignalgenerator': TestSignalGenerator
}

@app.get("/{intent}")
@app.post("/{intent}")
async def handle_intent(intent: str, request: Request):
    """
    This async endpoint receives requests, puts them in the queue, and waits for the result.
    """
    body = {}
    if request.method == 'POST' and request.headers.get('content-length'):
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return Response(content=json.dumps({"error": "Invalid JSON body"}), media_type="application/json", status_code=400)

    if intent not in INTENTS:
        raise ValueError(f"Unknown intent received: {intent}")

    request_id = str(uuid.uuid4())
    
    try:
        logging.info(f"Main Thread: Placing request {request_id} in queue...")
        await asyncio.wait_for(request_queue.put((request_id, INTENTS[intent], body)), timeout=5.0)
    except asyncio.TimeoutError:
        logging.error("Main Thread: Timed out waiting to place request in queue. The worker might be busy.")
        return Response(content=json.dumps({"error": "Service is busy, please try again later."}, status_code=503))

    result_data, error_str = {}, None
    for _ in range(600): # 60s timeout
        if request_id in results:
            result_data, error_str = results.pop(request_id)
            break
        await asyncio.sleep(0.1)
    else:
        error_str = "Request timed out waiting for a response from the IB worker thread."
        logging.error(f"Main Thread: {error_str} (Request ID: {request_id})")

    if error_str:
        result = {'error': error_str}
        status_code = 500
    else:
        result = result_data
        status_code = 200

    result['utcTimestamp'] = datetime.utcnow().isoformat()
    return Response(
        content=json.dumps(result, default=str) + '\n',
        media_type="application/json",
        status_code=status_code
    )