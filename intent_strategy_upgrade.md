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

整个自动化交易流程由 Cloud Scheduler (`orchestrator-daily-run`) 调用 Cloud Run 服务根路径 `POST /` 触发，FastAPI 会将该请求代理到 `orchestrator` 意图，并在单个 HTTP 调用里串行完成三段式流水线。由于多策略仍属中低频运行，一个 Scheduler 作业即可覆盖，无需额外的 Workflows/多作业编排。

**步骤 1: 策略计算 (串行触发)**
*   Orchestrator 读取 `strategies` 配置或显式 payload，依次运行 `STRATEGY_INTENT_REGISTRY` 内注册的意图（当前为 `spy_macd_vixy`、`testsignalgenerator`）。
*   每个策略拉取所需行情（IB、市价/指标）并只输出**目标仓位** (Target Position)；不会直接下单。
*   策略以 Firestore 文档 `strategies/{strategy_id}/intent/latest` 为唯一输出，写入 `status`、`metadata`、`target_positions`，Commander 通过 `updated_at` 判断是否在有效窗口内。

**步骤 2: 真实状态对账**
*   Orchestrator 可选地（默认 `runReconcile=true`）调用 `reconcile` 意图。
*   `reconcile` 连接 IB，获取真实**持仓**、**在途订单**、**账户指标**。
*   它将这些信息写入 `positions/{trading_mode}/latest_portfolio/snapshot`，并保留嵌入式 `positions/{trading_mode}` → `latest_portfolio` 以兼容遗留脚本；Commander 读取 snapshot 路径为事实来源。
*   运行频率与策略窗口一致即可（例如每日盘后一次），执行前无需加锁，只要在 Commander 前完成即可。

**步骤 3: 总指挥决策与执行**
*   编排函数在对账完成后，调用 `allocation` (总指挥) 意图。
*   总指挥执行以下操作：
    1.  **读取真实状态**: 首选 `positions/{mode}/latest_portfolio/snapshot`（若缺失则回退至嵌入式 `latest_portfolio`）。
    2.  **读取所有意图**: 遍历 `strategies` 集合，读取所有启用策略写入的“目标持仓”。
    3.  **综合与决策**:
        *   将所有策略的目标持仓聚合成“理想最终组合”，并记录贡献者列表。
        *   应用全局风险规则、预算拆分与 guardrail（如 `allowed_symbols`, `max_notional`, `exposure` 配额）。
        *   计算出从“真实状态”到“理想的最终组合”所需执行的具体交易订单（买/卖/调整）。
    4.  **执行交易**: 向 IB Gateway 发送所有计算出的交易订单。
    5.  **记录决策**: 将本次执行的完整上下文（读取的真实状态、各策略意图、最终决策、发出的订单）写入一个新的日志文档中（例如 `executions/{execution_id}`），用于审计和调试。

### 2.2 架构图

```mermaid
graph TD
    Scheduler[Cloud Scheduler<br/>orchestrator-daily-run] --> CloudRun[/Cloud Run Service<br/>POST / → Orchestrator/]
    CloudRun --> StrategyA[Strategy: spy_macd_vixy]
    CloudRun --> StrategyB[Strategy: testsignalgenerator]
    CloudRun --> Reconcile[Reconcile Intent]
    CloudRun --> Commander[Commander Intent]

    subgraph "Firestore Intent Bus"
        StrategyA -- "write target" --> IntentA[strategies/spy_macd_vixy/intent/latest]
        StrategyB -- "write target" --> IntentB[strategies/testsignalgenerator/intent/latest]
        Reconcile -- "write snapshot" --> PortfolioState[positions/{mode}/latest_portfolio/snapshot]
        Commander -- "read" --> IntentA
        Commander -- "read" --> IntentB
        Commander -- "read" --> PortfolioState
        Commander -- "write audit" --> Executions[executions/{exec_id}]
    end

    subgraph "IB Gateway"
        StrategyA -- "market data" --> IB[(IB)]
        StrategyB -- "market data" --> IB
        Reconcile -- "positions/orders" --> IB
        Commander -- "place orders" --> IB
    end
```

---

## 3. 运行时架构与意图清单

### 3.1 FastAPI + ib_insync 双线程模型

