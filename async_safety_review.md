# 架构升级回顾与最终异步模型 (v4 - 最终版)

**身份**: Google Cloud 架构师
**目标**: 本文档旨在记录项目从“同步-异步混合”模式升级为“基于ASGI Lifespan的完全异步”模式的最终架构，并阐明其设计理念与执行流程。

## 1. 问题陈述: `RuntimeError: ... attached to a different loop`

在将系统改造为异步的过程中，我们遇到了一个致命的 `RuntimeError`。其根源在于 `ib_insync` 库的初始化（特别是`patchAsyncio`）在Gunicorn的主进程中被触发，而API请求是在一个拥有独立事件循环的Uvicorn工作进程中被处理，导致了事件循环冲突，使应用无法启动。

## 2. 最终解决方案: ASGI Lifespan 持久化连接模型

为根除此问题，我们采用并实施了 ASGI Lifespan Protocol。这是一种现代Python Web框架（如Falcon, FastAPI, Starlette）管理后台资源（如数据库连接、消息队列、或本项目的IB Gateway连接）的标准最佳实践。

**核心理念**: 将连接的建立和断开，从“每个请求处理时”转移到“每个工作进程生命周期开始和结束时”。

**实现方式**: 我们在 `main.py` 中实现了一个 `lifespan` 上下文管理器，并将其注入到 `falcon.asgi.App` 中。它的工作流程如下：

1.  **应用启动时 (Startup)**: Gunicorn启动一个Uvicorn工作进程后，`lifespan` 函数会立即在**该工作进程的事件循环上**执行 `yield` 之前的代码。
    *   它首先执行 `util.patchAsyncio()`，确保 `ib_insync` 在正确的循环中被初始化。
    *   然后，它调用 `env.ibgw.start_and_connect_async()`，建立一个到IB Gateway的**持久化TCP连接**。
    *   这个连接在此后将一直保持，供该工作进程处理的所有后续请求复用。

2.  **应用运行时 (Serving)**: `lifespan` 函数 `yield` 控制权，应用开始接收和处理API请求。所有业务逻辑（Intents）现在都可以假设一个稳定、可用的 `ibgw` 连接已准备就绪。

3.  **应用关闭时 (Shutdown)**: 当Gunicorn决定关闭这个工作进程时，`lifespan` 函数会执行 `yield` 之后的代码，即调用 `env.ibgw.stop_and_terminate_async()`，优雅地断开连接并清理资源。

---

## 3. 最终架构下的代码实现与调用流程

### 3.1 核心实现代码

以下是新架构下两个最核心文件的最终实现代码，作为本项目的技术基准。

**`main.py` (生命周期管理器)**
```python
import asyncio
from contextlib import asynccontextmanager
# ... other imports
from ib_insync import util
from lib.environment import Environment

@asynccontextmanager
async def lifespan(app: falcon.asgi.App):
    logging.info("Lifespan startup: Initializing application...")
    logging.info("Lifespan startup: Applying asyncio patch for ib_insync...")
    util.patchAsyncio()

    # ... (Initialize Environment) ...
    env = Environment(TRADING_MODE, ibc_config)
    
    try:
        logging.info("Lifespan startup: Connecting to IB Gateway...")
        await env.ibgw.start_and_connect_async()
        logging.info("Lifespan startup: Successfully connected to IB Gateway.")
    except Exception as e:
        logging.critical(f"FATAL: Lifespan connection to IB Gateway failed: {e}", exc_info=True)
    
    yield
    
    logging.info("Lifespan shutdown: Disconnecting from IB Gateway...")
    if env.ibgw.isConnected():
        await env.ibgw.stop_and_terminate_async()
    logging.info("Lifespan shutdown: Disconnection complete.")

# ... (Main handler class)

app = falcon.asgi.App(lifespan=lifespan)
app.add_route('/{intent}', Main())
```

**`intent.py` (纯业务逻辑处理器)**
```python
import logging
from lib.environment import Environment

class Intent:
    # ... (__init__)

    async def _core(self):
        # Assumes connection is ready.
        return {'currentTime': (await self._env.ibgw.reqCurrentTimeAsync()).isoformat()}

    async def run(self):
        retval = {}
        exc = None
        try:
            if not self._env.config.get('tradingEnabled', True):
                raise SystemExit("Trading is globally disabled by kill switch.")
            
            self._env.ibgw.reqMarketDataType(self._env.config['marketDataType'])
            retval = await self._core()

        except BaseException as e:
            # ... (error handling)
            exc = e
        finally:
            # Connection is no longer managed here.
            self._log_activity()
        
        if exc is not None:
            raise exc
        
        return retval or self._activity_log
```

### 3.2 异步调用流程

一个API请求（如 `/allocation`）在当前架构下的完整生命周期如下：

1.  **启动**: Cloud Run 实例启动 -> Gunicorn 主进程启动 -> Uvicorn 工作进程启动。
2.  **Lifespan (Startup)**: `lifespan` 函数在工作进程中执行，完成 `patchAsyncio` 和 `ibgw.start_and_connect_async()`。
3.  **等待请求**: 应用建立长连接后，开始监听HTTP请求。
4.  **请求进入**: `curl` 命令发送的 `/allocation` 请求抵达。
5.  **`main.py`**: `Main` 处理器接收请求，并调用 `Allocation` 意图的 `run()` 方法。
6.  **`intent.py`**: `Allocation` 实例的 `run()` 方法被执行。它**不再需要管理连接**，直接进入 `_core()` 业务逻辑。
7.  **`allocation.py`**: `_core()` 方法调用 `trading.py` 中的 `place_orders_async()`。
8.  **`trading.py`**: `place_orders_async()` 使用**已存在的 `ibgw` 连接**，通过 `asyncio.gather` 并发地发送所有下单请求，并异步等待券商的 `Submitted` 状态确认。
9.  **返回响应**: 所有异步操作完成后，结果逐层返回，最终由 `main.py` 封装成JSON响应返回给 `curl`。
10. **持续服务**: 应用保持连接，继续等待下一个API请求。
11. **关闭**: 当Cloud Run决定缩容或关闭实例时，`lifespan` 的 `shutdown` 部分被触发，安全断开与IB Gateway的连接。

## 4. 结论

通过本次架构升级，系统完成了从“同步/混合模式”到“基于Lifespan的完全异步模式”的蜕变。这不仅从根本上解决了事件循环冲突的 `RuntimeError`，还通过连接复用提升了性能，并通过责任分离简化了代码，使系统达到了一个真正生产级的健壮、高效和可维护的水平。