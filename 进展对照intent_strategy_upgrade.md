对照 `intent_strategy_upgrade.md`，当前完成度与待办如下：

- ✅ **策略改造**：`testsignalgenerator`、`spy_macd_vixy` 已改写为只输出 Firestore 目标仓位（参见 `cloud-run/application/app/strategies/*.py`），Commander 从 `positions/{mode}/latest_portfolio` 读取真实仓位并集中决策（`intents/allocation.py`）。
- ✅ **Orchestrator 流程**：`/` POST 已代理到 orchestrator，顺序执行“策略 → 对账 → Commander”，并在 503 时提示 IB 重连状态（`main.py:117-165`、`intents/orchestrator.py`）。根路由 GET 提供健康检查，便于 Cloud Run/Scheduler 校验。
- ✅ **持仓快照与序列化**：`reconcile` 现已同步写入 `positions/{trading_mode}/latest_portfolio/snapshot`（同时保留嵌入式 `latest_portfolio` 以兼容旧逻辑）；自研 `lib/ib_serialization.contract_to_dict` 解决 ib_insync 兼容性并清理 Firestore 写入路径。
- ✅ **单测/脚本验证**：`python -m unittest discover -s _tests -t .` 通过；`verify_trading.py --show-intents` 在 paper 环境输出最新指令与敞口；Cloud Run 实例经 `curl` 验证返回 200。
- ✅ **云端验证（2025-11-09）**：部署后通过 `curl -X POST ${ORCHESTRATOR_URL}` 触发全链路（策略→对账→Commander），两个策略 `status=success`，Commander 日志 `missing=[]/stale=[]`，执行文档写入 `orders=[{"simulated":true,"symbol":"SPY","action":"BUY","quantity":2689}]`，验证策略规范化+总指挥决策闭环已在 Cloud Run 生效。
- ✅ **策略预算 & 约束（2025-11-09）**：运行 `setting_firestore.py` 将 `config/common.exposure` 按 33%/33%/34% 拆分，并为策略写入 `allowed_symbols`、`max_notional`；Commander 已读取并执行 guardrail（见 `intents/allocation.py` 新增 `_apply_guardrails`），确保超额目标会被裁剪或忽略。
- ⚠️ **待完成**
  1. **调度编排切换** —— ✅ 完成：`orchestrator-daily-run` 已在 us-central1 启用并通过干跑验证，asia-east1 的旧作业（`daily-reconciliation-job`、`eod-allocation-job`、`high-frequency-test-runner`）已删除；待运营确认后再将 Scheduler payload 从 `dryRun:true` 切换为实际下单。
  2. **多策略迁移**：除 `testsignalgenerator`、`spy_macd_vixy` 外，其余策略仍使用旧路径/命名，需要按计划迁移 Firestore 配置及风险预算（文档第 3.1 节）。
  3. **Secret & 凭证治理**：确认 Secret Manager 中 `ib-*-username/password` 的版本轮换策略，补充自动化检测（若凭证失效会导致 503）。
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
1. **稳定基础设施** —— ✅ 完成：`order_to_dict` 替换、对账序列化补丁与 IB 背景线程退避逻辑均已上线并在 Cloud Run 上通过一轮 orchestrator dry-run 复核。
2. **策略运行规范化** —— ✅ 完成核心：策略注册由 orchestrator 参数驱动、Commander 日志+执行文档已验证；新增 `positions/{mode}/latest_portfolio/snapshot` 支撑对账/Commander 解耦。后续“策略预算隔离”作为单独待办 4 跟进。
3. **编排切换** —— ✅ 完成核心：`orchestrator-daily-run` 已上线并干跑验证；待业务批准后仅需将 Scheduler payload 切换为 `dryRun:false`。
4. **多策略迁移** —— ⏳ 未启动：其余策略仍在旧路径，待 Firestore 配置迁移。
5. **Secret / 凭证治理** —— ⏳ 未启动：需梳理 Secret Manager 轮换策略。
6. **监控 & 告警** —— ⏳ 未启动：待为 orchestrator/IB 断线建立 Logging Metric 或 Error Reporting 告警。



