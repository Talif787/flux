# Flux Control Plane

GPU-accelerated ML inference and model serving platform. This repository is the
control plane: the strongly consistent service that owns the model catalog,
tenancy, access, and (in later phases) discovery, autoscaling, and cost.

This is a phased build. Phase 1 delivered the production foundation and the Model
Registry slice; Phase 2 added tenancy and role-based access control; Phase 3 adds
the request plane: an OpenAI-compatible serving API in front of clean router,
scheduler, engine, rate-limiter, and idempotency abstractions; Phase 4 (Part A)
adds the compute plane as a standalone Flux worker that serves inference behind a
pluggable backend port; Phase 4 (Part B) connected the two planes with a worker
registry, discovery-based routing, and a remote inference engine, so the gateway
dispatches requests to registered workers over HTTP.

## What is in Phase 1

- Clean/hexagonal architecture: domain, application, infrastructure, presentation.
- Model Registry: register models and model versions, list and fetch, per tenant.
- API-key authentication (secure by default): every business endpoint requires a key.
- Structured JSON logging with per-request correlation ids.
- OpenTelemetry tracing hooks (opt-in via configuration).
- Health, readiness, and liveness probes.
- PostgreSQL persistence with Alembic migrations and seed data.
- RFC 9457 problem+json error responses.
- Unit, integration, and API tests that run without external services (SQLite).
- Dockerfile (multi-stage, non-root) and Docker Compose for local development.

## What is in Phase 2

- Tenant lifecycle management: create, list, fetch, suspend, and reactivate tenants.
- API-key management: issue (plaintext returned exactly once), list (secret never
  shown, only a display prefix), and revoke. Revoked keys stop authenticating.
- Role-based access control with a canonical role vocabulary
  (platform.admin, tenant.admin, model.read, model.write).
- Platform admin acts as a superuser; tenant admins are scoped to their own tenant
  and cannot escalate privileges by granting platform.admin.
- RBAC enforced on the Model Registry: reads require model.read, writes model.write.
- A framework-free key hashing module (HMAC-SHA256) shared by auth and management.

## What is in Phase 3

- OpenAI-compatible chat completions at POST /v1/chat/completions, both a
  single JSON response and Server-Sent Events streaming (stream=true), with
  usage accounting (prompt, completion, total tokens).
- Request-plane abstractions as ports with in-process or Postgres adapters:
  a Router (single logical pool today, the seam for KV-aware routing), a
  Scheduler (bounded admission control that sheds load with HTTP 503), an
  InferenceEngine, a RateLimiter, and an IdempotencyStore.
- A deterministic stub engine behind the InferenceEngine port so the whole
  path is exercisable without GPUs. Real serving backends replace it in
  Phase 4 without touching callers.
- Per-tenant token-bucket rate limiting (HTTP 429 with a Retry-After header).
- Idempotent POST support via the Idempotency-Key header, backed by a
  Postgres record that also acts as an in-flight lock: repeats replay the
  stored response, a reused key with a different body is rejected (422), and
  a failed request is discarded so a retry can proceed.
- A new inference.invoke role gating the serving endpoints (platform.admin
  remains a superuser).
- Alembic migration 0003 adds the idempotency_records table.

## What is in Phase 4 (Part A): the Flux worker

- A standalone, runnable serving node (`flux.worker.app`) separate from the
  control plane, started with `make run-worker` (port 8090).
- An OpenAI-compatible inference surface on the worker
  (POST /v1/chat/completions, JSON and SSE streaming, GET /v1/models,
  livez/readyz), the same contract real engines such as vLLM and TGI expose.
- An InferenceBackend port with a deterministic EchoBackend (CPU, no GPU). A
  real GPU engine plugs into this port without changing the worker's HTTP
  surface.
- Model gating: a worker advertises the models it serves
  (`FLUX_WORKER_SERVED_MODELS`) and returns 404 for anything else; an empty
  set serves any model (developer convenience).
- Worker configuration is isolated under the `FLUX_WORKER_` prefix and an
  optional `.env.worker`, so a worker and the control plane run side by side.

## What is in Phase 4 (Part B): control-plane integration

- A worker registry (`/v1/workers`, `worker.register` role): register or update
  a worker (idempotent `PUT`), refresh liveness (`POST .../heartbeat`),
  deregister (`DELETE`), and list. Workers are platform-global, not
  tenant-scoped, and carry the models they serve plus a max-concurrency hint.
- Discovery-based routing (`RegistryRouter`): given a model, it asks the worker
  directory for active workers whose heartbeat is fresh (within
  `FLUX_WORKER_HEARTBEAT_TTL_SECONDS`) and that advertise the model, then picks
  one round-robin. No candidate yields HTTP 503.
