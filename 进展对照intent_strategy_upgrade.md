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