11-9
 - 验证日志显示 Secret Manager 中的 ib-paper-username/ib-paper-password 最新版本均处于 ENABLED 状态（创建于 2025‑10‑31），且可成功读取，说
    明 IB Gateway 凭证目前有效。
  - verify_trading.py（运行时间 2025‑11‑09 04:37 UTC）表明对账快照和两条策略的意图都在 Fresness 窗内：testsignalgenerator、spy_macd_vixy 均
    status=success，无 stale/missing 风险，Commander 聚合目标与 Cloud Run dry-run 结果一致。
  - 预算配置与“各占 1/3”设计不符：输出里两条策略的 Strategy Exposure 都是 100%，意味着 Firestore config/common.exposure.strategies 中这两个
    key 目前仍设为 1.0（而非 0.33/0.33/0.34 等分布），Commander 计算时会让任意一个策略都能独占 90% overall exposure。若希望“每策 1/3”，需在
    config/common 调整 exposure.strategies 映射，同时考虑剩余资金给未来策略或留白。
  - Allowed symbols 依旧是靠各策略代码里使用的合约（test_signal_generator.py 只生成 SPY，spy_macd_vixy.py 生成 SPY/VIXY），尚未通过
    Firestore 配置驱动。若要在 Commander 层防止其他合约被写入，需要在 strategies/{id} 文档新增 allowed_symbols（如 ["SPY"]、["SPY","VIXY"]）
    和 max_notional，并扩展 Allocation 在聚合时检查/裁剪。

  建议：1) 立即更新 Firestore 预算配置为目标比例，并在 verify_trading.py 再次确认数值；2) 设计 allowed_symbols/max_notional 字段并在
  Commander 中落地约束，避免策略逻辑失控；3) 在把 Scheduler 改为 dryRun:false 前，保持当前凭证/意图验证节奏，确保任何真实触发都基于最新
  快照。
  

Yes—functionally everything is ready. The new orchestrator-daily-run already fans through “策略 → 对账 → Commander” without missing/stale
  flags, and the legacy schedulers have been removed, so the job is the sole entrypoint.

  Before flipping to live orders, double-check:

  - IB Gateway creds/Secret Manager entries are current (avoids 503 loops).
  - The two active strategies’ intents are updating within the freshness window (no stale_strategies).
  - Any per-strategy budget/allowed-symbol constraints you expect are encoded, since Commander will honor exactly what the intents publish.

  Once those look good, switch the scheduler payload to dryRun:false:

  gcloud scheduler jobs update http orchestrator-daily-run \
    --project=gold-gearbox-424413-k1 \
    --location=us-central1 \
    --message-body='{"strategies":["testsignalgenerator","spy_macd_vixy"],"dryRun":false,"runReconcile":true}'

  Then watch Cloud Run logs on the next trigger to confirm Commander logs “placed” instead of “simulated” orders.

- 状态对照：策略改造、入口编排、Firestore 快照、单测与线上 dry-run 都已经按 intent_strategy_upgrade.md 落地，Commander/策略分工也在 Cloud
    Run 上通过 curl 与 Scheduler 干跑验证。最新待办集中在五项：
      1. 调度编排切换：手动触发的 orchestrator-daily-run 成功唤起服务，下一步是监控该任务的完整执行日志（确认“策略→对账→Commander”出现且
         missing=[]），然后 gcloud scheduler jobs update http 把 payload 改成 dryRun:false，最后删除 asia-east1 的旧作业。
      2. 多策略迁移：将剩余策略迁入“策略即意图”模型，对应的 Firestore 配置/预算项也要补齐。
      3. Secret & 凭证治理：审查 ib-*-username/password 的 Secret Manager 版本与轮换告警，避免 503。
      4. 策略预算孤立：在 Firestore strategies/{id} 文档维护 allowed_symbols、max_notional 等约束，并在 Commander 中读取这些配置裁剪
         aggregated_targets。
      5. 监控告警：为 orchestrator 503、超时和 IB 断线建立 Cloud Logging Metric 或 Error Reporting 告警。
  - 下一步修改建议：
      1. 完成 Scheduler 切换闭环（dry-run→logs→更新 payload→删除旧 job），验证一次真实下单流程。
      2. 选定下一批策略（例如 dummy 或其他生产策略），参照 spy_macd_vixy 的模式重构并补齐 Firestore 配置。
      3. 编写 Secret 轮换检测脚本或 Terraform 规则，并把告警连到 Pager/Email。
      4. 在 Commander 中实现 budget clamp（读取策略配置、限制目标敞口），并为这些逻辑补一组单测。


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
