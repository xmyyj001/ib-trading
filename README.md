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

## 2. 核心设计原则 (截至 2025-10-25 的版本)

经过多轮的实盘调试与迭代，本系统当前遵循以下核心设计原则，这对于理解系统的行为至关重要：

### 2.1 策略意图 (Strategy Intent) 是决策的唯一核心

*   **职责**: 每个策略意图（如 `test_signal_generator`）都是一个独立的、自包含的交易决策单元。
*   **状态来源**: 为了确保决策的绝对准确性和及时性，策略意图在每次运行时，**必须直接查询盈透证券 (IB)** 获取最实时的状态，包括：
    1.  **真实持仓 (`ib.portfolio()`)**: 这是计算目标仓位的基础。
    2.  **在途订单 (`ib.openTrades()`)**: 用于防止在市场波动或并发执行时下达重复订单。
*   **执行**: 策略意图在完成所有计算和保证金检查后，直接执行下单操作 (`placeOrder`)。

### 2.2 `trade_reconciliation` 仍在完善中

*   **现状**: 当前代码仅实现了**实时持仓快照**写入 Firestore (`positions/{mode}/holdings/all_positions`)。对成交记录的审计流程还在调试阶段，尚未稳定。
*   **风险提示**: 在 Google Cloud Run 中运行该意图时，会因为 Firestore 异步 API 的兼容性问题抛出异常；因此暂不建议在生产环境中依赖它更新订单状态。
*   **后续规划**: 完成异步 Firestore 客户端的接入后，再恢复对 `activity` 集合的更新与审计。

### 2.3 Firestore 的定位

*   **`config` 集合**: 作为系统的静态配置中心，存储交易开关、风险参数等。
*   **`activity` 集合**: 作为所有交易行为的**事件日志 (Event Log)**。目前只有部分意图（例如 `test_signal_generator`）会写入订单信息；审计流程仍在回归测试中。
*   **`positions/holdings` 集合**: 依然被 `Strategy`、`CloseAll` 等逻辑读取，以便计算虚拟持仓与针对性平仓。虽然真实持仓以 IB 为准，但 Firestore 持仓文档仍扮演辅助角色，属于历史设计遗留，更新策略需谨慎。

### 2.4 已知风险与未来演进

*   **风险**: 当前“策略即意图”模式的一个已知风险是，**系统无法自动感知并响应在IB TWS或手机端等外部进行的手动仓位调整**。因为策略的决策起点是其自身的逻辑，如果外部操作改变了仓位，策略可能会在下一次运行时“纠正”这个变化，从而与交易员的意图相悖。
*   **演进方向**: 未来的一个可选演进方向是“**对账先行**”模式。即在每次决策前，强制先运行一个对账任务，将IB的真实仓位写入 Firestore，然后所有策略都基于这个 Firestore 的“快照”进行计算。这可以解决外部仓位变化的同步问题，但会增加系统的复杂性。当前版本为了保持简洁和稳定，暂未采用此模式。

### 2.5 待办修订计划

*   **恢复 `trade_reconciliation` 审计**: 引入异步 Firestore 客户端或改造当前逻辑，确保在 Cloud Run 中可以安全更新 `activity` 集合。
*   **整理 Firestore `holdings` 使用方式**: 评估哪些策略仍需引用仓位快照，决定是继续维护文档还是迁移到纯 IB 数据流。
*   **重新启用 `allocation` 架构**: 在完成异步重构与依赖清理后，再次验证“总指挥”模式，并补全缺失的 API 端点。
*   **策略扩展**: 将 `spy_macd_vixy` 等策略升级到“策略即意图”范式，补齐端到端测试后再部署。

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
