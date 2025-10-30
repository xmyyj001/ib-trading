# “策略即意图”架构升级方案：引入“总指挥”模式

## 1. 概述

本文档旨在提出一个对现有“策略即意图”架构的升级方案。当前架构虽然实现了策略的模块化，但在多策略协调、全局风险管理和应对外部手动交易方面存在短板。

新方案将重新引入“总指挥”模式的核心思想，但以一种更现代化、更具扩展性的方式，构建一个**“信号生成”与“交易执行”相分离**的混合架构。

**核心目标:**

*   **集中执行**: 所有交易指令由唯一的“总指挥”意图（Commander）发出，便于统一管理风险和资金。
*   **分散决策**: 每个策略作为一个独立的“信号生成器”，只负责声明其理想的目标持仓，易于开发、测试和维护。
*   **状态清晰**: 利用 Firestore 作为“意图总线”，清晰记录每个策略的期望状态、系统的真实状态以及总指挥的决策过程，提高可追溯性和可调试性。
*   **兼容手动交易**: 通过定期的“对账”步骤，系统能够感知并适应在IB TWS等终端上的手动仓位调整。

---

## 2. 新架构设计

新架构包含三个核心组件：**策略意图 (Strategy Intent)**、**对账意图 (Reconciliation Intent)** 和 **总指挥意图 (Commander Intent)**。

### 2.1 工作流程

整个自动化交易流程被定义为三个清晰、串行的步骤，由单个计划任务触发一个编排函数（Cloud Function / Cloud Workflows 等）后顺序执行。由于多策略集中在中长期节奏，不存在日内高频触发需求，因此无需维护多个互相依赖的 Scheduler 作业。

**步骤 1: 策略计算 (并行)**
*   编排函数并行调用所有已启用的“策略意图”（如 `spy_macd_vixy`, `dummy_strategy` 等）。
*   每个策略连接 IB 获取所需市场数据，进行计算，并得出一个**理想的目标持仓** (Target Position)。
*   策略**不执行任何交易**，而是将其计算出的目标持仓写入各自在 Firestore 的专属文档中（例如 `strategies/{strategy_id}/intent/latest`）。
*   对于中长期策略，只要求每日（或其他低频窗口）更新一次该文档，Commander 在执行前仅需校验 `updated_at` 是否落在当前窗口即可。

**步骤 2: 真实状态对账**
*   编排函数调用 `reconcile` 意图。
*   `reconcile` 连接 IB，获取最真实的**当前持仓**和**在途订单 (Open Orders)**。
*   它将这些信息写入 Firestore 的一个全局状态文档中（例如 `positions/paper/latest_portfolio`）。这是整个系统执行决策的唯一“事实依据”。
*   运行频率与策略窗口一致即可（例如每日盘后一次），执行前不必额外加锁，只需确保完成时间早于 Commander 步骤。

**步骤 3: 总指挥决策与执行**
*   编排函数在对账完成后，调用 `allocation` (总指挥) 意图。
*   总指挥执行以下操作：
    1.  **读取真实状态**: 从 `positions/paper/latest_portfolio` 读取真实的持仓和在途订单。
    2.  **读取所有意图**: 遍历 `strategies` 集合，读取所有启用策略写入的“目标持仓”。
    3.  **综合与决策**:
        *   将所有策略的目标持仓聚合成一个“理想的最终组合”。
        *   应用全局风险规则、资金分配模型（例如，为每个策略分配的资金比例）。
        *   计算出从“真实状态”到“理想的最终组合”所需执行的具体交易订单（买/卖/调整）。
    4.  **执行交易**: 向 IB Gateway 发送所有计算出的交易订单。
    5.  **记录决策**: 将本次执行的完整上下文（读取的真实状态、各策略意图、最终决策、发出的订单）写入一个新的日志文档中（例如 `executions/{execution_id}`），用于审计和调试。

### 2.2 架构图

