# IB-Trading: 基于 Google Cloud Run 的算法交易系统

## 1. 项目概述

本项目是一个基于 Google Cloud Run 实现的、事件驱动的无服务器算法交易系统，旨在与盈透证券 (Interactive Brokers, IB) 进行自动化交易。

系统采用现代化的 **FastAPI** 框架和**后台线程架构**，将 Web 服务与 `ib_insync` 的异步事件循环完全解耦，确保了在高强度 I/O 操作下的稳定性和性能。每个交易策略都被设计成一个独立的、可通过标准 HTTP API 调用的**意图 (Intent)**。

**核心特性:**

*   **高性能异步架构**: 基于 FastAPI 和独立的 `asyncio` 后台线程，解决了 I/O 阻塞和事件循环冲突的根本问题。
*   **策略即意图**: 每个交易策略都是一个独立的、可通过专属 API 端点调用的微服务，实现了高度的模块化和可测试性。
*   **云原生集成**: 深度集成 Google Cloud 服务，包括 Artifact Registry (镜像存储), Cloud Build (CI/CD), Cloud Scheduler (定时任务), Secret Manager (凭据管理) 和 Firestore (配置与状态存储)。
*   **自动化**: 内置 IBC (Interactive Brokers Client) 实现 IB Gateway 的自动化登录和管理。
*   **无服务器**: 利用 Cloud Run 的弹性伸缩能力，按需执行，降低运维成本。

---

### 1.1 仓库结构速览

```
.
├── cloud-run/                 # Cloud Run 服务代码与容器镜像
│   ├── application/           # FastAPI 应用、Dockerfile 与 Cloud Build 配置
│   │   └── app/
│   │       ├── intents/       # Web API 意图（summary、trade_reconciliation、testsignalgenerator 等）
│   │       ├── strategies/    # 交易策略实现与实验代码
│   │       └── lib/           # 与 IB、GCP 交互的基础模块
│   └── base/                  # IB Gateway + IBC 的基础镜像与启动脚本
├── gke/                       # 早期 GKE 部署方案（YAML、脚本）
├── *.md / *.py                # 调试记录、方案文档、诊断脚本与集成测试工具
└── deployment_vars.sh         # 部署所需的环境变量模板
```

Cloud Run 版本目前是主线实现；`gke/` 目录保留历史方案与备用配置。根目录下的 Python 脚本（如 `verify_trading.py`, `connect_test.py`）用于本地验证连接、回放日志或手工排障。

---

## 1.2 本地开发环境准备

```bash
# 1. （可选）创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖（含 ib-insync 与 Google Cloud SDK 客户端）
pip install --upgrade pip
pip install -r cloud-run/application/app/requirements.txt

# 3. 运行测试
cd cloud-run/application/app
python3 -m unittest
```

> 如未配置 IB Gateway 或 GCP 凭据，部分测试会依赖 mock 并自动跳过；确保部署前在具备访问权限的环境验证完整流程。

---

## 2. 核心设计原则（2025-11 更新）

Cloud Run 上最新一轮部署已经把“策略直接下单”改造成“策略发布 → Commander 执行”的混合架构。以下原则概括了现在的运行方式：

### 2.1 策略意图生成目标，Commander 统一执行

* **职责拆分**：每个策略意图（如 `test_signal_generator`, `spy_macd_vixy`）仅负责读取 IB 数据、计算目标仓位，并写入 `strategies/{id}/intent/latest`。
* **状态来源**：策略仍直接从 IB Gateway 获取真实持仓 (`portfolio()`)、在途订单 (`openTrades()`)、净值等，以便生成精准的目标数量，避免重复下单。
* **执行链路**：`orchestrator` Intent 顺序执行“策略 → `reconcile` → `allocation`”，Commander 统一从 Firestore 读取意图与对账快照，应用 `allowed_symbols`/`max_notional` guardrail，再下发真实订单（或在 dry-run 中模拟）。

### 2.2 `reconcile` 是事实来源，`trade_reconciliation` 仍在调试

