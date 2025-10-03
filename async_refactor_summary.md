# [已废弃] 异步架构重构总结报告 (v1.0)

**<font color='red'>警告：本文档包含已废弃且不可行的架构方案。请勿用于实际开发。</font>**

**注意：本文档记录的为早期的、已被证明不可行的异步改造方案。其核心问题在于未能解决“事件循环冲突”和“循环依赖”导致的启动失败。最终的、正确的架构方案是“Sync-over-Async”模型，请参考 `async_safety_review.md`。**

**版本**: v1.0
**日期**: 2025-09-27

## 1. 为什么要采用异步架构？

### 1.1 问题的根源：同步的“服务员”与异步的“厨房”

在重构之前，我们的交易应用就像一个餐厅：

*   **Gunicorn/Uvicorn (餐厅经理)**: 负责接待客人（处理网络请求），本身是异步的，追求高效率。
*   **应用代码 (服务员)**: 负责接收点单，与后厨沟通，但其工作模式是**同步**的。
*   **IB Gateway (后厨)**: 负责实际的交易操作，这是一个需要花费时间（网络I/O）的地方。

当一个同步的“服务员”在一个异步的“餐厅”里工作时，会产生两个致命问题：

1.  **餐厅瘫痪 (阻塞)**: 当“服务员”向“后厨”下一个指令时（例如，请求账户数据），他会**站在原地死等**，直到数据返回。在此期间，他无法接待任何新客人或响应其他请求，导致整个餐厅（Cloud Run 实例）在高负载下显得毫无响应，甚至超时。

2.  **管理混乱 (事件循环冲突)**: “餐厅经理”（Uvicorn）希望“服务员”在发出指令后能立刻回来处理其他任务。但同步的“服务员”却被后厨卡住，不听从经理的调度。这种管理体系的冲突，最终导致了我们反复遇到的 `RuntimeError: ... attached to a different loop` 的程序崩溃。

### 1.2 解决方案：将“服务员”也升级为异步

我们最终采用的**彻底异步重构**，就是将我们的“服务员”（应用代码）也升级为现代、高效的异步模式。通过在整个调用链中使用 `async/await`，我们确保了：

*   **效率极大提升**: 在等待网络I/O的“空闲”时间里，CPU不再被阻塞，可以去处理成百上千个其他任务。
*   **冲突彻底解决**: 整个应用只有一个“餐厅经理”（Uvicorn的事件循环），所有任务都听从它的统一调度，从根源上消除了 `RuntimeError`。

---

## 2. 异步重构最终进展

**当前状态：已全部完成。**

我们已经成功地将项目的所有核心组件，从Web入口到与IB Gateway交互的底层，全部改造为完全异步的架构。代码库现在处于一个健壮、高效、且内部一致的状态，为最终部署做好了准备。

### 2.1 已完成的关键修改总结

1.  **`main.py` (入口)**
    *   **彻底移除 `util.patchAsyncio()`**: 消除了事件循环冲突的根源。
    *   **改造请求处理**: `_on_request` 方法现在会 `await intent_instance.run()`，将异步特性从入口点注入。

2.  **`lib/ibgw.py` (IB连接层)**
    *   **改造为 `async` 方法**: `start_and_connect` 和 `stop_and_terminate` 已被改造为 `start_and_connect_async` 和 `stop_and_terminate_async`。
    *   **使用 `await`**: 内部不再使用任何同步阻塞调用，全部改为 `await self.connectAsync(...)` 和 `await asyncio.sleep(...)`。

3.  **`lib/environment.py` (环境层)**
    *   **改造为 `async` 方法**: `get_account_values` 已被改造为 `get_account_values_async`，内部使用 `await self._env.ibgw.reqAccountValuesAsync(...)`。

4.  **`lib/trading.py` (交易执行层)**
    *   **实现异步带确认的下单**: `place_orders` 已被改造为 `place_orders_async`，它使用 `asyncio.gather` 并发下单，并通过一个 `_wait_for_order_status` 的辅助函数**等待**券商返回 `Submitted` 状态，彻底取代了不可靠的 `sleep`。
    *   **改造日志**: `_log_trades` 已被改造为 `_log_trades_async`。

5.  **`intents/intent.py` (逻辑基类)**
    *   **改造 `run` 和 `_core`**: 基类的核心执行方法 `run` 和 `_core` 都已变为 `async def`，强制所有子类都遵循异步模式。

