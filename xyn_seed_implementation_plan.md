# Xyn Seed (Xyn Core) — Implementation Plan (Living Document)

## 0. Purpose of this document
This is a **living implementation plan** for building **Xyn Seed** (the “Seed Node”) and the first user-facing expression, **Xyn Core**.

- It is written to be **fed into an IDE/agent** to drive development.
- It focuses on **fast-to-revenue + low surface area**, avoiding unnecessary infrastructure and ceremony.
- It is intentionally **code-light** and **decision-heavy**: clear scope, boundaries, interfaces, and sequencing.

We will update this plan iteratively in this conversation as decisions evolve.

---

## 1. Grounding: what we’re trying to achieve
### 1.1 The product in one sentence
**Xyn Seed** is a minimal, agent-native platform core that turns **events** into **plans** into **actions** with full **auditability**, and can **replicate itself** into new nodes.

### 1.2 The problem this solves
Modern ops/workflow systems accumulate surface area fast:
- too many moving parts (Kubernetes/Helm, IdP stacks, multiple control planes)
- human-centric planning artifacts (epics/user stories) that don’t match AI/agent execution
- slow iteration caused by translation layers (requirements → tickets → dev → deploy)

Xyn Seed aims to remove the translation layers and run in a simpler loop:

> **Event → Blueprint → Agent → Action → Audit**

### 1.3 The “native unit” of work
- Not user stories.
- Not epics.

The native unit is a **Blueprint**: a larger, coherent, agent-friendly workflow definition that can include:
- structured inputs
- analysis tasks
- tool calls
- execution steps
- approval gates
- artifacts/logs

### 1.4 Success criteria (what “done” looks like)
A **saleable nucleus** that can be deployed simply and used immediately:
- ingest events
- map events to blueprints
- execute plans with tools
- provide run history + audit trail
- support multiple LLM backends
- replicate/instantiate new nodes

---

## 2. Brief history / lineage (and what we are *not* doing)
### 2.1 “Xen” / prior platform lineage
A prior implementation of this overall idea existed under a different name and organizational container (the earlier telecom-oriented platform effort).

That system validated key concepts:
- event-driven attention (“signals”)
- structured operational workflows (“playbooks/blueprints”)
- integrations with monitoring / ops tools
- multi-tenant operational needs

### 2.2 Why we are starting over
The prior implementation accumulated weight through:
- broad framework gravity
- infrastructure surface area (cluster orchestration, charts, config)
- organizational constraints (human dev workflows, offshore coordination)

This restart keeps the validated core concepts while rebuilding the system **from the smallest feasible nucleus**, optimized for:
- agent-enabled development
- minimal dependencies
- rapid iteration
- clear boundaries and auditability

### 2.3 What we are *not* doing
- We are **not** recreating the previous system as-is.
- We are **not** optimizing for large-team human development rituals.
- We are **not** starting with Kubernetes/Helm as a requirement.
- We are **not** building an ERP.

We are building the **functional essence** as a lighter, more direct system.

### 2.4 Organizational shift
Development and ownership are now centered under **Xyence**.
- **Xyn** is the core engine.
- **Xyn Core** is the initial UI/product expression.

---

## 3. Architectural north star
### 3.0 Clarifying question: is this a dev environment or an app?
**Both — by design.**

- **Xyn Seed** is the *runtime spine* (the platform kernel + persistence + execution).
- It is also a *development forge* in the practical sense that it can use agents to generate/modify:
  - blueprints
  - action plugins
  - integrations
  - UI panels
  - tests and migrations

In other words, the Seed Node is a running application that can also *author* new capabilities via a gated self-building loop.

A key design rule follows:
- **All changes are expressed as versioned artifacts** (blueprints, plugins, packs), even when produced by agents.
- **Execution and authoring share the same primitives** (events, runs, steps, artifacts).

---

## 3. Architectural north star
### 3.1 “Platform kernel” (software kernel, not OS kernel)
Run on a boring substrate (Linux + containers) and build a *platform kernel* that provides:
1) event ingest
2) durable state
3) blueprint compilation
4) agent routing
5) action execution
6) audit/logging
7) replication

### 3.2 Surface-area budget
Rules of thumb:
- Prefer **Docker Compose** / single-node deploy first.
- Add Kubernetes only when there is a proven, unavoidable need.
- Keep IdP/auth minimal initially (token + role gates), evolve later.
- Prefer “one database, one queue” over a zoo of services.

### 3.3 Self-building loop (realistic version)
Agents can:
- propose new blueprints
- generate action stubs
- write tests
- open PR-ready changes

But production changes must be gated:
> **Agent proposes → automated checks → human approves/merges → rollout**

---

## 4. Scope boundaries (v0)
### Included in v0
- Event intake (webhook + manual trigger + cron)
- Durable event log (append-only)
- Blueprint format v0 (YAML/JSON)
- Blueprint compiler to execution plan
- Execution engine (step runner)
- Action runner interface + 2–3 core actions
- Agent router supporting multiple providers
- Audit log + run history
- Minimal HTMX UI (Xyn Core)
- Seed replication to create a new node (local first)

### Explicitly deferred
- Full multi-tenant RBAC and enterprise IdP integrations
- Kubernetes-native deployment
- Full “Signals app” rebuild
- Complex UI dashboards
- Marketplace/distribution system

---

## 5. Concepts & data model

### 5.0 The Thompson lesson (why this stays small)
There’s a useful parallel to early Unix: once the core substrate existed, the remaining pieces were a short list of *enabling tools* (editor, assembler/compiler, shell, etc.). A modern summary often retells Thompson’s estimate that after the core was in place, he needed roughly “a week each” for a few key tools to make the system self-hosting. ([redhat.com](https://www.redhat.com/en/blog/unix-linux-history?utm_source=chatgpt.com))

For Xyn Seed, the equivalent is a **toolchain kernel**: a small set of facilities that make the system **self-hosting for blueprints and packs** without turning into an IDE product.

### 5.1 Key entities
- **Event**: immutable input record.
- **Blueprint**: declarative workflow definition.
- **Run**: an execution instance of a blueprint.
- **Step**: an atomic unit in a run.
- **Artifact**: a generated output (files, JSON, logs, reports).
- **Node**: a deployed instance (seed or child).
- **Draft**: a non-active working object (draft blueprint/pack) that can be edited/promoted.

\1

### 5.3 Footprints & Impressions (v0 semantics)

#### 5.3.1 Definitions
- **Footprint** = measurable consumption emitted by the system.
  - Examples:
    - LLM usage: tokens_in/tokens_out, request_count, cache_hit
    - Execution: wall_ms, cpu_ms, bytes_in/out
    - Storage: artifact_bytes_written
    - Optional: dollars_est (derived via pricing tables; can be best-effort)
- **Impression** = a semantic label or summary derived from footprints and outcomes.
  - Examples:
    - severity=low/med/high
    - customer_visible=true/false
    - billable=true/false OR billing_tier=gold/silver/internal
    - anomaly=true with basis pointing to footprint outliers

#### 5.3.2 Required properties
- Every Run MUST have at least one footprint:
  - metric = "run.count", quantity=1, unit="count"
- Every Step SHOULD emit at least:
  - metric="step.count" (count=1)
  - metric="wall_ms" for execution duration (best effort)

#### 5.3.3 Cardinality rules (avoid runaway growth)
- Prefer **one footprint row per (source_kind, source_ref, metric) per step** for v0.
  - Example: an LLM call emits 2 rows max: tokens_in, tokens_out (plus optional wall_ms)
- Only emit high-cardinality dimensions into `dims_json` when needed for policy/audit.

#### 5.3.4 Policy hooks
- `class` is the stable policy-facing classifier:
  - informational | internal | billable | free_tier | etc
- Impressions are where “rating” logic lives:
  - billable decisioning, risk scoring, customer-visible tagging, quality scoring, etc.

#### 5.3.5 Storage and retention strategy (Postgres-first)
- Store atomic footprints for a bounded window (e.g., 30–90 days), then:
  - keep rollups indefinitely (or longer)
  - optionally archive full-detail footprints to object storage (Parquet) later
- Partition `footprints` and `impressions` by time (monthly) early to keep vacuum/indexes sane.
- **Outbox-ready (future event log):**
  - When writing events/runs/steps/footprints, also write an `outbox` row in the same transaction.
  - A background dispatcher can publish outbox messages to a durable log later (Kafka/Redpanda/NATS JetStream/etc.).
  - This preserves Postgres-first simplicity while keeping a clean migration path to a dedicated event log.

\21 Core flow
1) Event arrives
2) System selects blueprint(s)
3) Blueprint compiles to execution plan
4) Execution engine runs steps
5) Steps may:
   - call agent
   - call action
   - create artifact