- A remote inference engine (`RemoteInferenceEngine`): calls the selected
  worker's OpenAI-compatible surface over HTTP (JSON and SSE), parses the
  response, and maps transport failures or worker errors to HTTP 502.
- A serving-mode switch: `FLUX_SERVING_BACKEND=stub` (default) keeps the
  in-process stub engine; `remote` selects the registry router and remote
  engine. The switch is config-gated, so Phases 1 to 3 behavior is unchanged by
  default.
- Model linkage: the gateway still resolves the model in the caller's tenant
  (404 if unregistered), then routes to a worker that serves it (503 if none),
  so both the tenant catalog and the worker's advertised set must agree.

Migration `0004_workers` adds the `workers` table. `httpx` is now a runtime
dependency (the gateway calls workers).

In this phase workers are registered through the control-plane API (an operator
or a deploy hook issues the `PUT`); a generous heartbeat TTL means a single
registration keeps a worker routable for a test session. Worker self-registration
(a startup hook and heartbeat loop inside the worker) is a small follow-on.

Deferred to later phases: worker self-registration and a real GPU engine behind
the worker's InferenceBackend port (Phase 4 follow-on); streaming metering,
and autoscaling recommendations plus a real provisioner (with Phase 6); and further cost
(Phase 5), and the full Kubernetes/Helm/Terraform/CI stack (Phase 6).

## What is in Phase 5 (Part A): usage metering and cost

Phase 5 Part A adds the FinOps read side: it meters real usage from the serving
path, prices it, and reports cost per tenant and per model.

- Every non-streaming completion is metered into a `usage_records` row (tenant,
  model, prompt and completion tokens, timestamp). Metering is best-effort: a
  metering failure is logged and never fails the inference request. It is gated
  by `FLUX_METERING_ENABLED` (default on).
- Per-model prices are a managed resource under `/v1/pricing`: platform admins
  set rates (`PUT`), read one or list all (`GET`), and remove them (`DELETE`).
  Rates are per 1000 prompt tokens and per 1000 completion tokens. Models without
  an explicit price fall back to the configured defaults.
- A cost report is served at `GET /v1/usage`, aggregating usage by model over an
  optional time window (`from`, `to`) with an optional `model` filter. A tenant
  admin sees their own tenant; a platform admin can scope to any tenant (or all
  tenants). Each line carries token totals, request count, and computed cost, and
  the report carries the currency and grand totals.
- Money is computed with `Decimal`, quantized to six places, and serialized as a
  string in responses. Prices are stored as strings so exact rates survive on
  SQLite, which has no exact numeric type. Migration `0005_metering` adds the
  `usage_records` and `model_prices` tables.
- Metering reuses existing roles: `tenant.admin` views usage and prices,
  `platform.admin` manages prices. No new roles are introduced.

Scope note: only non-streaming completions are metered in Part A. Streaming usage
metering, per-tenant budgets with serving-path enforcement, and autoscaling
recommendations are deferred to Phase 5 Part B.

## What is in Phase 5 (Part B): budgets and enforcement

Phase 5 Part B completes the FinOps story: it turns the cost figures from Part A
into per-tenant monthly budgets and can enforce them at the serving path.

- Per-tenant budgets are a managed resource under `/v1/budgets`: platform admins
  set a monthly limit (`PUT`), list all budgets (`GET`), and remove one
  (`DELETE`). A budget is one monthly limit per tenant, in the configured billing
  currency. Migration `0006_budgets` adds the `budgets` table.
- `GET /v1/budgets/{tenant_id}` returns a budget status: the limit, current
  calendar-month spend (computed from usage and prices, reusing the Part A cost
  report), remaining amount, and whether the budget is exceeded. A tenant admin
  sees their own tenant; a platform admin can view any tenant.
- Enforcement is a serving-path guard. When `FLUX_BUDGET_ENFORCEMENT_ENABLED` is
  on, a request from a tenant whose month-to-date spend has reached its limit is
  rejected before admission with HTTP 402. The guard fails open: if spend cannot
  be determined it allows the request and logs, so a metering hiccup never blocks
  all traffic, and a tenant with no budget is unconstrained. Enforcement is off by
  default, so existing behavior is unchanged until it is switched on.
- Budgets reuse existing roles: `tenant.admin` views a budget, `platform.admin`
  manages budgets. No new roles.

Scope note: autoscaling recommendations (a scaling policy over load signals plus a
provisioner port) are not part of this phase. They pair naturally with the
Phase 6 provisioning and IaC work, where the actual scaling action lives.

## What is in Phase 6 (Part A): containerization and CI

Phase 6 Part A packages the control plane and automates the quality gates.

- A `.dockerignore` keeps the build context small and reproducible (no `.git`,
  virtualenv, caches, tests, or local `.env`). The existing multi-stage
  `Dockerfile` builds a slim, non-root runtime image that serves the gateway; the
  same image runs the worker by overriding the command
  (`uvicorn flux.worker.app:app --port 8090`).