Cloud Run 容器内部署 FastAPI 主线程与 `ib_insync` 后台线程：主线程只负责 HTTP 接入与请求排队，后台线程维持与 IB Gateway 的持久连接并执行 Intent。

```mermaid
graph TD
    subgraph "Google Cloud Platform"
        CloudScheduler[Cloud Scheduler] -- "POST /" --> CR[Cloud Run Service]
        User[Operator] -- "curl /intent" --> CR
        CR -- "读写" --> Firestore[Firestore]
        CR -- "拉取凭证" --> SM[Secret Manager]
        CloudBuild[Cloud Build] --> AR[Artifact Registry]
        AR -- "镜像" --> CR
    end

    subgraph "Cloud Run 容器"
        CR --> MainThread[FastAPI 主线程]
        MainThread --> Queue[请求队列 (最大 4)]
        BGThread[ib_insync 后台线程] --> Queue
        BGThread --> IBGW[IB Gateway/TWS]
        BGThread --> Results[结果缓存]
        MainThread --> Results
    end

    subgraph "External"
        IBGW --> IB[Interactive Brokers Servers]
    end
```

- 主线程 60s 内轮询结果，超时则返回 503 并清理队列，防止僵尸请求。
- 后台线程具备指数退避重连与 `reqCurrentTimeAsync` 健康探针，日志中以 `IB Thread (Outer Loop)` / `Inner Loop` 区分状态。

### 3.2 意图一览

| Intent | 类型 | 作用 |
| --- | --- | --- |
| `orchestrator` / `POST /` | 编排 | 顺序执行策略 → `reconcile` → `allocation`，支持 `strategies`、`dryRun`、`freshMinutes`、`runReconcile` 参数。 |
| `testsignalgenerator` | 策略 | 发布 SPY 静态信号（30m MACD），仅写 Firestore 目标。 |
| `spy_macd_vixy` | 策略 | 发布 SPY/VIXY 对冲信号，遵循同一输出契约。 |
| `reconcile` | 对账 | 拉取持仓/在途订单，写 `positions/{mode}/latest_portfolio/snapshot`。 |
| `allocation` | Commander | 聚合策略目标、应用 guardrail，生成订单并写 `executions/{exec_id}`。 |
| `summary` | 运维 | 查看账户净值、持仓、未结订单。 |
| `close-all` | 运维 | 平掉所有仓位并取消挂单（慎用）。 |
| `cash_balancer`、`collect_market_data` | 辅助 | 现金调节、行情采集等任务。 |
| `trade_reconciliation` | Legacy | 仍在调试，暂不纳入 orchestrator 流水线。 |

新增策略需在 `cloud-run/application/app/intents/orchestrator.py` 的 `STRATEGY_INTENT_REGISTRY` 注册，同时使用 `scripts/firestore/setting_firestore.py` 写入曝光和 guardrail。


---

## 4. Firestore 数据库设计

为了支撑新的混合架构，我们需要对 Firestore 的结构进行重新设计。

### 4.1 `strategies` 集合

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
              "price": 450.12,
              "contract": { ... } // lib.ib_serialization.contract_to_dict 输出
            },
            {
              "symbol": "VIXY",
              "secType": "STK",
              "exchange": "SMART",
              "currency": "USD",
              "quantity": -50,
              "price": 17.45,
              "contract": { ... }
            }
          ]
        }
        ```
    *   中长期策略只需在各自运行窗口内写入一次数据；Commander 通过 `updated_at` 与窗口起始时间比对，跳过陈旧或缺失的意图。

### 4.2 `positions` 集合

此集合用于存储从券商同步的真实账户状态（含快照与兼容层）。

*   **路径**: `positions/{trading_mode}/latest_portfolio/snapshot`（例如 `positions/paper/latest_portfolio/snapshot`）。  
    `reconcile` 首选写入该文档，同时在 `positions/{trading_mode}` 根文档内以 `latest_portfolio` 字段形式保留同一份 payload，方便旧脚本在迁移期间继续读取。
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
          "avgCost": 440.50,
          "contract": { ... } // lib.ib_serialization.contract_to_dict 输出
        }
      ],
      "open_orders": [
        {
          "orderId": 123,
          "symbol": "AAPL",
          "action": "BUY",
          "totalQuantity": 50,
          "remainingQuantity": 50,
          "status": "Submitted",
          "order": { ... },   // lib.ib_serialization.order_to_dict 输出
          "contract": { ... }
        }
      ]
    }
    ```
