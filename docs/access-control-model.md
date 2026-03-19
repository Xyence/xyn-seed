# Platform Access Control Model (Canonical v1)

This document defines the canonical role/capability shape for DealFinder-era app surfaces in Xyn.

## Scope

The model is capability-first and intended to be reusable across applications.

- Role checks should map to capabilities.
- Endpoint/service enforcement should check capabilities, not role-name conditionals.
- Scope is workspace-first, with optional application scope.

## Canonical Roles

- `application_admin`
- `campaign_operator`
- `read_only_analyst`

## Capability Families

Primary capability slugs are defined in [core/access_control.py](/home/jrestivo/src/xyn/core/access_control.py).

Admin/data-source capabilities include:

- `app.jurisdictions.manage`
- `app.sources.manage`
- `app.mappings.inspect`
- `app.refreshes.run`
- `app.ingest_runs.read`
- `app.failures.read`
- `app.artifacts.read`
- `app.provenance.read`
- `app.datasets.publish`
- `app.sources.diagnostics.read`

Campaign/operator capabilities include:

- `app.campaigns.manage`
- `app.watches.manage`
- `app.subscribers.manage`
- `app.notification_targets.manage`
- `app.matches.review`
- `app.signals.review`
- `app.campaign_history.read`
- `app.notifications.read`

Read-only analyst baseline includes:

- `app.read`
- read-oriented run/failure/campaign/signal/match/notification capabilities

## Reusable Enforcement Pattern

1. Resolve principal from request headers (`X-Roles`, `X-Capabilities`, optional scope headers).
2. Resolve effective capabilities from role mappings.
3. Call `assert_access(...)` with required capabilities and scope.
4. Return `403` on missing capability or out-of-scope access.

For FastAPI routes, use `require_capabilities(...)` where practical.

## Visibility Endpoints

- `GET /api/v1/access/roles` (role -> capability catalog)
- `GET /api/v1/access/me` (effective principal view)

## Notes

- This is intentionally a lightweight canonical shape, not a full IAM subsystem.
- Fine-grained row-level policy and dynamic role assignment UX are follow-on work.
