# Cloud Run 新版服务部署步骤（Commander 架构）

## 1. 目标与交付物

本指南面向已完成本地验证且准备上线“策略意图分离 + 总指挥”架构的新版本服务。目标是在 Google Cloud Run 上部署一套带有效 IB 凭证的 `application` 镜像，并确保：

* Cloud Run 服务上线后能够连接正式 IB Gateway，生成 Firestore 的 `strategies/<id>/intent/latest` 与 `positions/paper/latest_portfolio` 文档。
* `/orchestrator` 支持 `dryRun` 调用，可由 Cloud Scheduler 或手工触发。
* 部署结束即具备回滚手段和日志观测路径。

## 2. 代码仓库准备

为避免影响正在运行的仓库，请在全新目录中检出待部署分支。

1. **新建工作目录并克隆代码**
   ```bash
   mkdir -p ~/deployments && cd ~/deployments
   git clone <your_repo_url> ib-trading-deploy
   cd ib-trading-deploy
   git checkout <target_branch>
   ```
2. **同步部署变量模板**：复制当前生产环境的 `deployment_vars.sh`，或根据最新密钥手动填充。确保文件仅存在于本次部署目录，避免与老仓库共享。

> 之后所有命令均在此独立仓库内执行。

## 3. 前置条件检查

1. **环境变量**：确认 `deployment_vars.sh` 包含如下关键项且值正确：  
   `PROJECT_ID`, `GCP_REGION`, `SERVICE_NAME_BASE`, `IMAGE_REPO`, `IB_USERNAME_SECRET`, `IB_PASSWORD_SECRET`, `SERVICE_ACCOUNT_EMAIL`, `IB_USERNAME`, `IB_PASSWORD`, `CLOUD_BUILD_REGION`（推荐与 `GCP_REGION` 相同）。
2. **本地凭证**：运行 `gcloud auth list` 确认当前账号已登录，并使用 `gcloud config list project` 校验默认项目。
3. **代码状态**：确保工作区包含待部署分支的最新代码，必要时执行 `git status` 保证没有漏提的本地修改。
4. **网络要求**：本地环境需可访问 gcloud 与 Artifact Registry；若在 Cloud Shell，确认会话拥有部署权限。

## 4. 部署准备

> 以下命令默认在仓库根目录执行，如未显式说明均需 `source deployment_vars.sh` 预加载变量。

1. **加载部署变量**  
   ```bash
   source deployment_vars.sh
   ```
2. **启用所需 API（首部署或跨项目执行时）**  
   ```bash
   gcloud services enable \
     run.googleapis.com \
     cloudbuild.googleapis.com \
     artifactregistry.googleapis.com \
     iam.googleapis.com \
     secretmanager.googleapis.com
   ```
3. **Artifact Registry 仓库校验**：确认 `IMAGE_REPO` 指向的仓库位于与 Cloud Run 相同的地区；若尚未创建则执行：
   ```bash
   gcloud artifacts repositories describe ${SERVICE_NAME_BASE}-app \
     --location=${GCP_REGION} \
     --format="value(name)" >/dev/null 2>&1 || \
   gcloud artifacts repositories create ${SERVICE_NAME_BASE}-app \
     --repository-format=docker \
     --location=${GCP_REGION} \
     --description="IB Trading application images"
   ```
   *如已存在，可跳过或使用 `gcloud artifacts repositories describe` 校验 `location`.*
4. **Secret 准备**（仅当首次或需更新 IB 凭据时执行）  
   ```bash
   gcloud secrets describe ${IB_USERNAME_SECRET} --project=${PROJECT_ID} >/dev/null 2>&1 || \
     gcloud secrets create ${IB_USERNAME_SECRET} --replication-policy="automatic" --project=${PROJECT_ID}
   printf "%s" "${IB_USERNAME}" | \
     gcloud secrets versions add ${IB_USERNAME_SECRET} --data-file=-

   gcloud secrets describe ${IB_PASSWORD_SECRET} --project=${PROJECT_ID} >/dev/null 2>&1 || \
     gcloud secrets create ${IB_PASSWORD_SECRET} --replication-policy="automatic" --project=${PROJECT_ID}
   printf "%s" "${IB_PASSWORD}" | \
     gcloud secrets versions add ${IB_PASSWORD_SECRET} --data-file=-
   ```
5. **服务账号权限校验**：快速检查关键角色是否已绑定；若缺失则追加绑定。  
   ```bash
   gcloud projects get-iam-policy ${PROJECT_ID} \
     --flatten="bindings[]" \
     --filter="bindings.members:serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
     --format="value(bindings.role)"
   ```
   *缺失角色时，使用 `gcloud projects add-iam-policy-binding` 附加权限。*
6. **构建并推送 Base 镜像**（首次迁移到新地区时必须执行）  
   ```bash
   gcloud builds submit \
     --region=${CLOUD_BUILD_REGION} \
     --config cloud-run/base/cloudbuild.yaml \
     --substitutions=_BASE_IMAGE=${BASE_IMAGE_URL}
   ```
   *成功后，`${BASE_IMAGE_URL}` 会在新仓库中可用，后续应用镜像构建才能顺利拉取。*