*   Commander 先读取 snapshot 文档，如缺失则退回到嵌入式 `latest_portfolio`，并将引用指纹（`positions/{mode}/latest_portfolio/snapshot@timestamp`）记录在 `executions` 文档中。

### 4.3 `executions` 集合

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
        "portfolio_snapshot_ref": "positions/paper/latest_portfolio/snapshot@2025-10-29T16:15:00Z",
        "strategy_intents_refs": [
          "strategies/spy_macd_vixy/intent/latest@2025-10-29T16:10:00Z",
          "strategies/testsignalgenerator/intent/latest@2025-10-29T16:11:00Z"
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

### 4.4 `config` 集合

`config` 集合保持不变，继续用于存储全局配置，如 `tradingEnabled` 开关。总指挥和所有策略意图在执行前都应检查此开关。

### 4.5 Firestore 结构图

```mermaid
flowchart LR
    root[(Firestore)]

    subgraph strategies["strategies/{strategy_id}"]
        cfg["配置字段\nname/enabled/..."]
        intent["intent/latest\nstatus + metadata + target_positions"]
    end

    subgraph positions["positions/{trading_mode}"]
        snapshot["latest_portfolio/snapshot\nholdings + open_orders"]
        legacy["latest_portfolio (嵌入式)\n用于兼容旧逻辑"]
    end

    subgraph executions["executions/{execution_id}"]
        execSummary["summary/status/dry_run"]
        execCtx["context.strategy_intents_refs\n+ portfolio_snapshot_ref"]
        execOrders["decision.diff + orders"]
    end

    subgraph config["config/*"]
        cfgDocs["例如 tradingEnabled/exposure"]
    end

    root --> strategies
    root --> positions
    root --> executions
    root --> config
```

---

## 5. 多策略运行与对账分析

### 5.1 典型情景

- **双策略同向**：`testsignalgenerator` 与 `spy_macd_vixy` 同时看多 SPY 时，Commander 在 `aggregated_targets` 中合并贡献者（`contributors` 字段），生成一张合并买单，避免重复下单。
- **互相抵消**：一多一空时，同一合约的正负数量抵消，仅对剩余净暴露下单；若完全抵消，则不生成订单。不同合约互不影响。
- **策略缺失/陈旧**：`_collect_strategy_targets` 会将未更新的策略标记为 missing/stale，Commander 日志与 `executions` 文档会记录并忽略其目标，确保其他策略不受影响。
- **策略报错**：策略在 Firestore 写 `status="error"` 时，Commander 视为 stale，流水线继续执行，其余策略照常运行。
- **手动干预**：`reconcile` 捕获真实仓位后，Commander 下一个周期自动调整 delta，不需要额外手动同步。

### 5.2 审计顺序

1. **快照**：确认 `positions/{mode}/latest_portfolio/snapshot.updated_at` 在有效窗口；若缺失，说明对账未跑。
2. **目标与持仓**：对比 `strategies/<id>/intent/latest.target_positions` 与快照 holdings，推导 Commander `decision.diff`。
3. **执行文档**：查看 `executions/{exec_id}` 中的 `context.portfolio_snapshot_ref`、`strategy_intents_refs` 与 `orders`，可重现本次决策来源。
4. **日志**：Cloud Logging 中 `Planned X orders; simulated Y | missing=[] | stale=[]` 反映策略参与情况；若出现 missing/stale，回查对应 Firestore 文档。

该流程沿用旧版 README 的“多策略下的使用和结果分析方法”，适用于 dry-run 与实盘日常巡检。


---

## 6. 实施建议

1.  **策略输出目标仓位**: 确保 `spy_macd_vixy`、`test_signal_generator` 等意图只负责计算目标持仓并写入 `strategies/{strategy_id}/intent/latest` 文档，不直接触发交易。
2.  **实现 `reconcile` 意图**: 创建或完善 `reconcile` 意图，使其能准确获取 IB 的持仓和在途订单，并写入 `positions/{trading_mode}/latest_portfolio/snapshot`（同时 merge 到父文档的 `latest_portfolio` 字段以兼容旧逻辑）。
3.  **重构 `allocation` 意图**: 将 `allocation` 意图重构为“总指挥”，实现本文档第 2.1 节描述的决策逻辑。
4.  **调整计划任务**: 使用单个 Cloud Scheduler 作业（现名 `orchestrator-daily-run`），直接向 Cloud Run 服务发送 `POST /` 请求，payload 形如 `{"strategies": ["testsignalgenerator","spy_macd_vixy"], "dryRun": true, "runReconcile": true}`，由 FastAPI 内部顺序执行 `策略 -> 对账 -> 总指挥`。
5.  **增量迁移**: 可以先从一个策略开始迁移，验证整个流程跑通后，再逐步将更多策略加入到这个新架构中。

通过此方案，系统将获得一个既灵活又稳健的指挥体系，为未来扩展更复杂的策略组合和风控模型打下坚实的基础。

---

## 7. 推荐的分阶段验证流程

1. **本地 Dry-Run**  
   * 在启用虚拟环境并安装依赖后，运行 `python3 -m unittest`。  
   * 使用 `uvicorn main:app --reload` 启动服务，手动调用 `POST /`（或直接 `POST /orchestrator`），请求体设置 `{"strategies": ["testsignalgenerator", "spy_macd_vixy"], "dryRun": true, "runReconcile": false}`，确认 Firestore 写入逻辑不会触发真实下单。

2. **Sandbox / Staging 环境**  
   * 部署新的 Cloud Run 服务（例如 `trading-orchestrator-staging`），仅配置仿真账户凭据。  
   * 通过 Cloud Scheduler 或手动 `curl` 触发 `POST /`，检查以下 Firestore 文档：
     - `strategies/<id>/intent/latest` 更新 `updated_at` 且无错误。
     - `positions/{mode}/latest_portfolio/snapshot` 被 `/reconcile` 刷新（如需兼容旧脚本，可验证父文档的 `latest_portfolio` 字段同步更新）。  
     - `executions/{execution_id}` 包含 `aggregated_target`、`diff` 等字段。

3. **审计与观察**  
   * 在 Cloud Logging 中确认 orchestrator、reconcile、allocation 三段日志均成功，且 Commander 未对 `missing_strategies`、`stale_strategies` 报警。  
   * 对比 staging 与 baseline (`testsignalgenerator`) 的输出，确保 Commander 汇总的 `diff` 与策略单独计算的 `proposed_delta` 一致。

4. **灰度生产**  
   * 为生产账号创建独立 Cloud Run 修订，先以 `dryRun=true` 执行 1-2 个交易日，验证审计文档与日志。  
   * 切换 Cloud Scheduler 至 orchestrator 端点，同时保留旧的 `testsignalgenerator` 调度作为回滚手段。  
   * 一旦 Commander 输出稳定，再逐步将其他策略迁移到新的意图模型，最后停用旧意图。



### 7.1 Cloud Scheduler 触发器

- `orchestrator-daily-run`（us-central1）每日触发 Cloud Run 根路径 `/`，payload 默认 `{"strategies":["testsignalgenerator","spy_macd_vixy"],"dryRun":true,"runReconcile":true}`。
- 该作业一次性完成“策略 → 对账 → Commander”流水线，取代旧时代分别调用 `/testsignalgenerator`、`/reconcile`、`/allocation` 的多个 Scheduler。
- 切换至真实交易时，仅需将 payload 的 `dryRun` 改为 `false`。

### 7.2 组件结果识别

1. **策略意图**  
   - Cloud Run 日志出现 `Starting Robust, Target-Aware Signal Generator`、`Fetch 5D/30min...` 等 INFO 行。  
   - Firestore `strategies/<id>/intent/latest` 更新 `updated_at`、`status`、`target_positions`。  
   - `verify_trading.py --show-intents` 的 “Strategy Breakdown” 列出执行时间与目标。
2. **对账**  
   - 日志包含 `Starting portfolio reconciliation against IB Gateway...` 及 `ib_insync.wrapper:position` 输出。  
   - `positions/{mode}/latest_portfolio/snapshot` 被覆盖（父文档 `latest_portfolio` 同步更新）。
3. **Commander**  
   - 日志记录 `Planned X orders; simulated Y`、missing/stale 列表。  
   - Firestore `executions/{auto_id}` 写入 `decision.diff`、`orders`。  
   - `verify_trading.py` 的 “Commander” 段落展示 dry-run 结果与计划订单。

### 7.3 运维操作流程

1. 作业执行后，运行：
   ```bash
   gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="ib-paper"' \
     --project=gold-gearbox-424413-k1 --freshness=10m --limit=50 \
     --format="value(timestamp,textPayload)"
   ```
   确认策略 → 对账 → Commander 日志按顺序出现。
2. 在 Firestore Console 或 `query_firestore.py` 中查看 `strategies/<id>/intent/latest`、`positions/{mode}/latest_portfolio/snapshot`、`executions/*` 更新时间。
3. 如需人工复核策略输出与 Commander 决策，执行：
   ```bash
   python verify_trading.py --show-intents \
     --project-id gold-gearbox-424413-k1 \
     --strategies testsignalgenerator spy_macd_vixy
   ```

### 7.4 IB 就绪探针

FastAPI `GET /` 仅代表应用存活，无法判断 IB 后台线程是否连上网关。推荐使用 `/reconcile` 作为轻量探针：

```bash
curl -X POST "${ORCHESTRATOR_URL}/reconcile" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{"dryRun": true}'
```

- 若后台线程与 IB Gateway 已连通，会在几秒内返回 holdings/open_orders。  
- 若仍在重连或网关不可用，响应通常为 `{"error":"...Connection..."}`、`{"error":"Service is busy"}` 或 `{"error":"Request timed out"}`。  
- 只要该探针返回成功，即可安全触发 orchestrator，避免冷启动期间的误判。

---

## 8. 当前进展与待办（2025-11-09）

### 已完成（来自 `conversation_log.md` / `进展对照intent_strategy_upgrade.md`）
- `testsignalgenerator`、`spy_macd_vixy` 已完全迁移到“写 Firestore 目标仓位”的策略模型，Commander 只读 `positions/{mode}/latest_portfolio/snapshot` 做集中决策。
- FastAPI 根路由 `POST /` 已代理到 orchestrator，按“策略→对账→Commander”顺序执行，并在 503 时正确暴露 IB 重连状态；`GET /` 提供健康检查。
- Reconcile 意图升级为写 `latest_portfolio/snapshot`（并保留嵌入式字段），`lib/ib_serialization` 负责 contract/order 序列化，Commander/verify_trading 已适配新结构。
- 全量单测 (`python -m unittest discover -s _tests -t .`) 通过，`verify_trading.py --show-intents` 与 Cloud Run `curl POST /` dry-run 均验证策略成功、Commander missing/stale 为空。
- Guardrail 与预算脚本 `scripts/firestore/setting_firestore.py` 已写入 `allowed_symbols`、`max_notional` 等限制，Commander `_apply_guardrails` 在 Cloud Run dry-run 中确认能够裁剪超额目标。

### 待完成事项
1. **Cloud Run 部署 / Scheduler 切换**：重新部署含 guardrail/日志改动的镜像，并在运维批准后将 `orchestrator-daily-run` payload 由 `dryRun:true` 切为 `dryRun:false`，以恢复真实下单（见 `conversation_log.md` 11-9 “Next steps before going live”）。
2. **多策略迁移**：除上述两条策略外，其余生产策略仍在旧意图/脚本，需要依照第 4.1 节流程补齐 Firestore 配置、预算、guardrail，再加入 orchestrator（`进展对照intent_strategy_upgrade.md` 第 2 条）。
3. **Secret / 凭证治理**：审查并制定 `ib-*-username/password` Secret Manager 版本的轮换与失效检测，避免凭证过期造成 503（`进展对照intent_strategy_upgrade.md` 第 3 条）。
4. **监控 & 告警**：为 orchestrator 503、请求超时以及 IB 断线建立 Cloud Logging Metric 或 Error Reporting 告警链路，覆盖 Scheduler 成功率监测（`进展对照intent_strategy_upgrade.md` 第 5 条）。
5. **预算配置校准（进行中）**：已启动对 `config/common.exposure.strategies` 的重写，将按 33%/33%/34%（或运营确认的新版配额）落盘，并同步验证 Commander 输出/`verify_trading.py` 的 Strategy Exposure，防止任何单策略独占整体资金（参考 `conversation_log.md` 第 19 节备注）。

---