- GitHub Actions CI (`.github/workflows/ci.yml`) runs on every push to `main` and
  every pull request, in three jobs: quality (`make lint`, `make typecheck`,
  `make test`), migrations (applies the Alembic chain against a real PostgreSQL
  service and verifies it downgrades to base and re-upgrades), and a Docker build
  that proves the image builds.
- A release workflow (`.github/workflows/release.yml`) builds and publishes the
  image to the GitHub Container Registry on version tags (`v*`), tagged with the
  git tag, the semver version, and the commit SHA. It uses the built-in
  `GITHUB_TOKEN`, so no extra secrets are required.
- `make ci` runs the same lint, type-check, and test gates locally.

Scope note: Kubernetes manifests and a Helm chart (with autoscaling) are Phase 6
Part B; Terraform for the cloud footprint (GKE, Cloud SQL, Artifact Registry) is
Phase 6 Part C.

## What is in Phase 6 (Part B): Kubernetes and Helm

Phase 6 Part B packages the control plane for Kubernetes as a Helm chart and adds
horizontal autoscaling.

- The chart lives in `deploy/helm/flux`. It renders a gateway Deployment and
  Service, a ConfigMap for non-secret `FLUX_*` config, a Secret for the API key
  pepper and database URL (or an `existingSecret` you manage), a ServiceAccount, an
  optional Ingress, and an optional PodDisruptionBudget. Liveness and readiness
  probes use the app's `/livez` and `/readyz`.
- Autoscaling: a HorizontalPodAutoscaler (autoscaling/v2) scales the gateway on CPU
  utilization between `minReplicas` and `maxReplicas`. This is the autoscaling that
  earlier phases deferred; it requires the cluster's metrics-server. When
  autoscaling is enabled the Deployment omits a static replica count so the HPA
  owns it.
- Schema migrations run as a pre-install and pre-upgrade Helm hook Job
  (`alembic upgrade head`) using the same image, so the schema is current before new
  pods serve traffic.
- The worker is optional (`worker.enabled`, off by default since the stub backend
  needs none). When enabled it runs the same image with the worker command and its
  own Service, so one image serves both roles.
- `deploy/k8s/dev-postgres.yaml` is a development-only PostgreSQL manifest for
  testing the chart on a local cluster (kind or minikube). Production uses a managed
  database (Phase 6 Part C provisions Cloud SQL).

Validate and install:

    helm lint deploy/helm/flux
    helm template flux deploy/helm/flux            # render manifests
    helm install flux deploy/helm/flux --dry-run   # server-side dry run

Scope note: Terraform for the cloud footprint (GKE, Cloud SQL, Artifact Registry,
IAM) is Phase 6 Part C. This chart deploys onto an existing cluster and expects a
reachable database.

## Requirements

- Python 3.12+
- Docker and Docker Compose (for the containerized workflow)

## Local development

    make install
    cp .env.example .env
    docker compose up -d db
    make migrate
    make seed        # prints a one-time API key
    make run

Then:

    curl localhost:8000/livez
    curl -H "Authorization: Bearer <API_KEY>" \
      -H "Content-Type: application/json" \
      -d '{"name":"llama-3-8b","family":"llama"}' \
      localhost:8000/v1/models

Interactive API docs: http://localhost:8000/docs
OpenAPI (3.1) document: http://localhost:8000/openapi.json

## Full stack via Compose

    make compose-up      # builds the app, starts Postgres, runs migrations
    make compose-down

## Quality gates

    make lint            # ruff lint + format check
    make typecheck       # mypy (strict)
    make test            # pytest
    make cov             # coverage report

## Configuration

All configuration is environment driven with the FLUX_ prefix. See
`.env.example` for the full list.

| Variable | Default | Purpose |
|---|---|---|
| FLUX_ENV | local | Deployment environment |
| FLUX_DATABASE_URL | postgresql+asyncpg://... | Async SQLAlchemy URL |
| FLUX_API_KEY_PEPPER | change-me | HMAC pepper for API-key hashing |
| FLUX_LOG_JSON | true | JSON logs when true, console when false |
| FLUX_OTEL_ENABLED | false | Enable OpenTelemetry tracing |

## Layout

    src/flux/
      api/         app factory, middleware, health, DI wiring
      auth/        principal, api-key persistence, auth dependencies
      models/      model lifecycle: domain, application, persistence, API
      config.py    twelve-factor settings
      db.py        engine and session factory
      errors.py    error types and problem details
      events.py    domain events and in-process event bus
    migrations/    Alembic environment and versions
    scripts/       operational scripts (seed)
    tests/         unit, integration, api