```mermaid
graph TD
    subgraph "Scheduled Orchestrator"
        Scheduler[每日调度任务] --> Orchestrator[Orchestrator Function]
        Orchestrator --> StrategyA[Strategy A: spy_macd_vixy]
        Orchestrator --> StrategyB[Strategy B: dummy]
        Orchestrator --> Reconcile[Reconcile Intent]
        Orchestrator --> Commander[Commander Intent]
    end

    subgraph "Firestore as Intent Bus"
        StrategyA -- "Write" --> IntentA[strategies/spy_macd_vixy/intent/latest]
        StrategyB -- "Write" --> IntentB[strategies/dummy/intent/latest]
        Reconcile -- "Write" --> PortfolioState[positions/paper/latest_portfolio]
        Commander -- "Read" --> IntentA
        Commander -- "Read" --> IntentB
        Commander -- "Read" --> PortfolioState
        Commander -- "Write Log" --> Executions[executions/{exec_id}]
    end

    subgraph "Interaction with Broker"
        StrategyA -- "Read Market Data" --> IB
        StrategyB -- "Read Market Data" --> IB
        Reconcile -- "Read Portfolio" --> IB
        Commander -- "Place Orders" --> IB[IB Gateway]
    end
```

---

## 3. Firestore 数据库设计

为了支撑新的混合架构，我们需要对 Firestore 的结构进行重新设计。

### 3.1 `strategies` 集合

此集合用于管理所有策略的配置和意图。

*   **路径**: `strategies/{strategy_id}`
*   **文档内容**:
    ```json
    {
      "name": "SPY MACD VIXY Strategy",
      "description": "基于SPY的MACD指标和VIXY作为对冲的波段策略",
      "enabled": true,
      "author": "system",
      "capital_allocation": 0.6, // 分配给此策略的资金占总投资组合的比例
      "risk_parameters": {
        "max_drawdown": 0.15,
        "max_single_position_exposure": 0.4
      }
    }
    ```
*   **子集合**: `strategies/{strategy_id}/intent`
    *   **路径**: `strategies/{strategy_id}/intent/latest`
    *   **文档内容 (由策略意图写入)**:
        ```json
        {
          "updated_at": "2025-10-29T16:10:00Z",
          "status": "success", // "success" or "error"
          "error_message": null,
          "metadata": {
            "signal_strength": 0.85,
            "indicators": {
              "macd_hist": 12.34,
              "vixy_level": 25.5
            }
          },
          "target_positions": [
            {
              "symbol": "SPY",
              "secType": "STK",
              "exchange": "SMART",
              "currency": "USD",
              "quantity": 100,
              "contract_details": { ... } // IBContract 对象详情
            },
            {
              "symbol": "VIXY",
              "secType": "STK",
              "exchange": "SMART",
              "currency": "USD",
              "quantity": -50, // 负数表示空头
              "contract_details": { ... }
            }
          ]
        }
        ```
    *   中长期策略只需在各自运行窗口内写入一次数据；Commander 通过 `updated_at` 与窗口起始时间比对，跳过陈旧或缺失的意图。

### 3.2 `positions` 集合

此集合用于存储从券商同步的真实账户状态。

*   **路径**: `positions/{trading_mode}/latest_portfolio` (例如 `positions/paper/latest_portfolio`)
*   **文档内容 (由 `reconcile` 意图写入)**:
    ```json
    {
      "updated_at": "2025-10-29T16:15:00Z",
      "net_liquidation": 150000.00,
      "available_funds": 80000.00,
      "holdings": [
        {
          "symbol": "SPY",
          "quantity": 80,
          "market_price": 450.00,
          "market_value": 36000.00,
          "contract": { ... }
        }
      ],
      "open_orders": [
        {
          "orderId": 123,
          "symbol": "AAPL",
          "action": "BUY",
          "totalQuantity": 50,
          "lmtPrice": 170.00,
          "order_details": { ... } // IBOrder 对象详情
        }
      ]
    }
    ```
*   该文档作为 Commander 的单一事实来源即可，无需维护版本历史；如需追踪变更，可在命令执行日志中留存引用指纹。

### 3.3 `executions` 集合

此集合作为总指挥决策的审计日志。

