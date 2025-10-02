# Architecture Refactor: The "Connect-on-Demand" Model

## 1. Overview & Goal

After extensive debugging, a fundamental incompatibility was discovered between the `ib_insync` library and the `asyncio` event loop management of ASGI servers (like Uvicorn/FastAPI) when using a persistent connection model (`lifespan`). This resulted in a persistent `RuntimeError: ... attached to a different loop` during application startup.

The final, robust solution is to abandon the persistent connection model and adopt a **"Connect-on-Demand"** architecture. 

The core principle of this architecture is:

> Each incoming API request is a self-contained unit of work. It is responsible for creating its own connection to the IB Gateway, executing its logic, and guaranteeing disconnection upon completion.

This model is simpler, more resilient to startup race conditions, and completely avoids the event loop conflicts.

## 2. Architectural Changes

The new workflow is as follows:

1.  **No Startup Connection:** The web server starts without a `lifespan` manager and does not attempt to connect to the IB Gateway.
2.  **Request Arrival:** A `curl` request arrives at an endpoint like `/summary`.
3.  **On-Demand Environment:** The `handle_intent` function in `main.py` creates a **new** `Environment` instance for this specific request.
4.  **Dependency Injection:** The newly created `env` object is passed into the constructor of the appropriate `Intent` class (e.g., `Summary(env=env)`).
5.  **Self-Contained Execution:** The `run()` method within the `Intent` class now performs the full lifecycle:
    *   It calls `await self._env.ibgw.start_and_connect_async()`.
    *   It executes its core business logic.
    *   A `finally` block ensures that `self._env.ibgw.disconnect()` is **always** called, whether the logic succeeded or failed.

## 3. Code Implementation Details

The following files were modified to implement this architecture.

### `main.py`

The `lifespan` function is removed entirely. The `handle_intent` function now creates the `Environment` for each request.

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
```

### `intents/intent.py`

The `run()` method is rewritten to handle the full connection lifecycle. The `__init__` method is also corrected to accept the injected `env`.

```python
import json
from datetime import datetime
from hashlib import md5
import logging
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from lib.environment import Environment

class Intent:
    _activity_log = {}

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

    async def _core(self):
        """Placeholder for core logic in subclasses."""
        return {'currentTime': (await self._env.ibgw.reqCurrentTimeAsync()).isoformat()}

    def _log_activity(self):
        if self._activity_log:
            try:
                self._activity_log.update(timestamp=datetime.utcnow())
                self._env.db.collection('activity').document().set(self._activity_log)
            except Exception as e:
                self._env.logging.error(f"Failed to log activity: {e}", exc_info=True)

    async def run(self):
        retval = {}
        exc = None
        try:
            # Connect-on-demand: connect at the beginning of the request.
            await self._env.ibgw.start_and_connect_async()

            if not self._env.config.get('tradingEnabled', True):
                raise SystemExit("Trading disabled by kill switch.")
            
            self._env.ibgw.reqMarketDataType(self._env.config['marketDataType'])
            retval = await self._core()

        except BaseException as e:
            error_str = f'{e.__class__.__name__}: {e}'
            self._activity_log.update(exception=error_str)
            exc = e
        finally:
            # Always disconnect at the end of the request.
            if self._env.ibgw.isConnected():
                self._env.ibgw.disconnect()
            if self._env.env.get('K_REVISION', 'localhost') != 'localhost':
                self._log_activity()
        
        if exc:
            raise exc

        return retval or self._activity_log
```

### `lib/environment.py`

The class is simplified by removing the complex Singleton pattern.

```python
import logging
from os import environ
from ib_insync import util

from lib.gcp import GcpModule
from lib.ibgw import IBGW

class Environment(GcpModule):
    """Manages the application environment for a single request."""
    
    def __init__(self, trading_mode='paper', ibc_config=None):
        super().__init__()
        self._env = {k: v for k, v in environ.items() if k in ['K_REVISION', 'PROJECT_ID']}
        self._trading_mode = trading_mode
        
        ibc_config = ibc_config or {'gateway': True, 'twsVersion': environ.get('TWS_VERSION')}
        self._ibc_config = {**ibc_config, 'tradingMode': self._trading_mode}
        
        self._logging.info("Fetching configuration from Firestore...")
        common_doc = self.db.document('config/common').get()
        mode_doc = self.db.document(f'config/{self._trading_mode}').get()
        if not common_doc.exists or not mode_doc.exists:
            raise ValueError("Critical configuration documents not found in Firestore.")
        self._config = {**common_doc.to_dict(), **mode_doc.to_dict()}
        self._logging.info("Successfully loaded configuration.")

        self._logging.info("Eagerly instantiating IBGW for this request...")
        ib_connect_config = {'port': self._config.get('apiPort', 4002)}
        self._ibgw = IBGW(self._ibc_config, ib_config=ib_connect_config)
        util.logToConsole(logging.ERROR)

    @property
    def config(self): return self._config
    @property
    def env(self): return self._env
    @property
    def ibgw(self): return self._ibgw
    @property
    def logging(self): return self._logging
    @property
    def trading_mode(self): return self._trading_mode
```

## 4. Conclusion

This architecture is simpler, more robust, and directly mirrors the logic that was proven to work in our isolated interactive tests. It definitively solves the `asyncio` event loop conflict.
