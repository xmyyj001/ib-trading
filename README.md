IB-Trading: 基于 Google Cloud Run 的算法交易系统

## 1. 项目概述

本项目是一个基于 Google Cloud Run 实现的无服务器算法交易系统，旨在与盈透证券 (Interactive Brokers, IB) 进行自动化、事件驱动的交易。系统利用容器化技术，通过标准的 HTTP API 接收交易指令（“意图”），并根据可插拔的交易策略（“策略”）执行这些指令。

**核心特性:**

*   **无服务器架构**: 利用 Cloud Run 的弹性伸缩能力，按需执行，降低运维成本。
*   **意图驱动**: 通过简单的 HTTP 请求（如 `/allocation`, `/summary`）触发复杂的交易逻辑。
*   **动态策略加载**: 可以轻松添加新的交易策略，无需修改核心代码，系统会自动发现并注册它们。
*   **云原生集成**: 深度集成 Google Cloud 服务，包括 Artifact Registry (镜像存储), Cloud Build (CI/CD), Secret Manager (凭据管理) 和 Firestore (配置与状态存储)。
*   **自动化**: 内置 IBC (Interactive Brokers Client) 实现 IB Gateway 的自动化登录和管理。

---

## 2. 核心架构

系统架构分为两个核心容器镜像 (`base` 和 `application`)，它们协同工作以提供一个完整的交易环境。

*   **`base` 镜像 (`cloud-run/base/`)**: 提供 IB Gateway 运行所需的基础环境，包括 Java、相关库和 IBC 工具。
*   **`application` 镜像 (`cloud-run/application/`)**: 基于 `base` 镜像构建，包含所有 Python 交易逻辑、API 端点和策略实现。

当部署到 Cloud Run 时，`application` 镜像在一个容器内同时运行 IB Gateway 进程和 Python Falcon Web 应用。应用通过内部网络 (`127.0.0.1`) 与 IB Gateway 通信。

### 架构图

```mermaid
graph TD
    subgraph "Google Cloud Platform"
        CloudBuild[Cloud Build] --> AR[Artifact Registry]
        AR -- "部署镜像" --> CR[Cloud Run Service]
        CR -- "读/写" --> Firestore[Firestore (配置/状态)]
        CR -- "获取凭据" --> SM[Secret Manager]
    end

    subgraph "Cloud Run 容器内部"
        CR --> App[Python Falcon App]
        App -- "内部API调用" --> IBGW[IB Gateway]
    end

    subgraph "外部交互"
        User[用户/Cloud Scheduler] -- "HTTP API 请求" --> CR
        IBGW -- "交易/数据" --> IB[Interactive Brokers Servers]
    end
```

---

## 3. 应用程序设计

### 3.1 Intents (意图)

“意图”是系统的业务逻辑单元，代表一个具体的操作。每个意图都是一个可以通过 HTTP API 调用的端点。

*   **`allocation`**: 核心交易意图。根据一个或多个策略的信号，计算并执行投资组合的调整。
*   **`summary`**: 获取账户摘要，包括净值、持仓、未结订单等。
*   **`close_all`**: 平掉所有现有头寸并取消所有挂单。
*   **`cash_balancer`**: 调整账户中的现金余额。
*   **`collect_market_data`**: 收集特定金融工具的市场数据。
*   **`trade_reconciliation`**: 进行交易对账。

### 3.2 Strategies (策略)

“策略”是具体的交易逻辑实现。本项目的关键特性是**动态策略加载**：任何位于 `cloud-run/application/app/strategies/` 目录下的、继承自 `Strategy` 基类的 Python 文件都会被系统自动识别并注册。策略的名称（用于 API 调用）即为其类名的小写版本。

#### 现有策略

*   **`dummy`**: 一个简单的随机策略，用于测试和演示。它使用 **SPY ETF** 合约，并随机生成买入、卖出或无操作的信号。是验证 `allocation` 流程是否通畅的绝佳工具。

*   **`spymacdvixy` (新功能)**: 一个基于技术指标的对冲策略。
    *   **逻辑**: 跟踪 **SPY ETF** 的日线 **MACD** 指标。
    *   **买入信号 (金叉)**: 当 MACD 线上穿信号线时，做多 SPY，并清仓 VIXY（因市场看涨，无需对冲）。
    *   **卖出信号 (死叉)**: 当 MACD 线下穿信号线时，做空或清仓 SPY，并买入 **VIXY** 以对冲下行风险。