\1- persist artifacts
- emit footprints for step execution + tool/agent usage
- optionally emit impressions (or defer to later classifier pass)
\3

\1

### 6.3 Footprint capture points (v0)
- On step start: optional (step.count)
- On step finish: required (wall_ms + step.count)
- On agent call completion: required (tokens_in/tokens_out + request_count + provider/model dims)
- On action completion: required (wall_ms + optional bytes_in/out + action dims)
- On artifact write: optional (artifact_bytes_written)
\21 Design goals
- Human-readable, agent-friendly
- Declarative
- Supports gating
- Supports tools/actions
- Supports artifacts
- Supports drafts + promotion

### 7.2 Skeleton example
```yaml
id: bp.checkmk.auto_remediate
name: "Checkmk Alert Auto-Remediation"
trigger:
  event_type: "checkmk.alert"
inputs:
  - name: host
  - name: service
plan:
  - kind: agent_task
    id: analyze
    agent: openai
    model: gpt-5
    prompt: "Analyze alert and suggest remediation plan"
  - kind: gate
    id: approve
    mode: manual
  - kind: action_task
    id: run_fix
    action: ssh.run
    with:
      host: "{{inputs.host}}"
      cmd: "..."
outputs:
  - name: summary
```

### 7.3 Blueprint validation rules (v0)
- `id` required, must be stable and unique
- `trigger.event_type` required
- `plan[]` required
- each plan step must include:
  - `kind` in {agent_task, action_task, gate, transform}
  - `id` unique within blueprint
- `gate` must specify `mode` (v0: manual)
- `agent_task` must specify {provider, model, prompt_template}
- `action_task` must specify {action, with}
- template variables must resolve from `inputs` or prior step outputs

---

## 8. LLM / agent routing LLM / agent routing
### 8.1 Provider targets (v0)
- OpenAI (for planning/blueprint generation)
- Anthropic Claude (Sonnet/Opus) for implementation-level tasks
- Optional: Augment integration as a development backend

### 8.2 Routing policies
- Blueprint specifies preferred provider/model.
- System may override via config.
- All prompts/responses stored as artifacts for audit/debug (with redaction options later).

---

## 9. Actions / tools system

### 9.1 Action interface
Actions are plugins with:
- name
- input schema
- execution function
- output schema
- redaction rules

### 9.2 v0 action set
- http.call
- ssh.run
- container.exec

### 9.3 Internal platform actions (v0)
These are core actions implemented by the platform kernel and used by meta blueprints.

#### 9.3.1 `drafts.save`
**Purpose:** Persist a Blueprint Draft as a versioned working artifact.

**Inputs:**
- `draft_type` (enum: `blueprint` | `pack`)
- `name` (string)
- `trigger_event_type` (string)
- `definition` (string | object) — YAML/JSON
- `notes` (string, optional)
- `source_run_id` (string, optional)

**Behavior:**
- Creates or updates a draft record.
- Versions drafts (increment revision on change).
- Stores `definition` as an artifact.

**Outputs:**
- `draft_id` (string)
- `revision` (int)
- `status` (string: `draft`)

**Errors:**
- `invalid_definition`
- `storage_error`

---

#### 9.3.2 `blueprints.validate`
**Purpose:** Validate a Blueprint Draft against v0 rules.

**Inputs:**
- `draft_id` (string)

**Behavior:**
- Loads draft definition.
- Validates against Blueprint v0 rules.
- Produces a validation report artifact.

**Outputs:**
- `is_valid` (bool)
- `issues` (list)

**Errors:**
- `draft_not_found`
- `invalid_schema`

---

#### 9.3.3 `blueprints.promote`
**Purpose:** Promote a valid Blueprint Draft to an active Blueprint.

**Inputs:**
- `draft_id` (string)

**Behavior:**
- Requires prior successful validation.
- Creates or updates an active blueprint record.
- Freezes promoted revision.

**Outputs:**
- `blueprint_id` (string)
- `version` (string)
- `status` (string: `active`)

**Errors:**
- `draft_not_found`
- `validation_failed`
- `conflict`

---

## 9A. Integrating existing apps (VOLTHA, Oktopus, Checkmk, etc.)

### 9A.1 Uniform integration pattern
Treat every external system as an **App Pack** plus an **Adapter Action Pack**.

- **App Pack**: how to run/attach the app (managed container, external endpoint, or both)
- **Adapter Action Pack**: actions + event sources that expose the app to blueprints

This avoids coupling Xyn’s core DB model to each app.

### 9A.2 Three attachment modes
1) **Managed-in-environment**: Xyn deploys the app alongside the seed (Compose now; k8s later)
2) **External-managed**: Xyn connects to an existing app endpoint (URL/creds)
3) **Hybrid**: Xyn can do either depending on deployment profile

### 9A.3 Uniform API surface inside Xyn
Expose integrations to blueprints via:
- **Actions** (imperative): `oktopus.device.register`, `voltha.omci.provision`, `checkmk.acknowledge`
- **Events** (reactive): `checkmk.alert`, `oktopus.device.registered`, `voltha.onu.state_changed`

### 9A.4 Data model strategy (supportable)
Keep one core Postgres for Xyn.

For external apps:
- Prefer **API-first** interaction (actions/events) as the default.
- Optionally maintain **read-optimized mirrors** in Xyn tables for fast querying/UI.
  - Mirrors are populated by blueprints (pull) or event streams (push).
  - Mirrors are explicitly versioned and schema-controlled ("data contracts").

### 9A.5 Example mappings
- **Oktopus**
  - attachment: external-managed or managed-in-environment
  - events: `oktopus.device.registered`
  - actions: `oktopus.device.set_profile`, `oktopus.device.get_status`

- **VOLTHA**
  - attachment: managed-in-environment (heavier) or external-managed
  - events: `voltha.onu.discovered`, `voltha.onu.alarm`
  - actions: `voltha.onu.provision`, `voltha.onu.reboot`

- **Checkmk**
  - attachment: often external-managed
  - events: `checkmk.alert`
  - actions: `checkmk.downtime.set`, `checkmk.ack`, `checkmk.host.query`



---

## 16. UI testing & quality gates (design now, enforce early)

### 16.1 Goal
Avoid regressions and fear-driven development by ensuring UI changes ship with automation coverage.

### 16.2 Principle
UI test generation and execution should be the **default path**; missing tests must be an explicit, reviewable exception.

### 16.3 Recommended tooling
- **Playwright** for end-to-end UI automation.
- Prefer black-box tests (interact like a user).
- Require stable selectors via `data-testid` in templates.

### 16.4 UI Test Contract (minimum)
Any UI surface (Core UI or App Pack UI) must provide:
- stable selectors (`data-testid`)
- **1–3 smoke tests** minimum:
  - page loads
  - primary action works (e.g., create/validate/promote)
  - expected state change is visible (status updated, artifact created)

### 16.5 CI gates
CI should run:
- unit tests
- API contract tests
- UI smoke tests (Playwright)

Promotion of Pack revisions should be able to require passing tests (enforce later; design now).

### 16.6 Agent role
Agents may generate/maintain Playwright tests alongside UI changes, but all changes remain gated.

### 16.7 Standards enforcement (future)
Introduce a Pack Validator/Linter that can check:
- naming + namespaces
- required UI tests for UI packs
- blueprint schema compliance
- versioning rules

---

## 17. Administrative abstractions & role model (provider-of-provider safe)

### 17.1 Problem to solve
The old terminology (platform provider/service provider/end customer) breaks under nesting (provider-of-provider scenarios). We need a model that composes cleanly.

### 17.2 Proposed vocabulary (relative to an environment)
- **Operator**: whoever operates/manages an environment (Xyence, partner, customer).
- **Owner**: the organization that owns the environment’s data and policies.
- **Reseller**: an Owner that provisions environments for downstream Owners.
- **Tenant**: optional segmentation within an environment (defer unless needed).

This avoids hardcoding industry-specific labels into the platform.

### 17.3 Views (UI separation)
Instead of a separate “desk,” implement **views** within Xyn Core:
- **Operator View**: environment controls, packs, node health, replication, federation, backups.
- **Owner/Admin View**: domain settings exposed by app packs.
- **User View**: day-to-day workflows.