*   **路径**: `executions/{execution_id}` (文档ID可以是UUID或执行时间戳)
*   **文档内容 (由 `allocation` 总指挥意图写入)**:
    ```json
    {
      "executed_at": "2025-10-29T16:20:00Z",
      "trigger": "scheduled", // "scheduled" or "manual"
      "status": "completed", // "completed", "failed", "partial_success"
      "summary": "Placed 2 orders: BUY 20 SPY, SELL 50 VIXY.",
      "context": {
        "portfolio_snapshot_ref": "positions/paper/latest_portfolio@2025-10-29T16:15:00Z",
        "strategy_intents_refs": [
          "strategies/spy_macd_vixy/intent/latest@2025-10-29T16:10:00Z",
          "strategies/dummy/intent/latest@2025-10-29T16:11:00Z"
        ]
      },
      "decision": {
        "aggregated_target": [ ... ],
        "final_target": [ ... ],
        "diff": [ ... ]
      },
      "orders_placed": [
        {
          "orderId": 124,
          "symbol": "SPY",
          "action": "BUY",
          "totalQuantity": 20,
          "status": "Submitted"
        },
        {
          "orderId": 125,
          "symbol": "VIXY",
          "action": "SELL",
          "totalQuantity": 50,
          "status": "Submitted"
        }
      ]
    }
    ```
*   由于执行频率较低，可将详细上下文（如完整持仓快照、策略信号）写入 Cloud Logging 或 GCS 对象中，仅在文档内保留引用指纹，降低 Firestore 文档体积。

### 3.4 `config` 集合

`config` 集合保持不变，继续用于存储全局配置，如 `tradingEnabled` 开关。总指挥和所有策略意图在执行前都应检查此开关。

---

## 4. 实施建议

1.  **策略输出目标仓位**: 确保 `spy_macd_vixy`、`test_signal_generator` 等意图只负责计算目标持仓并写入 `strategies/{strategy_id}/intent/latest` 文档，不直接触发交易。
2.  **实现 `reconcile` 意图**: 创建或完善 `reconcile` 意图，使其能准确获取 IB 的持仓和在途订单，并写入 `positions/{trading_mode}/latest_portfolio`。
3.  **重构 `allocation` 意图**: 将 `allocation` 意图重构为“总指挥”，实现本文档第 2.1 节描述的决策逻辑。
4.  **调整计划任务**: 创建一个 Sponsor 级别的计划任务（Cloud Scheduler + Orchestrator Function / Workflows），在每日指定窗口触发三步流水线，内部顺序执行 `策略 -> 对账 -> 总指挥`。
5.  **增量迁移**: 可以先从一个策略开始迁移，验证整个流程跑通后，再逐步将更多策略加入到这个新架构中。

通过此方案，系统将获得一个既灵活又稳健的指挥体系，为未来扩展更复杂的策略组合和风控模型打下坚实的基础。

---

## 5. 推荐的分阶段验证流程

1. **本地 Dry-Run**  
   * 在启用虚拟环境并安装依赖后，运行 `python3 -m unittest`。  
   * 使用 `uvicorn main:app --reload` 启动服务，手动调用 `/orchestrator`，请求体设置 `{"strategies": ["testsignalgenerator", "spy_macd_vixy"], "dryRun": true, "runReconcile": false}`，确认 Firestore 写入逻辑不会触发真实下单。

2. **Sandbox / Staging 环境**  
   * 部署新的 Cloud Run 服务（例如 `trading-orchestrator-staging`），仅配置仿真账户凭据。  
   * 通过 Cloud Scheduler 或手动 `curl` 触发 `/orchestrator`，检查以下 Firestore 文档：
     - `strategies/<id>/intent/latest` 更新 `updated_at` 且无错误。
     - `positions/{mode}/latest_portfolio` 被 `/reconcile` 刷新。  
     - `executions/{execution_id}` 包含 `aggregated_target`、`diff` 等字段。

3. **审计与观察**  
   * 在 Cloud Logging 中确认 orchestrator、reconcile、allocation 三段日志均成功，且 Commander 未对 `missing_strategies`、`stale_strategies` 报警。  
   * 对比 staging 与 baseline (`testsignalgenerator`) 的输出，确保 Commander 汇总的 `diff` 与策略单独计算的 `proposed_delta` 一致。

4. **灰度生产**  
   * 为生产账号创建独立 Cloud Run 修订，先以 `dryRun=true` 执行 1-2 个交易日，验证审计文档与日志。  
   * 切换 Cloud Scheduler 至 orchestrator 端点，同时保留旧的 `testsignalgenerator` 调度作为回滚手段。  
   * 一旦 Commander 输出稳定，再逐步将其他策略迁移到新的意图模型，最后停用旧意图。
