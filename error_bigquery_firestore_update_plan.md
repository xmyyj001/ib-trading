

**修订并补充的 Google Cloud Run 部署计划**

(前面的项目架构分析和 Cloud Build 流程分析保持不变)

---
好的，我们来将这些调试后发现需要补充的命令整合进之前的一次性环境设置详细部署步骤中，并增加相应的标注。

## 部署到 Google Cloud Run 的详细步骤 (包含所有试错后补充内容)

**A. 一次性环境设置和手动操作 (在首次部署或重大环境变更时执行)**

这些步骤通常只需要执行一次。

```mermaid
graph TD
    A[开始] --> B(1. 登录gcloud CLI并设置项目);
    B --> C(2. 启用必要的Google Cloud API);
    C --> D(3. 创建或确认Cloud Run服务账号并授予核心权限);
    D --> D1(3.1 授予Cloud Build服务账号访问GCP资源的权限 ❗试错后补充);
    D1 --> E(4. 创建Artifact Registry仓库);
    E --> F(5. 构建并推送cloud-run/base基础镜像);
    F --> G(6. 创建BigQuery数据集和测试表 ❗试错后补充);
    G --> H(7. 创建Firestore数据库实例);
    H --> I(8. 创建并配置Google Secret Manager Secrets);
    I --> J(9. 授予Cloud Run服务账号访问Secrets的权限);
    J --> K(10. (可选)配置Cloud Build触发器);
    K --> L[环境设置完成];
```

**详细步骤：**

1.  **登录 gcloud CLI 并设置项目 (本地机器或 Cloud Shell)**
    ```bash
    gcloud auth login
    gcloud config set project gold-gearbox-424413-k1 # 已替换为您的项目ID
    ```

2.  **启用必要的 Google Cloud API (本地机器或 Cloud Shell)**
    ```bash
    gcloud services enable cloudbuild.googleapis.com \
                            run.googleapis.com \
                            artifactregistry.googleapis.com \
                            iam.googleapis.com \
                            secretmanager.googleapis.com \
                            bigquery.googleapis.com \
                            firestore.googleapis.com \
                            --project=gold-gearbox-424413-k1
    ```

3.  **创建或确认 Cloud Run 服务账号并授予核心权限 (本地机器或 Cloud Shell)**
    服务账号名称: `ib-trading`
    完整服务账号邮箱: `ib-trading@gold-gearbox-424413-k1.iam.gserviceaccount.com`
    *   **检查/创建服务账号 (如果不存在则创建):**
        ```bash
        PROJECT_ID="gold-gearbox-424413-k1"
        CR_SA_NAME="ib-trading"
        CR_SA_EMAIL="${CR_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

        gcloud iam service-accounts describe "${CR_SA_EMAIL}" --project="${PROJECT_ID}" > /dev/null 2>&1 || \
        gcloud iam service-accounts create "${CR_SA_NAME}" \
            --display-name="IB Trading Cloud Run Service Account" \
            --project="${PROJECT_ID}"
        ```
    *   **授予 IAM 角色给此 Cloud Run 服务账号 (使其能够访问所需资源)：**
        ```bash
        PROJECT_ID="gold-gearbox-424413-k1"
        CR_SA_EMAIL="ib-trading@${PROJECT_ID}.iam.gserviceaccount.com"

        # Secret Manager Secret Accessor (允许Cloud Run服务实例访问Secrets)
        gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
            --member="serviceAccount:${CR_SA_EMAIL}" \
            --role="roles/secretmanager.secretAccessor" \
            --condition=None # 确保无条件绑定

        # BigQuery User & Data Editor (允许Cloud Run服务实例读写BigQuery)
        gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
            --member="serviceAccount:${CR_SA_EMAIL}" \
            --role="roles/bigquery.user" \
            --condition=None
        gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
            --member="serviceAccount:${CR_SA_EMAIL}" \
            --role="roles/bigquery.dataEditor" \
            --condition=None

        # Firestore/Datastore User (允许Cloud Run服务实例读写Firestore)
        gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
            --member="serviceAccount:${CR_SA_EMAIL}" \
            --role="roles/datastore.user" \
            --condition=None
        ```

