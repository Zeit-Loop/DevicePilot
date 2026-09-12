# DevicePilot Phase 4 Productization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package DevicePilot as a secure, repeatable local and Docker portfolio MVP.

**Architecture:** Keep the existing React/FastAPI/SQLite application intact. Add focused environment configuration, an injected in-memory diagnosis limiter, an idempotent seed command, and nginx/Compose deployment around the accepted application.

**Tech Stack:** Python, FastAPI, SQLAlchemy, SQLite, React, TypeScript, Vite, nginx, Docker Compose

**Spec:** `docs/superpowers/specs/2026-08-29-productization-design.md`

## Global Constraints

- Do not add RAG, LangGraph, MCP, Redis, Celery, Kafka, Kubernetes, microservices, authentication, or Diagnosis History.
- Do not change existing API paths, JSON fields, database fields, or Diagnosis structured schema.
- Do not commit, push, create a remote, or create a GitHub repository.
- Fix deployment-level CRITICAL/HIGH security findings and BLOCKER/HIGH review findings.

---

### Task 1: Environment configuration and rate limiting

**Files:** `app/config.py`, `app/rate_limit.py`, `app/database.py`, `app/main.py`, `.env.example`, `tests/test_config.py`, `tests/test_diagnosis.py`, `tests/test_cors.py`

- [x] Write failing tests for environment parsing, explicit CORS, and HTTP 429.
- [x] Run focused tests and confirm failures are caused by missing behavior.
- [x] Add minimal settings and sliding-window limiter implementation.
- [x] Inject the limiter into only `POST /devices/{device_id}/diagnose`.
- [x] Run focused tests and the backend regression suite.

### Task 2: Demo data

**Files:** `scripts/seed_demo.py`, `tests/test_seed_demo.py`

- [x] Write a failing test that seeds expected statuses/faults and remains duplicate-free on a second run.
- [x] Implement stable-serial-number inserts and matching fault records.
- [x] Run the focused test twice and the backend regression suite.

### Task 3: Production containers

**Files:** `Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`, `docker-compose.yml`, `.dockerignore`, `frontend/.dockerignore`, `frontend/src/api/implementation.ts`, `frontend/vite.config.ts`

- [x] Add a frontend test asserting the default same-origin `/api` base.
- [x] Run it and confirm the current localhost default fails.
- [x] Add the Vite development proxy and nginx production proxy.
- [x] Add backend/frontend images and Compose with a persistent SQLite volume.
- [ ] Build images and verify Compose HTTP, OpenAPI, rate limiting, and persistence.

### Task 4: Portfolio documentation

**Files:** `README.md`, `docs/ARCHITECTURE.md`, `docs/CURRENT_STATE.md`, `docs/DECISIONS.md`, `docs/images/.gitkeep`, `docs/MANUAL_VERIFICATION.md`, `.gitignore`

- [x] Write concise documentation that matches tested commands and actual ports.
- [x] Document the three required manual screenshots without fabricating images.
- [x] Add the 1440/768/375 responsive and final E2E checklist.
- [x] Audit ignore rules and secret boundaries.

### Task 5: Final verification and reviews

- [x] Run backend tests, frontend tests, TypeScript check, and production build.
- [ ] Run Docker build and Compose runtime/persistence/HTTP checks.
- [x] Check for secrets, runtime databases, caches, dependencies, and build output in Git status.
- [x] Run Application Security Engineer; fix required findings and re-verify.
- [x] Run Code Reviewer; fix required findings and re-verify.
- [x] Run Reality Checker; distinguish application failure from browser tooling blockage.
- [ ] Report final status and stop without committing.
