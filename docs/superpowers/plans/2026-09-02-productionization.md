# DevicePilot Phase 9.1 Productionization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a locally validated, standalone single-node production deployment definition for DevicePilot without deploying to a VPS, configuring a real domain, using real secrets, or committing changes.

**Architecture:** Official Caddy is the only published edge service on ports 80 and 443. It authenticates every application request, removes `Authorization`, and proxies only to the un-published frontend nginx service; frontend nginx forwards `/api` over an internal Compose network to one un-published FastAPI backend using SQLite and the existing `/data` persistence layout. CI validates code, Compose, Caddy, and both images but never deploys.

**Tech Stack:** Docker Compose, Caddy 2, nginx, FastAPI, SQLAlchemy, SQLite online backup API, Pytest, React/Vite/Vitest, GitHub Actions.

**Spec:** Production deployment requirements recorded in this plan.

## Global Constraints

- Do not deploy to a real VPS or configure a real domain.
- Do not use or commit real usernames, passwords, password hashes, API keys, backups, or expanded production Compose output.
- Do not commit any changes during Phase 9.1.
- `compose.production.yml` is standalone and starts with `docker compose -f compose.production.yml up -d`.
- Only Caddy publishes host ports `80` and `443`; frontend and backend publish none.
- Caddy joins only `edge`; frontend joins `edge` and internal `app`; backend joins only internal `app`.
- Never mount the Docker socket and never add MCP, database, or Chroma services/ports.
- Require explicit `APP_VERSION`; backend and frontend image names include that immutable version and keep current/previous images locally without a registry.
- Protect the complete UI and API with Caddy Basic Auth; credentials are environment placeholders only; remove `Authorization` before proxying.
- Production disables FastAPI docs/OpenAPI and uses internal `/health/live` and `/health/ready` endpoints.
- Readiness may query SQLite only; it must not call LiteLLM, E5, Chroma, RAG, or any external service.
- Caddy is the public first hop and sanitizes incoming forwarding headers; frontend forwards Caddy's `X-Forwarded-For` unchanged and does not append `$remote_addr`.
- Keep SQLite, one backend process, `/data/devicepilot.db`, no WAL, no Alembic, unchanged RAG model/corpus/chunking/Top-K/`RAG_MAX_DISTANCE=0.143`.
- Production defaults `AUTO_SEED_DEMO=false`; seeding is an explicit, documented, idempotent one-time command.
- SQLite backup uses Python's online backup API, checks integrity, writes a SHA-256 checksum, and targets an independently mounted backup directory.
- Keep backend non-root and retain only hardening controls that pass runtime validation; do not invent resource limits.
- Docker logs are bounded; request bodies, secrets, Authorization, full fault text, prompts, RAG chunks, provider secret-bearing errors, and environment dumps are forbidden.
- CI runs tests/build/validation only with dummy values; no LLM call, deployment, or VPS credential.
- Do not change DiagnosisResult, RAG behavior, LangGraph behavior, MCP, or the troubleshooting Skill.

---

### Task 1: Backend production configuration, health, client identity, and seeding

**Files:**
- Modify: `app/config.py`
- Modify: `app/database.py`
- Modify: `app/main.py`
- Modify: `docker-compose.yml`
- Modify: `tests/test_config.py`
- Modify: `tests/test_database.py`
- Modify: `tests/test_diagnosis.py`
- Modify: `tests/test_seed_demo.py`

**Interfaces:**
- Produces: `Settings.production: bool`, `Settings.auto_seed_demo: bool`, and production-aware FastAPI docs configuration.
- Produces: `GET /health/live -> {"status": "ok"}` and `GET /health/ready -> {"status": "ready"}` or HTTP 503.
- Preserves: `client_identifier()` behavior behind the existing `trust_proxy_headers` injection boundary.
- Preserves: explicit `python -m scripts.seed_demo` idempotency.

