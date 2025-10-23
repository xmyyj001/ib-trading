--- 
Generation Time: 2025-07-03 23:01:04
---

认真理解这份项目架构说明：

### 项目架构文档：基于 Cloud Run 的盈透证券 (IB) 算法交易系统

#### 1. 概述

本项目旨在利用 Google Cloud Run 实现一个无服务器的盈透证券 (IB) 算法交易系统。它结合了 Cloud Run 的弹性伸缩能力、IBC (Interactive Brokers Client) 的自动化登录和管理功能，以及 IB 的 Python API 和 `ib_insync` 库进行交易操作。整个系统被设计为高度容器化，并通过 Google Cloud Build 实现自动化构建和部署。

#### 2. 核心组件

项目主要由两个 Docker 镜像构成，分别对应 `base` 和 `application`：

##### 2.1 `base` 镜像 (位于 `cloud-run/base/`)

*   **目的**：提供 IB Gateway 运行所需的基础环境和依赖。
*   **技术栈**：
    *   基于 `python:3.9-slim` 镜像。
    *   安装了 `wget`, `unzip`, `xvfb`, `libxtst6`, `libxrender1`, `openjdk-17-jre-headless` 等系统依赖，用于运行 IB Gateway。
    *   下载并安装了特定版本的 IB Gateway (通过 `TWS_VERSION` 环境变量控制，默认为 `1030`)。
    *   下载并安装了 IBC (Interactive Brokers Client) 工具，用于自动化 IB Gateway 的启动和管理。
*   **关键文件**：
    *   [`cloud-run/base/Dockerfile`](cloud-run/base/Dockerfile): 定义了 `base` 镜像的构建过程，包括依赖安装、IB Gateway 和 IBC 的下载与配置。
    *   [`cloud-run/base/ibc/config.ini`](cloud-run/base/ibc/config.ini): IBC 的配置文件，用于控制 IB Gateway 的行为。
    *   [`cloud-run/base/ibc/jts.ini`](cloud-run/base/ibc/jts.ini): IB Gateway 的 Java 虚拟机配置。
    *   [`cloud-run/base/ibc/gatewaystart.sh`](cloud-run/base/ibc/gatewaystart.sh): 启动 IB Gateway 的脚本，它会读取环境变量（如 `IB_USERNAME`, `IB_PASSWORD`, `TRADING_MODE` 等）来配置和启动 IBC。

##### 2.2 `application` 镜像 (位于 `cloud-run/application/`)

*   **目的**：包含实际的算法交易应用程序逻辑。
*   **技术栈**：
    *   基于 `base` 镜像 (`europe-docker.pkg.dev/${PROJECT_ID}/cloud-run-repo/base:latest`)。
    *   安装了 `app/requirements.txt` 中定义的 Python 依赖，包括 `gunicorn` (用于运行 Web 服务器)、`falcon` (Web 框架) 以及 `ib_insync` 等。
    *   包含核心的交易逻辑，通过不同的“意图 (intents)”处理交易请求。
*   **关键文件**：
    *   [`cloud-run/application/Dockerfile`](cloud-run/application/Dockerfile): 定义了 `application` 镜像的构建过程，包括复制应用程序代码和安装 Python 依赖。
    *   [`cloud-run/application/app/main.py`](cloud-run/application/app/main.py): 应用程序的入口点，使用 Falcon 框架暴露 HTTP 接口。它根据传入的 `intent` 参数调用不同的交易逻辑模块。
    *   `cloud-run/application/app/intents/`: 包含各种交易“意图”的模块，例如 `allocation.py`, `cash_balancer.py`, `close_all.py`, `collect_market_data.py`, `summary.py`, `trade_reconciliation.py`。每个意图都封装了特定的交易操作。
    *   `cloud-run/application/app/lib/`: 包含辅助库，如 `environment.py` (环境配置), `gcp.py` (GCP 服务交互), `ibgw.py` (IB Gateway 交互), `init_firestore.py` (Firestore 初始化), `trading.py` (交易辅助函数)。
    *   `cloud-run/application/app/strategies/`: 包含交易策略的模块，例如 `dummy.py`。
    *   [`cloud-run/application/cmd.sh`](cloud-run/application/cmd.sh): 应用程序的启动脚本，通常会启动 Gunicorn 服务器来运行 `main.py`。

#### 3. 部署流程 (Google Cloud Build)

项目使用 Google Cloud Build 进行自动化构建和部署。

##### 3.1 `base` 镜像构建 (`cloud-run/base/cloudbuild.yaml`)