## 5. 构建并上传应用镜像

1. **运行 Cloud Build 部署**（默认使用 `cloud-run/application/cloudbuild.yaml`）  
   ```bash
   gcloud builds submit \
     --region=${CLOUD_BUILD_REGION} \
     --config cloud-run/application/cloudbuild.yaml \
     --substitutions=_REGION=${GCP_REGION},_SERVICE_NAME=${CLOUD_RUN_SERVICE_NAME},_SERVICE_ACCOUNT=${SERVICE_ACCOUNT_EMAIL},_TRADING_MODE=${TRADING_MODE},_BASE_IMAGE_URL=${BASE_IMAGE_URL},_APPLICATION_IMAGE=${APPLICATION_IMAGE},_IMAGE_TAG=${IMAGE_TAG},_USERNAME_SECRET=${IB_USERNAME_SECRET},_PASSWORD_SECRET=${IB_PASSWORD_SECRET}
   ```
   *Build 完成后会自动 push 镜像并触发部署；Artifact Registry 中应出现带新 tag 的 `application` 镜像。*

2. **记录构建版本**：留存 `BUILD_ID` 与镜像 tag，方便回滚。  
   ```bash
   gcloud builds describe ${BUILD_ID} --format='value(images[0])'
   ```

## 6. 部署 Cloud Run 服务

Cloud Build 的 `Deploy-to-Cloud-Run` 步骤会自动发布新修订。完成后执行以下命令确认部署结果。

1. **预检查当前修订版本**  
   ```bash
   gcloud run services describe ${CLOUD_RUN_SERVICE_NAME} \
     --platform=managed \
     --region=${GCP_REGION} \
     --format='value(status.latestReadyRevisionName)'
   ```
2. **验证修订就绪**  
   ```bash
   gcloud run services describe ${CLOUD_RUN_SERVICE_NAME} \
     --platform=managed \
     --region=${GCP_REGION} \
     --format='value(status.latestCreatedRevisionName,status.latestReadyRevisionName)'
   ```
   *只有当 `latestCreated` 与 `latestReady` 一致时，服务才算完成发布。*

## 7. 部署后验证

1. **日志确认**：在 Cloud Logging 中筛选新修订的 `stdout`/`stderr`，确认 IB Gateway 登录成功、`spy_macd_vixy` 与 `reconcile` 执行无异常。
   ```bash
   gcloud logging read \
     "resource.type=cloud_run_revision AND resource.labels.service_name=${CLOUD_RUN_SERVICE_NAME}" \
     --limit=50 --freshness=1h --format="json" >logging50.txt
   ```
2. **Dry-Run 调用**：使用 Cloud Shell 或本地 `curl` 触发 orchestrator。
   ```bash
    unset ORCHESTRATOR_URL
   export ORCHESTRATOR_URL="https://ib-paper-599151217267.us-central1.run.app"

   curl -X POST "${ORCHESTRATOR_URL}" \
     -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
     -H "Content-Type: application/json" \
     -d '{"strategies":["testsignalgenerator","spy_macd_vixy"],"dryRun":true,"runReconcile":true}'
   ```

   * check running details:
   ```
   gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="ib-paper"' \
      --project=gold-gearbox-424413-k1 \
      --freshness=5m \
      --format="table(timestamp, severity, textPayload)" 
      ```

3. **Firestore 快照检查**（使用 `verify_trading.py` 或 `gcloud firestore`）  
   * 运行 `python verify_trading.py --mode paper`；输出应显示非零 `net_liquidation` 与最新 `updated_at`。  
   * 在 Firestore 控制台确认 `strategies/spy_macd_vixy/intent/latest` 与 `positions/paper/latest_portfolio` 已生成并刷新时间戳。

4. **Scheduler 验证**（如已配置）  
   ```bash
   gcloud scheduler jobs run daily-strategy-orchestrator --location=${GCP_REGION}
   gcloud scheduler jobs describe daily-strategy-orchestrator --location=${GCP_REGION}
   ```

## 8. 回滚策略

1. **快速回滚**：将 Cloud Run 服务流量切回上一修订。
   ```bash
   gcloud run services update-traffic ${CLOUD_RUN_SERVICE_NAME} \
     --platform=managed \
     --region=${GCP_REGION} \
     --to-revisions ${PREV_REVISION}=100
   ```
2. **镜像回滚**：若需彻底恢复旧版本，使用旧 tag 重新执行部署命令。
3. **日志保留**：记录失败时间段的日志与 Firestore 快照，便于根因分析。

## 9. 后续动作

* 将 Cloud Logging 中的关键日志加入监控或告警策略（IB 登录失败、策略缺失等）。
* 更新 `daily-strategy-orchestrator` 的请求体参数，确保引入新增策略或更改调度窗口时具备配置文件支撑。
* 在下一次代码改动前运行 `python -m unittest discover -s _tests -t .`，保持部署即测试的纪律。
