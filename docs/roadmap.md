# Xyn Roadmap

## Phase 1: Network Inventory Foundation

Goal: convert natural-language app requests into structured drafts and queued jobs that can produce deployable specs.

Scope:
- Workspace-scoped drafts (`app_intent`) with review/edit lifecycle.
- Workspace-scoped jobs (`generate_app_spec`, `deploy_app_local`, `smoke_test`) with status + logs.
- Submit flow: draft -> queued job.
- Seed defaults: guaranteed default workspace bootstrap.

Outcomes:
- API-first workflow for "build an app" intake.
- Persistent traceability from draft through job execution.

## Phase 2 Backlog

- TR-369 / EMS domain modeling and schema pack integration.
- EMS inventory synchronization and reconciliation jobs.
- Rich draft validation and policy checks before submit.
- Job workers for real execution (spec generation, deploy, smoke test).
- Artifact binding from jobs to release/runtime specs and rollout workflows.
