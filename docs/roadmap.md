# Xyn Roadmap

## Phase 1: Network Inventory Foundation

Goal: convert natural-language app requests into structured drafts and queued jobs that can produce deployable specs.

Scope:
- Workspace-scoped drafts (`app_intent`) with review/edit lifecycle.
- Workspace-scoped jobs (`generate_app_spec`, `deploy_app_local`, `smoke_test`) with status + logs.
- Submit flow: draft -> queued job.
- Seed defaults: guaranteed default workspace bootstrap.
- Drafts UI in xyn-ui for create/edit/submit + jobs visibility.
- AppSpec v0 generation and persistence as job output/artifact.
- Shared primitive catalog with reusable `location` primitive.
- Local net-inventory materialization via docker-compose.
- Sibling Xyn provisioning + smoke-test execution against deployed app.

Outcomes:
- API-first workflow for "build an app" intake.
- Persistent traceability from draft through job execution.

## Phase 2 Backlog

- TR-369 / EMS domain modeling and schema pack integration.
- EMS inventory synchronization and reconciliation jobs.
- Rich draft validation and policy checks before submit.
- Artifact binding from jobs to release/runtime specs and rollout workflows.

## Phase 2 Hardening (Current)

- Lightweight endpoint contracts for core API and net-inventory API.
- Contract validator tooling (`scripts/validate_contracts.py`) and end-to-end harness (`scripts/run_e2e_validation.sh`).
- Palette command registry (`palette_commands`) with workspace override + global fallback.
- Workspace isolation tests for palette/device flows.
- Persistence checks across net-inventory service and database restarts.
- Artifact refresh smoke path validation.