v0 can implement Operator + basic Owner controls; the model should exist early.

### 17.4 Implementation direction (phased)
- v0: simple auth token + role flag (operator vs owner)
- v1+: policy-driven RBAC
- later: tenant-aware segmentation if needed

---

## 18. Key design reminders added from discussion
- Plan for UI test automation early (Playwright + `data-testid` + CI smoke tests).
- Plan for governance/standards enforcement (namespaces, required tests, pack validation).
- Use role vocabulary that survives nesting (Operator/Owner/Reseller) and implement views instead of a separate desk.



---

## 19. DNS & naming (xyence.io, Route 53)

### 19.1 Goals
- Provide a consistent, automatable DNS strategy for environments (workcells) and services.
- Support both:
  - Xyence-operated environments under `xyence.io`
  - customer/partner-operated environments under their own domains via delegation

### 19.2 Recommended model
Treat DNS as a first-class **App Pack** + **Action Pack**:
- **App Pack:** AWS Route 53 (hosted zone management)
- **Action Pack:** `dns.zone.create`, `dns.record.upsert`, `dns.record.delete`, `dns.zone.delegate`

BluePrints can then provision DNS as part of environment replication/onboarding.

### 19.3 Domain structure proposal
Use `xyence.io` as the default parent domain.

**Environment identity should be ID-based** with optional aliases.

Recommended patterns:
- Environment canonical identity:
  - `e-<env_id>.xyence.io`
- Environment alias (optional):
  - `<alias>.xyence.io` CNAME → `e-<env_id>.xyence.io`
- Services within an environment:
  - `<svc>.e-<env_id>.xyence.io`
  - (aliases optionally mirror: `<svc>.<alias>.xyence.io`)

Examples:
- `e-7f3a.xyence.io`
- `dev.xyence.io` → CNAME `e-7f3a.xyence.io`
- `core.e-7f3a.xyence.io`, `api.e-7f3a.xyence.io`, `ui.e-7f3a.xyence.io`

### 19.4 One subdomain vs many instances
It is more flexible to treat **one subdomain as an environment namespace**, not a single instance.

Preferred:
- **One Environment → one subdomain** (namespace)
- Multiple internal services and even multiple “instances” can live beneath it:
  - `{instance}.{svc}.{env}.xyence.io` if needed

Avoid hard-coding **one Xyn == one subdomain**; instead:
- define a stable environment identity (subdomain)
- allow multiple nodes/replicas behind the same service name

### 19.5 Routing & certificates
- Prefer a small number of well-known service names per environment (e.g., `core`, `api`).
- Support wildcard certificates per environment (e.g., `*.dev.xyence.io`) for simplicity.

### 19.6 Delegation for partners/customers (future)
To support reseller/provider-of-provider:
- allow environment creation that either:
  - uses `xyence.io` (Xyence-operated)
  - or requests a customer domain and creates NS records for delegation

Expose this via UI and/or blueprint:
- invitation → acceptance → delegated zone created → records managed via actions.

### 19.7 Security & permissions
- Route 53 access should be via least-privilege IAM:
  - scoped to specific hosted zone(s)
  - separate credentials per operator if needed
- Store credentials via config now; move to vault later.



---

## 20. IPv6-first networking (design now, adopt early)

### 20.1 Rationale
IPv6 reduces network complexity by enabling direct end-to-end addressing (less NAT dependence), which aligns well with:
- self-replicating environments
- automated troubleshooting/health checks
- federation/B2B links between environments

IPv4 remains supported for compatibility, but internal and inter-environment networking should prefer IPv6 where feasible.

### 20.2 Principles
- **Dual-stack by default** when running in typical cloud/VPC environments.
- Prefer **IPv6-native** inside the “Xyn interior” (service-to-service and environment-to-environment).
- Avoid introducing new IPv4 NAT dependencies beyond what is unavoidable.

### 20.3 Identity & addressing (future-friendly)
- Treat `env_id` as canonical identity; IPv6 prefixes/addresses may be used as an additional routing/authorization signal later.
- Do not hard-couple identity to IP addresses in v0, but design for:
  - policy based on known partner prefixes
  - simpler peer allowlists when using IPv6

### 20.4 Federation implications
When federation (B2B trust) is implemented:
- support mTLS regardless of IP family
- prefer IPv6 peering where possible
- allow peer policies to include:
  - IPv6 prefix allowlists
  - DNS-based identities (preferred)

### 20.5 Implementation phasing
- v0: ensure components work on dual-stack; avoid IPv4-only assumptions
- v1: document IPv6 deployment guidance (AWS VPC IPv6, security groups, routing)
- v2+: optional IPv6-first peering defaults for federation links

### 20.6 Operational notes
- Prefer DNS names for services; IPs are an optimization/transport detail.
- For health checks and automation, allow ping/HTTP checks over IPv6 as first attempt, then fallback to IPv4.



---

## 21. Backups & disaster recovery (design now, implement v1)

### 21.1 Goals
- Provide automated, reliable backups for:
  - Xyn core Postgres
  - Redis/queue state if needed (often rebuildable; capture configs)
  - App Pack state stores (when apps include their own DB)
  - Local file storage (artifacts on LocalFS; uploads; other state)
- Make backups **automatic** with sane defaults and configurable policies.
- Support restores as a first-class, documented procedure.

### 21.2 Data classification
Classify what must be backed up:
- **Critical:** core Postgres (events, runs, drafts, blueprints, nodes, metadata)
- **Important:** artifact store (if LocalFS), pack definitions, configs
- **Rebuildable:** ephemeral caches, temporary workspaces, derived mirrors

### 21.3 Backup targets
Default backup target: **S3**.
- Use a **separate bucket/prefix** from artifact storage by default.
  - rationale: separate lifecycle rules, access policies, and risk domains

### 21.4 Backup mechanism
Provide a **Backup Pack** (App Pack + Action Pack) that can be invoked by blueprints and scheduled jobs.

Minimum v1 capabilities:
- `backup.postgres.dump` (pg_dump + compress + encrypt optional)
- `backup.files.sync` (rsync/tar + compress + upload)
- `backup.catalog.write` (write backup metadata/artifact)
- `backup.restore.postgres` (documented + guarded)

Backups should be stored as artifacts with explicit retention classes.

### 21.5 Scheduling defaults (sane)
- **Daily** full backup of core Postgres (e.g., 02:00 local)
- Optional: **hourly** WAL archiving or incremental strategy (defer unless required)
- **Daily** file backup if LocalFS is used for artifacts

### 21.6 Retention defaults (sane)
- Daily backups retained **30 days**
- Weekly backups retained **12 weeks**
- Monthly backups retained **12 months**

Support configurable lifecycle:
- S3 Standard → IA → Glacier as policy options

### 21.7 Security
- Encrypt backups at rest (SSE-S3 or SSE-KMS).
- Optionally encrypt client-side before upload.
- Separate IAM role/policy for backup writes.

### 21.8 Multi-database / many-app consideration
If App Packs run their own DBs:
- each App Pack declares its **Backup Contract**:
  - what volumes/DBs are stateful
  - how to dump/restore
- Backup Pack discovers registered packs and executes pack-specific backup actions.

### 21.9 Restore experience (must be real)
- Provide a documented restore runbook.
- Provide a guarded restore blueprint for operator-only use.
- Restore should be testable in a fresh environment (replicated workcell).



---

## 22. Edge, ingress functions, and TLS (v0 required)

### 22.1 Goal
Provide a viable web interface (UI + API) without Kubernetes ingress by including an explicit edge layer.

### 22.2 Recommended approach: Edge Pack
Treat “ingress-ish” concerns as an **Edge Pack** (App Pack + Action Pack).

- **App Pack:** `edge` reverse proxy
- **Responsibilities:**
  - TLS termination + renewals
  - HTTP→HTTPS redirects
  - host-based routing (`ui.*` / `api.*`)
  - security headers (baseline)
  - optional rate limiting (minimal v0, expand v1)

### 22.3 Implementation choice (v0)
Use **Caddy** as the edge proxy (Compose-friendly; ACME built-in).

### 22.4 Certificate issuance strategies
Support both, but set v0 default to keep things simple:

**v0 Default: HTTP-01 (direct-to-host):**
- expose ports 80 and 443 on the host
- Caddy performs ACME HTTP challenge automatically

