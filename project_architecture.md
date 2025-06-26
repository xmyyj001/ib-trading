# 项目架构描述

## 1. 概述

本项目旨在通过 Google Cloud Run 实现无服务器算法交易，并与盈透证券 (Interactive Brokers, IB) 集成。它提供了一个基于 HTTP 请求的接口，用于执行各种交易意图（如资金分配、现金平衡、市场数据收集、交易汇总等），并利用 Google Cloud 服务进行凭证管理、数据存储和自动化部署。

## 2. 核心组件

### 2.1 Docker 镜像

项目主要由两个 Docker 镜像组成，它们通过多阶段构建的方式协同工作：

#### `cloud-run/base` 镜像

*   **作用：** 提供运行 IB Gateway 所需的基础环境。
*   **内容：**
    *   基于 `python:3.9-slim`。
    *   安装了 IB Gateway 运行所需的系统依赖项（如 `wget`, `unzip`, `xvfb`, `libxtst6`, `libxrender1`, `openjfx` 等）。
    *   下载并安装 IB TWS (Trader Workstation) 或 IB Gateway。
    *   下载并解压 IBC (Interactive Brokers Console)，用于自动化 IB Gateway 登录和管理。
    *   复制 IBC 的 `config.ini` 和 Jts 的 `jts.ini` 配置文件。
    *   设置 `DISPLAY` 环境变量，用于运行图形界面的 IB Gateway。
*   **构建方式：** 通过 `cloud-run/base/Dockerfile` 构建，并推送到 Artifact Registry。

#### `cloud-run/application` 镜像

*   **作用：** 包含实际的 Python 应用程序代码和其依赖项，并基于 `cloud-run/base` 镜像构建。
*   **内容：**
    *   基于 `cloud-run/base` 镜像。
    *   复制 Python 应用程序代码（位于 `app` 目录）。
    *   安装 Python 应用程序所需的依赖项（通过 `requirements.txt`）。
*   **入口点：** `CMD ./cmd.sh`，该脚本会启动 `Xvfb` 和 `gunicorn` 来运行 `main:app`。

### 2.2 应用程序结构 (`cloud-run/application/app`)

应用程序代码组织清晰，主要分为以下几个模块：

*   **`main.py`**:
    *   应用程序的入口点，负责初始化环境、配置日志，并处理传入的 HTTP 请求。
    *   包含 `Main` 类和 `_on_request` 静态方法，用于根据请求的 `intent` 调用相应的处理逻辑。
*   **`intents/`**:
    *   包含各种交易意图的实现。每个文件通常对应一个具体的交易操作或数据查询。
    *   示例：`allocation.py` (资金分配), `cash_balancer.py` (现金平衡), `close_all.py` (平仓), `collect_market_data.py` (收集市场数据), `summary.py` (交易汇总), `trade_reconciliation.py` (交易对账)。
    *   `intent.py` 可能定义了意图的基类或接口。
*   **`lib/`**:
    *   包含通用库和工具函数，供应用程序的各个部分使用。
    *   示例：`environment.py` (环境配置，包括从 Secret Manager 获取凭证), `gcp.py` (Google Cloud Platform 相关工具), `ibgw.py` (IB Gateway 交互逻辑), `init_firestore.py` (Firestore 初始化), `trading.py` (交易相关通用函数)。
*   **`strategies/`**:
    *   包含交易策略的实现。
    *   示例：`dummy.py` (示例策略), `strategy.py` (策略基类或接口)。
*   **`_tests/`**:
    *   包含应用程序的单元测试和集成测试，确保代码质量和功能正确性。

### 2.3 Google Cloud Services

项目广泛利用 Google Cloud Platform (GCP) 服务来实现其功能和部署：

*   **Cloud Run**:
    *   无服务器计算平台，用于部署和运行容器化的交易应用程序。
    *   提供自动扩缩、按请求付费的特性，适合处理偶发或突发的交易请求。
*   **Artifact Registry**:
    *   用于存储和管理 Docker 镜像的私有仓库。
    *   `cloud-run/base` 和 `cloud-run/application` 镜像都存储在此。
*   **Secret Manager**:
    *   安全地存储敏感信息，如 IB Gateway 的用户 ID 和密码。
    *   应用程序在运行时直接从 Secret Manager 获取凭证，提高了安全性。
