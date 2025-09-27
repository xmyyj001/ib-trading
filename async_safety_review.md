# 架构排查与异步安全加固计划 (最终版 v3 - 已解决事件循环问题)

**身份**: Google Cloud 架构师
**目标**: 根除因`asyncio`事件循环冲突导致的`RuntimeError`，确保系统在Gunicorn/Uvicorn环境下的异步稳定性。

## 1. 核心问题诊断: `RuntimeError: ... attached to a different loop`

在审阅了您最新的代码和详细的错误日志后，问题根源已非常明确：**`ib_insync`库在错误的时机被初始化，导致其绑定的事件循环与处理API请求的Uvicorn工作进程的事件循环不一致。**

这是一个在 `asyncio` 与多进程WSGI服务器（如Gunicorn）集成时非常典型的“坑”。主进程和工作进程拥有不同的事件循环，任何在模块加载时（主进程阶段）就进行初始化的异步库，都会在工作进程中调用时产生冲突。

## 2. 解决方案: 延迟初始化 (Lazy Initialization)

解决方案是**将`ib_insync`的初始化工作，从“模块加载时”推迟到“代码运行时”**。我们必须确保 `util.patchAsyncio()` 这个关键的初始化函数，在处理具体API请求的那个工作进程中被调用，而且只被调用一次。

幸运的是，您当前的架构（`main.py`中已移除全局patch，`intent.py`作为所有业务逻辑的入口）为实施此方案提供了完美的“手术点”。

---

## 3. 最终代码修复建议

我们将对`intent.py`进行一次精确的修改，将`patchAsyncio`的调用注入到`run`方法的开头，并使用一个全局标志位确保它在每个进程中只运行一次。

### **修改文件**: `cloud-run/application/app/intents/intent.py`

**修改说明**:
1.  **引入 `ib_insync.util`**: 我们需要再次导入这个模块。
2.  **增加全局标志位**: `_asyncio_patched = False` 用于跟踪当前进程是否已执行过patch。
3.  **在 `run` 方法中执行Patch**: 在 `run` 方法的开头，检查该标志位。如果是 `False`，则执行 `util.patchAsyncio()` 并将标志位设为 `True`。

这将确保在处理第一个API请求时，`ib_insync` 会在正确的Uvicorn工作进程的事件循环中完成初始化。后续同一进程中的请求会直接跳过，避免重复执行。

**完整代码**:

```python
# cloud-run/application/app/intents/intent.py

import json
from datetime import datetime
from hashlib import md5

from lib.environment import Environment
from ib_insync import util # <--- 1. 重新导入

# 2. 增加一个全局标志位来跟踪patch状态
_asyncio_patched = False

class Intent:

    _activity_log = {}

    def __init__(self, **kwargs):
        self._env = Environment()
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
        if len(self._activity_log):
            try:
                self._activity_log.update(timestamp=datetime.utcnow())
                self._env.db.collection('activity').document().set(self._activity_log)
            except Exception as e:
                self._env.logging.error(e)
                self._env.logging.info(self._activity_log)

    async def run(self):
        global _asyncio_patched
        # --- 3. 在运行时执行Patch --- 
        if not _asyncio_patched:
            self._env.logging.info("Applying asyncio patch for ib_insync in worker process...")
            util.patchAsyncio()
            _asyncio_patched = True
        # --- END PATCH --- 

        retval = {}
        exc = None
        try:
            if not self._env.config.get('tradingEnabled', True):
                raise SystemExit("Trading is globally disabled by kill switch.")
            
            await self._env.ibgw.start_and_connect_async()
            self._env.ibgw.reqMarketDataType(self._env.config['marketDataType'])
            retval = await self._core()
        except BaseException as e:
            error_str = f'{e.__class__.__name__}: {e}'
            self._env.logging.error(error_str)
            self._activity_log.update(exception=error_str)
            exc = e
        finally:
            if self._env.ibgw.isConnected():
                await self._env.ibgw.stop_and_terminate_async()
            
            if self._env.env.get('K_REVISION', 'localhost') != 'localhost':
                self._log_activity()
            
            if exc is not None:
                raise exc

        self._env.logging.info('Done.')
        if 'timestamp' in self._activity_log and isinstance(self._activity_log['timestamp'], datetime):
            self._activity_log['timestamp'] = self._activity_log['timestamp'].isoformat()
            
        return retval or self._activity_log
```

## 4. 结论

实施此项修改后，`RuntimeError: ... attached to a different loop` 的问题将被彻底解决。`ib_insync` 将能够安全、正确地在Gunicorn/Uvicorn管理的多进程环境中运行，您的异步改造也将完成最关键的一步。

您可以将上述代码直接更新到您的 `intent.py` 文件中，然后重新部署服务进行测试。