**Optional: DNS-01 (Route 53, cloud-friendly):**
- no port 80 requirement
- works behind load balancers/restricted networks
- enables wildcard certs per environment

### 22.5 Routing model (ties to DNS plan) (ties to DNS plan)
With env-id canonical domains:
- UI: `core.e-<env_id>.xyence.io` → Xyn Core UI service
- API: `api.e-<env_id>.xyence.io` → Xyn Core API service

Optional alias mirroring:
- `core.<alias>.xyence.io` and `api.<alias>.xyence.io`

### 22.6 Baseline edge policies (v0)
- enforce HTTP→HTTPS redirect
- set timeouts and max body size (sane defaults)
- set basic security headers
- preserve `X-Forwarded-*` headers

### 22.7 Rate limiting and auth (v1+)
- add rate limiting rules for public endpoints
- add optional IP allowlists (IPv6-friendly)
- integrate with future RBAC/IdP layers

### 22.8 Actions (future)
Define edge actions (not required for v0 but planned):
- `edge.config.apply`
- `edge.cert.status`
- `edge.rate_limit.set`



---

## 25. Identity, authentication, and authorization (design now, implement progressively)

### 25.1 v0 stance (local-first)
- v0 local development may run **without authentication** (operator on localhost).
- However, v0 must avoid hard-coding assumptions that block auth later:
  - all requests should flow through a single API layer where auth middleware can be inserted
  - UI routes should be able to switch from "open" to "requires auth" by config

### 25.2 Goals
- Support multi-layer administration safely (operator/owner/reseller) without “leaking” identities across layers.
- Provide a sane authorization model that is:
  - centrally managed
  - composable across app packs
  - supports both organizational roles and functional groupings (teams)
- Support both:
  - external IdPs (OIDC/OAuth2) quickly
  - local accounts that behave equivalently to IdP-backed identities

### 25.3 Terminology (aligns with Admin Model)
- **Principal**: a user or service identity.
- **Operator / Owner / Reseller**: administrative layers relative to an environment.
- **Team**: a functional grouping used for resource access.
- **Role**: coarse-grained privileges (operator/admin/user), not the only access mechanism.

Rule: principals do not “see up the chain.” Higher layers can see lower layers.

### 25.4 Authentication options (phased)
**v0:** none (localhost) OR simple shared token (optional)

**v1:** OIDC/OAuth2 integration using standard libraries (keep surface area low)
- Prefer integrating with external IdPs (Google, Microsoft Entra, Authentik, etc.) via OIDC.
- Avoid requiring Authentik in-core; treat it as an optional App Pack if ever needed.

**v2+:** service-to-service identities and federation identities (mTLS + signed tokens)

### 25.5 Authorization model (core design)
Use **policy-based RBAC + teams**:
- **Roles** provide coarse permissions (Operator, OwnerAdmin, User).
- **Teams** provide resource-level access across roles.

Resources that should support team-based ACLs (planned):
- files/artifacts (where appropriate)
- agents
- blueprints/packs
- datasets/data contracts

### 25.6 Visibility / scoping rules (fixes the "contact leak" issue)
Introduce explicit **scopes** on principals and objects:
- `layer`: operator | owner | reseller
- `owner_org_id`: which org owns the identity/object
- optional `tenant_id` later

Default UI/API queries must include scoping filters so lower layers never see operator identities.
Operator view can bypass scopes (with audit).

### 25.7 Claims mapping (OIDC)
When using OIDC, map claims into Xyn primitives:
- subject (`sub`) → principal id
- email/name → profile
- groups/entitlements → roles and/or team memberships

### 25.8 Local accounts must behave like OIDC accounts
Design requirement:
- A locally-created account must result in the same internal principal representation as an OIDC-backed account.
- “Entitlements” must be representable in Xyn without depending on a specific IdP feature.

Approach:
- internal **Principal** record is authoritative
- OIDC login is just one way to create/update a principal and memberships

### 25.9 API surface (identity manager direction)
Plan a future **Xyn Identity Manager** pack that provides:
- principal CRUD (operator-only)
- role assignment
- team management
- policy management
- audit logs

v1 can start with minimal versions of these endpoints; UI can remain operator-only initially.

### 25.10 Audit (design requirement)
All privileged actions (operator bypass, promotions, identity changes) must create audit events.



---

## 26. Secrets management (design now, keep v0 simple)

### 26.1 v0 stance (local-first)
- For v0 on localhost, keep secrets simple:
  - `.env` / environment variables for provider keys (OpenAI/Anthropic, etc.)
  - do not store secrets in Postgres
  - do not echo secrets into logs/artifacts
- Treat this as a temporary stance; the interfaces should allow swapping in a real secrets backend.

### 26.2 Goals
- Centralize secret storage and access control.
- Support:
  - operator-managed system secrets (provider keys, integration credentials)
  - team-scoped secrets (project/service credentials)
  - optional user-scoped secrets (later)
- Avoid leaking secrets via artifacts, prompts, or debug logs.

### 26.3 Secrets interface (pluggable)
Define a `SecretStore` interface, similar to `ArtifactStore`:
- `put_secret(path, value, metadata?)`
- `get_secret(path) -> value`
- `list_secrets(prefix) -> list[path]` (metadata only)
- `delete_secret(path)` (optional)

The platform should reference secrets by **path**, not by value.

### 26.4 Path-based namespacing (avoid many vaults)
Prefer **one secrets backend** with path namespaces over many vault instances.

Canonical path scheme:
- `sys/<env_id>/providers/<provider>` (system/provider keys)
- `sys/<env_id>/integrations/<name>` (integration creds)
- `team/<team_id>/<name>` (team-scoped)
- `user/<principal_id>/<name>` (user-scoped; later)

This achieves “namespaces” even if the backend lacks them.

### 26.5 Recommended backends (phased)
**v0:** `.env` / process env vars (local only)

**v1 (local + portable):**
- introduce a default **Encrypted Local Secret Store** (file-based) using OS keyring or a local master key.

**v1+ (optional, external): HashiCorp Vault as an App Pack**
- Treat Vault as optional, not required.
- Use a single Vault and enforce isolation via:
  - path prefixes (above)
  - Vault policies
  - per-role/per-team tokens

**Cloud profile (AWS-ready):**
- allow AWS Secrets Manager or SSM Parameter Store as alternative SecretStore backends.

### 26.6 Vault bootstrap/unseal (when used)
If Vault is used:
- automate initialization and unseal.
- in AWS: use KMS auto-unseal.
- locally: start with manual unseal for dev, then consider transit/auto-unseal if needed.

### 26.7 Secrets & teams/roles integration
- Team membership controls access to `team/<team_id>/...` prefixes.
- Operator role controls `sys/<env_id>/...`.
- Owners/admins can be delegated access per policy.

### 26.8 Non-negotiables
- Never persist raw secret values in artifacts.
- Add redaction patterns to log scrubbers.
- Prefer passing secrets to actions by reference:
  - `with: { api_key_ref: "sys/<env_id>/providers/openai" }`

### 26.9 Near-term deliverable (v0/v1 boundary)
- v0: document required env vars (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.)
- v1: implement `SecretStore` + encrypted local backend + secret references in actions



---

## 27. Infrastructure access control (design now, enforce in cloud profile)

### 27.1 Principle
For infrastructure operations, the simplest consistent model is:
- **Access to an infrastructure credential implies authority** to act with that credential.
- Therefore, controlling *who can read/use the credential reference* is the core authorization control.

### 27.2 Implementation direction
- Store infra credentials in `SecretStore` under:
  - `sys/<env_id>/infra/aws/<credential_name>` (or similar)
- Infrastructure actions accept secret references:
  - `aws_cred_ref: "sys/<env_id>/infra/aws/provisioner"`
- Authorization gates access to secret paths:
  - only Operator (and delegated OwnerAdmins if desired) can use infra creds

### 27.3 Audit requirements
Every infrastructure action must emit audit events including:
- principal (actor)
- credential reference used
- resources created/modified
- outcome

---

## 28. Code storage & source control (local-first, Git-compatible)

### 28.1 Guiding position
Do not depend on GitHub for v0/v1. Keep code local and shareable via federation later.

However, keep **Git as the underlying versioning primitive** because:
- it is the universal ecosystem tool
- it enables diff/merge/history
- it maps naturally to AI-driven change review

### 28.2 v0 approach
- Store repositories locally on disk (bare or working repos) under a managed directory.
- Expose minimal repo operations via actions:
  - `git.repo.init`, `git.repo.clone` (optional), `git.commit`, `git.diff`, `git.checkout`, `git.log`