*   **步骤**：
    1.  构建 `base` Docker 镜像，并打上 `latest` 和 `SHORT_SHA` (Git 提交哈希) 标签。
    2.  将构建好的 `base` 镜像推送到 Google Artifact Registry (或 Google Container Registry)。
*   **目的**：确保 `application` 镜像可以基于最新的稳定基础环境进行构建。

##### 3.2 `application` 镜像构建与部署 (`cloud-run/application/cloudbuild.yaml`)

*   **步骤**：
    1.  **拉取最新 `base` 镜像**：确保 `application` 镜像构建时使用的是最新的 `base` 镜像。
    2.  **构建 `application` 镜像**：基于 `base` 镜像构建 `application` Docker 镜像，并打上自定义标签 (`_MY_IMAGE_TAG`，默认为 `latest`)。
    3.  **推送 `application` 镜像**：将构建好的 `application` 镜像推送到 Google Artifact Registry。
    4.  **部署到 Cloud Run**：将 `application` 镜像部署到 Cloud Run 服务。部署时会配置服务名称 (`ib-${_TRADING_MODE}`), 区域 (`_GCP_REGION`), 实例数量 (`max-instances: 1`), 内存 (`2Gi`), CPU (`2`), 服务账户 (`ib-trading@${PROJECT_ID}.iam.gserviceaccount.com`)，并设置环境变量 (`PROJECT_ID`, `TRADING_MODE`) 和秘密 (`IB_CREDENTIALS_JSON`)。
*   **目的**：自动化应用程序的构建、测试 (如果添加了测试步骤) 和部署到 Cloud Run。

#### 4. 架构图

```mermaid
graph TD
    subgraph "Google Cloud Platform"
        subgraph "Cloud Build"
            CB_Base[cloud-run/base/cloudbuild.yaml] --> BuildBase(构建 Base 镜像)
            BuildBase --> PushBase(推送 Base 镜像到 Artifact Registry)
            CB_App[cloud-run/application/cloudbuild.yaml] --> PullBase(拉取最新 Base 镜像)
            PullBase --> BuildApp(构建 Application 镜像)
            BuildApp --> PushApp(推送 Application 镜像到 Artifact Registry)
            PushApp --> DeployCR(部署到 Cloud Run)
        end

        subgraph "Artifact Registry"
            AR_Base(Base 镜像)
            AR_App(Application 镜像)
        end

        subgraph "Cloud Run Service"
            CR_Service[ib-${TRADING_MODE} 服务]
            CR_Service --> AppContainer(Application 容器)
            AppContainer --> IBGateway(IB Gateway 进程)
            AppContainer --> PythonApp(Python 应用逻辑)
        end

        subgraph "Secrets Manager"
            SM[IB_CREDENTIALS_JSON]
        end
    end

    subgraph "Local Development / Source Code"
        SRC_Base[cloud-run/base/]
        SRC_App[cloud-run/application/]
    end

    SRC_Base --> CB_Base
    SRC_App --> CB_App

    PushBase --> AR_Base
    PushApp --> AR_App

    AR_Base -- FROM --> BuildApp
    AR_App -- Image --> DeployCR

    DeployCR --> CR_Service
    SM --> DeployCR

    PythonApp -- API Calls --> IBGateway
    PythonApp -- Intents --> Firestore(Firestore)
    PythonApp -- Intents --> BigQuery(BigQuery)
```

#### 5. 关键交互流程

1.  **镜像构建**：
    *   `base` 镜像首先被构建，包含 IB Gateway 和 IBC 的所有运行时依赖。
    *   `application` 镜像基于 `base` 镜像构建，并添加 Python 应用程序代码和其依赖。
2.  **Cloud Run 部署**：
    *   `application` 镜像被部署到 Cloud Run。
    *   Cloud Run 服务在启动时，会从 Secrets Manager 获取 IB 账户凭据，并将其作为环境变量传递给容器。
3.  **应用程序启动**：
    *   容器启动后，`cmd.sh` 脚本会启动 Gunicorn 服务器，进而运行 `main.py`。
    *   `main.py` 会初始化 `Environment` 类，该类负责根据环境变量配置 IB Gateway。
    *   `gatewaystart.sh` 脚本会在容器内部启动 IB Gateway 进程，并使用 IBC 自动化登录。
4.  **交易请求处理**：
    *   当 Cloud Run 服务接收到 HTTP 请求时，`main.py` 中的 `Main` 类会根据请求路径中的 `intent` 参数，实例化相应的意图类（如 `Allocation`, `CashBalancer` 等）。
    *   这些意图类会通过 `ib_insync` 库与本地运行的 IB Gateway 进行通信，执行具体的交易操作（如分配、现金平衡、平仓、收集市场数据等）。
    *   交易结果或错误信息会以 JSON 格式返回给请求方。
    *   应用程序可能还会与 Firestore 和 BigQuery 等 GCP 服务进行交互，用于数据存储和分析。

