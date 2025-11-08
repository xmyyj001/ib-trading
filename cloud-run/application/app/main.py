# ===================================================================
# == FINAL ARCHITECTURE v7: main.py (Resilient)
# == Adds a top-level reconnection loop to the background thread.
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
from queue import Queue, Empty, Full

from intents.allocation import Allocation
from intents.cash_balancer import CashBalancer
from intents.close_all import CloseAll
from intents.collect_market_data import CollectMarketData
from intents.intent import Intent
from intents.summary import Summary
from intents.trade_reconciliation import TradeReconciliation
from intents.reconcile import Reconcile
from intents.orchestrator import Orchestrator
from strategies.test_signal_generator import TestSignalGenerator
from lib.environment import Environment

# --- 1. Thread Communication Setup ---
request_queue = Queue(maxsize=4)
results = {}


def _drop_pending_request(queue: Queue, request_id: str) -> None:
    """Remove a pending request from the queue if it timed out before dispatch."""
    with queue.mutex:
        for idx, item in enumerate(queue.queue):
            if item[0] == request_id:
                del queue.queue[idx]
                if queue.unfinished_tasks > 0:
                    queue.unfinished_tasks -= 1
                queue.all_tasks_done.notify_all()
                break

# --- 2. IB Background Thread with Auto-Reconnect ---
def ib_thread_loop(env, loop, queue, results_dict):
    asyncio.set_event_loop(loop)

    async def resilient_main_logic():
        """Wraps the main logic in a perpetual auto-reconnect loop."""
        min_backoff = 15
        max_backoff = 300
        backoff_seconds = min_backoff
        while True:
            connection_established = False
            try:
                logging.info("IB Thread (Outer Loop): Attempting to connect...")
                await env.ibgw.connectAsync(host='127.0.0.1', port=4002, clientId=1, timeout=15)
                logging.info("IB Thread (Outer Loop): Successfully connected.")

                try:
                    await env.ibgw.reqCurrentTimeAsync()
                    logging.info("IB Thread: Connectivity probe succeeded.")
                except Exception as probe_exc:
                    logging.warning("IB Thread: Health probe failed after connect: %s", probe_exc, exc_info=True)
                    raise

                backoff_seconds = min_backoff
                connection_established = True

                # --- Inner loop for processing requests ---
                while True:
                    try:
                        request_id, intent_class, body = queue.get(timeout=1.0)
                    except Empty:
                        await asyncio.sleep(0.01)
                        # Check connection status periodically in the inner loop
                        if not env.ibgw.isConnected():
                            logging.warning("IB Thread (Inner Loop): Connection lost. Breaking to reconnect.")
                            break # Break inner loop to trigger reconnection
                        continue

                    logging.info(f"IB Thread: Received request {request_id} for {intent_class.__name__}")
                    result_data, error_str = {}, None
                    try:
                        intent_instance = intent_class(env=env, **body)
                        result_data = await intent_instance.run()
                    except Exception as e:
                        logging.error(f"IB Thread: Error running intent: {e}", exc_info=True)
                        error_str = f'{e.__class__.__name__}: {e}'

                    results_dict[request_id] = (result_data, error_str)
                    queue.task_done()

            except asyncio.TimeoutError:
                logging.warning(
                    "IB Thread: Connection attempt timed out. Retrying in %ds...",
                    backoff_seconds
                )
            except Exception as e:
                logging.critical(
                    "IB Thread (Outer Loop): Critical error: %s. Retrying in %ds...",
                    e,
                    backoff_seconds,
                    exc_info=True
                )
            finally:
                if env.ibgw.isConnected():
                    env.ibgw.disconnect()
                logging.info(
                    "IB Thread (Outer Loop): Disconnected. Attempting reconnection in %d seconds...",
                    backoff_seconds
                )

            await asyncio.sleep(backoff_seconds)
            if not connection_established:
                backoff_seconds = min(backoff_seconds * 2, max_backoff)
            else:
                backoff_seconds = min_backoff

    loop.run_until_complete(resilient_main_logic())

# --- 3. Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Lifespan: Startup...")
    app.state.env = Environment()
    app.state.request_queue = request_queue
    app.state.results = results

    ib_loop = asyncio.new_event_loop()
    thread = threading.Thread(
        target=ib_thread_loop, 
        args=(app.state.env, ib_loop, app.state.request_queue, app.state.results), 
        daemon=True
    )
    thread.start()
    logging.info("Lifespan: IB background thread started.")
    yield
    logging.info("Lifespan: Shutdown.")

# --- 4. FastAPI App & Routes ---
logging.basicConfig(level=logging.INFO)
app = FastAPI(lifespan=lifespan)

INTENTS = {
    'allocation': Allocation,
    'cash-balancer': CashBalancer,
    'close-all': CloseAll,
    'collect_market_data': CollectMarketData,
    'summary': Summary,
    'trade-reconciliation': TradeReconciliation,
    'reconcile': Reconcile,
    'testsignalgenerator': TestSignalGenerator,
    'orchestrator': Orchestrator
}

@app.get("/")
async def root_status():
    """Lightweight status endpoint for health checks."""
    return {
        'status': 'ok',
        'registered_intents': sorted(INTENTS.keys())
    }


@app.post("/")
async def orchestrator_entrypoint(request: Request):
    """Backward-compatible entrypoint that proxies to the orchestrator intent."""
    return await handle_intent('orchestrator', request)


@app.get("/{intent}")
@app.post("/{intent}")
async def handle_intent(intent: str, request: Request):
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
        request.app.state.request_queue.put((request_id, INTENTS[intent], body), timeout=5)
    except Full:
        return Response(content=json.dumps({"error": "Service is busy"}), status_code=503)

    results_dict = request.app.state.results
    for _ in range(600): # 60s timeout
        if request_id in results_dict:
            result_data, error_str = results_dict.pop(request_id)
            break
        await asyncio.sleep(0.1)
    else:
        error_str = "Request timed out"
        _drop_pending_request(request.app.state.request_queue, request_id)
    
    if error_str:
        result = {'error': error_str}
        if 'ConnectionError' in error_str or 'connect' in error_str.lower():
            status_code = 503
        else:
            status_code = 500
    else:
        result = result_data
        status_code = 200

    result['utcTimestamp'] = datetime.utcnow().isoformat()
    return Response(content=json.dumps(result, default=str), media_type="application/json", status_code=status_code)