- The UI/workbench can show:
  - latest commits
  - diffs for a run
  - patch review

### 28.3 v1+ optional hosting
If you need a “GitHub-like” UI without GitHub:
- run a lightweight local Git service (e.g., Gitea) as an App Pack.
- federation can later replicate repos between environments.

### 28.4 Provenance binding
Link code changes to Xyn runs:
- a run produces commits tagged with `run_id`
- store diffs/patches as artifacts for audit and review

---

## 29. Build/test/deploy pipeline (event-driven; replaces Jenkins/GitHub Actions)

### 29.1 Goal
Replace external CI/CD systems with a native, event-driven pipeline that:
- builds in ephemeral workcells
- tests in clean, fresh environments
- promotes artifacts through dev → test → prod with gates

### 29.2 Environment stages (conceptual)
Define logical stages:
- **dev**: ephemeral workcell(s) used by agents to implement changes
- **test**: fresh install environment used to validate
- **prod**: long-lived environment

Stages are policies and workflows, not necessarily separate AWS accounts.

### 29.3 Ephemeral workcells (critical design)
- Each significant build/test run should use a **fresh workcell**.
- After completion, workcells are torn down to reduce drift.
- Testing always occurs on a clean spin-up to validate install + migrations.

### 29.4 Event naming conventions (platform-wide)
Use dot-separated, lowercase event names.

**Prefix:**
- Core platform events: `xyn.*`

**Pattern:**
- `xyn.<domain>.<noun>.<verb_or_state>`

Examples:
- `xyn.run.started`
- `xyn.draft.promoted`
- `xyn.cicd.test.passed`

**Event payload baseline (all events):**
- `event_id` (uuid)
- `event_name` (string)
- `occurred_at` (timestamp)
- `env_id` (string)
- `actor` (principal id or `system`)
- `correlation_id` (string; links a chain)
- `run_id` / `step_id` (nullable)
- `resource` (object: `{type, id}`)
- `data` (object; domain-specific)

### 29.5 Core event catalog (sane defaults)
This is the recommended initial catalog. Domains can add more, but these names should remain stable.

\1
#### 29.5.X Footprints & impressions
- `xyn.footprint.recorded`
- `xyn.impression.recorded`
- `xyn.footprint.rollup.created` (optional; for batch rollups)
\1
#### 29.5.X Footprints & impressions
- `xyn.footprint.recorded`
- `xyn.impression.recorded`
- `xyn.footprint.rollup.created` (optional; for batch rollups)
- `xyn.artifact.attached` (artifact linked to run/step/draft)

\1
#### 29.5.X Footprints & impressions
- `xyn.footprint.recorded`
- `xyn.impression.recorded`
- `xyn.footprint.rollup.created` (optional; for batch rollups)
\1
#### 29.5.X Footprints & impressions
- `xyn.footprint.recorded`
- `xyn.impression.recorded`
- `xyn.footprint.rollup.created` (optional; for batch rollups)
\1
#### 29.5.X Footprints & impressions
- `xyn.footprint.recorded`
- `xyn.impression.recorded`
- `xyn.footprint.rollup.created` (optional; for batch rollups)
#### 29.5.6 CI/CD (native)
- `xyn.cicd.change.ready` (implementation complete; ready for test)
- `xyn.cicd.workcell.created`
- `xyn.cicd.workcell.destroyed`
- `xyn.cicd.build.requested`
- `xyn.cicd.build.completed`
- `xyn.cicd.build.failed`
- `xyn.cicd.test.requested`
- `xyn.cicd.test.passed`
- `xyn.cicd.test.failed`
- `xyn.cicd.promotion.requested`
- `xyn.cicd.promotion.approved`
- `xyn.cicd.promotion.rejected`
- `xyn.cicd.deploy.requested`
- `xyn.cicd.deploy.completed`
- `xyn.cicd.deploy.failed`

\1
#### 29.5.X Footprints & impressions
- `xyn.footprint.recorded`
- `xyn.impression.recorded`
- `xyn.footprint.rollup.created` (optional; for batch rollups)
\1
#### 29.5.X Footprints & impressions
- `xyn.footprint.recorded`
- `xyn.impression.recorded`
- `xyn.footprint.rollup.created` (optional; for batch rollups)
\1
#### 29.5.X Footprints & impressions
- `xyn.footprint.recorded`
- `xyn.impression.recorded`
- `xyn.footprint.rollup.created` (optional; for batch rollups)
\1
#### 29.5.X Footprints & impressions
- `xyn.footprint.recorded`
- `xyn.impression.recorded`
- `xyn.footprint.rollup.created` (optional; for batch rollups)
\1
#### 29.5.X Footprints & impressions
- `xyn.footprint.recorded`
- `xyn.impression.recorded`
- `xyn.footprint.rollup.created` (optional; for batch rollups)
### 29.6 Pipeline as blueprints
Model CI/CD steps as blueprints reacting to events:
- `xyn.cicd.change.ready`
- `xyn.cicd.test.requested`
- `xyn.cicd.test.passed` / `xyn.cicd.test.failed`
- `xyn.cicd.promotion.requested`
- `xyn.cicd.promotion.approved`
- `xyn.cicd.deploy.requested`
- `xyn.cicd.deploy.completed`

### 29.7 Build artifacts
- Build outputs are artifacts:
  - container image references
  - SBOMs (later)
  - test reports
  - UI screenshots (optional)

### 29.8 Image build & registry strategy
**v0:** can defer image builds if running directly from source.

**v1 local:**
- build images with BuildKit
- push to a **local registry** App Pack (e.g., `registry:2`) OR store as tar artifacts

**AWS profile:**
- push to ECR

### 29.9 Deployment mechanics
Deployment is substrate-specific but orchestrator-agnostic:
- local/compose: replace containers via compose project update
- later/k8s: rolling update

### 29.10 Gates and approvals
- Promotion to prod requires explicit approval (operator/owner admin).
- CI/test results are attached as artifacts to the promotion request.

### 29.11 Observability hooks
- Every pipeline step emits events and stores logs/artifacts.
- Failures generate Signals/notifications (later).



---

## 30. Programmable Organization Units (POUs) (design now; implement v2+)

### 30.1 Purpose
Create a neutral, future-proof abstraction for "organization" that supports:
- ownership of environments, data, artifacts, packs
- governance (approvals, promotion authority)
- treasury/revenue routing
- delegation and reseller/provider-of-provider nesting

This intentionally captures the useful intent behind “DAO” without requiring blockchain.

### 30.2 Core concept
A **POU** is an entity that can own resources and define policies. A POU may represent:
- a legal company
- a reseller/partner
- a product/program unit
- a project entity
- a customer organization

POUs can form a hierarchy (parent/child) and can delegate authority.

### 30.3 Minimal POU object (schema sketch)
Fields (v2+):
- `pou_id` (uuid)
- `name` (string)
- `type` (enum: company | reseller | project | customer | internal)
- `parent_pou_id` (nullable)
- `status` (active | suspended | archived)
- `default_env_id` (nullable)
- `governance_policy_id` (nullable)
- `treasury_policy_id` (nullable)
- `metadata_json` (optional)

Relationships:
- POU ↔ principals (memberships)
- POU ↔ teams (optional)
- POU ↔ environments (ownership)
- POU ↔ datasets/data contracts (ownership)
- POU ↔ packs/blueprints (ownership/publishing)

### 30.4 Governance (policy engine direction)
Governance answers: “who can do what, under what conditions?”

Minimum policy capabilities:
- approvals required for:
  - promote blueprint/pack
  - deploy to prod
  - create federation link
  - use infra credentials
- approvers can be:
  - roles (Operator, OwnerAdmin)
  - teams
  - explicit principals
- conditions can include:
  - stage (dev/test/prod)
  - risk level (low/med/high)
  - target resource type

### 30.5 Treasury / revenue routing (direction)
Treasury policy answers: “where does money/credit go?”

Design targets:
- attach payment processors later (Stripe, invoices, etc.)
- represent revenue shares for:
  - reseller arrangements
  - marketplace blueprint licensing
  - partner integrations

Keep this as policy + ledger events first; integrate payment rails later.

### 30.6 Optional external ledger anchoring (future)
If desired, a POU can optionally be “anchored” to an external ledger:
- store a reference in metadata (chain + contract/address + network)
- treat it as an additional verification/audit channel, not the primary system of record

