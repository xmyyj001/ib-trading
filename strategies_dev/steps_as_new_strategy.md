- 将 cloud-run/application/app/strategies/ib_macd_stoch.py 改写为遵循 Commander 架构的意图：实现 IbMacdStochIntent，默认覆盖 META/AMZN/
    INTC/MSFT/AAPL，异步获取 1Y/15m 行情，计算 MACD+Stoch，并依据账户 NetLiquidation 与配置 exposure 生成目标仓位及 metadata；异常路径写入
    status="error"，调用 contract_to_dict、_activity_log.update 以保持 Firestore/日志一致。
  - 提供指标、持仓/在途映射等辅助函数，清除回测框架；python -m py_compile cloud-run/application/app/strategies/ib_macd_stoch.py 通过语法
    校验。

  上线前你需确认

  1. strategies/ib_macd_stoch Firestore 文档存在、enabled=true，并用 scripts/firestore/setting_firestore.py 设置 --overall-exposure, --ib-     macd-stoch-weight, --ib-macd-stoch-max-notional, allowed_symbols 等 guardrail。
  2. 在 STRATEGY_INTENT_REGISTRY 注册 ib_macd_stoch，同时为该意图添加单测并跑通 python -m unittest discover -s _tests -t .。
  3. Cloud Scheduler/orchestrator payload 若需包含此策略，先以 dryRun=true 验证 activity 中 missing/stale 为空，再按
     cloud_run_new_dep_steps.md 控制发布与回滚。


 - IbMacdStochIntent 现在默认覆盖 ("META","AMZN","TSLA","MSFT","AAPL")，文件在 cloud-run/application/app/strategies/ib_macd_stoch.py 并通过
    py_compile 校验。
  - Guardrail 建议：
      - 在 scripts/firestore/setting_firestore.py 中设置 --overall-exposure 0.90（或你希望的全局值）、--ib-macd-stoch-weight
        0.20、--testsignalgenerator-weight 0.20、--spy-macd-vixy-weight 0.20、--reserve-weight 0.20；剩余 0.20 可留给其他策略或保留为
        reserve_pool。
      - 为 ib_macd_stoch 指定 --ib-macd-stoch-max-notional <上限> 和 --ib-macd-stoch-allowed-symbols META AMZN TSLA MSFT AAPL，确保
        Commander 不会调仓到其他标的。
  - 其他上线步骤：在 STRATEGY_INTENT_REGISTRY 注册 ib_macd_stoch、添加单测并运行 python -m unittest；更新 Cloud Scheduler payload（先
    dryRun=true 验证 activity missing/stale 为空），用 verify_trading.py --strategies ib_macd_stoch testsignalgenerator spy_macd_vixy 巡检
    Firestore 输出。


==================
详细步骤：
     Guardrail 配置

  - 准备环境：在部署目录 ~/deployments/ib-trading-deploy 下 source deployment_vars.sh，确保 PROJECT_ID 指向生产/测试项目。
  - 运行配置脚本（先 dry-run 查看 diff，确认后去掉 --dry-run）：

 — ✅ 完成   python scripts/firestore/setting_firestore.py \
      --project-id gold-gearbox-424413-k1 \
      --overall-exposure 0.90 \
      --ib-macd-stoch-weight 0.20 \
      --ib-macd-stoch-max-notional 400000 \
      --ib-macd-stoch-allowed-symbols META AMZN TSLA MSFT AAPL \
      --testsignalgenerator-weight 0.20 \
      --spy-macd-vixy-weight 0.20 \
      --reserve-weight 0.20 \
      --dry-run
  - 去掉 dry-run 后再次执行同命令，让权重/上限写入 config/common.exposure 和 strategies/ib_macd_stoch 文档。

  — ✅ 完成代码接入

  - 在 cloud-run/application/app/strategies/__init__.py 与 intents/orchestrator.py 的 STRATEGY_INTENT_REGISTRY 中追加：

    from strategies.ib_macd_stoch import IbMacdStochIntent
    STRATEGY_INTENT_REGISTRY = {
        ...
        'ib_macd_stoch': IbMacdStochIntent,
    }
  - Firestore 手工创建/更新 strategies/ib_macd_stoch 文档（enabled: true, 描述、作者、guardrail 引用等）。

  测试与验证

  - 新增单测 cloud-run/application/app/strategies/_tests/test_ib_macd_stoch.py，mock IB 数据验证 target_positions 与 metadata。
  — ✅ 完成- 本地跑 python -m unittest discover -s _tests -t .。
  — ✅ 完成- 使用 verify_trading.py 检查 Firestore：

    python verify_trading.py \
      --project-id gold-gearbox-424413-k1 \
      --strategies ib_macd_stoch testsignalgenerator spy_macd_vixy \
      --show-intents

   — ✅ 完成- Cloud Run 验证

  - 部署最新镜像（gcloud builds submit ... + gcloud run deploy ...），确保新意图包含在镜像内。
  - 手动 dry-run orchestrator：

    gcloud run services invoke ${CLOUD_RUN_SERVICE_NAME} \
      --region ${GCP_REGION} \
      --format=json \
      --data='{"strategies":["ib_macd_stoch","testsignalgenerator","spy_macd_vixy"],"dryRun":true,"runReconcile":true}'
  - 浏览 Cloud Logging / activity 集合，确认 missing=[]、stale=[]，strategies/ib_macd_stoch/intent/latest 写入成功。

  调度与上线

  - 更新 Cloud Scheduler payload，加入 "ib_macd_stoch"（仍以 dryRun:true），观察 1-2 个周期。
  - 转正前再执行：

    gcloud scheduler jobs update http orchestrator-daily-run \
      --message-body='{"strategies":["ib_macd_stoch","testsignalgenerator","spy_macd_vixy"],"dryRun":false,"runReconcile":true}'
  - 若出现异常，按 cloud_run_new_dep_steps.md 第 8 步回滚至上一 revision，并记录日志/Firestore 快照。

  持续巡检

  - 定期运行 verify_trading.py --show-intents，与 Cloud Logging 中 Commander: Planned... 对照，确保 Guardrail 与分配权重生效。
  - 监控 activity 文档中的 allocations、deployable_capital 与 allowed_symbols，防止越权下单。