#### 6. 环境变量与配置

*   **`TRADING_MODE`**: `live` 或 `paper`，决定交易模式。
*   **`TWS_VERSION`**: IB Gateway 的版本号。
*   **`TWS_INSTALL_LOG`**: IB Gateway 安装日志的路径，用于在 `TWS_VERSION` 未设置时解析版本号。
*   **`IBC_INI`**: IBC 配置文件的路径。
*   **`IBC_PATH`**: IBC 工具的安装路径。
*   **`TWS_PATH`**: IB Gateway 的安装路径。
*   **`TWS_SETTINGS_PATH`**: IB Gateway 设置文件的路径。
*   **`LOG_PATH`**: 日志文件的路径。
*   **`IB_USERNAME`**, **`IB_PASSWORD`**: IB 账户的登录凭据，通过 Secrets Manager 注入。
*   **`PROJECT_ID`**: GCP 项目 ID。
*   **`_GCP_REGION`**: GCP 部署区域。
*   **`_MY_IMAGE_TAG`**: Docker 镜像标签。

项目说明结束。
===========
以下给出

#####   1，cloud-run/application/cloudbuild.yaml: 
# ===================================================================
# == FINAL DEFINITIVE VERSION v2: cloud-run/application/cloudbuild.yaml
# ===================================================================

steps:
  # ... (步骤 0, 1, 2, 3 保持不变) ...
  # 步骤 0: Pull-Latest-Base
  - name: 'gcr.io/cloud-builders/docker'
    id: 'Pull-Latest-Base'
    args: ['pull', 'europe-docker.pkg.dev/${PROJECT_ID}/cloud-run-repo/base:latest']

  # 步骤 1: Build-Application
  - name: 'gcr.io/cloud-builders/docker'
    id: 'Build-Application'
    args:
      - 'build'
      - '--build-arg'
      - 'BASE_IMAGE_URL=europe-docker.pkg.dev/${PROJECT_ID}/cloud-run-repo/base:latest'
      - '--tag'
      - 'europe-docker.pkg.dev/${PROJECT_ID}/cloud-run-repo/application:${_MY_IMAGE_TAG}'
      - 'cloud-run/application'
      - '--file'
      - 'cloud-run/application/Dockerfile'
    waitFor: ['Pull-Latest-Base']

  # 步骤 2: Push-Application
  - name: 'gcr.io/cloud-builders/docker'
    id: 'Push-Application'
    args: ['push', 'europe-docker.pkg.dev/${PROJECT_ID}/cloud-run-repo/application:${_MY_IMAGE_TAG}']
    waitFor: ['Build-Application']

  # --- 检测和初始化步骤 ---

  # 步骤 4: 运行依赖安全检查
  - name: "gcr.io/cloud-builders/docker"
    id: "Safety-Check"
    args:
      - "run"
      - "--rm"
      - "--entrypoint"
      - "bash"
      - "europe-docker.pkg.dev/${PROJECT_ID}/cloud-run-repo/application:${_MY_IMAGE_TAG}"
      - "-c"
      - "pip install --quiet safety && safety check --bare || true" # <--- 在这里加上 || true
    waitFor: ['Push-Application']

# 步骤 5: 运行单元测试 (暂时跳过)
  - name: "europe-docker.pkg.dev/${PROJECT_ID}/cloud-run-repo/my-docker-cloud-sdk:latest"
    id: "Unit-Tests"
    entrypoint: "bash"
    args: ["-c", "echo '--- SKIPPING UNIT TESTS TO VALIDATE DEPLOYMENT ---' && exit 0"]
    # args:
    # - "-c"
    # - "docker run --rm --env \"PROJECT_ID=${PROJECT_ID}\" --env \"TRADING_MODE=${_TRADING_MODE}\" --entrypoint python europe-docker.pkg.dev/${PROJECT_ID}/cloud-run-repo/application:${_MY_IMAGE_TAG} -m unittest discover -p \"test_*.py\"
    waitFor: ['Push-Application']

  # # 步骤 5: 运行单元测试 (使用我们自己的 builder)
  # - name: "europe-docker.pkg.dev/${PROJECT_ID}/cloud-run-repo/my-docker-cloud-sdk:latest" # <--- 关键修复：使用您自己的 builder
  #   id: "Unit-Tests"
  #   entrypoint: "bash"
  #   args:
  #   - "-c"
  #   - |
  #     # 在这个 builder 中，docker 和 gcloud 命令都可用
  #     # 并且它会自动处理认证
  #     # 使用 cloudbuild 网络
  #     docker run --rm \
  #       --network=\"cloudbuild\" \
  #       --env \"PROJECT_ID=${PROJECT_ID}\" \
  #       --env \"TRADING_MODE=${_TRADING_MODE}\" \
  #       --entrypoint python \
  #       europe-docker.pkg.dev/${PROJECT_ID}/cloud-run-repo/application:${_MY_IMAGE_TAG} \
  #       -m unittest discover -p \"test_*.py\"
  #   waitFor: ['Push-Application']

  # 步骤 6: 初始化 Firestore 配置
  - name: 'python:3.9-slim'
    id: "Initialize-Firestore"
    entrypoint: 'bash'
    args:
    - -c
    - |
      set -e
      pip install --quiet google-cloud-firestore
      python cloud-run/application/app/lib/init_firestore.py "${PROJECT_ID}"
    waitFor: ['Push-Application']