### 30.7 Events (future)
- `xyn.pou.created`
- `xyn.pou.updated`
- `xyn.pou.membership.changed`
- `xyn.pou.governance.policy.updated`
- `xyn.pou.treasury.policy.updated`



---

## 31. Policy objects (governance + treasury) (design now; implement v2+)

### 31.1 Design goals
- Policies must be:
  - human-reviewable (UI-friendly)
  - machine-enforceable (deterministic evaluation)
  - versioned and auditable
  - attachable to POUs and (optionally) environments

### 31.2 Common policy envelope (base schema)
All policies share a common envelope:
- `policy_id` (uuid)
- `policy_type` (enum: `governance | treasury`)
- `name` (string)
- `owner_pou_id` (uuid)
- `status` (enum: `draft | active | deprecated`)
- `version` (int)
- `evaluation_mode` (enum: `first_match | deny_overrides | collect_requirements`; default `first_match`)
- `created_at`, `updated_at`
- `description` (optional)
- `rules` (list)
- `metadata_json` (optional)

Rules are evaluated in order according to `evaluation_mode`:
- `first_match` (default): first matching rule decides.
- `deny_overrides`: evaluate all matches; any `deny` wins; otherwise prefer `require_approval` over `allow`.
- `collect_requirements`: evaluate all matches; merge requirements (e.g., max approvals, union of approver sets, require tests if any rule requires), then decide.


### 31.3 GovernancePolicy object shape
Governance policies gate actions (promote, deploy, federation, infra, etc.).

#### 31.3.1 GovernanceRule shape
- `rule_id` (uuid)
- `priority` (int)
- `match` (object)
- `requirements` (object)
- `effect` (enum: `allow | deny | require_approval`)

#### 31.3.2 Match keys (recommended)
`match` may include:
- `action` (string; e.g., `pack.promote`, `cicd.deploy`, `infra.apply`, `federation.link.establish`)
- `stage` (enum: `dev | test | prod | any`)
- `resource_type` (string; e.g., `pack`, `blueprint`, `env`, `dns_record`)
- `risk` (enum: `low | medium | high | any`)
- `env_id` (optional; for env-scoped overrides)

#### 31.3.3 Requirements keys (recommended)
`requirements` may include:
- `approvals`:
  - `min` (int)
  - `from_any_of` (list of subjects)
- `mfa` (bool; future)
- `time_window` (optional; e.g., maintenance window)
- `tests_required` (bool; e.g., require latest CI pass)

Subjects for approval can be:
- `role:<RoleName>` (e.g., `role:Operator`, `role:OwnerAdmin`)
- `team:<team_id>`
- `principal:<principal_id>`

#### 31.3.4 Example GovernancePolicy (informal)
- deny any `infra.apply` unless actor is Operator
- require 1 approval from `role:OwnerAdmin` for `cicd.deploy` to `prod`
- require tests for any `pack.promote`

### 31.4 TreasuryPolicy object shape
Treasury policies route revenue/credits and define splits.

#### 31.4.1 TreasuryRule shape
- `rule_id` (uuid)
- `priority` (int)
- `match` (object)
- `allocation` (object)
- `effect` (enum: `apply | ignore`)

#### 31.4.2 Match keys (recommended)
`match` may include:
- `event_type` (string; e.g., `invoice.paid`, `license.sale`, `usage.metered`)
- `product` (optional string)
- `channel` (optional enum; e.g., `direct | reseller | marketplace`)
- `pou_id` (optional; match a specific org)
- `metadata` (optional; key/value selectors)

#### 31.4.3 Allocation keys (recommended)
`allocation` defines one or more splits:
- `splits`: list of
  - `to` (subject: `pou:<id>` or `wallet:<ref>`)
  - `type` (enum: `percent | fixed`)
  - `value` (number)

Rules should validate that percent splits sum to 100 when used.

#### 31.4.4 Ledger-first implementation
Implement treasury initially as:
- emit ledger events that record intended splits
- integrate payment rails later (Stripe, ACH, on-chain) as adapters

### 31.5 Evaluation model (deterministic)
- Input context:
  - `actor` (principal)
  - `pou_id` (current org)
  - `env_id`
  - `action`
  - `stage`
  - `resource` (type/id)
  - `risk`
  - `artifacts` (e.g., test reports present)
- Output decision:
  - `allow` | `deny` | `require_approval`
  - plus `requirements` if approval is required

### 31.6 Versioning and audit
- Policies are immutable once activated; changes create a new version.
- Every evaluation for a privileged action should record:
  - `policy_id` + `version`
  - matched `rule_id`
  - decision

### 31.7 Events (future)
- `xyn.policy.created`
- `xyn.policy.updated`
- `xyn.policy.activated`
- `xyn.policy.deprecated`
- `xyn.policy.evaluated`



---

## 32. Observability (logs, correlation, artifacts) (v0 required)

### 32.1 Logging format
- **JSON logs** everywhere (structured).
- Logs are written to:
  - **stdout** (primary)
  - **file artifact attachment** per run/workcell/pipeline step (secondary)

### 32.2 Correlation propagation (required)
- `correlation_id` must propagate through:
  - HTTP requests (header)
  - event emission
  - action execution
  - run/step logs

Recommended headers:
- `X-Correlation-Id` (incoming/outgoing)
- `X-Run-Id` / `X-Step-Id` (optional)

### 32.3 Log redaction
- Redact secrets and sensitive fields by default.
- Never log raw secret values.

---

## 33. Notifications & event console (v0 minimal)

### 33.1 v0 stance
Because event frequency/shape is unknown, start with:
- notify on **failures** and **critical events**
- route notifications to a **local graphical event console** (initially)

### 33.2 Notification triggers (default)
- any of:
  - `xyn.*.failed`
  - `xyn.*.validation_failed`
  - `xyn.cicd.test.failed`
  - `xyn.cicd.deploy.failed`
  - `xyn.infra.*.failed`
  - `xyn.backup.failed`

### 33.3 Future targets (v1+)
- Slack, email, SMS, webhook targets via adapters.

---

## 34. API surface & versioning (optimized for automation)

### 34.1 Versioning approach
Use **path-based versioning**:
- `/api/v1/...`

Rationale:
- easiest for automated generation, routing, and backward compatibility
- simple to support multiple versions in parallel

### 34.2 Core vs internal APIs (sane default)
Define two categories:
- **Core API**: stable, versioned (`/api/v1/...`)
  - runs, steps, events
  - artifacts (metadata + signed access later)
  - drafts/blueprints/packs
  - minimal git operations (if exposed)
  - health/status
- **Internal API**: not guaranteed stable
  - mounted under `/api/internal/...`
  - used for workcell control, operator-only maintenance, debug

Default rule:
- only Core APIs are used by external/federated consumers.

---

## 35. v0 bootstrap & preflight (Python wrapper)

### 35.1 Goal
Provide a simple `docker compose up` experience with a preflight that ensures required configuration is present.

### 35.2 Approach
Create a Python bootstrapper (e.g., `xynctl`) that:
1) validates required env vars / `.env`
2) prints actionable errors for missing keys
3) optionally helps generate a `.env` template
4) then runs `docker compose up`

### 35.3 Required credentials (v0)
Define required AI provider keys as:
- `OPENAI_API_KEY` (if OpenAI provider enabled)
- `ANTHROPIC_API_KEY` (if Anthropic provider enabled)

Sane default behavior:
- require at least **one** provider key to be present
- allow disabling a provider via config

### 35.4 Extensibility
As more integrations are added, register required env vars in a central manifest so preflight stays authoritative.

---

## 36. Database strategy (manageability vs scalability)

### 36.1 Recommended default
Use a **single shared Postgres** as the default datastore.

Isolation strategy:
- logical namespaces (schemas/prefixes) per pack
- pack migrations are still pack-owned

Rationale:
- easiest operationally (backups, upgrades)
- best early-stage reliability
- avoids explosion of DB instances on a single node

### 36.2 When to split DBs (later)
Allow per-pack databases only when justified by:
- scaling/isolation requirements
- security/compliance boundaries
- operational ownership boundaries

---

## 37. Pack versioning & migrations (sane stub)

### 37.1 Version model
- Packs use **semantic versioning**: `MAJOR.MINOR.PATCH`.
- Pack registry records:
  - `pack_id`, `name`, `version`, `digest` (content hash)
  - compatibility range for core (`xyn_core >= ...`)

