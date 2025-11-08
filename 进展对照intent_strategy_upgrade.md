对照 `intent_strategy_upgrade.md`，当前完成度与待办如下：

- ✅ **策略改造**：`testsignalgenerator`、`spy_macd_vixy` 已改写为只输出 Firestore 目标仓位（参见 `cloud-run/application/app/strategies/*.py`），Commander 从 `positions/{mode}/latest_portfolio` 读取真实仓位并集中决策（`intents/allocation.py`）。
- ✅ **Orchestrator 流程**：`/` POST 已代理到 orchestrator，顺序执行“策略 → 对账 → Commander”，并在 503 时提示 IB 重连状态（`main.py:117-165`、`intents/orchestrator.py`）。根路由 GET 提供健康检查，便于 Cloud Run/Scheduler 校验。
- ✅ **持仓快照与序列化**：`reconcile` 统一写入 `positions/{trading_mode}/latest_portfolio`；自研 `lib/ib_serialization.contract_to_dict` 解决 ib_insync 兼容性并清理 Firestore 写入路径。
- ✅ **单测/脚本验证**：`python -m unittest discover -s _tests -t .` 通过；`verify_trading.py --show-intents` 在 paper 环境输出最新指令与敞口；Cloud Run 实例经 `curl` 验证返回 200。
- ⚠️ **待完成**
  1. **调度编排切换**：准备创建 `orchestrator-daily-run`（POST `https://ib-paper-.../`，JSON 载荷 `{"strategies":["testsignalgenerator","spy_macd_vixy"],"dryRun":true,"runReconcile":true}`，OIDC 服务账号 `ib-trading@…`），并逐步停用旧作业（`daily-reconciliation-job`、`eod-allocation-job`、`high-frequency-test-runner`）；待 Cloud Scheduler/Workflows 调整后即可勾掉此项。
  2. **多策略迁移**：除 `testsignalgenerator`、`spy_macd_vixy` 外，其余策略仍使用旧路径/命名，需要按计划迁移 Firestore 配置及风险预算（文档第 3.1 节）。
  3. **Secret & 凭证治理**：确认 Secret Manager 中 `ib-*-username/password` 的版本轮换策略，补充自动化检测（若凭证失效会导致 503）。
  4. **策略预算孤立**：在 `strategies/{id}` 配置中增加 `allowed_symbols`/`max_notional` 等约束，策略生成目标时遵守；Commander 在 `Allocation._collect_strategy_targets` → `order_plan` 之间插入权重裁剪逻辑，确保多策略共存仍按各自资金池执行，互不干扰。
  5. **监控告警**：落地针对 orchestrator 503/超时的 Cloud Logging Metric 或 Error Reporting 告警，保证 Gateway 断线可及时通知运维。

下一步建议按上述待办优先级推进，完成调度切换→策略迁移→凭证治理→监控告警的闭环。***


## 修复工程：对账 & Commander 可观测性（11-08 启动）

1. **修复 `orderToDict` 崩溃**（`cloud-run/application/app/intents/reconcile.py`）  
   - 做法：改用 `lib/ib_serialization.order_to_dict` 或手动序列化 ib_insync 订单对象，确保字段齐全；为空缺值设默认。  
   - 验证：  
     1) 在 `cloud-run/application/app` 执行 `python -m unittest discover -s _tests -t .`，其中新增的 Reconcile 单测 mock `ibgw.openTrades()` 并断言 `open_orders` 结构。  
     2) `uvicorn main:app --reload` 后 `curl -X POST http://localhost:8080/reconcile`，确认 HTTP 200、日志无 AttributeError。  
   - 估时：约 1~1.5 小时（含测试）。

2. **IB Gateway 连接稳固化**  
   - 做法：在 `main.py` 的 `ib_thread_loop` 外层连接逻辑引入指数退避与健康探针（例如 `reqCurrentTimeAsync` 成功视为 ready），同时复核 4002 端口、证书/隧道配置。  
   - 验证：  
     1) 沙箱里模拟端口关闭，观察日志是否按退避节奏重试。  
     2) 真实环境跑一轮 orchestrator，核查 `Warning 1100` 与 `TimeoutError` 是否下降。  
   - 估时：~2–3 小时。

3. **策略选择逻辑显式化**  
   - 做法：通过 env/Firestore 开关控制是否强制注册 `testsignalgenerator`；生产默认仅启用真实策略，并在日志打印当前策略列表。  
   - 验证：  
     1) 部署后 hit `/` 或 `/orchestrator`，确认日志只列出期望策略。  
     2) 检查 `strategies/*/intent/latest` 文档，验证真实策略目标仓位更新。  
   - 估时：~1 小时。

4. **Commander 阶段日志可见性**  
   - 做法：在 `Allocation._core_async` 中 `order_plan` 生成后、下单前新增 `self._env.logging.info("Commander: planned %d orders; %s %d", ...)`，dry-run 时输出 “simulated”；否则输出实际下单数。同步把该 summary 写入执行文档。  
   - 当前状态：代码已提交；待部署后通过 orchestrator 调用验证日志输出。  
   - 估时：<20 分钟。

5. **统一验证步骤（适用于上述每项）**  
   - 代码改动后在 `cloud-run/application/app` 跑 `python -m unittest discover -s _tests -t .`。  
   - 必要时 `uvicorn main:app --reload` + mock IB 走端到端流程。  
   - 最终以一次 orchestrator 调用验证“策略 → Reconcile → Commander”完整链路，并确认 `Allocation` 新增的日志出现。***

## 项目整体工程顺序（建议）
1. **稳定基础设施**：完成 `orderToDict` 修复 + Gateway 退避改造（本修复工程第 1-2 项），确保对账/连接可靠。
2. **策略运行规范化**：落地策略选择开关 & Commander 日志（修复工程第 3-4 项，已提交代码，待部署验证），同时推进“策略预算隔离”待办（为每个策略配置 allowed symbols、资金上限，并在 Commander 做权重裁剪）。
3. **编排切换**：创建新的 orchestrator Scheduler/Workflows，逐步替换旧作业（待办 1）。
4. **多策略迁移**：按架构要求迁移剩余策略及 Firestore 配置（待办 2）。
5. **Secret / 凭证治理**（待办 3）。
6. **监控 & 告警**（待办 5），覆盖 orchestrator 超时、Gateway 断线、策略意图缺失等关键指标。



• - 这一步改的是 IB 背景线程的连接退避/探针逻辑，属于系统级基础设施。建议尽早部署到 Cloud Run：只有跑在真实 Gateway 环境下，才能观察连接日
    志是否按预期退避、以及 4002 端口偶发故障时的恢复速度。部署后可顺便跑一次 orchestrator dry-run（POST / with {"dryRun": true}）验证整条
    链路。
  - 工程顺序上，下一阶段“策略规范化”（取消强制 test 策略、Commander 打日志、策略预算配置）和“调度切换”可以并行开发，但最好按“代码→本地单测→
    一次性部署”分批提交，以免多项修改同时上线时难以定位问题。推荐节奏：
      1. 当前退避补丁：部署 + Cloud Run 验证 → 形成基线。
      2. 策略规范化 & Commander 日志：这两个改动都在应用层（orchestrator/allocation），可以合在一个发布批次，部署后一次 orchestrator 调用即
         可同时验证“策略不再被 override + Commander 日志出现”。
      3. 调度切换：在应用层稳定后，再调整 Cloud Scheduler/Workflows；这涉及 GCP 配置，最好在前两批上线、稳定运行后再做，避免同时调度和代码变
         化导致排障困难。
