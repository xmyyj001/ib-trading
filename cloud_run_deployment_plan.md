# Google Cloud Run 部署计划（修订版）

## 1. 项目架构分析

该项目旨在通过 Google Cloud Run 实现无服务器算法交易，并与盈透证券 (Interactive Brokers, IB) 集成。其核心是两个协同工作的 Docker 镜像：

*   **`base` 镜像**: 提供一个包含 IB Gateway 和 IBC (自动化管理工具) 的基础环境。
*   **`application` 镜像**: 基于 `base` 镜像，包含所有 Python 交易逻辑、API 和策略。

当部署时，`application` 镜像在一个容器内同时运行 IB Gateway 进程和 Python 应用。两者通过内部网络 (`127.0.0.1`) 通信。

## 2. 核心部署流程

部署流程由 `cloud-run/application/cloudbuild.yaml` 文件全自动定义，主要步骤包括：构建镜像、运行测试、部署到 Cloud Run。

以下是手动执行首次部署及相关设置的详细步骤。

### 步骤一：环境与权限准备

1.  **登录 gcloud CLI**
    ```bash
    gcloud auth login
    gcloud config set project [YOUR_PROJECT_ID]
    ```

2.  **启用必要的 Google Cloud API**
    ```bash
    gcloud services enable cloudbuild.googleapis.com run.googleapis.com artifactregistry.googleapis.com iam.googleapis.com secretmanager.googleapis.com
    ```

3.  **创建并授权服务账号**
    您的 Cloud Run 服务需要一个专用的身份（服务账号）来运行。
    ```bash
    # 创建服务账号
    gcloud iam service-accounts create ib-trading --display-name="IB Trading Service Account"

    # 授予部署和运行服务所需的最小权限
    gcloud projects add-iam-policy-binding [YOUR_PROJECT_ID] \
        --member="serviceAccount:ib-trading@[YOUR_PROJECT_ID].iam.gserviceaccount.com" \
        --role="roles/run.invoker"
    gcloud projects add-iam-policy-binding [YOUR_PROJECT_ID] \
        --member="serviceAccount:ib-trading@[YOUR_PROJECT_ID].iam.gserviceaccount.com" \
        --role="roles/storage.objectUser" # Cloud Build 需要访问GCS存储桶

    # 授予服务账号访问Secret的权限
    gcloud projects add-iam-policy-binding [YOUR_PROJECT_ID] \
        --member="serviceAccount:ib-trading@[YOUR_PROJECT_ID].iam.gserviceaccount.com" \
        --role="roles/secretmanager.secretAccessor"
    ```

### 步骤二：存储IB凭据 (使用 Secret Manager)

我们使用 Secret Manager 来安全地存储您的 IB 用户名和密码。

1.  **创建 Secret**
    将 `[YOUR_SECRET_NAME]` 替换为您选择的名称 (例如 `ib-paper-credentials`)。
    ```bash
    gcloud secrets create [YOUR_SECRET_NAME] --replication-policy="automatic"
    ```

2.  **添加 Secret 内容**
    将 `[USER_ID]` 和 `[PASSWORD]` 替换为您的真实凭据。
    ```bash
    printf '{"userid": "[USER_ID]", "password": "[PASSWORD]"}' | gcloud secrets versions add [YOUR_SECRET_NAME] --data-file=-
    ```

### 步骤三：构建与推送基础镜像

此步骤只需在您修改基础环境（如升级IBC或Java版本）后执行一次。

1.  **创建 Artifact Registry 仓库** (如果尚未创建)
    ```bash
    gcloud artifacts repositories create cloud-run-repo --repository-format=docker --location=[YOUR_GCP_REGION]
    ```

2.  **配置 Docker 认证**
    ```bash
    gcloud auth configure-docker [YOUR_GCP_REGION]-docker.pkg.dev
    ```

3.  **构建并推送**
    ```bash
    cd cloud-run/base
    docker build -t [YOUR_GCP_REGION]-docker.pkg.dev/[YOUR_PROJECT_ID]/cloud-run-repo/base:latest .
    docker push [YOUR_GCP_REGION]-docker.pkg.dev/[YOUR_PROJECT_ID]/cloud-run-repo/base:latest
    cd ../..
    ```

### 步骤四：部署应用并挂载凭据

这是将您的应用部署到 Cloud Run 并安全连接凭据的关键一步。