3.1. **(❗试错后补充) 授予 Cloud Build 服务账号 (`[PROJECT_NUMBER]@cloudbuild.gserviceaccount.com`) 访问 GCP 资源的权限**
    Cloud Build 服务账号在执行构建和测试（尤其是集成测试）以及部署时，需要相应的权限。
    您的项目ID是 `gold-gearbox-424413-k1`，项目编号是 `599151217267`。

    ```bash
    PROJECT_ID="gold-gearbox-424413-k1"
    PROJECT_NUMBER="599151217267" # 您提供的项目编号
    CB_SA_EMAIL="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
    CR_SA_EMAIL="ib-trading@${PROJECT_ID}.iam.gserviceaccount.com" # Cloud Run 服务账号

    # (❗试错后补充/确认) 允许 Cloud Build 服务账号部署到 Cloud Run (Cloud Run Admin 角色)
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
        --member="serviceAccount:${CB_SA_EMAIL}" \
        --role="roles/run.admin" \
        --condition=None # 确保无条件绑定

    # (❗试错后补充/确认) 允许 Cloud Build 服务账号作为 Cloud Run 服务账号 (ib-trading) 行事
    # (这样Cloud Run服务部署时可以被设置为使用 ib-trading 服务账号)
    gcloud iam service-accounts add-iam-policy-binding \
        "${CR_SA_EMAIL}" \
        --member="serviceAccount:${CB_SA_EMAIL}" \
        --role="roles/iam.serviceAccountUser" \
        --project="${PROJECT_ID}"

    # 允许 Cloud Build 服务账号写入 Artifact Registry
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
        --member="serviceAccount:${CB_SA_EMAIL}" \
        --role="roles/artifactregistry.writer" \
        --condition=None

    # (❗试错后补充) 授予 Cloud Build 服务账号 BigQuery User 和 BigQuery Data Editor 角色 (用于集成测试)
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
        --member="serviceAccount:${CB_SA_EMAIL}" \
        --role="roles/bigquery.user" \
        --condition=None
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
        --member="serviceAccount:${CB_SA_EMAIL}" \
        --role="roles/bigquery.dataEditor" \
        --condition=None

    # (❗试错后补充) 授予 Cloud Build 服务账号 Firestore/Datastore User 角色 (用于集成测试)
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
        --member="serviceAccount:${CB_SA_EMAIL}" \
        --role="roles/datastore.user" \
        --condition=None

    # (可选，如果集成测试需要访问Secrets) 授予 Cloud Build 服务账号 Secret Manager Secret Accessor 角色
    # gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    #     --member="serviceAccount:${CB_SA_EMAIL}" \
    #     --role="roles/secretmanager.secretAccessor" \
    #     --condition=None
    # (可选) 针对特定secret的权限 (如果上面项目级别的没给)
    # SECRET_NAME_USER="ib-gateway-username"
    # SECRET_NAME_PASS="ib-gateway-password"
    # gcloud secrets add-iam-policy-binding "${SECRET_NAME_USER}" --member="serviceAccount:${CB_SA_EMAIL}" --role="roles/secretmanager.secretAccessor" --project="${PROJECT_ID}"
    # gcloud secrets add-iam-policy-binding "${SECRET_NAME_PASS}" --member="serviceAccount:${CB_SA_EMAIL}" --role="roles/secretmanager.secretAccessor" --project="${PROJECT_ID}"
    ```
    **说明：** `--condition=None` 用于确保添加的绑定是无条件的，覆盖任何可能存在的同成员同角色的条件性绑定。

4.  **创建 Artifact Registry 仓库 (本地机器或 Cloud Shell)**
    (您已创建，此处为确认或首次设置)
    ```bash
    PROJECT_ID="gold-gearbox-424413-k1"
    AR_LOCATION="europe"

    # `cloud-run-repo` (用于应用程序镜像):
    gcloud artifacts repositories describe cloud-run-repo --location="${AR_LOCATION}" --project="${PROJECT_ID}" > /dev/null 2>&1 || \
    gcloud artifacts repositories create cloud-run-repo \
        --repository-format=docker \
        --location="${AR_LOCATION}" \
        --description="Docker repository for Cloud Run ib-trading application" \
        --project="${PROJECT_ID}"

    # `eu.gcr.io` (用于基础镜像，这是您 Artifact Registry 中的仓库名):
    gcloud artifacts repositories describe eu.gcr.io --location="${AR_LOCATION}" --project="${PROJECT_ID}" > /dev/null 2>&1 || \
    gcloud artifacts repositories create eu.gcr.io \
        --repository-format=docker \
        --location="${AR_LOCATION}" \
        --description="Repository for base images, named eu.gcr.io" \
        --project="${PROJECT_ID}"
    ```