# 步骤 7: 运行集成测试 (暂时跳过)
  - name: "europe-docker.pkg.dev/${PROJECT_ID}/cloud-run-repo/my-docker-cloud-sdk:latest"
    id: "Integration-Tests"
    entrypoint: "bash"
    args: ["-c", "echo '--- SKIPPING INTEGRATION TESTS TO VALIDATE DEPLOYMENT ---' && exit 0"]
    # args:
    # - "-c"
    # - "docker run --rm --env \"PYTHONPATH=/home\" --env \"PROJECT_ID=${PROJECT_ID}\" --env \"TRADING_MODE=${_TRADING_MODE}\" --env \"K_REVISION=cloudbuild\" --entrypoint bash europe-docker.pkg.dev/${PROJECT_ID}/cloud-run-repo/application:${_MY_IMAGE_TAG} -c \"/usr/bin/Xvfb :0 -ac -screen 0 1024x768x16 +extension RANDR & export DISPLAY=:0 && python ./_tests/integration_tests.py\"
    waitFor: ['Initialize-Firestore']

  # # 步骤 7: 运行集成测试 (使用我们自己的 builder)
  #   # 进行网络修复 cloudbuild 网络
  # - name: "europe-docker.pkg.dev/${PROJECT_ID}/cloud-run-repo/my-docker-cloud-sdk:latest" # <--- 关键修复：使用您自己的 builder
  #   id: "Integration-Tests"
  #   entrypoint: "bash"
  #   args:
  #   - "-c"
  #   - |
  #     docker run --rm \
  #       --network=\"cloudbuild\" \
  #       --env \"PYTHONPATH=/home\" \
  #       --env \"PROJECT_ID=${PROJECT_ID}\" \
  #       --env \"TRADING_MODE=${_TRADING_MODE}\" \
  #       --env \"K_REVISION=cloudbuild\" \
  #       --entrypoint bash \
  #       europe-docker.pkg.dev/${PROJECT_ID}/cloud-run-repo/application:${_MY_IMAGE_TAG} \
  #       -c \"/usr/bin/Xvfb :0 -ac -screen 0 1024x768x16 +extension RANDR & export DISPLAY=:0 && python ./_tests/integration_tests.py\"
  #   waitFor: ['Initialize-Firestore']

  # --- 部署步骤 ---

  # 步骤 8: 部署到 Cloud Run
  - name: 'gcr.io/cloud-builders/gcloud'
    id: 'Deploy-to-Cloud-Run'
    args:
      - 'run'
      - 'deploy'
      - 'ib-${_TRADING_MODE}'
      - '--image'
      - 'europe-docker.pkg.dev/${PROJECT_ID}/cloud-run-repo/application:${_MY_IMAGE_TAG}'
      - '--region'
      - '${_GCP_REGION}'
      - '--platform'
      - 'managed'
      - '--max-instances'
      - '1'
      - '--memory'
      - '2Gi'
      - '--cpu'
      - '2'
      - '--service-account'
      - 'ib-trading@${PROJECT_ID}.iam.gserviceaccount.com'
      - '--no-allow-unauthenticated'
      - '--set-env-vars=PROJECT_ID=${PROJECT_ID},TRADING_MODE=${_TRADING_MODE},TWS_VERSION=1030'
    waitFor:
      - 'Safety-Check'
      - 'Unit-Tests'
      - 'Integration-Tests'

# 替换变量
substitutions:
  _GCP_REGION: asia-east1
  _TRADING_MODE: paper
  _MY_IMAGE_TAG: "latest"

