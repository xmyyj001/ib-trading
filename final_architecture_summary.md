# Final Architecture Summary

This document contains the final, validated code for the core components of the application after a comprehensive debugging and refactoring process. This architecture is designed to be robust and correctly handle the `asyncio` event loop interactions between the ASGI server and the `ib_insync` library.

## End-to-End Logic Flow

The final architecture establishes a clear and robust sequence of events, from container startup to handling an individual request. Here is the logical flow and the role each file plays:

1.  **Container Startup (`cmd.sh`):**
    *   When the Cloud Run container starts, it executes `cmd.sh`.
    *   This script first starts the necessary background services (`Xvfb` for the virtual display and the IB Gateway Java process).
    *   After waiting 90 seconds for the gateway to initialize, its final action is to execute `exec python launcher.py`.

2.  **Event Loop Initialization (`launcher.py`):**
    *   This is the first Python code to run. Its sole purpose is to create a stable `asyncio` environment.
    *   It immediately calls `uvloop.install()`, which replaces the standard Python event loop with a high-performance, compatible version.
    *   It then programmatically starts the Uvicorn server, telling it to run the `app` object from the `main.py` file. Because `uvloop` was installed first, Uvicorn automatically uses it.

3.  **Application & Connection Startup (`main.py` - `lifespan`):**
    *   As Uvicorn starts, it begins the ASGI `lifespan` protocol defined in `main.py`.
    *   The `lifespan` function in `main.py` is now running on the stable `uvloop`.
    *   It creates an instance of the `Environment` class and stores it in the application's shared state: `app.state.env`.
    *   Crucially, it then calls `await app.state.env.ibgw.start_and_connect_async()` to establish the persistent connection to the IB Gateway. This all happens once, at startup.

4.  **Request Handling (`main.py` - `handle_intent`):**
    *   The application is now running and waiting for requests.
    *   When a `curl` request for `/summary` arrives, the `handle_intent` function in `main.py` is called.
    *   It retrieves the shared, worker-specific `Environment` object from `request.app.state.env`.
    *   It then performs **dependency injection**: it creates an instance of the appropriate `Intent` class (e.g., `Summary`) and passes the `env` object into its constructor: `Summary(env=request.app.state.env)`.

5.  **Business Logic Execution (`intent.py` & `summary.py`):**
    *   The `Summary` class's `__init__` method receives the `env` object and stores it as `self._env`.
    *   The `handle_intent` function then calls `await summary_intent.run()`.
    *   The `run()` method in the `Intent` base class now has access to the fully initialized and connected `self._env.ibgw` object and can proceed with its business logic (e.g., calling `reqCurrentTimeAsync`).

6.  **Configuration & Core Logic (`environment.py`):**
    *   This file defines the `Environment` class. Its key role is to use the **eager loading** pattern. When it is instantiated in `main.py`'s `lifespan`, its `__init__` method immediately creates the `IBGW` instance, ensuring it is born on the correct event loop.

This flow guarantees that the `IBGW` object is created and connected in the correct `asyncio` context and is then safely passed to where it's needed during request handling, resolving all the `RuntimeError` and `TypeError` issues we encountered.

---

## 1. The Blueprint: `test_core_connection.py`

**Purpose:** This simple, successful test script serves as the blueprint for the entire architecture. It proved that the core logic of creating an `Environment` object (which eagerly creates an `IBGW` instance) and then connecting it within a clean `asyncio` context works correctly. The production code below replicates this successful pattern within a web server framework.