- [ ] **Step 1: Add failing configuration and health tests**

  Add tests proving `APP_ENV=production` disables `/docs`, `/redoc`, and `/openapi.json`; `AUTO_SEED_DEMO` defaults false in production and remains explicitly configurable; liveness does not touch the database; readiness executes `SELECT 1`, returns 200 when available, and returns sanitized 503 when unavailable. Name each test after the production break it catches.

- [ ] **Step 2: Run focused tests and verify RED**

  Run: `.\.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_database.py tests/test_diagnosis.py tests/test_seed_demo.py -q`

  Expected: new tests fail because production flags and health routes do not exist.

- [ ] **Step 3: Implement minimal production configuration and health routes**

  Parse `APP_ENV` as `development|production`, parse `AUTO_SEED_DEMO` with the existing strict boolean helper, configure FastAPI with `docs_url=None`, `redoc_url=None`, and `openapi_url=None` only in production, and implement liveness/readiness without initializing any AI or RAG service. Use SQLAlchemy `text("SELECT 1")` for readiness and return only `{"status": "not ready"}` on failure.

- [ ] **Step 4: Add failing client-identity and seed-startup tests**

  Prove two syntactically valid trusted `X-Forwarded-For` values receive independent Diagnosis limiter buckets, untrusted development mode ignores `X-Forwarded-For`, production startup with `AUTO_SEED_DEMO=false` does not seed, and explicit seeding remains idempotent.

- [ ] **Step 5: Run focused tests and verify RED, then implement startup behavior**

  Run the focused tests. Replace the unconditional local Compose shell command with environment-controlled startup: local Compose explicitly sets `AUTO_SEED_DEMO=true`; production later sets false and uses the normal image command. Do not add implicit production data mutation.

- [ ] **Step 6: Evaluate SQLite busy timeout with a behavior test**

  Add a database integration test that opens two SQLite connections through `create_database()` and proves a short-lived write lock can be waited out when a finite timeout is configured. If the current driver default already provides adequate bounded waiting, document the finding and avoid redundant configuration; otherwise add a tested `timeout` connect argument without WAL.

- [ ] **Step 7: Run Task 1 tests GREEN**

  Run the focused tests and `python -m compileall -q app scripts tests`.

---

### Task 2: Consistent SQLite backup and local restore rehearsal

**Files:**
- Create: `scripts/backup_sqlite.py`
- Create: `tests/test_backup_sqlite.py`
- Create: `docs/PRODUCTION_DEPLOYMENT.md`

**Interfaces:**
- Produces: `backup_database(source: Path, destination_dir: Path, now: datetime | None = None) -> BackupResult`.
- Produces: `BackupResult.database_path: Path`, `BackupResult.checksum_path: Path`, `BackupResult.sha256: str`.
- CLI consumes `--source` and `--destination`; destination must differ from and not be nested under the source database directory.
- Restore remains an explicit documented operation, not an automatic application rollback side effect.

- [ ] **Step 1: Write failing backup behavior tests**

  Cover: online snapshot retains committed data; backup passes `PRAGMA integrity_check`; checksum file equals the backup bytes' SHA-256; missing source fails non-zero; unsafe destination inside the primary data directory is rejected; an existing final filename is never partially overwritten; failure cleans temporary files.

- [ ] **Step 2: Run tests and verify RED**

  Run: `.\.venv\Scripts\python.exe -m pytest tests/test_backup_sqlite.py -q`

  Expected: import fails because `scripts.backup_sqlite` does not exist.

- [ ] **Step 3: Implement the bounded backup utility**

  Use `sqlite3.connect(source)` and `source_connection.backup(destination_connection)`. Write to a uniquely named temporary database in the destination directory, run `PRAGMA integrity_check`, fsync/close, compute SHA-256 by streaming fixed-size chunks, atomically rename the database and checksum into final timestamped names, and clean temporary artifacts on every failure. Print only final paths and checksum; never print database content or environment.

- [ ] **Step 4: Run backup tests GREEN**

  Run the focused backup suite, then `python -m compileall -q scripts tests`.

