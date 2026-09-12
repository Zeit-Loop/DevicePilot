# Phase 5 RAG Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development`. Do not commit; preserve all unrelated work.

**Goal:** Add a demonstrable, device-aware local RAG knowledge base to DevicePilot diagnosis while preserving the existing non-RAG path.

**Architecture:** Keep the exact bounded chain `DocumentLoader -> deterministic chunker -> EmbeddingProvider -> ChromaVectorStore -> RetrievalService -> Diagnosis Service -> LiteLLM`. Every external or heavyweight boundary is injectable so tests use deterministic doubles.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Chroma, sentence-transformers, `intfloat/multilingual-e5-small`, React/TypeScript, Pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-08-31-rag-knowledge-base-design.md`

## Global Constraints

- No Git commits.
- Only Markdown and TXT; PDF is a documented limitation.
- No LangGraph, Agent, MCP, reranker, hybrid search, Graph RAG, web search, memory, cloud vector database, or upload UI.
- Real embedding model initialization is lazy; automated tests must not download it.
- E5 query/passages prefixes belong only in `EmbeddingProvider`.
- Chroma uses an explicitly configured cosine metric; lower distance is more relevant.
- `RAG_ENABLED=false` preserves the existing diagnosis behavior.
- Retrieval errors are warned safely, never exposed to the frontend, and fall back to `sources=[]`.
- Sources come only from retrieval metadata.

---

### Task 1: Knowledge ingestion and configuration

**Files:** create `knowledge/*.md`, `app/rag/documents.py`, `app/rag/chunking.py`, `app/rag/embeddings.py`, `app/rag/types.py`; modify `app/config.py`, `.env.example`, dependency files; add focused tests.

- [ ] Write failing tests for Markdown/TXT loading, unsupported extension rejection, path traversal, oversize/unreadable files, metadata, deterministic chunking/overlap, normalized equipment type, RAG config validation, lazy E5 initialization, and distinct `query: ` / `passage: ` inputs.
- [ ] Run the focused tests and confirm failures are caused by missing behavior.
- [ ] Implement the minimum typed document/chunk models, safe loader, normalization, chunker, RAG settings, embedding protocol, fake-friendly E5 provider, and four original demo documents.
- [ ] Run the focused tests to green and preserve the 62-test Backend baseline.

### Task 2: Persistent vector store, indexing, retrieval, and evaluation

**Files:** create `app/rag/vector_store.py`, `app/rag/retrieval.py`, `app/rag/indexing.py`, `scripts/index_knowledge.py`, `scripts/evaluate_rag.py`; add focused tests.

- [ ] Write failing tests for cosine collection configuration, stable identity, inserted/updated/skipped/error statistics, idempotence, changed/deleted-source reconciliation, `--rebuild`, device filtering, four demo-device hits, `top_k`, no results, missing index, query embedding, and threshold rejection.
- [ ] Run the focused tests and confirm expected failures.
- [ ] Implement persistent Chroma adapters and deterministic fake-compatible indexing/retrieval. Normal indexing reconciles indexed sources; rebuild clears first.
- [ ] Implement five deterministic evaluation cases, calibrate a conservative maximum cosine-distance threshold, and record the threshold and evidence in `docs/DECISIONS.md`.
- [ ] Run focused tests and `python -m scripts.evaluate_rag` to green without a real model download.

### Task 3: Diagnosis and frontend integration

**Files:** modify `app/services/diagnosis.py`, `app/schemas.py`, `app/main.py`, diagnosis tests, `frontend/src/types.ts`, `frontend/src/Application.tsx`, CSS and frontend tests.

- [ ] Write failing tests for RAG disabled, retrieval context delivery, prompt boundary/injection resistance, trusted-device precedence, uncertainty language, safe fallback, metadata-derived/deduplicated sources, unchanged endpoint/rate limiting/provider contracts, and Chinese source rendering.
- [ ] Run Backend and Frontend focused tests and confirm expected failures.
- [ ] Keep LiteLLM independent of Chroma; add a Diagnosis Service that optionally retrieves, builds explicitly separated prompt sections, calls the provider once, and attaches sources after model validation.
- [ ] Add backward-compatible `sources` response data and render only a compact `参考知识` list below diagnosis results.
- [ ] Run focused Backend and Frontend tests to green.

### Task 4: Deployment, documentation, and full verification

**Files:** modify `Dockerfile`, `docker-compose.yml`, `README.md`, `docs/ARCHITECTURE.md`, `docs/CURRENT_STATE.md`, `docs/DECISIONS.md`, `.env.example`, and ignore rules if required.

- [ ] Package knowledge and indexing scripts in the Backend image; reuse `/data` for persistent `data/chroma` without automatic startup indexing.
- [ ] Document actual model, formats, chunking, cosine-distance direction/threshold, indexing/rebuild commands, retrieval/fallback behavior, sources, Docker persistence, and PDF limitation.
- [ ] Run full Backend tests, five-case RAG evaluation, frontend tests/typecheck/build, import/startup checks, and Git status.
- [ ] Hand the resulting working-tree diff to Code Reviewer, then Application Security Engineer, then Reality Checker; fix only required severity findings with regression tests before re-verification.
