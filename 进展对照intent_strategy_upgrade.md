 对照 intent_strategy_upgrade.md，当前进行到了哪一步？

    Firestore 目标仓位而非直接下单（cloud-run/application/app/strategies/spy_macd_vixy.py:84，cloud-run/application/app/strategies/
    latest_portfolio（cloud-run/application/app/intents/reconcile.py:15）。
  - 已完成：重构 allocation 意图（intent_strategy_upgrade.md:230），Commander 逻辑现集中聚合策略信号、计算 delta 并记录执行日志（cloud-run/
    application/app/intents/allocation.py:22）。
  - 已落实：编排入口 Orchestrator 实现了“策略→对账→总指挥”流水线顺序（intent_strategy_upgrade.md:231，对应 cloud-run/application/app/
    intents/orchestrator.py:17）。
  - 待完成：调整计划任务 仍未执行——Cloud Scheduler / Workflows 尚未更新，新旧调度并行策略和 dry-run 切换仍在计划中
    （intent_strategy_upgrade.md:231）。
  - 待持续：增量迁移 正处于首个策略上线阶段，仅 spy_macd_vixy 切换到新 ID 并更新 Firestore 预算，其它策略和完整迁移节奏尚未启动
    （intent_strategy_upgrade.md:232）。


    • 了解。建议你先暂时停掉自动 GitHub 触发的 Cloud Build（比如关闭触发器或把目标分支改到临时分支），确保仓库改动不会即时部署。接下来按我们更新
  到 • Implementation Plan.md 的步骤来：

  1. 本地环境：安装依赖后在 cloud-run/application/app 目录运行 python -m unittest discover -s _tests -t .，确认代码层面没有回归。
  2. Cloud Shell：运行

     python verify_trading.py --project-id gold-gearbox-424413-k1 --strategies spy_macd_vixy --dry-run
     或加 --show-intents 查看目标仓位，确保 Commander 能读到复核后的敞口。
  3. 如果 dry-run 正常，再重新提交一次 Cloud Build（gcloud builds submit --config cloudbuild.yaml）或恢复 GitHub 触发器，完成部署。
  4. 部署后监控一次 /orchestrator 调用（日常调度或手动 dry-run），在 Cloud Logging 核对 spy_macd_vixy deployable capital 是否使用了新键值。


• verify_trading.py 现在已经更新为：如果 Firestore 里还没有 positions/<mode>/latest_portfolio，脚本会降级打印 “snapshot missing” 而不是直接
  抛错，并把净值当成 0。请确保 Cloud Shell 使用的是这份最新版脚本（cat verify_trading.py 应该能看到 snapshot_status 输出），然后重新运行：

  python verify_trading.py --project-id gold-gearbox-424413-k1 --strategies spy_macd_vixy --show-intents

  输出里会出现：

  Snapshot Updated  : None (missing)
  Net Liquidation   : 0.00
  ...
      - Strategy Exposure : 100.00%
      - Deployable Capital: 0.00

  这说明预算键读对了，只是还没写入最新的组合快照。由于在 Cloud Shell 触发 reconcile 时 IB 未连接，Firestore 依旧没有生成 latest_portfolio 文
  档。等到重新部署并让 Commander / Reconcile 在有凭据的 Cloud Run 实例上跑一次，就会自动创建该文档，届时再跑脚本能看到真实净值。如果你想本地
  验证 Firestore 结构，也可以暂时手动写入一个简化文档：

  from google.cloud import firestore

  client = firestore.Client(project="gold-gearbox-424413-k1")
  doc_ref = client.document("positions/paper/latest_portfolio")
  doc_ref.set({
      "updated_at": "2025-10-30T00:00:00Z",
      "net_liquidation": 120000.0,
      "holdings": [],
      "open_orders": []
  })

  然后再次运行 verify_trading.py 即可看到 deployable capital = 108,000（0.9×1.0×120,000）。无需调整 Firestore 结构或 lib/init_firestore.py：
  当前问题只是缺少一次成功的对账写入。


  当前 Firestore 没有 positions/paper/latest_portfolio 的快照，也没有 strategies/spy_macd_vixy/intent/latest 的意图文档，verify_trading.py
  才会显示 “snapshot missing / deployable capital 0”。要进入下一步部署前，建议先在 Cloud Shell 手动跑一次完整编排，确保两份文档都写出来：

  1. 触发 orchestrator（带 dry-run）：

     python cloud-run/application/app/main.py --intent orchestrator --project-id gold-gearbox-424413-k1 --dryRun true --strategies spy_macd_vixy
     这会顺序执行策略→reconcile→Commander，写入 strategies/spy_macd_vixy/intent/latest 和 positions/paper/latest_portfolio。
     这会顺序执行策略→reconcile→Commander，写入 strategies/spy_macd_vixy/intent/latest 和 positions/paper/latest_portfolio。
  2. 按需再跑一次策略单体（若希望确认 intent 文档单独生效）：

     python cloud-run/application/app/main.py --intent spy_macd_vixy --project-id gold-gearbox-424413-k1 --dryRun true
  3. 重新执行 python verify_trading.py ...，确认输出里 Snapshot Updated 不再是 missing，Deployable Capital 为非零，并且 Intent Status 显
     示 success。

  完成上述验证后，再恢复/执行 Cloud Build 部署会更稳妥。




  现状确认

  - verify_trading.py 能读取 Firestore 配置，但因为 Firestore 里还没出现 strategies/spy_macd_vixy/intent/latest 和 positions/paper/
    latest_portfolio 两个文档，所以“Snapshot Updated” 显示 missing、部署资本为 0。
  - 在 Cloud Shell 直接跑 orchestrator、spy_macd_vixy 意图时，后台 IB 线程仍然连不上真实网关，策略拿不到数据就直接退出，未能写入 Firestore。
    这是离线环境的正常现象。

  可行的下一步

  - 先按计划部署：推送到 Cloud Build 并发布新版 Cloud Run 服务，确保服务拿到有效的 IB 凭证。
  - 部署完成后，等下一次 Scheduler 触发或手动调用 /orchestrator（建议先 dry-run）。在 Cloud Logging 中确认策略意图和 Reconcile 日志成功，然
    后再用 verify_trading.py 查看，此时应该能看到非零净值和最新快照。
  - 如需在云端预先验证 Firestore 结构，可暂时手动写一个 positions/paper/latest_portfolio 文档（含 updated_at、net_liquidation、空 holdings
    等），验证脚本就能计算出正数部署资本。

  总结：离线测试阶段能确认键名与配置同步已足够，最后一步需要在部署后的真实环境里跑一遍 orchestrator/reconcile，确保 Firestore 自动补齐快照。
