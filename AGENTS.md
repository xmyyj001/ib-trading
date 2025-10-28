# Repository Guidelines

## Project Structure & Module Organization
- `cloud-run/application/app` contains the FastAPI service; `main.py` wires the intent registry, `intents/` wraps HTTP-facing orchestration, `strategies/` hosts trading logic, and `lib/` encapsulates IB and GCP integrations.
- `_tests/` under the same directory holds unit and integration suites. Historical GKE assets live in `gke/`, while root-level scripts such as `verify_trading.py` and `query_firestore.py` support manual diagnostics.
- Docker and Cloud Build assets sit in `cloud-run/application` (`Dockerfile`, `cloudbuild.yaml*`), and IB Gateway base images live under `cloud-run/base`.

## Build, Test, and Development Commands
- Set up dependencies from the service root with `pip install -r cloud-run/application/app/requirements.txt`.
- Run the API locally via `uvicorn main:app --reload` from `cloud-run/application/app` after exporting `PROJECT_ID` and IB credentials.
- Execute unit tests with `python -m unittest discover -s _tests -t .` inside `cloud-run/application/app`.
- For release builds, submit to Cloud Build using `gcloud builds submit --config cloudbuild.yaml` within `cloud-run/application`.

## Coding Style & Naming Conventions
- Python code follows PEP 8 with 4-space indentation and descriptive snake_case identifiers; intents and strategies should align file names with the public intent name (e.g., `strategies/test_signal_generator.py` powering `/testsignalgenerator`).
- Preserve structured logging via `logging` and keep async flows explicit (`async`/`await`) to avoid blocking the IB event loop.
- Configuration constants belong in `lib/` modules; avoid hard-coding secrets outside Secret Manager stubs.

## Testing Guidelines
- Prefer `unittest` cases; mirror existing patterns in `_tests/integration_tests.py` and isolate IB/GCP dependencies with `unittest.mock.patch`.
- Name test modules with the `test_*.py` prefix and group Cloud Run focused scenarios under `_tests/`.
- Before deploying, run the full suite and, when touching Firestore or BigQuery paths, add smoke checks via the integration harnesses already stubbed for CI.

## Commit & Pull Request Guidelines
- Follow the repository’s terse, present-tense commit style (`intent short summary`, `update with ...`); keep subjects under ~60 characters.
- Reference linked issues or incident docs in the PR description, summarize trading impact, and attach logs or screenshots for Cloud Run dashboards when relevant.
- Ensure PRs describe rollout steps (scheduler updates, secrets rotation) and note any manual verification such as `verify_trading.py` runs or staged scheduler triggers.

## Environment & Security Notes
- Every local run requires valid IB Gateway credentials and `PROJECT_ID`; never store them in the repo—use `deployment_vars.sh` as an editable template.
- When debugging, capture transient secrets or logs in temporary files under `/tmp` and purge before committing.
