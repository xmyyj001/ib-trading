# 风险管理架构（RiskManager）设计与实施方案

**目标读者**：不熟悉量化交易业务，但具备基础 IT 知识的开发与运维人员。

**核心目标**：在不改变现有“后台线程”异步模式的前提下，引入一个集中式的风险管理服务，以实现对所有独立交易策略的统一资金分配和持仓控制。

---

## 第一部分：最初的“总指挥”架构回顾与评价

在项目初期，我们采用了一种非常经典和直观的架构模式，可以称之为**“总指挥模式”**。这个模式的核心是 `allocation` 这个意图（Intent）。

### 1.1 “总指挥” allocation 的工作流程

让我们用一个餐厅的厨房来比喻这个模式：

*   **`allocation` 意图**：是厨房的**行政总厨**。他不亲自炒菜，但他决定今晚要做哪些菜，以及每道菜用多少预算。
*   **策略 (如 `spymacdvixy`)**：是负责研发菜谱的**菜品研发员**。他们只负责提供“菜谱”（交易信号），比如“今天适合多放点辣”（看涨信号，权重 `1.0`）或者“今天应该清淡点”（看跌信号，权重 `-0.5`）。他们不关心这道菜具体要炒多少份，也不关心后厨的采购成本。
*   **HTTP 请求**: 是来自前厅的**订单**。订单上写着：“尊敬的总厨，请用今晚的预算，做一份‘辣子鸡丁’（`spymacdvixy`）和一份‘清炒时蔬’（`dummy`）。”

**工作流程如下**：

1.  “总厨”(`allocation`) 接到订单，看到需要做 `spymacdvixy` 和 `dummy` 两道菜。
2.  他去问 `spymacdvixy` 的研发员：“今天的菜谱是什么？” 研发员回答：“多放辣（权重 `1.0`）。”
3.  他又去问 `dummy` 的研发员，得到另一份菜谱。
4.  “总厨”拿到所有菜谱后，拿出厨房的总预算（账户净值 `netLiquidation`），根据每道菜的权重，计算出具体要用多少钱来买原材料（`exposure * weight`），然后根据原材料市价（`price`），计算出要买多少斤（`quantity`）。
5.  最后，“总厨”把采购清单交给采购员（`place_order` 方法），完成下单。

### 1.2 对“总指挥”模式的评价

这种模式对于初创项目来说，非常清晰易懂。

*   **优点：集中控制**
    *   **资金管理**: 所有的资金分配都由“总厨”一人负责，绝对不会超预算。全局风险控制非常容易。
    *   **策略简单**: “菜品研发员”非常省心，只需要专注于味道（信号强弱），不需要考虑成本和库存，开发新“菜谱”很快。

*   **缺点：僵化与瓶颈**
    *   **总厨是瓶颈**: 随着餐厅菜品越来越多，“总厨”需要了解的菜谱也越来越多，他的工作变得异常复杂。如果某道菜需要一种特殊的烹饪技巧（例如，不是炒，而是低温慢煮），“总厨”就必须亲自去学，他的能力决定了整个厨房的上限。
        *   **对应到代码**: 如果一个新策略需要特殊的订单类型（如期权组合单）或下单逻辑，“总厨” `allocation` 就必须被修改，变得越来越臃g肿和难以维护。
    *   **沟通模糊**: “菜谱”里的“多放点辣”是一个很模糊的概念。到底放多少？“总厨”只能根据自己的理解（`exposure * weight / price`）去转换。当厨房预算很少，或者辣椒很贵时，他计算出的辣椒用量可能是 `0.01` 克，取整后就变成了 `0`，导致菜里最终没有放辣。
        *   **对应到代码**: 这正是我们遇到的 `int(0.xx)` 问题。策略提供的抽象 `weight` 无法保证在所有资金和价格下都能转换成有效的交易数量。

**结论**：“总指挥”模式在系统规模扩大、策略复杂度增加后，其**灵活性不足和沟通模糊**的缺点会成为严重的瓶颈。因此，我们需要一种新的、更能适应变化的架构。

---

## 第二部分：RiskManager - “去中心化”的风险管理架构

为了解决“总指挥”模式的瓶颈，我们演进到了**“策略即意图”**的新模式。在这个模式下，每个策略都是一位能独立开单的“厨师”，拥有自己的“灶台”（API 端点）。