```python
import asyncio
import logging
import os
from lib.environment import Environment

logging.basicConfig(level=logging.INFO)

async def main():
    logging.info("--- Starting Core Connection Test ---")
    
    # 1. Set up environment
    TRADING_MODE = os.environ.get('TRADING_MODE', 'paper')
    TWS_VERSION = os.environ.get('TWS_VERSION')
    ibc_config = {'gateway': True, 'twsVersion': TWS_VERSION}
    
    # 2. Create the Environment instance using the eager-loading pattern
    env = Environment(TRADING_MODE, ibc_config)
    logging.info("Environment object and IBGW instance created.")

    try:
        # 3. Connect
        logging.info("Attempting to connect...")
        await env.ibgw.start_and_connect_async()
        logging.info("Connection successful.")

        # 4. Perform a simple, direct API call
        logging.info("Requesting current server time...")
        server_time = await env.ibgw.reqCurrentTimeAsync()
        
        # 5. Check the result
        if server_time:
            logging.info(f">>> SUCCESS: Received server time: {server_time}")
        else:
            logging.error(">>> FAILURE: API call returned no data.")

    except Exception as e:
        logging.critical(f">>> FAILURE: Test failed during connection or API call: {e}", exc_info=True)
    finally:
        # 6. Disconnect
        if hasattr(env, 'ibgw') and env.ibgw and env.ibgw.isConnected():
            env.ibgw.disconnect()
            logging.info("Disconnected cleanly.")

    logging.info("--- Core Connection Test Finished ---")

if __name__ == "__main__":
    print("Running core connection validation...")
    asyncio.run(main())
```

---

## 2. `cloud-run/application/app/launcher.py`

**Purpose:** This is the new entrypoint for the container. Its sole responsibility is to install a high-performance `uvloop` event loop *before* any other code runs. It then programmatically starts the Uvicorn web server, which will automatically use this stable event loop. This resolves the fundamental conflict between the web server and `ib_insync`.

```python
import uvicorn
import uvloop

# Install the uvloop event loop policy at the absolute start of the process
uvloop.install()

if __name__ == "__main__":
    # Programmatically start the Uvicorn server
    # It will now automatically use the uvloop
    uvicorn.run("main:app", host="0.0.0.0", port=8080)
```

---

## 3. `cloud-run/application/app/requirements.txt`

**Purpose:** Defines all Python dependencies.

**Confirmation:** This file correctly includes `fastapi` as the web framework and `uvloop` for the event loop policy. `gunicorn` is no longer used to manage workers but is kept as a dependency.

```
numpy<2.0
dateparser==1.1.0
fastapi
google-cloud-firestore==2.13.1
google-cloud-bigquery[pandas]==3.11.0
google-cloud-logging==3.5.0
google-cloud-secret-manager==2.16.2
gunicorn==20.1.0
ib-insync==0.9.86
statsmodels==0.14.0
uvicorn
nest_asyncio
uvloop
```

---

## 4. `cloud-run/application/app/cmd.sh`

**Purpose:** The shell script that the container executes on startup.

**Confirmation:** This script now correctly executes the new Python launcher instead of Gunicorn, ensuring the `uvloop` is installed before the server starts.

```bash
#!/bin/bash
set -e

export PROJECT_ID="${PROJECT_ID}"

echo ">>> Starting Xvfb..."
Xvfb :0 -screen 0 1024x768x24 &
export DISPLAY=:0

echo ">>> Starting IB Gateway..."
/opt/ibc/gatewaystart.sh > /tmp/gateway-startup.log 2>&1 &

echo ">>> Waiting for IB Gateway to initialize (90 seconds)..."
sleep 90

echo ">>> Starting application via custom launcher..."
exec python launcher.py
```

---

## 5. `cloud-run/application/app/lib/environment.py`

**Purpose:** Manages the application's shared state, including configuration and the IB Gateway connection object.

**Confirmation:** This file uses the **eager loading** pattern. The `IBGW` instance is created directly inside the `__init__` constructor. This ensures that when the `lifespan` function creates the `Environment` object, the `IBGW` instance is created at the same time, on the correct, active event loop.