- [ ] **Step 5: Document and execute local restore rehearsal**

  Document a separate `/var/backups/devicepilot` mount, root ownership/`0600`, daily/weekly/monthly retention of 7/4/3, mandatory encrypted off-host copy, and the exact sequence: stop backend, preserve current database, verify checksum, copy the snapshot while stopped, correct ownership, start backend, call readiness, inspect Device/Fault data, and rebuild Chroma only when needed. Rehearse locally using a temporary database and assert restored row counts and `PRAGMA integrity_check=ok`.

---

### Task 3: Standalone production Compose, Caddy authentication, proxy chain, and container hardening

**Files:**
- Create: `compose.production.yml`
- Create: `deploy/Caddyfile`
- Create: `deploy/.env.production.example`
- Modify: `frontend/nginx.conf`
- Modify: `Dockerfile`
- Modify: `frontend/Dockerfile`
- Modify: `tests/test_deployment_config.py`

**Interfaces:**
- Consumes: Task 1 `/health/live`, `/health/ready`, `APP_ENV=production`, `AUTO_SEED_DEMO=false`.
- Consumes: Task 2 backup CLI and independent `/backups` mount.
- Produces: standalone Compose project with required `${APP_VERSION:?set APP_VERSION}` interpolation and version-tagged local image names.
- Produces: Caddy environment placeholders `DEVICEPILOT_DOMAIN`, `BASIC_AUTH_USERNAME`, and `BASIC_AUTH_PASSWORD_HASH` supplied by `/etc/devicepilot/caddy.env`.

- [ ] **Step 1: Write failing runtime-oriented deployment tests**

  Parse rendered Compose YAML/JSON rather than grepping source. Assert only Caddy publishes `80:80` and `443:443`; frontend/backend have no `ports`; `app.internal=true`; exact service network membership; Caddy has no `app`; no Docker socket/MCP/database/Chroma service; `APP_VERSION` is required and appears in backend/frontend image tags; one backend instance/worker; external env file paths and independent `/backups` mount; bounded `local` logs; production flags; unchanged RAG values.

- [ ] **Step 2: Run deployment tests and verify RED**

  Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deployment_config.py -q`

  Expected: tests fail because standalone production artifacts do not exist.

- [ ] **Step 3: Implement standalone Compose and example environment**

  Define complete build/image/environment/volume/network/health/restart/logging settings without extending local Compose. Use image names such as `devicepilot-backend:${APP_VERSION:?set APP_VERSION}` and `devicepilot-frontend:${APP_VERSION:?set APP_VERSION}` so separate immutable tags remain locally available. Backend uses its image default command and no auto-seed. Mount an independent host backup path only for an explicit backup profile/one-shot service, not as general application storage.

- [ ] **Step 4: Add failing Caddy/nginx integration assertions**

  Validate the Caddyfile with the official Caddy image using dummy domain and password hash. Add a local runtime test that sends a forged public `X-Forwarded-For` through Caddy and confirms frontend/backend observe Caddy's client identity rather than the forged value; confirm two distinct trusted values at the internal frontend boundary remain distinct. Assert Caddy strips `Authorization`, protects both `/` and `/api`, and may answer only a minimal public `/healthz` without auth.

- [ ] **Step 5: Implement Caddy and trusted nginx forwarding**

  Use whole-site `basic_auth` with environment placeholders, conservative HSTS without preload/includeSubDomains, `X-Content-Type-Options`, `Referrer-Policy`, and a tested same-origin CSP. Reverse proxy only to `frontend:80`, remove upstream `Authorization`, and rely on Caddy's first-hop XFF sanitization. In nginx forward `$http_x_forwarded_for` unchanged to backend, never `$remote_addr` or `$proxy_add_x_forwarded_for`; disable duplicate nginx access logging while keeping errors.

- [ ] **Step 6: Evaluate backend hardening one control at a time**

  First retain `no-new-privileges`, run the production backend health/readiness/SQLite/RAG import smoke. Then add `cap_drop: [ALL]` and re-run. Then add `read_only: true` plus bounded `/tmp` tmpfs and re-run SQLite, Chroma path, model-cache path, and health checks. Revert any control that fails and record the exact failure; do not add arbitrary resource limits or harden Caddy/nginx blindly.

- [ ] **Step 7: Validate production runtime GREEN**

  With dummy env files and a local test hostname, run `docker compose -f compose.production.yml config --quiet`, Caddy validation, both production Docker builds, `up -d`, network/port inspection, health checks, unauthenticated 401 checks, authenticated UI/API checks, XFF spoof test, and `down` without deleting volumes. Never print expanded secrets or real Compose config.

---

### Task 4: CI and production operations documentation

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `docs/PRODUCTION_DEPLOYMENT.md`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CURRENT_STATE.md`
- Modify: `docs/DECISIONS.md`
- Modify: `.env.example`
- Modify: `.gitignore`
- Modify: `.dockerignore`