但这立刻带来了新问题：如果没有了“总厨”，谁来确保厨房不会超预算？谁来保证冰箱里的食材不会被某一个厨师全部用光？

`RiskManager` 架构应运而生。它不再是一个发号施令的“总厨”，而是厨房里一个提供共享服务的**“中央服务台”**。

### 2.1 “中央服务台” RiskManager 的设计思想

“中央服务台”不决定你要做什么菜，但它提供你做菜所需的所有**公共信息和最终审批**。

*   **`RiskManager`**: 厨房的“中央服务台”。
*   **策略意图 (如 `test_signal_generator`)**: 拥有决策权的“厨师”。

**新的工作流程如下**：

1.  “厨师”(`test_signal_generator`) 决定今天要做一道“辣子鸡丁”。
2.  他走到“中央服务台”(`RiskManager`)，查询两个信息：
    *   **“今天我的预算是多少？”** (`get_available_capital_for_strategy`)
    *   **“冰箱里还有没有位置放我的新菜？”** (`can_place_trade` 的持仓检查)
3.  “中央服务台”根据厨房的整体运营情况（总预算、所有厨师的权重、冰箱容量等）告诉他：“你有 50 元预算，冰箱也还有空位。”
4.  “厨师”拿到这些信息后，自己计算具体要买多少斤鸡肉和辣椒（计算 `quantity`），并自己填写采购单（创建 `Order`）。
5.  在把采购单发出去之前，他最后一次来到“中央服务台”，让其盖一个**“批准”**的印章 (`can_place_trade` 的最终检查)。
6.  盖章通过后，“厨师”亲自将采购单交给采购员，完成下单。

### 2.2 RiskManager 的详细实现

这个“中央服务台”将作为一个新的 `RiskManager` 类，被集成到我们现有的“后台线程”架构中，完全兼容，无需改变架构本身。

#### 步骤 1: 创建 `lib/risk_manager.py`

我们将创建一个 `RiskManager` 类。它在初始化时接收 `env` 对象，从而获得了访问数据库 (`db`) 和 IB Gateway (`ibgw`) 的能力。

```python
# /home/app/lib/risk_manager.py
import asyncio
from ib_insync import Contract
from lib.environment import Environment

class RiskManager:
    def __init__(self, env: Environment):
        self._env = env

    async def get_available_capital_for_strategy(self, strategy_id: str) -> float:
        """
        计算并返回该策略【真正可用】的资金额度。
        可用资金 = 理论总额度 - 已有持仓的总市值 - 所有未成交挂单的名义价值
        """
        try:
            # 1. 获取理论总额度
            account_summary = await self._env.ibgw.reqAccountSummaryAsync()
            net_liquidation = float(next((v.value for v in account_summary if v.tag == 'NetLiquidation'), 0))
            overall_exposure_pct = self._env.config['exposure']['overall']
            strategy_weight_pct = self._env.config['exposure']['strategies'].get(strategy_id, 0)
            total_allocated_capital = net_liquidation * overall_exposure_pct * strategy_weight_pct

            # 2. 获取该策略的已有持仓市值
            current_holdings_value = await self._get_strategy_holdings_value(strategy_id)

            # 3. 获取该策略的在途挂单名义价值
            pending_exposure = await self._get_pending_exposure()
            pending_value = pending_exposure.get(strategy_id, 0.0)

            # 4. 计算最终可用的净额度
            available_capital = total_allocated_capital - current_holdings_value - pending_value
            
            self._env.logging.info(
                f"Capital for {strategy_id}: TotalAllocated={total_allocated_capital:.2f}, "
                f"CurrentHoldings={current_holdings_value:.2f}, PendingOrders={pending_value:.2f} "
                f"-> NetAvailable={max(0, available_capital):.2f}"
            )
            return max(0, available_capital)
        except Exception as e:
            self._env.logging.error(f"Error calculating capital for {strategy_id}: {e}")
            return 0.0

    async def can_place_trade(self, proposed_trade) -> (bool, str):
        """
        在下单前的最后一道关卡，进行所有全局规则的检查。
        """
        # 规则 1: 检查全局交易开关
        if not self._env.config.get('tradingEnabled', False):
            return (False, "Global trading is disabled.")

        # 规则 2: 检查是否会超过最大持仓数量
        try:
            holdings_ref = self._env.db.collection(f'positions/{self._env.trading_mode}/holdings')
            all_strategy_docs = [doc async for doc in holdings_ref.stream()]
            current_total_positions = sum(len(doc.to_dict()) for doc in all_strategy_docs)
            max_positions = self._env.config.get('max_positions', 10)

            if current_total_positions >= max_positions:
                return (False, f"Trade would exceed maximum position limit of {max_positions}.")
        except Exception as e:
            self._env.logging.error(f"Error checking position limits: {e}")
            return (False, "Failed to verify position limits.")

        return (True, "All risk checks passed.")

    async def _get_strategy_holdings_value(self, strategy_id: str) -> float:
        """
        计算指定策略当前持仓的总市值。
        """
        holdings_doc_ref = self._env.db.collection(f'positions/{self._env.trading_mode}/holdings').document(strategy_id)
        holdings_doc = await holdings_doc_ref.get()
        if not holdings_doc.exists: return 0.0

        total_value = 0.0
        holdings = holdings_doc.to_dict()
        contracts_to_fetch = [Contract(conId=int(conId_str)) for conId_str in holdings.keys()]
        if not contracts_to_fetch: return 0.0

        tickers = await self._env.ibgw.reqTickersAsync(*contracts_to_fetch)
        for ticker in tickers:
            if ticker and ticker.marketPrice():
                conId = ticker.contract.conId
                quantity = holdings.get(str(conId), 0)
                total_value += abs(quantity) * ticker.marketPrice()
        return total_value

    async def _get_pending_exposure(self) -> dict:
        """
        计算所有策略当前未成交挂单的名义风险敞口。
        """
        pending_exposure = {}
        open_orders_ref = self._env.db.collection(f'positions/{self._env.trading_mode}/openOrders')
        async for order_doc in open_orders_ref.stream():
            order_data = order_doc.to_dict()
            for strategy_id, quantity in order_data.get('source', {}).items():
                # 简化处理：使用一个估算的价格，实际中可做得更精确
                price = order_data.get('lmtPrice', 1.0) 
                nominal_value = abs(quantity) * price
                pending_exposure[strategy_id] = pending_exposure.get(strategy_id, 0) + nominal_value
        return pending_exposure
```