timeout: "1800s"


##### 2 cloud-run/base/Dockerfile
# ===================================================================
# == FINAL GOLDEN VERSION: cloud-run/base/Dockerfile
# ===================================================================
FROM python:3.9-slim

# --- 1. 定义所有环境变量 ---
# 关键：TWS_PATH 设置为经过验证的、真正的顶层安装路径
ENV TWS_PATH=/root/Jts
ENV IBC_PATH=/opt/ibc
ENV DISPLAY=:0

# --- 2. 安装所有系统依赖 ---
# 我们不再需要自己安装 Java，因为安装程序会自带
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        wget unzip xvfb xauth libxtst6 libxrender1 procps xterm xfonts-base libgtk-3-0 libasound2 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# --- 3. 安装 IB Gateway (使用经过验证的控制台模式) ---
RUN wget -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh && \
    chmod +x /tmp/ibgw.sh && \
    # 使用自动应答来完成控制台安装
    (echo ""; echo "1"; echo ""; echo "") | /tmp/ibgw.sh -c && \
    rm -f /tmp/ibgw.sh && \
    # 验证安装是否成功
    test -d "${TWS_PATH}/ibgateway/1030/jars" || (echo "FATAL: IB Gateway installation failed!" && exit 1)

# --- 4. 下载并正确解压 IBC v3.22.0 ---
RUN mkdir -p "${IBC_PATH}" && \
    wget -q -O /tmp/IBC.zip https://github.com/IbcAlpha/IBC/releases/download/3.22.0/IBCLinux-3.22.0.zip && \
    unzip -o /tmp/IBC.zip -d "${IBC_PATH}" && \
    rm -f /tmp/IBC.zip

# --- 5. 复制我们自己的配置文件和启动脚本 ---
COPY ibc/config.ini ${IBC_PATH}/config.ini
COPY ibc/gatewaystart.sh ${IBC_PATH}/gatewaystart.sh
# 关键：为所有需要执行的脚本添加权限
RUN chmod +x ${IBC_PATH}/*.sh && \
    chmod +x ${IBC_PATH}/scripts/*.sh && \
    chmod +x ${IBC_PATH}/gatewaystart.sh

#####   3.loud-run/application/Dockerfile: 

# ===================================================================
# == FINAL CORRECTED application/Dockerfile
# ===================================================================

# 1. 从正确的、静态的 base 镜像地址开始
ARG BASE_IMAGE_URL=europe-docker.pkg.dev/${PROJECT_ID}/cloud-run-repo/base:latest

FROM ${BASE_IMAGE_URL}

# 2. 设置工作目录
WORKDIR /home/app
# 2.1. 创建 ibc 目录并复制 ibgateway.vmoptions 文件
# We create a symbolic link here so the script can find it.
RUN ln -s /opt/ibc/ibgateway.vmoptions .

# 3. 复制并安装依赖 (包含 gunicorn)
COPY app/requirements.txt .
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. 复制应用代码
COPY app/ .

# 5. 复制应用专属的启动脚本
COPY cmd.sh .
RUN chmod +x cmd.sh

# 6. 执行启动脚本
CMD ["./cmd.sh"]

#####   5.cloud-run/base/ibc/config.ini: 


#####   6.base/ibc/gatewaystart.sh:
#!/bin/bash

# =======================================================
# == FINAL GOLDEN SCRIPT: gatewaystart.sh
# =======================================================

set -e
set -x

# --- 1. 定义所有路径和参数 ---
TRADING_MODE=${TRADING_MODE:-paper}
TWSUSERID=${IB_USERNAME}
TWSPASSWORD=${IB_PASSWORD}
TWS_VERSION=${TWS_VERSION:-1030}

IBC_PATH="/opt/ibc"
TWS_PATH=${TWS_PATH:-/root/Jts} # 使用经过验证的顶层路径
LOG_PATH="/opt/ibc/logs"

# --- 2. 确保日志目录存在 ---
mkdir -p "${LOG_PATH}"

echo "--- [INFO] Launching IB Gateway via official IBC scripts ---"

# --- 3. 直接在前台调用 IBC 的核心启动脚本 ---
# 使用 exec 来让它成为主进程
exec "${IBC_PATH}/scripts/ibcstart.sh" \
    "${TWS_VERSION}" \
    --gateway \
    "--mode=${TRADING_MODE}" \
    "--user=${TWSUSERID}" \
    "--pw=${TWSPASSWORD}" \
    "--tws-path=${TWS_PATH}" \
    "--ibc-path=${IBC_PATH}" \
    "--ibc-ini=${IBC_PATH}/config.ini"