```python
import logging
from os import environ
from ib_insync import util

from lib.gcp import GcpModule
from lib.ibgw import IBGW

class Environment:
    class __Implementation(GcpModule):
        def __init__(self, trading_mode, ibc_config):
            super().__init__()
            self._env = {k: v for k, v in environ.items() if k in ['K_REVISION', 'PROJECT_ID']}
            self._trading_mode = trading_mode
            self._ibc_config = {**ibc_config, 'tradingMode': self._trading_mode}
            self._logging.info("Fetching configuration from Firestore...")
            common_doc = self.db.document('config/common').get()
            mode_doc = self.db.document(f'config/{self._trading_mode}').get()
            if not common_doc.exists or not mode_doc.exists:
                raise ValueError("Critical configuration documents not found in Firestore.")
            self._config = {**common_doc.to_dict(), **mode_doc.to_dict()}
            self._logging.info("Successfully loaded configuration.")
            self._logging.info("Eagerly instantiating IBGW in constructor...")
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

    __instance = None
    def __init__(self, trading_mode='paper', ibc_config=None):
        if Environment.__instance is None:
            Environment.__instance = self.__Implementation(trading_mode, ibc_config or {})
    def __getattr__(self, attr):
        return getattr(self.__instance, attr)
```

---

## 6. `cloud-run/application/app/main.py`

**Purpose:** The main application file, defining the FastAPI server and its routes.

**Confirmation:** This file correctly implements the full, validated architecture.
- It uses `FastAPI(lifespan=...)`.
- The `lifespan` function creates the `Environment` instance at startup and stores it in `app.state.env`.
- The `handle_intent` route handler uses **dependency injection**, passing the `env` object from `request.app.state.env` to the `Intent` constructor.

```python
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
        logging.critical(f"FATAL: Lifespan connection to IB Gateway failed: {e}", exc_info=True)
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
```

---

## 7. `cloud-run/application/app/intents/intent.py`

**Purpose:** The base class for all business logic intents.

**Confirmation:** The `__init__` method is now correctly defined as `def __init__(self, env: "Environment", **kwargs):`, allowing it to accept the injected `env` object. The Firestore logging call is also correctly synchronous.

```python
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

    async def _core(self):
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
            if not self._env.ibgw.isConnected():
                raise ConnectionError("Not connected. Check lifespan logs.")
            if not self._env.config.get('tradingEnabled', True):
                raise SystemExit("Trading disabled by kill switch.")
            self._env.ibgw.reqMarketDataType(self._env.config['marketDataType'])
            retval = await self._core()
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

---

## 8. `cloud-run/application/app/intents/summary.py`

**Purpose:** A specific intent implementation.

**Confirmation:** The `__init__` method is now correctly defined as `def __init__(self, env, **kwargs):` and correctly passes the `env` object to its parent class using `super().__init__(env=env, **kwargs)`.

```python
from intents.intent import Intent
import asyncio

class Summary(Intent):
    def __init__(self, env, **kwargs):
        super().__init__(env=env, **kwargs)
        self._activity_log = {}  # don't log summary requests

    async def _core(self):
        portfolio, open_trades, fills, account_summary = await asyncio.gather(
            self._get_positions(),
            self._get_trades(),
            self._get_fills(),
            self._env.ibgw.reqAccountValuesAsync(self._env.config['account'])
        )
        return {
            'accountSummary': account_summary,
            'portfolio': portfolio,
            'openTrades': open_trades,
            'fills': fills
        }

    async def _get_fills(self):
        fills = await self._env.ibgw.reqFillsAsync()
        return {f.contract.localSymbol: [{'side': f.execution.side, 'shares': int(f.execution.shares)}] for f in fills}

    async def _get_positions(self):
        portfolio_items = await self._env.ibgw.reqPortfolioAsync()
        return {item.contract.localSymbol: {'position': int(item.position)} for item in portfolio_items}

    async def _get_trades(self):
        trades = await self._env.ibgw.reqOpenTradesAsync()
        return {t.contract.localSymbol: [{'isActive': t.isActive(), 'isDone': t.isDone()}] for t in trades}
```