1.  **通过 Cloud Build 部署**
    推荐使用 Cloud Build 部署，它会自动执行测试。请确保 `cloud-run/application/cloudbuild.yaml` 中的 `_GCP_REGION` 和 `_TRADING_MODE` 等变量符合您的设定。
    ```bash
    gcloud builds submit --config cloud-run/application/cloudbuild.yaml .
    ```

2.  **为服务挂载 Secret (关键步骤)**
    首次部署后，服务已经运行，但还无法登录 IB Gateway。我们需要通过更新服务，将 Secret Manager 中的凭据作为环境变量注入到容器中。
    ```bash
    gcloud run services update ib-paper --region [YOUR_GCP_REGION] \
      --set-secrets="IB_USER=[YOUR_SECRET_NAME]:latest,IB_PASSWORD=[YOUR_SECRET_NAME]:latest"
    ```
    **工作原理**: 
    *   `--set-secrets` 指令告诉 Cloud Run 创建两个环境变量：`IB_USER` 和 `IB_PASSWORD`。
    *   `IB_USER` 的值将从 `[YOUR_SECRET_NAME]` 的最新版本中，解析 JSON 并提取 `userid` 字段。
    *   `IB_PASSWORD` 的值将从同一个 Secret 中，解析 JSON 并提取 `password` 字段。
    *   这两个环境变量随后会被容器内的 `gatewaystart.sh` 脚本读取，用于自动登录 IB Gateway。**Python 应用本身完全不接触明文密码**，实现了安全解耦。

### 步骤五：验证与测试

1.  **获取服务 URL 和认证令牌**
    ```bash
    SERVICE_URL=$(gcloud run services describe ib-paper --region [YOUR_GCP_REGION] --format="value(status.url")
    TOKEN=$(gcloud auth print-identity-token)
    ```

2.  **测试 `/summary` 端点**
    ```bash
    curl -H "Authorization: Bearer ${TOKEN}" "${SERVICE_URL}/summary"
    ```
    如果看到返回的账户信息，则代表系统已成功连接并登录 IB Gateway。

### 附录：生产场景的 Cloud Scheduler 配置

以下是为场景A和场景D设置Cloud Scheduler作业所需的gcloud命令行指令。

**注意**: 请将命令中的 `[SERVICE_URL]`、`[SERVICE_ACCOUNT_EMAIL]` 和 `[YOUR_PROJECT_ID]` 替换为您的实际值。

#### 场景 A: 日线级别的“波段/趋势交易者”

此场景仅需一个作业，在每日收盘后触发策略分配。

```bash
gcloud scheduler jobs create http eod-allocation-job --project=[YOUR_PROJECT_ID] \
    --schedule="15 16 * * 1-5" \
    --time-zone="America/New_York" \
    --uri="${SERVICE_URL}/allocation" \
    --http-method=POST \
    --oidc-service-account-email="[SERVICE_ACCOUNT_EMAIL]" \
    --message-body='{"strategies": ["spymacdvixy"]}' \
    --headers="Content-Type=application/json"
```

#### 场景 D: “混合模式”日内交易者

此场景需要三个独立的作业，分别负责开盘、盘中和收盘的逻辑。

**1. 作业一: 开盘交易**
```bash
gcloud scheduler jobs create http open-allocation-job --project=[YOUR_PROJECT_ID] \
    --schedule="30 9 * * 1-5" \
    --time-zone="America/New_York" \
    --uri="${SERVICE_URL}/allocation" \
    --http-method=POST \
    --oidc-service-account-email="[SERVICE_ACCOUNT_EMAIL]" \
    --message-body='{"strategies": ["spymacdvixy"]}' \
    --headers="Content-Type=application/json"
```

**2. 作业二: 盘中风控**
```bash
gcloud scheduler jobs create http midday-risk-check-job --project=[YOUR_PROJECT_ID] \
    --schedule="0 13 * * 1-5" \
    --time-zone="America/New_York" \
    --uri="${SERVICE_URL}/risk-check" \
    --http-method=POST \
    --oidc-service-account-email="[SERVICE_ACCOUNT_EMAIL]"
```

**3. 作业三: 收盘对账**
```bash
gcloud scheduler jobs create http eod-reconciliation-job --project=[YOUR_PROJECT_ID] \
    --schedule="55 15 * * 1-5" \
    --time-zone="America/New_York" \
    --uri="${SERVICE_URL}/eod-check" \
    --http-method=POST \
    --oidc-service-account-email="[SERVICE_ACCOUNT_EMAIL]"
```