5.  **构建并推送 `cloud-run/base` 基础镜像 (本地机器或 Cloud Shell)**
    (如果您的基础镜像内容没有变化，此步骤可能不需要重复执行)
    ```bash
    PROJECT_ID="gold-gearbox-424413-k1"
    AR_LOCATION="europe"
    BASE_IMAGE_REPO_IN_AR="eu.gcr.io" # Artifact Registry中基础镜像仓库的名称
    BASE_IMAGE_PATH_IN_REPO="cloud-run/base" # 镜像在仓库中的路径
    BASE_IMAGE_TAG="latest"
    FULL_BASE_IMAGE_NAME="${AR_LOCATION}-docker.pkg.dev/${PROJECT_ID}/${BASE_IMAGE_REPO_IN_AR}/${BASE_IMAGE_PATH_IN_REPO}:${BASE_IMAGE_TAG}"

    # 配置 Docker 认证 Artifact Registry：
    gcloud auth configure-docker "${AR_LOCATION}-docker.pkg.dev" --project="${PROJECT_ID}"

    # 进入 `cloud-run/base` 目录，构建并推送：
    # 假设您当前在项目根目录 ~/ib-trading
    cd ~/ib-trading/cloud-run/base  # 确保路径正确
    docker build -t "${FULL_BASE_IMAGE_NAME}" .
    docker push "${FULL_BASE_IMAGE_NAME}"
    cd ~/ib-trading # 返回项目根目录
    ```

6.  **(❗试错后补充) 创建 BigQuery 数据集和测试表 (本地机器或 Cloud Shell)**
    集成测试需要 `historical_data.test` 表。
    ```bash
    PROJECT_ID="gold-gearbox-424413-k1"
    BQ_LOCATION="EU" # BigQuery数据集的位置
    DATASET_ID="historical_data"
    TABLE_ID="test"

    # 检查并创建数据集 (如果不存在)
    bq show --project_id="${PROJECT_ID}" --format=prettyjson "${DATASET_ID}" > /dev/null 2>&1 || \
      bq --location="${BQ_LOCATION}" mk --dataset \
        --description="Dataset for historical trading data" \
        "${PROJECT_ID}:${DATASET_ID}"

    # 检查并创建表 (如果不存在)
    # Schema: date:DATE, instrument:STRING, key:STRING, value:FLOAT64
    bq show --project_id="${PROJECT_ID}" --format=prettyjson "${DATASET_ID}.${TABLE_ID}" > /dev/null 2>&1 || \
      bq mk --table \
        --description "Test table for integration tests" \
        "${PROJECT_ID}:${DATASET_ID}.${TABLE_ID}" \
        date:DATE,instrument:STRING,key:STRING,value:FLOAT64
    ```

7.  **创建 Firestore 数据库实例 (本地机器或 Cloud Shell / Google Cloud Console)**
    推荐通过 Cloud Console 首次创建以准确选择模式和位置。
    *   **通过 Cloud Console:**
        1.  导航到 Google Cloud Console > "Firestore"。
        2.  如果尚未创建，点击 "CREATE DATABASE" 或 "Select Native Mode"。
        3.  **选择模式:** "Native Mode"。
        4.  **选择位置:** 例如 `asia-northeast1` (东京), `asia-east2` (香港), 或与Cloud Run `asia-east1` 兼容的区域。**位置一旦选定，通常无法更改。**
        5.  点击 "CREATE DATABASE"。
    *   **通过 `gcloud` (如果已确定模式和位置，例如 Native Mode，位置 `asia-east1`):**
        ```bash
        PROJECT_ID="gold-gearbox-424413-k1"
        FIRESTORE_LOCATION="asia-east1" # 或您最终选择的位置

        # 检查数据库是否已存在
        # (gcloud firestore databases list --project=${PROJECT_ID} --format="value(name)" | grep -q "(default)") || \
        # 由于创建命令如果存在会报错，可以直接尝试创建
        gcloud firestore databases create --location="${FIRESTORE_LOCATION}" --type=firestore-native \
            --project="${PROJECT_ID}" || echo "Firestore database likely already exists or there was an issue with the location/type."
        ```
        **注意：** `asia-east1` (台湾彰化) 支持 Firestore。

8.  **创建并配置 Google Secret Manager Secrets (本地机器或 Cloud Shell)**
    (如果已创建且内容正确，则无需重复)
    ```bash
    PROJECT_ID="gold-gearbox-424413-k1"
    SECRET_NAME_USER="ib-gateway-username"
    SECRET_NAME_PASS="ib-gateway-password"

    # 检查并创建用户名的 Secret
    gcloud secrets describe "${SECRET_NAME_USER}" --project="${PROJECT_ID}" > /dev/null 2>&1 || \
    echo -n "your_actual_ib_username" | gcloud secrets create "${SECRET_NAME_USER}" \
        --data-file=- \
        --replication-policy=automatic \
        --project="${PROJECT_ID}"

    # 检查并创建密码的 Secret
    gcloud secrets describe "${SECRET_NAME_PASS}" --project="${PROJECT_ID}" > /dev/null 2>&1 || \
    echo -n "your_actual_ib_password" | gcloud secrets create "${SECRET_NAME_PASS}" \
        --data-file=- \
        --replication-policy=automatic \
        --project="${PROJECT_ID}"
    ```
    将 `your_actual_ib_username` 和 `your_actual_ib_password` 替换为您的真实凭据。

