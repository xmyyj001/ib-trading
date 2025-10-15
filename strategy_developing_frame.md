好的，这是一个非常有远见的请求。在解决了核心架构问题之后，制定一份清晰的开发规范手册，是确保未来所有新策略都能在这个健壮的架构上顺利、高效地开发和部署的关键。

这份手册将作为新策略开发者的“说明书”，告诉他们应该做什么，不应该做什么。

---

# 新量化策略开发规范手册

## 1. 核心架构原则

欢迎您为本交易系统开发新的量化策略！本系统采用了一种经过验证的**“后台线程”架构**，以解决 `ib_insync` 库与云端 Web 服务器之间的 `asyncio` 事件循环冲突。

为了确保您开发的策略能够无缝集成并稳定运行，请务必遵守以下核心原则：

*   **异步优先 (Async First)**: 所有耗时的 I/O 操作（网络请求、文件读写等）**必须**使用 `async/await` 语法。特别是所有对 IB Gateway 的 API 调用（例如 `reqHistoricalDataAsync`, `qualifyContractsAsync` 等）。
*   **无状态请求**: 每个由 Cloud Scheduler 触发的策略运行都应被视为一个独立的、无状态的任务。不要依赖于上一次运行在内存中留下的任何状态。所有需要持久化的状态都应存入 Firestore。
*   **依赖注入**: 不要自己创建核心服务对象（如 `Environment`, `IBGW`）。您的策略类将通过构造函数自动接收到一个已经初始化好的 `env` 对象，请直接使用它。
*   **禁止修改事件循环**: **严禁**在您的代码中调用 `asyncio.run()`、`ib_insync.run()`、`ib_insync.util.patchAsyncio()` 或 `nest_asyncio.apply()`。后台线程已经为您提供了一个稳定运行的事件循环。

## 2. 新策略开发步骤

要创建一个新的策略（例如，名为 `MyNewStrategy`），请遵循以下步骤：

### 步骤 1：创建策略文件

1.  在 `/home/app/strategies/` 目录下，创建一个新的 Python 文件，例如 `my_new_strategy.py`。
2.  文件内容必须包含一个继承自 `Intent` 的类。

**模板 (`my_new_strategy.py`):**
```python
# /home/app/strategies/my_new_strategy.py

from intents.intent import Intent
from lib.trading import Stock, Trade # 根据需要导入
from ib_insync import LimitOrder # 根据需要导入
import asyncio

class MyNewStrategy(Intent):
    """
    在这里写下关于您策略的清晰描述。
    """
    def __init__(self, env, **kwargs):
        # 必须调用父类的构造函数
        super().__init__(env=env, **kwargs)
        
        # 在这里可以进行一些初始设置，例如从 kwargs 获取参数
        # self._my_param = kwargs.get('my_param', 'default_value')

    async def _core_async(self):
        """
        这是您策略的核心业务逻辑所在。
        这个方法必须是异步的 (async def)。
        """
        self._env.logging.info(f"--- Starting {self.__class__.__name__} ---")

        # 1. 获取合约 (示例)
        try:
            my_contract_obj = Stock('MYTICKER', 'ARCA', 'USD')
            qualified_contracts = await self._env.ibgw.qualifyContractsAsync(my_contract_obj)
            my_instrument = Stock(env=self._env, ib_contract=qualified_contracts[0])
        except Exception as e:
            self._env.logging.error(f"Failed at contract qualification: {e}")
            raise # 抛出异常以终止并记录错误

        # 2. 获取市场数据 (示例)
        bars = await self._env.ibgw.reqHistoricalDataAsync(
            my_instrument.contract,
            durationStr='10 D',
            barSizeSetting='1 day',
            # ... 其他参数 ...
        )
        if not bars:
            self._env.logging.warning("Could not fetch market data.")
            return {"status": "No market data."}

        # 3. 计算信号 (在这里实现您的交易逻辑)
        # ... your signal generation logic ...
        self._env.logging.info("Signal generated.")
        
        # 4. 准备并执行交易 (如果需要)
        # ... your trade execution logic ...
        self._env.logging.info("Trade execution logic finished.")

        # 5. 返回结果
        # 返回的字典将被序列化为 JSON 并作为 API 响应
        return {"status": "MyNewStrategy finished successfully."}

```