### 37.2 Migration stub
- Each pack may provide migrations as ordered steps.
- Add actions (planned):
  - `pack.migrate.plan`
  - `pack.migrate.apply`

### 37.3 Default policy
- v0/v1: **forward-only migrations** (no automatic rollback).
- Rollback is achieved by restoring from backups + redeploying prior pack version.

---

## 38. Resource limits & safety rails (sane defaults)

### 38.1 Defaults (local-first)
- Max concurrent workcells: **3**
- Max concurrent CI/test workcells: **1**
- Workcell TTL (auto-destroy): **2 hours** after inactivity
- Artifact store quota (LocalFS): **20 GB** (configurable)
- Max artifact size (single): **250 MB**
- Max event backlog retained locally: **7 days** (or cap by size)

### 38.2 Runaway automation protection
- per-run max steps: **200**
- per-run wall-clock limit: **60 minutes** (configurable)
- rate-limit event handlers if backlog grows

### 38.3 Overrides
All limits are configurable per deployment profile.



---

## 39. Data portability & inter-environment transfers (design now; implement v1+)

### 39.1 Goals
- Enable moving data between environments as a first-class capability (local ↔ cloud, env ↔ env).
- Support both:
  - **federated access** (query/operate remotely)
  - **bulk transfer** (copy/replicate datasets, packs, artifacts)
- Make transfers auditable, policy-governed, and resumable.

### 39.2 Transfer primitives
Introduce a generic transfer concept:
- **ExportPackage**: a versioned bundle describing what was exported
- **ImportRun**: a run that applies an ExportPackage into a target environment

ExportPackage contents may include:
- database subsets (by resource type or query)
- artifacts (files/blobs)
- pack/blueprint definitions
- metadata manifests

### 39.3 Packaging format (sane default)
- Use a manifest-driven bundle:
  - `manifest.json` (what’s included, checksums, versions, timestamps)
  - `db/` (logical dumps per resource domain)
  - `blobs/` (artifact objects)
- Transport options:
  - local file (zip/tar)
  - object store (S3) location

### 39.4 Deterministic IDs and remapping
To support safe imports:
- prefer stable IDs for core resources (`env_id`, `pou_id`, `pack_id`, etc.)
- support ID remapping on import when collisions occur
- record mappings in the ImportRun artifacts

### 39.5 Security and policy
- Transfers must be governed by GovernancePolicy:
  - exporting sensitive data requires approval depending on risk
  - importing into prod requires approval
- Use signed manifests (future) and checksum verification.

### 39.6 Federation integration (B2B portal)
In B2B/federation:
- remote environments can request:
  - dataset export
  - artifact export
  - pack export
- data owners approve via governance gates.

### 39.7 Actions (planned)
- `transfer.export.plan`
- `transfer.export.run`
- `transfer.import.plan`
- `transfer.import.run`

### 39.8 Events (planned)
- `xyn.transfer.export.requested`
- `xyn.transfer.export.completed`
- `xyn.transfer.import.requested`
- `xyn.transfer.import.completed`
- `xyn.transfer.failed`

---

## 40. Documentation pipeline (AI-generated post-test, pre-prod)

### 40.1 Principle
During implementation, the primary agent should focus on code. Documentation is generated **after tests pass** and **before production deployment**.

### 40.2 Default workflow
- Development agent instructions:
  - do **not** generate or update documentation files
  - keep changes minimal and code-focused

- After tests pass:
  - trigger a **Documentation Review** agent that:
    - reviews the diff/commits (scoped to changes since last doc run)
    - updates canonical docs
    - generates/updates mermaid diagrams
    - produces user-facing and technical docs as needed

- Before deploy:
  - require doc run completion for eligible changes (configurable)

### 40.3 Canonical documentation structure (sane default)
Per pack/app:
- `docs/overview.md` (what it is, why it exists)
- `docs/usage.md` (how to use, API examples)
- `docs/architecture.md` (components, data flow)
- `docs/diagrams/*.mmd` (mermaid sources)
- `CHANGELOG.md` (optional; can be AI-maintained)

### 40.4 Documentation artifacts
Store documentation outputs as artifacts linked to:
- the run
- the pack version

### 40.5 Events (planned)
- `xyn.docs.requested`
- `xyn.docs.completed`
- `xyn.docs.failed`



---

## 41. Consistency sweep (actions, events, storage, phase)

### 41.1 Conventions
For each subsystem, ensure:
1) **Actions** exist (what can be done)
2) **Events** exist (what happened)
3) **Storage contracts** are clear (DB vs ArtifactStore vs SecretStore)
4) **Phase** is explicit (v0/v1/v2+)

### 41.2 Subsystem matrix (current)

#### Core runtime (v0)
- Storage: Postgres (core), ArtifactStore (logs)
- Actions: run/step execution; action runner
- Events: `xyn.run.*`, `xyn.step.*`
- Notes: correlation propagation required

#### Artifacts (v0)
- Storage: ArtifactStore (LocalFS v0)
- Events: `xyn.artifact.*`
- Notes: no secrets in artifacts

#### Secrets (design v0, implement v1)
- Storage: SecretStore (env vars v0; encrypted local v1)
- Actions (planned v1): `secret.put`, `secret.get`, `secret.list`
- Events (planned v1): `xyn.secret.updated` (metadata only)

#### Edge (v0 localhost)
- Storage: config as code + runtime config
- Actions (planned): `edge.config.apply`
- Events (planned): `xyn.edge.config.applied`
- Phase: HTTP-only localhost in v0; ACME v1+

#### DNS (v1+)
- Storage: SecretStore for Route53 creds; DB for desired state
- Actions (planned): `dns.zone.create`, `dns.record.upsert`, `dns.record.delete`
- Events: `xyn.dns.*`

#### Backups (design v0, implement v1)
- Storage: S3 (cloud) or local target (later); artifacts for manifests
- Actions: `backup.*` (planned)
- Events: `xyn.backup.*`, `xyn.restore.*`

#### CI/CD pipeline (design v0, implement v1)
- Storage: artifacts (test reports), DB (promotion requests)
- Actions: `cicd.build.*`, `cicd.test.*`, `cicd.deploy.*` (planned)
- Events: `xyn.cicd.*`

#### Git (v0 minimal)
- Storage: local repos on disk
- Actions: `git.*` (minimal in v0)
- Events: `xyn.git.*`

#### Notifications / event console (v0 minimal)
- Storage: DB (events), UI console
- Actions (planned): `notify.route.set`, `notify.target.add`
- Events: `xyn.notify.*` (optional later)

#### Federation / B2B (design v0, implement v2+)
- Storage: DB (links, policies), ArtifactStore (export bundles)
- Actions: `federation.invite.*`, `federation.link.*` (planned)
- Events: `xyn.federation.*`

#### Transfers / portability (design v0, implement v1+)
- Storage: ArtifactStore (bundles), DB (requests, mappings)
- Actions: `transfer.export.*`, `transfer.import.*`
- Events: `xyn.transfer.*`

#### Identity / authz (design v0, implement v1+)
- Storage: DB (principals, roles, teams), SecretStore (keys if any)
- Actions (planned): `identity.principal.*`, `identity.team.*`, `policy.evaluate`
- Events: `xyn.identity.*`, `xyn.policy.*`

#### POUs + governance/treasury (design v0, implement v2+)
- Storage: DB (pou + policy objects)
- Actions (planned): `pou.*`, `policy.*`
- Events: `xyn.pou.*`, `xyn.policy.*`

### 41.3 Open questions to resolve before v0 build
- Pick the initial **API framework** for core (Python) and the minimal route set for v0 UI/API.
- Confirm initial **UI scope** (event console + run launcher + artifact browser).
- Confirm the minimal **action runner** interface shape (inputs/outputs, secret refs, artifact refs).

---

## 42. Phase map (what ships when)

### 42.1 v0 (local-first, simplest)
- Docker Compose + Python bootstrap preflight (`xynctl`)
- Core API `/api/v1` (minimal)
- Local UI (HTTP-only) with:
  - event console
  - run launcher
  - artifact/log browser
- Postgres + Redis
- ArtifactStore: LocalFS
- Secrets: env vars only (no DB)
- Git: local repo operations (minimal)
- JSON logs to stdout + file artifacts
- Safety rails defaults

### 42.2 v1 (operational hardening)
- SecretStore (encrypted local) + secret refs in actions
- Backup Pack (daily backups; restore blueprint)
- Transfer export/import actions for portability
- CI/CD blueprint pipeline with ephemeral workcells + test-on-fresh
- Optional local registry + image build

