# Phase 3 AI Diagnosis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reliable, backend-mediated, structured OpenAI fault diagnosis flow to the existing Device Detail page.

**Architecture:** A synchronous FastAPI route loads the trusted Device record and calls a focused diagnosis service. The service calls an injectable OpenAI provider using Responses API Pydantic Structured Outputs; the React client renders the validated result and recoverable states.

**Tech Stack:** FastAPI, Pydantic 2, SQLAlchemy, OpenAI Python SDK, python-dotenv, React, TypeScript, Vitest, Testing Library

**Spec:** `docs/superpowers/specs/2026-08-28-ai-diagnosis-design.md`

## Global Constraints

- `OPENAI_MODEL` is configurable; `.env.example` defaults to `gpt-5-mini`.
- Browser and frontend bundle never receive `OPENAI_API_KEY`.
- Do not persist diagnosis results or automatically create Fault records.
- Do not introduce RAG, LangChain, LangGraph, MCP, Agent, streaming, WebSocket, memory, provider registries, or plugin frameworks.
- Do not refactor the passing Device/Fault CRUD beyond the minimal `create_app()` dependency hook.
- Automated tests never call the paid OpenAI API.
- Do not commit changes.

---

### Task 1: Backend schema, provider, service, and route

**Files:**
- Create: `app/services/__init__.py`
- Create: `app/services/diagnosis.py`
- Create: `tests/test_diagnosis.py`
- Create: `.env.example`
- Modify: `app/schemas.py`
- Modify: `app/main.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces `DiagnosisRequest`, `DiagnosisResult`, and `RiskLevel` Pydantic types.
- Produces a synchronous `DiagnosisProvider.diagnose(device, description) -> DiagnosisResult` boundary and minimal injected callable/service accepted by `create_app()`.
- Produces `POST /devices/{device_id}/diagnose`.

- [ ] Write failing API tests for mocked success, exact structured response fields, missing device `404`, whitespace/oversized description `422`, missing configuration, and safe provider failure.
- [ ] Run `\.venv\Scripts\python.exe -m pytest tests/test_diagnosis.py -v` and confirm failures are caused by the absent feature.
- [ ] Add the Pydantic request/result models, including `LOW`, `MEDIUM`, `HIGH`, and `CRITICAL` risk values and trimmed bounded descriptions.
- [ ] Implement the centralized prompt, minimal service/provider boundary, lazy environment configuration, and OpenAI `responses.parse(..., text_format=DiagnosisResult)` call with `output_parsed` validation.
- [ ] Map configuration, authentication, rate-limit, timeout/network/unavailable, refusal, and invalid-structured-output failures to safe API responses without leaking provider details.
- [ ] Add the route, loading the Device from the database before invoking diagnosis.
- [ ] Add `openai` and `python-dotenv` dependencies plus placeholder-only root `.env.example`.
- [ ] Re-run the focused tests until green, then run `\.venv\Scripts\python.exe -m pytest -v`.

### Task 2: Frontend API contract and Diagnosis UI

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/implementation.ts`
- Modify: `frontend/src/api/client.test.ts`
- Modify: `frontend/src/Application.tsx`
- Modify: `frontend/src/App.device-detail.test.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/feedback.css` only if an existing feedback style is reusable there.

**Interfaces:**
- Consumes `POST /devices/{device_id}/diagnose` with `{ description: string }`.
- Produces `api.diagnoseDevice(id, input) -> Promise<DiagnosisResult>` and renders every structured field.

- [ ] Add failing client tests for the exact diagnosis route, method, request body, structured response, and safe backend error detail.
- [ ] Add failing Device Detail tests for initial form state, client validation, loading, complete successful rendering, provider/configuration error recovery, and duplicate-submit prevention.
- [ ] Run `pnpm test -- src/api/client.test.ts src/App.device-detail.test.tsx` from `frontend` and confirm expected feature-missing failures.
- [ ] Add TypeScript diagnosis types and the API client method.
- [ ] Replace only the existing AI placeholder with an accessible textarea, Diagnose button, status/error feedback, retry-capable state, risk badge, summary, causes, checks, and actions.
- [ ] Disable submission during a request and retain the editable description after failures.
- [ ] Add focused responsive styles consistent with the existing design system.
- [ ] Run the focused tests until green, then run `pnpm test`, `pnpm exec tsc -b`, and `pnpm build`.

### Task 3: Deterministic end-to-end and regression verification

**Files:**
- Modify test support only if required to inject a deterministic provider without production-only test hooks.

**Interfaces:**
- Consumes the real React, FastAPI route, diagnosis service, SQLite Device record, and a mocked provider boundary.
- Produces evidence that structured diagnosis traverses the complete local application chain.

- [ ] Start FastAPI with a deterministic provider through the minimal dependency boundary and start Vite against it.
- [ ] Create a real SQLite-backed Device through the API.
- [ ] In a real browser, open Device Detail, submit a diagnosis, and verify risk, summary, causes, checks, and actions render.
- [ ] Verify loading/duplicate prevention and a safe provider error without a page-level crash.
- [ ] Run full backend tests, frontend tests, TypeScript check, production build, and existing CRUD browser smoke checks.
- [ ] If `OPENAI_API_KEY` is present, run exactly one minimal real provider diagnosis; otherwise record `Real Provider Test: NOT RUN` without requesting a key.

### Task 4: Security and code review closure

**Files:**
- Modify only files required to fix validated CRITICAL/HIGH security findings or BLOCKER/HIGH code-review findings.

**Interfaces:**
- Consumes the complete Phase 3 change set and verification evidence.
- Produces no unresolved CRITICAL/HIGH security or BLOCKER/HIGH correctness findings.

- [ ] Have Application Security Engineer perform a read-only review of secret exposure, `.env`, bundle variables, logs, error leakage, CORS, prompt input, trusted device data, and dependency/config risks.
- [ ] For every CRITICAL/HIGH finding, first add a failing regression test, then implement and re-verify the smallest fix.
- [ ] Have Code Reviewer perform a read-only review of service boundary, blocking correctness, schema validation, errors, duplication, regressions, and maintainability blockers.
- [ ] For every BLOCKER/HIGH finding, first add a failing regression test, then implement and re-verify the smallest fix.
- [ ] Have Reality Checker repeat the mocked browser end-to-end journey after fixes.
- [ ] Run final backend regression, frontend tests, TypeScript check, production build, secret search, and `git status`.