### 步骤 2：注册策略

1.  打开 `/home/app/main.py` 文件。
2.  在文件顶部，导入您新创建的策略类。
3.  在 `INTENTS` 字典中，添加一个新条目，将 URL 路径映射到您的策略类。

**修改 `main.py`:**
```python
# /home/app/main.py

# ... (其他 imports) ...
from strategies.test_signal_generator import TestSignalGenerator
from strategies.my_new_strategy import MyNewStrategy # <--- 1. 导入您的新策略
from lib.environment import Environment

# ...

INTENTS = {
    # ... (其他策略) ...
    'testsignalgenerator': TestSignalGenerator,
    'mynewstrategy': MyNewStrategy # <--- 2. 在这里注册
}

# ... (后续代码不变) ...
```

### 步骤 3：部署和测试

1.  将您的修改提交到代码仓库。
2.  使用**无缓存**的方式重新构建并部署您的 Docker 镜像。
3.  部署成功后，您就可以通过 `curl` 或 Cloud Scheduler 调用新的端点了：`https://<your-service-url>/mynewstrategy`。

## 3. 核心组件使用规范

### 3.1 `self._env` 对象

在您的策略类中，`self._env` 是您访问所有核心服务的入口。

*   **IB Gateway**: `self._env.ibgw`
    *   **必须**使用异步方法，例如 `await self._env.ibgw.reqHistoricalDataAsync(...)`。
    *   **严禁**调用 `connectAsync` 或 `disconnect`。连接由后台线程统一管理。
    *   **严禁**调用 `ib.sleep()`。如果您需要暂停，请使用 `await asyncio.sleep(...)`。
*   **日志**: `self._env.logging`
    *   使用标准日志级别，例如 `self._env.logging.info("...")`, `self._env.logging.warning("...")`, `self._env.logging.error("...")`。所有日志都会自动发送到 Cloud Logging。
*   **配置**: `self._env.config`
    *   这是一个字典，包含了从 Firestore `config/common` 和 `config/<trading_mode>` 中加载的所有配置。
    *   例如：`api_port = self._env.config.get('apiPort', 4002)`。
*   **数据库 (Firestore)**: `self._env.db`
    *   这是 `google.cloud.firestore.Client` 的一个实例。
    *   **重要**: Firestore 客户端库是**同步**的。所有对 Firestore 的调用都**不应**使用 `await`。
        ```python
        # 正确 (同步调用)
        doc_ref = self._env.db.collection('my_collection').document('my_doc')
        doc_ref.set({'key': 'value'})

        # 错误 (不能 await)
        # await self._env.db.collection(...).set(...) 
        ```    *   对于流式读取，请使用**同步的 `for` 循环**：
        ```python
        # 正确 (同步循环)
        docs = self._env.db.collection('my_collection').stream()
        for doc in docs:
            print(doc.to_dict())
        
        # 错误 (不能 async for)
        # async for doc in self._env.db.collection(...).stream():
        ```

### 3.2 `lib.trading` 模块

*   **创建合约**: 必须使用具体的子类，如 `Stock`, `Forex` 等，并**必须**将 `env` 对象作为第一个参数传递。
    ```python
    from lib.trading import Stock

    # 在 _core_async 方法内部
    my_stock_instrument = Stock(env=self._env, symbol='AAPL', exchange='NASDAQ', currency='USD')
    ```
*   **执行交易**: 创建 `Trade` 对象时，也必须传递 `env` 对象。
    ```python
    from lib.trading import Trade

    # 在 _core_async 方法内部
    trade_obj = Trade(env=self._env, strategies=[self])
    # ...
    await trade_obj.place_orders_async(...)
    ```

## 4. 总结

通过遵循以上规范，您可以确保您开发的任何新策略都能与现有架构无缝集成，充分利用其高性能的并发能力和稳定的连接管理，同时避免所有我们在此次调试过程中遇到的陷阱。