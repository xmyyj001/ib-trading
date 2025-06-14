# Project Directory Structure

```bash
/Users/yuyongjun/ib-trading
```

```
.
├── .gitignore
├── cloud_run_deployment_plan.md
├── error_bigquery_firestore_update_plan.md
├── README.md
├── cloud-run
│   ├── explanation_integration_test_revise.md
│   ├── README.md
│   ├── application
│   │   ├── .dockerignore
│   │   ├── cloudbuild.yaml
│   │   ├── cloudbuild.yaml.new
│   │   ├── Dockerfile
│   │   ├── app
│   │   │   ├── main.py
│   │   │   ├── requirements.txt
│   │   │   ├── _tests
│   │   │   │   ├── __init__.py
│   │   │   │   ├── integration_tests.py
│   │   │   │   └── test_unittest_setup.py
│   │   │   ├── intents
│   │   │   │   ├── __init__.py
│   │   │   │   ├── allocation.py
│   │   │   │   ├── cash_balancer.py
│   │   │   │   ├── close_all.py
│   │   │   │   ├── collect_market_data.py
│   │   │   │   ├── intent.py
│   │   │   │   ├── summary.py
│   │   │   │   ├── trade_reconciliation.py
│   │   │   │   └── _tests
│   │   │   │       ├── __init__.py
│   │   │   │       ├── test_allocation.py
│   │   │   │       ├── test_cash_balancer.py
│   │   │   │       ├── test_close_all.py
│   │   │   │       ├── test_intent.py
│   │   │   │       ├── test_summary.py
│   │   │   │       └── test_trade_reconciliation.py
│   │   │   ├── lib
│   │   │   │   ├── __init__.py
│   │   │   │   ├── environment.py
│   │   │   │   ├── gcp.py
│   │   │   │   ├── ibgw.py
│   │   │   │   ├── init_firestore.py
│   │   │   │   ├── trading.py
│   │   │   │   └── _tests
│   │   │   │       ├── __init__.py
│   │   │   │       ├── test_environment.py
│   │   │   │       ├── test_gcp.py
│   │   │   │       ├── test_ibgw.py
│   │   │   │       └── test_trading.py
│   │   │   └── strategies
│   │   │       ├── __init__.py
│   │   │       ├── dummy.py
│   │   │       ├── strategy.py
│   │   │       └── _tests
│   │   │           ├── __init__.py
│   │   │           ├── test_dummy.py
│   │   │           └── test_strategy.py
│   ├── base
│   │   ├── .dockerignore
│   │   ├── cloudbuild.yaml
│   │   ├── cmd.sh
│   │   ├── Dockerfile
│   │   └── ibc
│   │       ├── config.ini
│   │       └── jts.ini
└── gke
    ├── __init__.py
    ├── deployment-config.yaml
    ├── get-ibapi.sh
    ├── namespace.yaml
    ├── README.md
    ├── allocator
    │   ├── __init__.py
    │   ├── allocator-es-random-paper.yaml
    │   ├── allocator.py
    │   ├── Dockerfile
    │   └── requirements.txt
    ├── ib-gateway
    │   ├── __init__.py
    │   ├── ib-gateway-paper.yaml
    │   ├── healthcheck
    │   │   ├── __init__.py
    │   │   ├── Dockerfile
    │   │   ├── main.py
    │   │   └── requirements.txt
    │   └── ibc
    │       ├── cmd.sh
    │       ├── Dockerfile
    │       └── config
    │           ├── config.ini
    │           └── jts.ini
    ├── secrets
    │   ├── create.sh
    │   └── credentials-ib-gateway.template.yaml
    └── strategy-api
        ├── __init__.py
        ├── Dockerfile
        ├── requirements.txt
        ├── strategy-es-random.yaml
        ├── strategy.py
        └── strategies
            ├── __init__.py
            └── es_random.py
```

## Key Directories
- **cloud-run/**: Cloud Run deployment configuration and application code
- **gke/**: Google Kubernetes Engine (GKE) deployment configurations
- **cloud-run/application/app/**: Main application codebase
  - `intents/`: Trading intent implementations
  - `lib/`: Shared libraries and utilities
  - `strategies/`: Trading strategy implementations
  - `_tests/`: Test suites
