对照 `intent_strategy_upgrade.md`，当前完成度与待办如下：

- ✅ **策略改造**：`testsignalgenerator`、`spy_macd_vixy` 已改写为只输出 Firestore 目标仓位（参见 `cloud-run/application/app/strategies/*.py`），Commander 从 `positions/{mode}/latest_portfolio` 读取真实仓位并集中决策（`intents/allocation.py`）。
- ✅ **Orchestrator 流程**：`/` POST 已代理到 orchestrator，顺序执行“策略 → 对账 → Commander”，并在 503 时提示 IB 重连状态（`main.py:117-165`、`intents/orchestrator.py`）。根路由 GET 提供健康检查，便于 Cloud Run/Scheduler 校验。
- ✅ **持仓快照与序列化**：`reconcile` 统一写入 `positions/{trading_mode}/latest_portfolio`；自研 `lib/ib_serialization.contract_to_dict` 解决 ib_insync 兼容性并清理 Firestore 写入路径。
- ✅ **单测/脚本验证**：`python -m unittest discover -s _tests -t .` 通过；`verify_trading.py --show-intents` 在 paper 环境输出最新指令与敞口；Cloud Run 实例经 `curl` 验证返回 200。
- ⚠️ **待完成**
  1. **调度编排切换**：准备创建 `orchestrator-daily-run`（POST `https://ib-paper-.../`，JSON 载荷 `{"strategies":["testsignalgenerator","spy_macd_vixy"],"dryRun":true,"runReconcile":true}`，OIDC 服务账号 `ib-trading@…`），并逐步停用旧作业（`daily-reconciliation-job`、`eod-allocation-job`、`high-frequency-test-runner`）；待 Cloud Scheduler/Workflows 调整后即可勾掉此项。
  2. **多策略迁移**：除 `testsignalgenerator`、`spy_macd_vixy` 外，其余策略仍使用旧路径/命名，需要按计划迁移 Firestore 配置及风险预算（文档第 3.1 节）。
  3. **Secret & 凭证治理**：确认 Secret Manager 中 `ib-*-username/password` 的版本轮换策略，补充自动化检测（若凭证失效会导致 503）。
  4. **监控告警**：落地针对 orchestrator 503/超时的 Cloud Logging Metric 或 Error Reporting 告警，保证 Gateway 断线可及时通知运维。

下一步建议按上述待办优先级推进，完成调度切换→策略迁移→凭证治理→监控告警的闭环。***




日志里 commander 报错的根因就在这一行：

  Allocation._core_async → util.dictToContract(plan['contract'])
  AttributeError: module 'ib_insync.util' has no attribute 'dictToContract'


  建议的修复思路

  1. 在 lib/ib_serialization.py 内新增一个 dict_to_contract 辅助方法（与现有 contract_to_dict 对偶），根据 Firestore 存下的字段构造
     ib_insync.contract.Contract 或具体子类，并处理 __slots__。
  2. intents/allocation.py 中把
     如果返回的合约缺少 conId，可沿用原先的 qualifyContractsAsync 流程补齐。
  3. 重新部署后复测 orchestrator / scheduler；verify_trading.py 中的 Commander 段落也要检查是否能读取 orders。
  4. 为防回归，考虑补一条单元测试或 integration stub，构造一个 plan 样例验证 dict_to_contract 能成功还原 Stock 合约。

  待修完再跑一次调度，Commander 部分就不会因为缺少 API 而提前失败。

• - Added a native dict_to_contract helper so we can rebuild IB contracts without the removed ib_insync.util.dictToContract; see cloud-run/
    application/app/lib/ib_serialization.py:9-85.
  - Updated Commander to use the new helper when materialising contracts before order placement, removing the dependency on the deprecated
    util call (cloud-run/application/app/intents/allocation.py:1-158).

  Tests: python -m unittest discover -s _tests -t .

  Next up, rebuild the application image and redeploy Cloud Run, then rerun the orchestrator (or the new Scheduler job) to confirm Commander
  now executes without errors.




  Fix Summary

  - Added reusable serializers that mirror the old ib_insync helpers so we no longer depend on removed APIs; _object_to_mapping, _normalize_mapping, and the
    new order_to_dict now live alongside the existing contract utilities (cloud-run/application/app/lib/ib_serialization.py:25, cloud-run/application/app/lib/
    ib_serialization.py:64, cloud-run/application/app/lib/ib_serialization.py:96).
  - Updated the reconcile intent to serialize orders via our local helper, eliminating the failing util.orderToDict call (cloud-run/application/app/intents/
    reconcile.py:4, cloud-run/application/app/intents/reconcile.py:47).
  - Added unit coverage to confirm order serialization works and that contract round-trips remain intact (cloud-run/application/app/_tests/
    test_ib_serialization.py:1).

  Tests

  - python -m unittest discover -s _tests -t .

  Next Steps

  1. Redeploy the Cloud Run service so the orchestrator picks up the new serializer.
  2. Re-run the reconcile workflow (e.g., the same curl invocation) to confirm the error is resolved.

 