* `/reconcile` 会写入 `positions/{mode}/latest_portfolio/snapshot`，其中包含 `updated_at`、净值、持仓、未结订单，是 Commander 的唯一事实来源。
* `/trade-reconciliation` 继续保留历史持仓写入逻辑，但成交审计仍未恢复；生产场景请以 `/reconcile` 为准。

### 2.3 Firestore 承担“意图总线”角色

* `config/common`：存储整体曝光、策略权重、特性开关等。
* `strategies/{id}/intent/latest`：策略的最新目标文档，包含 `metadata`（信号、理由、最后价格等）。
* `positions/{mode}/latest_portfolio/snapshot`：`/reconcile` 写入的真实持仓与未结订单。
* `executions/{exec_id}`：Commander 的执行记录，串联引用了哪份持仓快照、哪些策略意图，以及规划/下发的订单。

### 2.4 风险与 guardrail

* **手动干预**：如果在 TWS/移动端手动下单，必须依靠下一次 `/reconcile` 同步之后 Commander 才能感知差异。
* **策略约束**：Commander 会读取 Firestore 中的 `allowed_symbols`、`max_notional`。不在白名单内的标的直接丢弃，超过金额阈值的目标被截断并在日志中记录。
* **凭证可用性**：Secret Manager 的 IB 凭证失效会导致 orchestrator 503；上线前需通过 `gcloud secrets versions access` 或一次 dry-run `/` 验证。

### 2.5 当前待办

* **多策略迁移**：把旧策略迁入新意图模型，补充 Firestore 权重及 guardrail 配置。
* **Secret & 凭证治理**：为 `ib-*-username/password` 制定轮换与监控策略。
* **监控告警**：基于 Cloud Logging / Error Reporting 对 orchestrator 503、IB 断线、意图缺失等关键信号建立告警。
* **Scheduler 正式化**：`orchestrator-daily-run` 已在 us-central1 干跑；确认 guardrail 后即可把 Scheduler payload 改为 `dryRun:false` 投入真实下单。

---

## 3. 应用程序设计：“策略即意图”

系统采用**主线程 + 后台工作线程**的模式，运行在单个 Cloud Run 容器实例中。

*   **主线程 (FastAPI)**: 负责接收外部 HTTP 请求，将其快速放入一个线程安全的任务队列中，并等待结果返回。
*   **后台线程 (ib_insync)**: 运行一个独立的 `asyncio` 事件循环，持续监听任务队列。一旦收到任务，它就负责执行所有与 IB Gateway 相关的异步 I/O 操作（如获取数据、下单等），并将结果存入一个共享的字典中，供主线程读取。

这种设计彻底隔离了 Web 服务器和 `ib_insync` 的事件循环，是确保系统稳定运行的关键。

### 架构图

```mermaid
graph TD
    subgraph "Google Cloud Platform"
        CloudScheduler[Cloud Scheduler] -- "触发 /testsignalgenerator" --> CR[Cloud Run Service]
        User[用户] -- "触发 /summary" --> CR
        CR -- "读/写" --> Firestore[Firestore (配置/状态)]
        CR -- "获取凭据" --> SM[Secret Manager]
        CloudBuild[Cloud Build] --> AR[Artifact Registry]
        AR -- "部署镜像" --> CR
    end

    subgraph "Cloud Run 容器内部"
        CR -- "HTTP 请求" --> MainThread[主线程: FastAPI]
        MainThread -- "任务入队" --> Queue[线程安全队列]
        BGThread[后台线程: ib_insync] -- "任务出队" --> Queue
        BGThread -- "交易/数据 (asyncio)" --> IBGW[IB Gateway]
        MainThread -- "等待并读取结果" --> Results[共享结果字典]
        BGThread -- "写入结果" --> Results
    end

    subgraph "外部交互"
        IBGW -- "TWS API" --> IB[Interactive Brokers Servers]
    end
```

---

## 3. 应用程序设计：“策略即意图”

在本系统中，每一个**策略 (Strategy)** 都被实现为一个独立的**意图 (Intent)**。这意味着每个策略都有自己的专属 API 端点，并负责其完整的业务逻辑，从获取数据到执行下单。

