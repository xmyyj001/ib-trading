# IB-Trading 运维手册

> 最新验证：2025-11-09（Cloud Run dry-run + Firestore guardrail 配置）

本仓库承载 Cloud Run 上的 IB 自动化交易服务。系统采用 FastAPI + ib_insync 后台线程，所有交易通过 HTTP 意图（Intent）触发。该文档面向需要 **配置、部署、运行与排障** 的工程师，聚焦实操步骤。

---

## 1. 快速上手

### 1.1 先决条件

- Python 3.11+
- gcloud CLI（`gcloud auth login && gcloud auth application-default login`）
- 对 `gold-gearbox-424413-k1` Firestore、Cloud Run、Artifact Registry、Secret Manager 的访问权限
- IB Gateway 纸面账户凭证存于 Secret Manager (`ib-paper-username/password`)

### 1.2 本地环境

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r cloud-run/application/app/requirements.txt
cd cloud-run/application/app
python -m unittest
```

> 单测默认使用 mock，无需真实 IB 连接。

---

## 2. Firestore 配置与 Guardrail

Firestore 是“意图总线”：`config/*` 保存全局开关和曝光，`strategies/{id}` 保存策略配置/guardrail，`positions/{mode}/latest_portfolio/snapshot` 保存对账快照。

### 2.1 初始化（仅新环境或灾备）

```bash
python scripts/firestore/init_firestore.py gold-gearbox-424413-k1
```

该脚本会重写 `config/common`、`config/paper`、`config/live`，默认曝光 0.90、33%/33%/34%。

### 2.2 日常调优（推荐）

```bash
python scripts/firestore/setting_firestore.py \
  --project-id gold-gearbox-424413-k1 \
  --overall-exposure 0.90 \
  --testsignalgenerator-weight 0.33 \
  --spy-macd-vixy-weight 0.33 \
  --reserve-weight 0.34 \
  --testsignalgenerator-max-notional 600000 \
  --spy-macd-vixy-max-notional 600000
```

- 加 `--dry-run` 可先查看 payload。
- 适用于新增策略、调整预算或更新 `allowed_symbols` / `max_notional`。

### 2.3 验证配置

```bash
python query_firestore.py gold-gearbox-424413-k1
```

脚本会列出 `config` 集合、`positions/paper/latest_portfolio/snapshot`、`activity` 最新文档，便于检查 exposure 和对账快照。

---

## 3. 部署与更新

1. `source deployment_vars.sh`（包含 `PROJECT_ID`, `GCP_REGION`, `TRADING_MODE` 等）
2. 构建并部署：
   ```bash
   gcloud builds submit --config cloud-run/application/cloudbuild.yaml cloud-run/application \
     --substitutions _REGION=us-central1,_SERVICE_NAME=ib-paper,_TRADING_MODE=paper,_INIT_FIRESTORE=true
   ```
3. Cloud Build 流程包含：
   - 构建/推送应用镜像
   - 运行 `scripts/firestore/init_firestore.py`（会覆盖 Firestore！可通过 `_INIT_FIRESTORE=false` 跳过）
   - 部署 Cloud Run revision（服务账号 `ib-trading@PROJECT.iam.gserviceaccount.com`）

> 部署完成后，获取服务 URL：  
> `gcloud run services describe ib-paper --region us-central1 --format="value(status.url)"`

### 3.1 Firestore 回写（部署后必须执行）

`init_firestore.py` 会把 `config/common`、`config/paper` 等文档重置为模板值。若你在运行 `gcloud builds submit` 时使用 `_INIT_FIRESTORE=false`，可跳过重置；否则请在部署结束后立即运行 `setting_firestore.py` 恢复实际曝光与 guardrail：

```bash
python scripts/firestore/setting_firestore.py \
  --project-id gold-gearbox-424413-k1 \
  --overall-exposure 0.90 \
  --testsignalgenerator-weight 0.33 \
  --spy-macd-vixy-weight 0.33 \
  --reserve-weight 0.34 \
  --testsignalgenerator-max-notional 600000 \
  --spy-macd-vixy-max-notional 600000
```

生产环境建议直接在 Cloud Build YAML 中禁用 `Initialize-Firestore` 步骤，仅在全新项目/灾备恢复时启用；否则每次部署都需要重新落库。

---

## 4. 运行方式与 API

### 4.1 入口与环境

- Cloud Run 服务：`ib-paper`（us-central1）
- 根路由 `POST /` 代理到 orchestrator；`GET /` 返回健康信息
- 后台线程与 IB Gateway 通过 4002 端口通信，断线会返回 503

### 4.2 常用 Intent

| Intent | 说明 | 示例 |
| --- | --- | --- |
| `/` or `/orchestrator` | 顺序执行“策略 → reconcile → commander` | `curl -X POST ${URL}/ -H "Authorization: Bearer ${TOKEN}" -d '{"strategies":["testsignalgenerator","spy_macd_vixy"],"dryRun":true,"runReconcile":true}'` |
| `/testsignalgenerator` | 仅写 Firestore 目标仓位，不下单 | `curl -X POST ${URL}/testsignalgenerator -d '{"dryRun":true}' ...` |
| `/spy_macd_vixy` | 同上，生成 SPY/VIXY 目标组合 | |
| `/reconcile` | 拉取 IB 持仓/未结订单，写入 `positions/{mode}/latest_portfolio/snapshot` | `curl -X POST ${URL}/reconcile -d '{"dryRun":true}' ...` |
| `/allocation` | Commander：读取 Firestore 意图 + 快照，生成订单（dryRun 默认 false） | `curl -X POST ${URL}/allocation -d '{"dryRun":true}' ...` |
| `/summary` | 快速查看账户摘要 | `curl -X GET ${URL}/summary ...` |
| `/close-all` | 平掉所有仓位并取消挂单（慎用） | `curl -X POST ${URL}/close-all -d '{}' ...` |

所有请求都需要 Identity Token：  
`TOKEN=$(gcloud auth print-identity-token)`

### 4.3 Cloud Scheduler

- us-central1 `orchestrator-daily-run` 每日调用 `POST /`，当前 payload 默认 `dryRun:true`
- 需要恢复真实下单时：  
  `gcloud scheduler jobs update http orchestrator-daily-run --message-body='{"strategies":["testsignalgenerator","spy_macd_vixy"],"dryRun":false,"runReconcile":true}' ...`

---

## 5. 验证与监控

### 5.1 手动验证

1. **IB 就绪探针**  
   `curl -X POST ${URL}/reconcile -H "Authorization: Bearer ${TOKEN}" -d '{"dryRun":true}'`  
   - 成功返回 holdings/open_orders 表示网关可用  
   - `503` 或 `Service is busy` 表示后台线程仍在重连

2. **全链路 dry-run**  
   `curl -X POST ${URL}/ -H "Authorization: Bearer ${TOKEN}" -d '{"strategies":["testsignalgenerator","spy_macd_vixy"],"dryRun":true,"runReconcile":true}'`

3. **脚本**  
   `python verify_trading.py --show-intents --project-id gold-gearbox-424413-k1 --strategies testsignalgenerator spy_macd_vixy`

### 5.2 观察 Firestore

- `positions/paper/latest_portfolio/snapshot`：最新对账快照  
- `strategies/<id>/intent/latest`：策略输出（`status`, `target_positions`, `metadata`）  
- `executions/{auto_id}`：Commander 执行记录（`orders`, `diff`, `context.strategy_intents_refs`）

### 5.3 Cloud Logging / Error Reporting

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="ib-paper"' \
  --limit=50 --freshness=10m --format="value(timestamp,textPayload)"
```

重点关注：
- `IB Thread (Outer Loop)` 连续报错 ⇒ Gateway 无法连接
- `Service is busy` ⇒ 请求队列已满（并发 >4）
- Commander INFO：`Planned X orders; simulated Y | missing=[] | stale=[]`

---

## 6. 常见问题 & 对策

| 问题 | 定位 | 处理 |
| --- | --- | --- |
| `config` 集合为空 | Firestore 未初始化或被清空 | 运行 `scripts/firestore/init_firestore.py` 或 `setting_firestore.py` 补写配置 |
| `exposure.strategies` 显示 1.0/1.0 | guardrail 未更新 | 运行 `scripts/firestore/setting_firestore.py ...` 并复查 Commander 输出 |
| `/` 返回 503 `Service is busy` | 请求队列满或 IB 重连 | 等待后台线程恢复，或减少并发调用；必要时重启 Cloud Run revision |
| Commander `missing_strategies` | Firestore 未找到策略文档 | 确认 `strategies/{id}` 存在且 `enabled=true`，`updated_at` 在 `freshMinutes` 内 |
| IB 警告 1100/1102 | Gateway 断线或重连 | 检查 Secret Manager 凭证、4002 端口、底层 VM（GKE/Compute）是否运行 |

---

## 7. 后续工作状态（2025-11）

1. 多策略迁移：其余生产策略尚未接入 orchestrator，需要按意图模型重构并设置 guardrail。
2. Secret & 凭证治理：制定 `ib-*-username/password` 轮换与告警策略，防止凭证过期导致 503。
3. 监控与告警：为 orchestrator 503/超时、IB 断线、Scheduler 失败创建 Cloud Logging Metric 或 Error Reporting 通知。
4. Scheduler 正式化：待 ops 批准后，将 `orchestrator-daily-run` payload 切换到 `dryRun:false`，进入真实交易模式。

---

## 8. 参考脚本 & 文档

- `scripts/firestore/init_firestore.py` / `scripts/firestore/setting_firestore.py`：配置管理
- `query_firestore.py`：查询 Firestore 关键集合
- `verify_trading.py`：本地/Cloud Run 结果校验
- `intent_strategy_upgrade.md`：架构与迁移计划
- `进展对照intent_strategy_upgrade.md`：最新进度对照表

如需更多背景或历史方案，可查阅 `AGENTS.md`, `cloud_run_deployment_plan.md`, `scenario_a_swing_trader.md` 等文档。

---

## 9. 新策略开发规范

该规范确保新增策略遵循“策略输出 → Commander 执行”的架构，并能够被 orchestrator 正确编排。

1. **目录与命名**
   - 在 `cloud-run/application/app/strategies/` 下新增 `your_strategy_name.py`。
   - 类名建议采用 `CamelCaseIntent`（例如 `MyNewStrategyIntent`），并继承 `intents.intent.Intent`。
   - 文件名与 Firestore 文档 ID / API 路径保持一致（`strategies/my_new_strategy`、`/my_new_strategy`）。

2. **代码结构**
   - 构造函数应接收 `strategy_id`, `dryRun`, `freshMinutes` 等，沿用 `TestSignalGenerator`/`SpyMacdVixyIntent` 的模版。
   - 核心逻辑放在 `async def _core_async(self)`，严禁阻塞调用；所有 IB 操作需 `await` ib_insync 方法。
   - 输出必须写入 Firestore：`strategies/{strategy_id}/intent/latest`，字段至少包含
     ```json
     {
       "updated_at": "...",
       "status": "success" | "error",
       "error_message": null | "...",
       "metadata": {...},            // 策略自定义指标
       "target_positions": [
         {
           "symbol": "SPY",
           "secType": "STK",
           "exchange": "SMART",
           "currency": "USD",
           "quantity": 100,
           "price": 450.0,
           "contract": {...}         // lib.ib_serialization.contract_to_dict
         }
       ]
     }
     ```
   - 失败时务必写入 `status="error"` 并抛出异常，以便 orchestrator 捕获。

3. **注册与配置**
   - 在 `cloud-run/application/app/intents/orchestrator.py` 的 `STRATEGY_INTENT_REGISTRY` 中注册新策略。
   - 使用 `scripts/firestore/setting_firestore.py` 为该策略配置曝光权重、`allowed_symbols`、`max_notional`：
     ```bash
     python scripts/firestore/setting_firestore.py \
       --project-id gold-gearbox-424413-k1 \
       --overall-exposure 0.90 \
       --your-strategy-weight 0.20 \
       --your-strategy-max-notional 400000 \
       --reserve-weight 0.30 \
       --dry-run   # 预览后去掉
     ```
     （如脚本未内置该策略，可仿照现有逻辑扩展参数。）

4. **测试与验证**
   - 为策略添加至少一个单测（可在 `cloud-run/application/app/strategies/_tests/` 或意图级 `_tests` 中 mock IB 数据）。
   - 本地运行 `python -m unittest`，再通过 `verify_trading.py --show-intents --strategies your_strategy` 检查 Firestore 文档。
   - 在 Cloud Run 上以 dry-run 调用 orchestrator，确认 Commander 日志 `missing[]/stale[]`。

5. **Observability**
   - 在策略日志中输出关键信号（`self._env.logging.info`），但避免泄露凭证。
   - 确保 `metadata` 字段包含诊断所需信息（行情、信号值、原因标签等），以便 `activity` 文档提供上下文。

遵循以上步骤可确保新策略平滑接入 orchestrator 流水线，并与现有 guardrail、监控体系兼容。