*   **BigQuery**:
    *   用于存储和分析历史交易数据。
    *   部署计划中提到了创建 `historical_data` 数据集和 `test` 表。
*   **Firestore**:
    *   NoSQL 文档数据库，用于存储实时或半实时数据。
    *   部署计划中提到了创建 Firestore 数据库实例。
*   **Cloud Build**:
    *   持续集成和持续部署 (CI/CD) 服务。
    *   自动化构建 Docker 镜像、运行测试和部署到 Cloud Run 的流程。

## 3. 部署流程

项目的部署流程通过 `cloudbuild.yaml` 文件在 Google Cloud Build 中自动化执行：

```mermaid
graph TD
    A[代码提交/手动触发] --> B(Cloud Build 触发);
    B --> C{构建 cloud-run/application 镜像};
    C --> D[推送到 Artifact Registry];
    D --> E[运行安全检查 (safety)];
    E --> F[运行单元测试];
    F --> G[运行集成测试];
    G --> H{部署到 Google Cloud Run};
    H --> I[创建/更新 Cloud Run 服务 (ib-${_TRADING_MODE})];
    I --> J[删除旧修订版和未引用镜像];
    J --> K[部署完成];
```

**详细步骤：**

1.  **代码提交/手动触发：** 当代码推送到指定分支或手动触发 Cloud Build 时，部署流程开始。
2.  **构建 `cloud-run/application` 镜像：** Cloud Build 使用 `cloud-run/application/Dockerfile` 构建应用程序镜像。如果 `cloud-run/base` 镜像不存在或需要更新，它会首先被构建和推送。
3.  **推送到 Artifact Registry：** 构建完成的应用程序镜像被推送到 Artifact Registry。
4.  **运行安全检查：** 使用 `safety` 工具检查 Python 依赖项是否存在已知的安全漏洞。
5.  **运行单元测试：** 在 Docker 镜像中执行 Python 单元测试。
6.  **运行集成测试：** 在 Docker 镜像中执行集成测试，这可能涉及到与 IB Gateway 的交互。
7.  **部署到 Google Cloud Run：**
    *   使用 `gcloud run deploy` 命令将应用程序部署到 Google Cloud Run。
    *   服务名称为 `ib-${_TRADING_MODE}` (例如 `ib-paper`)。
    *   配置包括区域、平台、最大实例数、内存限制和服务账号。
    *   环境变量 `PROJECT_ID` 和 `TRADING_MODE` 被设置。
8.  **删除旧修订版：** 根据配置（默认为保留 3 个修订版），删除旧的 Cloud Run 修订版和不再被任何修订版引用的 Docker 镜像，以节省资源。

## 4. 数据流和交互

```mermaid
graph LR
    User[用户/外部系统] -- HTTP 请求 --> CloudRunService[Google Cloud Run 服务];
    CloudRunService -- 调用 --> Application[Python 应用程序];
    Application -- 获取凭证 --> SecretManager[Google Secret Manager];
    Application -- 交易指令/数据请求 --> IBGateway[IB Gateway (运行在容器内)];
    IBGateway -- 交易数据/市场数据 --> InteractiveBrokers[盈透证券];
    Application -- 写入历史数据 --> BigQuery[Google BigQuery];
    Application -- 写入/读取实时数据 --> Firestore[Google Firestore];
    CloudBuild[Google Cloud Build] -- 部署 --> CloudRunService;
    CloudBuild -- 推送镜像 --> ArtifactRegistry[Google Artifact Registry];
```

**交互流程：**

1.  **用户/外部系统** 通过 HTTP 请求调用 **Google Cloud Run 服务**。
2.  **Cloud Run 服务** 接收请求并将其路由到 **Python 应用程序** 实例。
3.  **Python 应用程序** 在处理请求时，会从 **Google Secret Manager** 安全地获取 IB Gateway 的登录凭证。
4.  应用程序通过内部运行的 **IB Gateway** 与 **盈透证券** 进行交互，发送交易指令或请求市场数据。
5.  应用程序将历史交易数据写入 **Google BigQuery** 进行存储和分析。
6.  应用程序可能还会与 **Google Firestore** 进行实时或半实时的读写操作。
7.  **Google Cloud Build** 负责自动化部署流程，包括构建 Docker 镜像并将其推送到 **Google Artifact Registry**，然后将应用程序部署到 **Google Cloud Run 服务**。