#### 步骤 2: 在 `Environment` 中集成

就像 `db` 和 `ibgw` 一样，我们将 `RiskManager` 变成 `Environment` 的一个标准组件。

```python
# /home/app/lib/environment.py
from lib.risk_manager import RiskManager # 1. 导入

class Environment:
    def __init__(self, ...):
        # ...
        self.risk_manager = RiskManager(self) # 2. 实例化
```

#### 步骤 3: 在策略意图中调用

所有下单的意图（如 `test_signal_generator`, `close_all`）都必须遵循“先申请/检查，后执行”的原则。

```python
# 在 test_signal_generator.py 的 _core_async 方法中

# ... (信号生成之后) ...

# 1. 向服务台“申请”资金额度
allocated_capital = await self._env.risk_manager.get_available_capital_for_strategy(self.id)

# 2. 策略自己计算具体数量
if last_price > 0:
    calculated_quantity = allocated_capital * weight / price
    # 自己的逻辑，确保至少交易1股
    target_quantity = int(calculated_quantity) or (1 if calculated_quantity > 0 else -1)
else:
    target_quantity = 0

self.trades = { spy_instrument.contract.conId: target_quantity }
# ...

# 3. 在下单前，让服务台“盖章”批准
trade_obj = Trade(self._env, [self])
trade_obj.consolidate_trades_from_quantity() # 使用我们新的、更简单的方法

can_trade, reason = await self._env.risk_manager.can_place_trade(trade_obj)
if not can_trade:
    self._env.logging.warning(f"Trade blocked by Risk Manager: {reason}")
    return {"status": "Trade blocked", "reason": reason}

# 4. 盖章后，才允许执行下单
if not self._dry_run:
    orders = await trade_obj.place_orders_async(...)
    # ...
```

### 2.3 新架构的优势总结

这个“中央服务台”架构，完美地结合了两种模式的优点：