#### 如何添加新策略

1.  在 `cloud-run/application/app/strategies/` 目录下创建一个新的 Python 文件 (例如 `my_strategy.py`)。
2.  在该文件中，创建一个继承自 `strategies.strategy.Strategy` 的类。
3.  实现 `_setup()` 方法：定义策略所需的金融工具（如股票、ETF）。
4.  实现 `_get_signals()` 方法：编写你的核心逻辑，根据市场数据或其他条件生成交易信号。
5.  完成以上步骤后，你的策略将自动以其类名的小写形式（例如 `mystrategy`）注册，并可以通过 `allocation` 意图进行调用。

---

## 4. API 用法与测试指南

### 4.1 使用 `curl` 进行 API 测试

你可以使用 `curl` 向部署的服务发送 HTTP 请求来测试各种意图。

*   **获取服务 URL 和认证 Token (如果需要)**:
    ```bash
    SERVICE_URL=$(gcloud run services describe ib-paper --region <your-region> --format="value(status.url)")
    TOKEN=$(gcloud auth print-identity-token)
    ```

*   **示例 1: 测试 `summary` 意图 (GET 请求)**
    ```bash
    curl -X GET -H "Authorization: Bearer ${TOKEN}" "${SERVICE_URL}/summary"
    ```

*   **示例 2: 测试 `allocation` 意图 (POST 请求)**
    
    调用 `spymacdvixy` 策略进行模拟运行 (`dryRun: true`):
    ```bash
    curl -X POST \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer ${TOKEN}" \
      -d '{
        "dryRun": true,
        "strategies": ["spymacdvixy"]
      }' \
    "${SERVICE_URL}/allocation"
    ```

### 4.2 单元测试

项目采用 `unittest` 框架进行单元测试，并大量使用 `unittest.mock` 来模拟外部依赖（如 GCP 服务和 IB Gateway）。这使得测试可以在没有实际凭据和连接的情况下快速、独立地运行。开发者在添加新功能时，应为其编写相应的单元测试。

---

## 5. 部署流程

项目的部署通过 Google Cloud Build 自动化完成。`cloud-run/base/cloudbuild.yaml` 和 `cloud-run/application/cloudbuild.yaml` 文件定义了 CI/CD 流程，包括：

1.  构建 `base` 和 `application` 镜像。
2.  将镜像推送到 Artifact Registry。
3.  运行测试（如果已配置）。
4.  将新版本的 `application` 镜像部署到 Cloud Run 服务。

---

## 6. Firestore 数据库结构

Firestore 用于存储应用的配置和交易状态，主要包含两个顶级集合：`config` 和 `positions`。

```mermaid
graph TD
    Firestore --> ConfigCollection[Collection: config];
    Firestore --> PositionsCollection[Collection: positions];

    ConfigCollection --> ConfigCommonDoc[Document: common];
    ConfigCollection --> ConfigPaperDoc[Document: paper];
    ConfigCollection --> ConfigLiveDoc[Document: live];

    ConfigCommonDoc -- Fields --> CommonFields(marketDataType, risk_limit, ...);
    ConfigPaperDoc -- Fields --> PaperFields(account, max_positions, ...);

    PositionsCollection --> TradingModeSub[Sub-collection: {trading_mode}];
    TradingModeSub --> OpenOrdersCollection[Sub-collection: openOrders];
    TradingModeSub --> HoldingsCollection[Sub-collection: holdings];

    HoldingsCollection --> StrategyHoldingsDoc[Document: {strategy_id}];
    StrategyHoldingsDoc -- Fields --> HoldingsFields(contractId1: quantity1, ...);
```

*   **`config` 集合**: 存储应用的配置。`common` 文档包含通用配置，而 `paper` 和 `live` 文档包含特定交易模式的配置（如IB账户ID）。
*   **`positions` 集合**: 存储交易状态。在每个交易模式 (`paper`/`live`) 下：
    *   `openOrders`: 存储未完成的订单。
    *   `holdings`: 按策略 ID 存储当前持仓。每个文档的 ID 是策略的 ID，内容是合约ID到持仓数量的映射。