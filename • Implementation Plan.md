• Implementation Plan

  - Prep
      - Review current intents and strategies in cloud-run/application/app and confirm existing tests via python -m unittest discover -s _tests -t ..
      - Freeze current deployment: record active Cloud Run revision and Scheduler job configs for rollback.
  - Strategy Refactor
      - Update each strategy module (e.g., cloud-run/application/app/strategies/spy_macd_vixy.py, .../test_signal_generator.py) so run/_core_async returns
        target positions and writes to strategies/{id}/intent/latest with updated_at, status, and minimal metadata.
      - Remove direct order placement from strategies; adapt unit tests in _tests to validate Firestore writes and window freshness logic.
  - Reconcile Intent
      - Ensure cloud-run/application/app/intents/reconcile.py syncs holdings/open orders to positions/{mode}/latest_portfolio without awaiting sync Firestore
        calls; add tests to cover daily cadence.
  - Commander Intent
      - Refactor cloud-run/application/app/intents/allocation.py into Commander: consume fresh strategy intents, apply allocation rules, compute diffs, submit
        orders through IB gateway adapter, and log execution references.
      - Externalize risk parameters/allocations into config (e.g., lib/config.py or Firestore config doc); add integration tests mocking Firestore/IB.
  - Orchestrator
      - Implement new entry point (e.g., cloud-run/application/app/intents/orchestrator.py or a dedicated FastAPI route) that sequentially triggers: parallel
        strategy intents → reconcile → Commander, enforcing window validation and timeout handling.
      - Support dry-run and strategy whitelist parameters to facilitate testing.
  - Firestore & Schema
      - Create migration script or manual doc to seed strategies/{id} config documents with allocation metadata.
      - Run exposure-key migration before redeploying: in Cloud Shell create `rename_spy_key.py` with
        ```
        from google.cloud import firestore

        PROJECT_ID = "YOUR_PROJECT_ID"

        db = firestore.Client(project=PROJECT_ID)
        doc_ref = db.collection("config").document("common")
        snapshot = doc_ref.get()
        data = snapshot.to_dict()
        strategies = dict(data.get("exposure", {}).get("strategies", {}))
        legacy = strategies.pop("spymacdvixy", None)
        if legacy is not None:
            strategies["spy_macd_vixy"] = legacy
            doc_ref.update({"exposure.strategies": strategies})
            print(f"Moved exposure {legacy} -> spy_macd_vixy")
        else:
            print("No spymacdvixy key found; nothing to migrate.")
        ```
        and execute `python rename_spy_key.py` after exporting `GOOGLE_APPLICATION_CREDENTIALS`.
      - Capture before/after exposure snapshots (`gcloud beta firestore documents describe config/common`) and attach to change log.
      - Document intent freshness policy and execution log references in intent_strategy_upgrade.md.
  - Deployment
      - Build new container revision including orchestrator; deploy to separate Cloud Run service (e.g., trading-orchestrator) keeping existing service
        untouched.
      - Configure environment variables/Secret Manager bindings identical to current service plus new toggles (COMMANDER_ENABLED, etc.).
      - Post-migration, run `python verify_trading.py --project-id YOUR_PROJECT_ID --strategies spy_macd_vixy --dry-run` and record Commander exposure output
        before cutting traffic.
  - Scheduler
      - Provision single Cloud Scheduler job (daily-strategy-orchestrator) targeting the new orchestrator endpoint with appropriate cron and OIDC auth; keep
        testsignalgenerator job for baseline until cutover.
  - Testing & Verification
      - Run unit/integration suites locally; create end-to-end dry-run invoking orchestrator with mocked IB to ensure Firestore writes occur in correct order.
      - Local sanity checklist before deployment:
        ```
        # 从 repo 根目录启动虚拟环境后安装依赖
        pip install -r cloud-run/application/app/requirements.txt

        # 切换到服务目录运行单元与集成用例
        cd cloud-run/application/app
        python -m unittest discover -s _tests -t .
        cd -
        ```
      - In Cloud Shell, confirm Commander sees non-zero exposure:
        ```
        python verify_trading.py --project-id gold-gearbox-424413-k1 --strategies spy_macd_vixy --dry-run
        ```
      - After Firestore change, trigger `/orchestrator` dry-run and review Cloud Logging (filter `logName` for Commander) to confirm `spy_macd_vixy`
        deployable capital reflects the migrated exposure.
      - In staging/project sandbox, execute manual curl to orchestrator, inspect Firestore documents (strategies/.../intent/latest, positions/.../
        latest_portfolio, executions/...) and Cloud Logging.
  - Rollout
      - Monitor new service for at least one trading window; compare Commander-generated orders against legacy strategy outputs.
      - When satisfied, migrate additional strategies and gradually disable legacy endpoints/Scheduler jobs; keep test_signal_generator active for regression
        checks until final switchover.
  - Observability & Safety
      - Extend monitoring dashboards to track orchestrator latency, missing intents, Commander failures; add alerting when no execution log is produced in
        a window.
      - Document rollback: disable orchestrator Scheduler, revert Commander flag, redeploy previous revision if anomalies occur.