1.  **保留了灵活性**: 每个“厨师”（策略）都可以自由地决定自己的“菜谱”（交易逻辑），并使用特殊的“烹饪技巧”（订单类型）。
2.  **实现了集中控制**: 所有的“厨师”都必须向同一个“中央服务台”申请预算和接受检查，确保了整个“厨房”的运营（资金和持仓）处于可控范围内。
3.  **高度可扩展**: 当一个新的“厨师”加入时，他只需要学会如何与“中央服务台”打交道即可，而不需要去修改服务台的内部构造。同样，如果厨房要增加一条新的规定（例如“晚上10点后不许用明火”），只需要在服务台的检查流程里加一条规则即可，所有厨师都会自动遵守。

这个方案在不改变我们成功的“后台线程”模式的基础上，为项目的长期发展和多人协作提供了清晰、健壮、可扩展的风险管理框架。

### 2.4 现有各类意图的整合与改进

`RiskManager` 作为一个中心化的服务，必须能够理解并服务于项目中所有可能改变风险状况的意图。以下是针对现有各类意图的整合分析与改进建议。

#### A. 信息获取类 (只读)

*   **涉及意图**: `summary`, `collect_market_data`
*   **分析**: 这些意图只读取数据，不产生交易，风险为零。
*   **整合建议**: **无需整合**。`RiskManager` 反过来会依赖 `summary` 提供的数据（如账户净值）来做决策。

#### B. 状态维护类 (数据库操作，不下单)

*   **涉及意图**: `trade_reconciliation`, `reconcile`
*   **分析**: 
    *   `trade_reconciliation`: 负责将已成交的订单记入 `holdings`，是确保 `RiskManager` 数据准确性的**关键依赖**。
    *   `reconcile`: 是一个强力的手动同步工具，直接用券商数据覆盖 `holdings`。
*   **整合建议**: **无需整合**。这些意图是 `RiskManager` 做出正确判断的**数据基础**。我们必须保证它们在交易时段后被可靠地执行，以确保 `RiskManager` 在下一个交易时段开始前能拿到最准确的持仓数据。

#### C. 交易执行类 (下单)

这是 `RiskManager` 发挥核心作用的地方。所有这类意图在执行下单前，都必须调用 `RiskManager` 的检查方法。

*   **`test_signal_generator` (策略意图)**
    *   **当前逻辑**: 根据市场信号计算目标数量，并创建限价单。
    *   **改进建议**: 严格遵循 **“申请资金 -> 计算数量 -> 请求审批 -> 执行下单”** 的流程。
        1.  在计算 `target_quantity` 之前，先调用 `await self._env.risk_manager.get_available_capital_for_strategy(self.id)` 获取资金额度。
        2.  在调用 `place_orders_async` 之前，必须调用 `can_trade, reason = await self._env.risk_manager.can_place_trade(trade_obj)`，并检查返回结果。

*   **`close_all` (清仓意图)**
    *   **当前逻辑**: 获取所有持仓，然后为每一笔持仓创建一个反向的市价单来清空。
    *   **风险**: 这是一个高风险操作。如果被意外触发（例如，在市场暴跌时），可能会导致在最差的时机卖出所有资产。
    *   **改进建议**: 在下单循环之前，增加一道专门的审批程序。
        1.  在 `RiskManager` 中创建一个专门的方法，例如 `async def can_liquidate_portfolio(self) -> (bool, str):`。
        2.  这个方法可以实现特定的逻辑，比如：“如果VIX指数高于40，则不允许自动清仓”，或者“只允许在特定时间窗口内执行清仓”。
        3.  在 `close_all.py` 的 `placeOrderAsync` 循环前，调用 `can_liquidate, reason = await self._env.risk_manager.can_liquidate_portfolio()` 并进行检查。

*   **`cash_balancer` (现金平衡意图)**
    *   **当前逻辑**: 计算非基础货币的现金余额，如果超过阈值，则通过 `FXCONV` 下市价单进行兑换。
    *   **风险**: 外汇市场波动可能很大，无限制的市价单可能会导致在不利的汇率下成交。此外，频繁的现金兑换也可能违反某些账户规定。
    *   **改进建议**: 将其纳入 `RiskManager` 的通用交易审批流程。
        1.  `can_place_trade` 方法需要被扩展，使其能够理解并评估外汇交易的风险。它可以检查交易的规模是否过大，或者当日的货币兑换次数是否超限。
        2.  在 `cash_balancer.py` 的 `placeOrderAsync` 循环前，为即将发生的外汇交易构建一个简化的 `trade_obj`，并调用 `can_trade, reason = await self._env.risk_manager.can_place_trade(trade_obj)`。