### 3.1 核心意图 (Intents)

**已部署 / 可调用**
*   `testsignalgenerator`: 获取 SPY 的 30 分钟 K 线，计算 MACD 指标，并将目标持仓写入 Firestore（不再直接下单）。
*   `spy_macd_vixy`: 经典 SPY/VIXY 组合策略，发布多空对冲的目标仓位。
*   `orchestrator`: 掌管“策略 → 对账 → 总指挥”三步流程的编排入口，可一次性驱动多个策略和 Commander。
*   `summary`: 获取账户摘要，包括净值、持仓、未结订单等。
*   `close_all`: 平掉所有现有头寸并取消所有挂单。
*   `cash_balancer`: 调整账户中的现金余额。

**运行中但待完善**
*   `trade_reconciliation`: 仍在调试，暂时只可靠地写入持仓快照，成交审计需待修复。

**计划中的意图**
*   更多策略意图：`spy_macd_vixy`、`dummy` 等仍在迁移，未来会加入 orchestrator 编排。
*   `risk-check` / `eod-check` 等风控意图：处于设计阶段，未来用于配合 Scheduler 场景执行。
*   历史策略文件（如 `spymacdvixy`, `dummy`）仍在本地开发，待完成意图化改造后部署。

### 3.2 如何添加新策略（意图）

开发新策略需遵循 `strategy_developing_frame.md` 中定义的规范。核心步骤如下：

1.  **创建文件**: 在 `cloud-run/application/app/strategies/` 目录下创建一个新文件（例如 `my_strategy.py`）。
2.  **继承 `Intent`**: 在文件中创建一个继承自 `intents.intent.Intent` 的类。
3.  **实现核心逻辑**: 实现 `__init__` 和 `async def _core_async(self)` 方法。所有与 IB 的交互都必须是异步的 (`await`)。
4.  **注册意图**: 在 `main.py` 的 `INTENTS` 字典中，将您选择的 URL 路径映射到您的新策略类。

---

## 4. API 用法与测试指南

### 4.1 获取服务 URL 和认证 Token

```bash
SERVICE_URL=$(gcloud run services describe ib-paper --region <your-region> --format="value(status.url)")
TOKEN=$(gcloud auth print-identity-token)
```

### 4.2 示例 1: 触发 `orchestrator` 编排

这是一个 `POST` 请求，编排过程依次执行所有策略意图、`/reconcile` 和 `/allocation`。

```bash
curl -X POST -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"strategies": ["testsignalgenerator", "spy_macd_vixy"], "dryRun": true}' \
  "${SERVICE_URL}/orchestrator"
```

> 调试单个策略仍可直接调用 `/testsignalgenerator`，但该端点只写入 Firestore 目标仓位，不会下单。

### 4.3 示例 2: 查看账户摘要

这是一个 `GET` 请求，用于查看账户的当前状态，包括由任何策略创建的未结订单和持仓。

```bash
curl -X GET -H "Authorization: Bearer ${TOKEN}" "${SERVICE_URL}/summary"
```

### 4.4 示例 3: 执行交易对账

在订单成交后，运行此意图来更新系统在 Firestore 中的持仓记录。

```bash
###curl -X POST -H "Authorization: Bearer ${TOKEN}" "${SERVICE_URL}/trade-reconciliation"

curl -X POST -H "Authorization: Bearer ${TOKEN}" \
 -H "Content-Type: application/json" \
 -d '{}' \
 "${SERVICE_URL}/trade-reconciliation"
```

