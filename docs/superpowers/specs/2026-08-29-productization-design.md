# DevicePilot Phase 4 Productization Design

## Scope

Phase 4 packages the accepted DevicePilot MVP for local development, single-instance Docker deployment, public portfolio review, and repeatable demonstration. It adds configuration, abuse protection, deployment assets, demo data, and concise documentation without changing Device/Fault CRUD or the Diagnosis schema.

## Runtime design

- Backend configuration comes from environment variables: `DATABASE_URL`, `CORS_ORIGINS`, `OPENAI_API_KEY`, `OPENAI_MODEL`, and `DIAGNOSIS_RATE_LIMIT_PER_MINUTE`.
- The frontend uses same-origin `/api` by default. Vite proxies it during development and nginx proxies it in Docker.
- Docker Compose runs a FastAPI backend and nginx-served React production build. SQLite is stored in a named volume.
- The backend is not published as a public container port; nginx is the public entry point. A localhost-only backend port supports local API/OpenAPI inspection.

## Diagnosis cost protection

The diagnosis route uses a small in-memory, per-client sliding-window limiter. The nginx proxy supplies the originating client address; direct requests use the socket peer address. Exceeding the configured limit returns HTTP 429 with a stable, non-sensitive error. This protects a single-instance MVP only; multi-instance deployment requires a gateway or shared store.

## Demo data

An explicit idempotent seed command inserts a small Chinese portfolio dataset identified by stable serial numbers. It can be run repeatedly, never stores secrets, and is not imported by tests or normal application startup. Compose runs it before starting the backend so a new demo volume is immediately useful.

## Deployment and security boundaries

The OpenAI key remains backend-only. nginx serves static assets and proxies `/api`; the browser never receives provider credentials. CORS is disabled unless origins are explicitly configured. SQLite is documented as a single-instance MVP choice, with PostgreSQL reserved for future work.

## Verification

Automated checks cover configuration parsing, rate limiting, seed idempotency, backend regression, frontend regression, TypeScript, and production build. Docker verification checks image builds, Compose startup, frontend/API/OpenAPI HTTP, rate-limit behavior, and SQLite persistence across container recreation. Browser tooling failure is reported separately with a 1440/768/375 manual checklist.