### 42.3 v2+ (multi-org / federation / governance)
- Identity Manager (OIDC + local accounts)
- Teams-first authorization everywhere
- POUs + governance/treasury policies
- Federation/B2B portal + approvals + data-sharing policies
- Optional external ledger anchoring

---

## 43. v0 guardrails (explicit)

- v0 assumes **Local v0 deployment profile**.
- v0 runs **HTTP-only on localhost**.
- v0 does not require Route53/DNS/ACME.
- v0 treats auth as open localhost, but retains a single API layer where auth middleware can be inserted later.



---

## 44. v0 minimal route inventory (FastAPI + Jinja2 + HTMX)

### 44.1 UI routes (server-rendered)
Base UI is HTML pages with HTMX-driven partial updates.

- `GET /` → redirect to `/ui/events`

**Event console**
- `GET /ui/events` → main event console page
- `GET /ui/events/stream` → HTMX polling endpoint (returns event list partial)
- `GET /ui/events/:event_id` → event detail page

**Runs**
- `GET /ui/runs` → list runs
- `GET /ui/runs/new` → run launcher form
- `POST /ui/runs` → create a run (then redirect to run detail)
- `GET /ui/runs/:run_id` → run detail (steps, status)
- `GET /ui/runs/:run_id/steps/:step_id` → step detail

**Artifacts**
- `GET /ui/artifacts` → artifact browser
- `GET /ui/artifacts/:artifact_id` → artifact detail + download link
- `GET /ui/runs/:run_id/artifacts` → artifacts for a run (partial)

**Health**
- `GET /ui/health` → simple status page

### 44.2 API routes (versioned)
All stable APIs live under `/api/v1`.

**Health**
- `GET /api/v1/health` → {status, version, uptime}

**Events**
- `GET /api/v1/events` → list/filter events (supports pagination)
- `GET /api/v1/events/:event_id` → event detail
- `POST /api/v1/events` → emit event (operator/system; v0 open localhost)

**Runs & steps**
- `POST /api/v1/runs` → create run
- `GET /api/v1/runs` → list runs
- `GET /api/v1/runs/:run_id` → run detail
- `POST /api/v1/runs/:run_id/cancel` → cancel run
- `GET /api/v1/runs/:run_id/steps` → list steps
- `GET /api/v1/runs/:run_id/steps/:step_id` → step detail

**Artifacts**
- `POST /api/v1/artifacts` → create artifact metadata + upload initiation (v0 can be direct upload)
- `GET /api/v1/artifacts` → list artifacts
- `GET /api/v1/artifacts/:artifact_id` → artifact metadata
- `GET /api/v1/artifacts/:artifact_id/download` → download

**Drafts / packs / blueprints (stubs allowed in v0)**
- `POST /api/v1/drafts` → create draft
- `GET /api/v1/drafts` → list drafts
- `GET /api/v1/drafts/:draft_id` → draft detail

### 44.3 Internal API routes (not stable; operator-only later)
Mounted under `/api/internal`.

- `POST /api/internal/actions/execute` → execute an action (v0 may call directly from core)
- `GET /api/internal/workcells` → list workcells (v1)
- `POST /api/internal/workcells/create` → create workcell (v1)
- `POST /api/internal/workcells/:id/destroy` → destroy workcell (v1)

### 44.4 HTMX partial conventions
For each page, define partial endpoints returning fragments:
- `GET /ui/events/_list`
- `GET /ui/runs/_list`
- `GET /ui/runs/:run_id/_status`
- `GET /ui/artifacts/_list`

### 44.5 Notes
- v0 is open localhost; auth middleware can be inserted later.
- Ensure all UI actions are backed by API calls or a single service layer to avoid split logic.



---

## 45. v0 payload schemas (API DTOs; sane defaults)

### 45.1 Conventions
- JSON keys are **snake_case**.
- Timestamps are ISO-8601 UTC strings.
- IDs are UUID strings unless noted.
- All responses include `correlation_id` when available.

### 45.2 Health
**GET `/api/v1/health` → HealthResponse**
- `status` (string; e.g., `ok`)
- `version` (string)
- `uptime_seconds` (int)
- `now` (timestamp)

### 45.3 Events

**Event**
- `event_id` (uuid)
- `event_name` (string)
- `occurred_at` (timestamp)
- `env_id` (string)
- `actor` (string; principal id or `system`)
- `correlation_id` (string)
- `run_id` (uuid, nullable)
- `step_id` (uuid, nullable)
- `resource` (object: `{ "type": string, "id": string }`, nullable)
- `data` (object; arbitrary JSON)

**GET `/api/v1/events` → EventListResponse**
- `items` (list[Event])
- `next_cursor` (string, nullable)

Query params (defaults):
- `limit` (int, default 50)
- `cursor` (string, nullable)
- `event_name` (string, nullable)
- `run_id` (uuid, nullable)

**POST `/api/v1/events` → EmitEventRequest**
- `event_name` (string)
- `resource` (nullable)
- `data` (object)
- `run_id` / `step_id` (nullable)

Response: `Event`

### 45.4 Runs & steps

**RunCreateRequest**
- `name` (string)
- `blueprint_ref` (string, nullable)  
  (v0 can be a placeholder; later becomes `pack/blueprint@version`)
- `inputs` (object; arbitrary JSON; default `{}`)
- `priority` (int, default 0)

**Run**
- `run_id` (uuid)
- `name` (string)
- `status` (enum: `created | running | completed | failed | cancelled`)
- `created_at` (timestamp)
- `started_at` (timestamp, nullable)
- `completed_at` (timestamp, nullable)
- `actor` (string)
- `correlation_id` (string)
- `inputs` (object)
- `outputs` (object, nullable)
- `error` (object, nullable)

**RunListResponse**
- `items` (list[Run])
- `next_cursor` (string, nullable)

**Step**
- `step_id` (uuid)
- `run_id` (uuid)
- `name` (string)
- `status` (enum: `created | running | completed | failed | skipped`)
- `started_at` (timestamp, nullable)
- `completed_at` (timestamp, nullable)
- `logs_artifact_id` (uuid, nullable)
- `inputs` (object, nullable)
- `outputs` (object, nullable)
- `error` (object, nullable)

**POST `/api/v1/runs` response**
- returns `Run`

**POST `/api/v1/runs/:run_id/cancel` response**
- returns `Run` (updated)

### 45.5 Artifacts

**ArtifactCreateRequest**
- `name` (string)
- `kind` (string; e.g., `log | report | bundle | file`)
- `content_type` (string; e.g., `application/json`, `text/plain`)
- `byte_length` (int, nullable)
- `run_id` (uuid, nullable)
- `step_id` (uuid, nullable)
- `metadata` (object, default `{}`)

**Artifact**
- `artifact_id` (uuid)
- `name` (string)
- `kind` (string)
- `content_type` (string)
- `byte_length` (int, nullable)
- `created_at` (timestamp)
- `created_by` (string)
- `run_id` / `step_id` (nullable)
- `sha256` (string, nullable)
- `metadata` (object)

**ArtifactListResponse**
- `items` (list[Artifact])
- `next_cursor` (string, nullable)

**POST `/api/v1/artifacts` response**
Two acceptable v0 patterns:
1) direct upload:
   - request includes a base64 or multipart upload
   - response returns `Artifact`
2) two-step upload (preferred long-term):
   - response returns `Artifact` + `upload_url` (internal/local in v0)

**GET `/api/v1/artifacts/:artifact_id/download`**
- returns raw bytes with appropriate content-type

### 45.6 Draft stubs (v0 optional)
**Draft**
- `draft_id` (uuid)
- `name` (string)
- `kind` (string; e.g., `pack | blueprint`)
- `status` (enum: `draft | validated | promoted`)
- `created_at` (timestamp)
- `updated_at` (timestamp)
- `content` (object; arbitrary JSON)

### 45.7 Error shape (standard)
**ErrorResponse**
- `error`:
  - `code` (string)
  - `message` (string)
  - `details` (object, nullable)
- `correlation_id` (string, nullable)

### 45.8 Pagination (standard)
Use cursor pagination consistently:
- request: `?limit=50&cursor=<token>`
- response: `next_cursor` (nullable)

### 45.9 Notes
- Keep DTOs stable in `/api/v1`.
- Internal endpoints may return richer debug shapes.