### 4.5 多策略下的使用和结果分析方法：
• 交互情景

  - 两策都看多：testsignalgenerator 和 spy_macd_vixy 同时输出正向目标，Commander 在 intents/allocation.py:127-188 聚合后对同一合约的贡献做加    总（contributors 字段）。如果两者都指向 SPY，Commander 会用 sum(目标) 对照 positions/{mode}/latest_portfolio/snapshot 的持仓/在途订单求    差，生成一张合并买单，避免重复下单。
  - 一多一空：当 MACD 策略转空而测试策略仍看多，Commander 在 aggregated_targets 里把 SPY 的正负数量抵消，只下剩余差额的方向订单，或在完全抵
    消时不下单。若 spy_macd_vixy 还想做 VIXY，对 SPY 结果为 0，但 VIXY 部分仍会生成独立目标；不同合约互不干扰。
  - 策略缺失/陈旧：若某策略未写意图或 updated_at 超过 freshMinutes，在 _collect_strategy_targets 中被加入 missing_strategies 或
    stale_strategies，Commander 会在执行日志和 Cloud Run 日志中标注，并完全忽略它的目标，防止过期指令影响其他策略。
  - 单策略报错：比如 testsignalgenerator 无法拿到历史数据，它会写 status: "error"，Commander同样把它视作 stale，并继续处理其余策略。
    strategies/{id}/intent/latest 里保留错误信息供诊断。
  - Reconcile 发现真实仓位偏差：若手动交易或 IB 误差导致真实持仓与目标差距大，对账后的 positions/{mode}/latest_portfolio/snapshot 记录会显示
    异常数量。Commander 计算 delta 时自动包含该偏差，下一次 orchestrator 就会下反向单把组合拉回策略合意位置，不会因为某策略临时调整而影响另
    一策略的目标输入。

  每日对账分析

  - cloud-run/application/app/intents/reconcile.py 写入的数据包括 updated_at, net_liquidation, available_funds, holdings[], open_orders[]。    用 verify_trading.py 或后台控制台查看这个快照即可掌握真实仓位；holdings 里的 contract 序列化细节让 Commander 能准确识别合约，open_orders     反映在途指令。
  - 每次 orchestrator 后 Commander 会生成一条 executions/{exec_id} 记录（intents/allocation.py:188-239），context.portfolio_snapshot_ref 指     向这次决策所依赖的对账文档，便于审计“某天的仓位/现金 → Commander 的 diff → 下单结果”。
  - 分析顺序建议：
      1. 查看 positions/{mode}/latest_portfolio/snapshot 的 updated_at 是否在预期窗口内；若落后，说明对账未跑或失败。
      2. 对照 holdings 与各策略 intent/latest.target_positions，可以判断 Commander 是否需要动作（target - holdings - open_orders 的结果就是   Commander decision.diff 里的 delta）。
      3. 若 Commander 日志出现 missing / stale，根据 strategy_intents_refs 里的时间戳回查对应策略意图文档中的 status 和 error_message，确定   是参数、数据源或环境问题。
      4. 监控 net_liquidation / available_funds 对策略预算的影响；策略逻辑里通常用 config.exposure（在 env.config）决定部署资本，若资金大幅
         波动、目标数量也会等比例调整。

---

## 5. 部署流程

项目的部署通过 Google Cloud Build 自动化完成。任何推送到主分支的提交都会触发 `cloudbuild.yaml` 中定义的 CI/CD 流程，自动构建镜像并将其部署到 Cloud Run。

---

## 6. Firestore 数据库结构

Firestore 用于存储应用的配置和交易状态。

```mermaid
graph TD
    Firestore --> ConfigCollection[Collection: config];
    Firestore --> PositionsCollection[Collection: positions];

    ConfigCollection --> ConfigDocs[Docs: common, paper, live];
    
    PositionsCollection --> TradingModeDoc[Doc: {trading_mode}];
    TradingModeDoc --> OpenOrdersCollection[Sub-collection: openOrders];
    TradingModeDoc --> HoldingsCollection[Sub-collection: holdings];

    HoldingsCollection --> StrategyDoc[Doc: {strategy_id}];
```

*   **`config` 集合**: 存储应用的通用配置和分环境配置。
*   **`positions/{trading_mode}/openOrders`**: 尚未上线。当前代码不会写入该集合，后续如需启用需要补充相应的意图逻辑。
*   **`positions/{trading_mode}/holdings`**: 存储每个策略的历史持仓快照。`Strategy` 基类、`close_all` 与 `reconcile` 会读取它来辅助计算目标仓位；`trade_reconciliation` 目前仅维护 `holdings/all_positions` 总表。