**Interfaces:**
- Consumes: standalone Compose/Caddy validation contracts from Task 3.
- Produces: CI-only workflow for PRs and main pushes with `permissions: contents: read`.
- Produces: manual Phase 9.2 deployment/rollback contract based on exact Git version and `APP_VERSION`.

- [ ] **Step 1: Add CI workflow with no deployment authority**

  Add jobs for backend full Pytest, Python compile and pip check; frontend frozen install, Vitest, typecheck and build; dummy-value production Compose validation; official Caddyfile validation; backend and frontend Docker builds. Use no LLM call, production secret, SSH key, `pull_request_target`, Docker push, or deploy command.

- [ ] **Step 2: Validate CI syntax and commands locally**

  Run each workflow command locally where available. Inspect workflow permissions and event triggers, then run a YAML parser or action linter if already available; do not install a new global tool solely for linting.

- [ ] **Step 3: Complete operations documentation**

  Document `/etc/devicepilot/backend.env` and `/etc/devicepilot/caddy.env` as root-owned `0600`; dummy example values only; DNS/TLS prerequisites for Phase 9.2; one-time demo seed command; backup/restore/retention/off-host requirements; exact-version manual deployment; health and authenticated smoke checks; retaining current/previous images; application rollback by switching `APP_VERSION`; database restore only for corruption/incompatible data; Chroma rebuild and Hugging Face re-download; MCP/Skill exclusions.

- [ ] **Step 4: Update architecture/current-state/decision records**

  Record Caddy choice, Basic Auth boundary, SQLite continuation, logical `/data` persistence classes, trusted proxy chain, CI-only decision, no automatic production seed, and no remote MCP. Keep local Docker instructions intact and add standalone production usage without real domain/secret examples.

---

### Task 5: Full verification and independent reviews

**Files:**
- Verify all changed files; modify only through a reviewed fix round.

**Interfaces:**
- Consumes all Task 1-4 deliverables.
- Produces the Phase 9.1 implementation report and a clear Phase 9.2 blocker list.

- [ ] **Step 1: Run complete non-Docker verification**

  Run backend full tests, frontend tests, typecheck/build, Python compile, pip check, existing RAG regression tests, `git diff --check`, and secret-pattern review.

- [ ] **Step 2: Run complete Docker verification**

  Validate standalone Compose and Caddyfile with dummy values, build both images, start the production stack locally, assert published ports/networks, check backend liveness/readiness from inside the network, test Basic Auth and Authorization removal, test spoofed XFF handling, verify no seed on restart, execute backup snapshot/integrity/checksum, rehearse restore, and stop without deleting persistent volumes.

- [ ] **Step 3: Dispatch independent reviewers**

  Code Reviewer checks correctness and maintainability; Application Security Engineer checks auth, proxy trust, secrets, ports, logging, container privileges, backup exposure, and CI permissions; Reality Checker verifies the locally running end-to-end topology. Reviewers are read-only. Any Critical/Important finding enters one bounded fix-and-re-review round.

- [ ] **Step 4: Produce final report without committing or deploying**

  Report standalone topology, exact ports, Caddy/TLS/Auth, proxy IP chain, health, docs/seed behavior, secrets, SQLite, backup/restore rehearsal, unchanged RAG persistence, hardening actually retained, logging, CI, rollback model, tests, Docker evidence, security review, changed files, rulings, and remaining real-VPS blockers.
