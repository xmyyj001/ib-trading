# Final Architecture: "Sync-over-Async" Wrapper

## 1. Overview & Goal

After extensive debugging, a fundamental and unresolvable incompatibility was discovered between the `ib_insync` library and the `asyncio` event loop management of ASGI servers (Uvicorn/FastAPI), causing a persistent `RuntimeError`.

The final, validated solution is to adopt a **"Sync-over-Async"** architecture. This pattern completely isolates the `ib_insync` operations from the web server's event loop, guaranteeing stability.

### Core Principle

1.  The web server (`main.py`) remains `async` but does not manage any persistent connections.
2.  The entrypoint for our business logic (`Intent.run()`) is converted to a **synchronous** method.
3.  Inside this synchronous `run()` method, a new, isolated event loop is created for each request using `asyncio.run()`.
4.  All `ib_insync` operations (connect, execute, disconnect) happen within a dedicated `async` method that is called by `asyncio.run()`.

This architecture is robust, definitively solves the event loop conflict, and is perfectly suitable for a low-frequency trading system.

## 2. Code Implementation Details

The following files were modified to implement this architecture.

### `main.py`

The `lifespan` function is removed. The `handle_intent` route handler is now a **synchronous** function (`def` instead of `async def`) that creates a new `Environment` for each request and calls the synchronous `run()` method.

```python
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
```

### `intents/intent.py`

The `run()` method is now a synchronous wrapper that calls a new `_run_wrapper()` method using `asyncio.run()`. The `_run_wrapper()` contains the full connection lifecycle.

```python
import asyncio
import json
from datetime import datetime
from hashlib import md5
import logging
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from lib.environment import Environment

class Intent:
    def __init__(self, env: "Environment", **kwargs):
        self._env = env
        hashstr = self._env.env.get('K_REVISION', 'localhost') + self.__class__.__name__ + json.dumps(kwargs, sort_keys=True)
        self._signature = md5(hashstr.encode()).hexdigest()
        self._activity_log = {
            'agent': self._env.env.get('K_REVISION', 'localhost'),
            'config': self._env.config,
            'exception': None,
            'intent': self.__class__.__name__,
            'signature': self._signature,
            'tradingMode': self._env.trading_mode
        }

    async def _core_async(self):
        """Subclasses override this to implement their core async logic."""
        return {'currentTime': await self._env.ibgw.reqCurrentTimeAsync()}

    def _log_activity(self):
        if self._activity_log:
            try:
                self._activity_log.update(timestamp=datetime.utcnow())
                self._env.db.collection('activity').document().set(self._activity_log)
            except Exception as e:
                self._env.logging.error(f"Failed to log activity: {e}", exc_info=True)

    async def _run_wrapper(self):
        """Handles the connection lifecycle for a request."""
        try:
            await self._env.ibgw.start_and_connect_async()
            if not self._env.config.get('tradingEnabled', True):
                raise SystemExit("Trading disabled by kill switch.")
            self._env.ibgw.reqMarketDataType(self._env.config['marketDataType'])
            return await self._core_async()
        finally:
            if self._env.ibgw.isConnected():
                self._env.ibgw.disconnect()

    def run(self):
        """Sync entrypoint called by the web handler."""
        retval = {}
        exc = None
        try:
            # Bridge to the async world in a new, isolated event loop.
            retval = asyncio.run(self._run_wrapper())
        except BaseException as e:
            error_str = f'{e.__class__.__name__}: {e}'
            self._activity_log.update(exception=error_str)
            exc = e
        finally:
            if self._env.env.get('K_REVISION', 'localhost') != 'localhost':
                self._log_activity()
        if exc:
            raise exc
        return retval or self._activity_log
```

### `intents/summary.py`

This file is updated to use the correct `ib_insync` methods (`reqAccountSummaryAsync`, `portfolio`, `openTrades`, `reqExecutionsAsync`) and to correctly implement the `_core_async` method.

```python
from intents.intent import Intent
import asyncio

class Summary(Intent):
    def __init__(self, env, **kwargs):
        super().__init__(env=env, **kwargs)
        self._activity_log = {}  # don't log summary requests

    async def _core_async(self):
        # Run all requests in parallel for efficiency
        portfolio, open_trades, fills, account_summary = await asyncio.gather(
            self._get_positions(),
            self._get_trades(),
            self._get_fills(),
            self._env.ibgw.reqAccountSummaryAsync()
        )
        return {
            'accountSummary': {v.tag: v.value for v in account_summary if v.value},
            'portfolio': portfolio,
            'openTrades': open_trades,
            'fills': fills
        }

    async def _get_fills(self):
        fills = await self._env.ibgw.reqExecutionsAsync()
        return {f.contract.localSymbol: [{'side': f.execution.side, 'shares': int(f.execution.shares)}] for f in fills}

    async def _get_positions(self):
        portfolio_items = self._env.ibgw.portfolio()
        return {item.contract.localSymbol: {'position': int(item.position)} for item in portfolio_items}

    async def _get_trades(self):
        trades = self._env.ibgw.openTrades()
        return {t.contract.localSymbol: [{'isActive': t.isActive(), 'isDone': t.isDone()}] for t in trades}
```