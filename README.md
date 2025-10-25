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

## 2. 核心设计原则 (截至 2025-10-25 的版本)

经过多轮的实盘调试与迭代，本系统当前遵循以下核心设计原则，这对于理解系统的行为至关重要：

### 2.1 策略意图 (Strategy Intent) 是决策的唯一核心

*   **职责**: 每个策略意图（如 `test_signal_generator`）都是一个独立的、自包含的交易决策单元。
*   **状态来源**: 为了确保决策的绝对准确性和及时性，策略意图在每次运行时，**必须直接查询盈透证券 (IB)** 获取最实时的状态，包括：
    1.  **真实持仓 (`ib.portfolio()`)**: 这是计算目标仓位的基础。
    2.  **在途订单 (`ib.openTrades()`)**: 用于防止在市场波动或并发执行时下达重复订单。
*   **执行**: 策略意图在完成所有计算和保证金检查后，直接执行下单操作 (`placeOrder`)。

### 2.2 `trade_reconciliation` 是事后审计工具

*   **职责**: `trade_reconciliation` 意图的功能是作为**事后账本**和**审计工具**。
*   **工作模式**: 它在交易发生后运行，获取真实的**成交记录 (Fills)**，并用这些记录去更新 Firestore `activity` 集合中对应订单的状态（例如，从 `Submitted` 更新为 `Filled`）。
*   **关键点**: 此意图**不参与**任何交易决策，也不应被任何交易决策逻辑所依赖。

### 2.3 Firestore 的定位

*   **`config` 集合**: 作为系统的静态配置中心，存储交易开关、风险参数等。
*   **`activity` 集合**: 作为所有交易行为的**事件日志 (Event Log)**。策略在下单时记录“意图”，`trade_reconciliation` 在成交后更新“结果”。
*   **`positions/holdings` 集合 (已废弃)**: 在当前的设计模式下，此集合**不应被用于交易决策**。试图在 Firestore 中维护一个实时的仓位副本被证明是复杂且有风险的。系统的“唯一真实持仓来源”是直接来自 IB 的 `portfolio` 数据。

### 2.4 已知风险与未来演进

*   **风险**: 当前“策略即意图”模式的一个已知风险是，**系统无法自动感知并响应在IB TWS或手机端等外部进行的手动仓位调整**。因为策略的决策起点是其自身的逻辑，如果外部操作改变了仓位，策略可能会在下一次运行时“纠正”这个变化，从而与交易员的意图相悖。
*   **演进方向**: 未来的一个可选演进方向是“**对账先行**”模式。即在每次决策前，强制先运行一个对账任务，将IB的真实仓位写入 Firestore，然后所有策略都基于这个 Firestore 的“快照”进行计算。这可以解决外部仓位变化的同步问题，但会增加系统的复杂性。当前版本为了保持简洁和稳定，暂未采用此模式。

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

*   **策略类意图**:
    *   `testsignalgenerator`: 一个高频策略范例。它会获取 SPY 的 30 分钟 K 线，计算 MACD 指标，并根据信号直接下达限价单。
    *   *您可以仿照它创建自己的策略意图。*
*   **管理类意图**:
    *   `summary`: 获取账户摘要，包括净值、持仓、未结订单等。
    *   `trade_reconciliation`: **（关键维护意图）** 用于核对系统在 Firestore 中的记录与券商的真实成交记录，并同步持仓状态。
    *   `close_all`: 平掉所有现有头寸并取消所有挂单。
    *   `cash_balancer`: 调整账户中的现金余额。

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

### 4.2 示例 1: 触发 `testsignalgenerator` 策略

这是一个 `POST` 请求，因为它会产生实际的交易行为。

```bash
curl -X POST -H "Authorization: Bearer ${TOKEN}" "${SERVICE_URL}/testsignalgenerator"
```

### 4.3 示例 2: 查看账户摘要

这是一个 `GET` 请求，用于查看账户的当前状态，包括由任何策略创建的未结订单和持仓。

```bash
curl -X GET -H "Authorization: Bearer ${TOKEN}" "${SERVICE_URL}/summary"
```

### 4.4 示例 3: 执行交易对账

在订单成交后，运行此意图来更新系统在 Firestore 中的持仓记录。

```bash
curl -X POST -H "Authorization: Bearer ${TOKEN}" "${SERVICE_URL}/trade-reconciliation"
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
*   **`positions/{trading_mode}/openOrders`**: **待办事项**。由策略意图在下单后创建，记录了所有已提交但未确认成交的订单。
*   **`positions/{trading_mode}/holdings`**: **官方持仓**。此处的记录**只应由 `trade_reconciliation` 意图在确认券商的成交回报后进行更新**。每个文档的 ID 是策略的 ID。