## 5. 架构图

```mermaid
graph TD
    subgraph CI/CD
        CB[Cloud Build] --> AR[Artifact Registry];
        CB --> CR[Cloud Run];
    end

    subgraph Google Cloud Platform
        CR -- 访问凭证 --> SM[Secret Manager];
        CR -- 写入/读取 --> BQ[BigQuery];
        CR -- 写入/读取 --> FS[Firestore];
    end

    subgraph Cloud Run Service
        CR --> App[Python 应用程序];
        App -- 内部通信 --> IBGW[IB Gateway];
    end

    IBGW -- 交易/数据 --> IB[Interactive Brokers];

    User[用户/外部系统] -- HTTP 请求 --> CR;

    style CB fill:#f9f,stroke:#333,stroke-width:2px
    style AR fill:#bbf,stroke:#333,stroke-width:2px
    style CR fill:#bfb,stroke:#333,stroke-width:2px
    style SM fill:#fbb,stroke:#333,stroke-width:2px
    style BQ fill:#ccf,stroke:#333,stroke-width:2px
    style FS fill:#cfc,stroke:#333,stroke-width:2px
    style App fill:#ffc,stroke:#333,stroke-width:2px
    style IBGW fill:#fcf,stroke:#333,stroke-width:2px
    style IB fill:#cff,stroke:#333,stroke-width:2px
    style User fill:#eee,stroke:#333,stroke-width:2px
## 6. 项目文件结构

```
.
├── .gitignore
├── cloud_run_deployment_plan.md
├── cloud-run_project_architecture.md
├── delete_old_images.md
├── env_TWS_error.md
├── error_bigquery_firestore_update_plan.md
├── project_design_and_test_architecture_analysis.md
├── project_directory_structure.md
├── project_structure.md
├── README.md
├── solve_using_community_docker.md
├── use_VM.md
├── cloud-run/
│   ├── explanation_integration_test_revise.md
│   ├── README.md
│   └── application/
│       ├── .dockerignore
│       ├── cloudbuild.yaml
│       ├── cloudbuild.yaml.new
│       ├── cloudbuild.yaml.new1
│       ├── cmd.sh
│       ├── Dockerfile
│       └── app/
│           ├── main.py
│           ├── requirements.txt
│           ├── _tests/
│           │   ├── __init__.py
│           │   ├── integration_tests.py
│           │   └── test_unittest_setup.py
│           ├── intents/
│           │   ├── __init__.py
│           │   ├── allocation.py
│           │   ├── cash_balancer.py
│           │   ├── close_all.py
│           │   ├── collect_market_data.py
│           │   ├── intent.py
│           │   ├── summary.py
│           │   ├── trade_reconciliation.py
│           │   └── _tests/
│           │       ├── __init__.py
│           │       ├── test_allocation.py
│           │       ├── test_cash_balancer.py
│           │       ├── test_close_all.py
│           │       ├── test_intent.py
│           │       ├── test_summary.py
│           │       └── test_trade_reconciliation.py
│           ├── lib/
│           │   ├── __init__.py
│           │   ├── environment.py
│           │   ├── gcp.py
│           │   ├── ibgw.py
│           │   ├── init_firestore.py
│           │   ├── trading.py
│           │   └── _tests/
│           │       ├── __init__.py
│           │       ├── test_environment.py
│           │       ├── test_gcp.py
│           │       ├── test_ibgw.py
│           │       └── test_trading.py
│           └── strategies/
│               ├── __init__.py
│               ├── dummy.py
│               ├── strategy.py
│               └── _tests/
│                   ├── __init__.py
│                   ├── test_dummy.py
│                   └── test_strategy.py
└── cloud-run/base/
    ├── .dockerignore
    ├── cloudbuild.yaml
    ├── cmd.sh
    ├── Dockerfile
    ├── Dockerfile.old
    └── ibc/
        ├── config.ini
        ├── gatewaystart.sh
        └── jts.ini
```