# Flux Control Plane

GPU-accelerated ML inference and model serving platform. This repository is the
control plane: the strongly consistent service that owns the model catalog,
tenancy, access, and (in later phases) discovery, autoscaling, and cost.

This is a phased build. Phase 1 delivered the production foundation and the Model
Registry slice; Phase 2 adds tenancy and role-based access control.

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

Deferred to later phases: the inference gateway and OpenAI-compatible serving API,
router/scheduler and GPU workers, autoscaling and cost, and the full
Kubernetes/Helm/Terraform/CI stack.

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