6.  **所有意图子类 (Intents)**
    *   **`summary.py`**: `_core` 和所有获取数据的方法（`_get_positions` 等）都已改造为 `async`，并使用 `asyncio.gather` 并发获取数据。
    *   **`allocation.py`**: `_core` 方法已改造为 `async`，并正确地 `await` 所有异步调用。
    *   **`trade_reconciliation.py`**: 已完全改造为异步，并使用了正确的 `@async_transactional` 装饰器（从 `google.cloud.firestore_v1.async_transaction` 导入）来保证数据原子性操作。

---

## 3. 下一步

代码层面的重构和修复已全部完成。下一步是进行最终的生产部署。

---

# 最终复盘与总结 (v2.0 - 正确的、最终的架构)

## 1. 初始目标

我们的初始目标是将项目从一个基于同步请求的模式，升级为一个更高效、更健壮的异步模式，以解决潜在的性能瓶颈和状态管理风险。

## 2. 试错与迭代过程

我们的改造之路并非一帆风顺，主要经历了三个阶段的试错：

*   **第一阶段：初步异步化与“事件循环冲突”**
    *   **尝试**: 我们将 `main.py` 和 `intent.py` 等核心流程改造为 `async/await` 模式。
    *   **遇到的问题**: `RuntimeError: ... attached to a different loop`。
    *   **错误分析**: 我们共同诊断出，这是因为 `ib_insync` 库在 Gunicorn 的主进程中被初始化，而 API 请求在拥有不同事件循环的工作进程中处理，导致了冲突。
    *   **解决方案**: 我们决定采用 **ASGI Lifespan Protocol**，将 `ib_insync` 的初始化和连接操作，移到每个工作进程启动时、在正确的事件循环上执行。

*   **第二阶段：Lifespan实施与“循环依赖”**
    *   **尝试**: 我们着手实施 Lifespan 架构，一次性改造 `main.py`, `intent.py`, `trading.py` 等核心文件。
    *   **遇到的问题**: `ImportError: cannot import name 'Contract' from 'lib.trading'` 以及 `Worker failed to boot`。
    *   **错误分析**: 通过交互式排错，我们精确定位到这是一个典型的 Python 循环依赖问题。`strategies` 包为了实现策略逻辑而导入 `lib.trading`，而 `lib.trading` 为了整合策略的交易结果，又反向依赖于 `strategies` 包，在应用启动时形成了死锁。
    *   **解决方案**: 我们采用了“**延迟导入**” (Lazy/Local Import) 的标准实践。

*   **第三阶段：修复循环依赖的扩散性**
    *   **尝试**: 我们修复了 `strategies/strategy.py` 中的循环依赖。
    *   **遇到的问题**: `ImportError` 依然存在，但错误来源指向了 `strategies/dummy.py`。
    *   **错误分析**: 我们意识到循环依赖问题是**模式化**的，存在于**每一个**在顶层导入 `lib.trading` 的策略文件中。
    *   **最终解决方案**: 我们将“延迟导入”的修复模式，彻底应用到了 `strategies/dummy.py`, `strategies/spymacdvixy.py` 和 `lib/trading.py` 中，从两个方向完全斩断了依赖循环。

## 3. 最终达成的架构

**<font color='red'>警告：以下描述的架构已被证明是失败的。</font>**

**此架构（基于 ASGI Lifespan）在最终测试中被证明与 `ib_insync` 存在根本性的、无法解决的事件循环冲突。正确的、最终的架构是“Sync-over-Async”模型，详情请见 `async_safety_review.md`。**

经过上述迭代，我们最终达成了一个健壮、现代化的异步架构：

1.  **连接管理**: 由 `main.py` 中的 **ASGI Lifespan** 统一管理，实现了一个全局的、持久化的 IB Gateway 连接。
2.  **事件循环**: 通过在 `lifespan` 中执行 `patchAsyncio`，彻底解决了事件循环冲突问题。
3.  **循环依赖**: 通过在所有策略文件和 `trading.py` 中使用“延迟导入”，彻底解决了 `ImportError` 导致的启动失败问题。
4.  **业务逻辑**: `Intent` 层被简化为纯粹的业务处理器，不再关心连接细节。
5.  **核心操作**: 订单执行 (`trading.py`) 和状态更新 (`trade_reconciliation.py`) 都被改造为完全异步、非阻塞且包含状态确认和事务安全的核心模块。