9.  **授予 Cloud Run 服务账号访问 Secrets 的权限 (本地机器或 Cloud Shell)**
    (如果您已正确授予，则无需重复)
    ```bash
    PROJECT_ID="gold-gearbox-424413-k1"
    CR_SA_EMAIL="ib-trading@${PROJECT_ID}.iam.gserviceaccount.com"
    SECRET_NAME_USER="ib-gateway-username"
    SECRET_NAME_PASS="ib-gateway-password"

    gcloud secrets add-iam-policy-binding "${SECRET_NAME_USER}" \
        --member="serviceAccount:${CR_SA_EMAIL}" \
        --role="roles/secretmanager.secretAccessor" \
        --project="${PROJECT_ID}"
    gcloud secrets add-iam-policy-binding "${SECRET_NAME_PASS}" \
        --member="serviceAccount:${CR_SA_EMAIL}" \
        --role="roles/secretmanager.secretAccessor" \
        --project="${PROJECT_ID}"
    ```

10. **(可选) 配置 Cloud Build 触发器 (Google Cloud Console)**
    如果您希望在代码推送到 Git 仓库时自动运行构建和部署，可以设置 Cloud Build 触发器。

---

**B. 每次代码变更后的部署流程 (在 Cloud Shell 或配置了 gcloud 的本地机器)**

1.  **确保代码已提交到 Git 仓库并拉取最新代码：**
    ```bash
    # 假设当前在项目根目录 ~/ib-trading
    # git add .
    # git commit -m "Your commit message"
    # git push origin your-branch
    git pull origin master # 或者您的开发分支
    ```

2.  **运行 Cloud Build 部署：**
    ```bash
    GIT_TAG=$(git rev-parse --short HEAD)
    gcloud builds submit --config cloud-run/application/cloudbuild.yaml \
      --substitutions=_TRADING_MODE=paper,_GCP_REGION=asia-east1,_MY_IMAGE_TAG=${GIT_TAG:-manual-latest} .
    ```

---
**关于 `TWS_INSTALL_LOG` 的说明：**

在您的 `cloudbuild.yaml` 的集成测试步骤中，`TWS_INSTALL_LOG` 环境变量的设置依然很重要。如果 Cloud Build 环境中没有一个真实的 IB Gateway 安装过程，那么 `integration_tests.py` 将无法从中提取 `twsVersion`。
您需要：
*   **确认该环境变量在 Cloud Build 的集成测试步骤中是如何被设置的，以及它指向的文件内容是什么。**
*   如果它依赖于一个在 Cloud Build 中不会发生的过程，您可能需要在 `cloudbuild.yaml` 的该步骤中通过 `--env TWS_VERSION=XXX` 来直接提供一个模拟的 TWS 版本号，并在 `integration_tests.py` 中优先使用这个环境变量，而不是尝试解析一个可能不存在的日志文件。

例如，在 `cloudbuild.yaml` 的集成测试步骤中：
```yaml
  # ...
  - "--env"
  - "MOCK_TWS_VERSION=981" # 提供一个模拟版本
  - "--env"
  - "TWS_INSTALL_LOG=/tmp/dummy_install.log" # 可以指向一个空文件或包含模拟内容的文件
  # ...
```
然后在 `integration_tests.py` 中：
```python
# ...
mock_tws_version = environ.get('MOCK_TWS_VERSION')
extracted_tws_version = None

if mock_tws_version:
    extracted_tws_version = mock_tws_version
    print(f"Using MOCK_TWS_VERSION: {extracted_tws_version}")
else:
    # ... (原来的 TWS_INSTALL_LOG 解析逻辑) ...
    tws_version_match = re.search('IB Gateway ([0-9]{3})', install_log_content)
    if tws_version_match:
        extracted_tws_version = tws_version_match.group(1)
    else:
        print("Warning: IB Gateway version pattern not found in install_log_content and MOCK_TWS_VERSION not set.")

ibc_config = {
    'gateway': True,
    'twsVersion': extracted_tws_version, # 现在优先使用 mock 版本
    **env_vars
}
# ...
```
这将使您的集成测试在 Cloud Build 环境中更稳定。

