# DevicePilot MCP Read-only Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development while implementing this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not commit; the user explicitly prohibited commits for Phase 7.1.

**Goal:** Add a bounded, read-only DevicePilot MCP v2 stdio server exposing exactly three typed tools for device lookup, recent fault history, and existing RAG retrieval.

**Architecture:** Use the official `mcp==2.1.1` SDK resolved from `mcp>=2,<3`, with `MCPServer` from `mcp.server.mcpserver` and protocol tests through `Client(mcp)`. Tool handlers delegate to a read service that owns one SQLAlchemy session per database operation and closes it before RAG retrieval; RAG uses the existing E5, Chroma, threshold, source sanitizer, and `RetrievalService` without LiteLLM or LangGraph.

**Tech Stack:** Python 3.12, MCP Python SDK 2.1.1, Pydantic 2, SQLAlchemy 2, SQLite, pytest, existing Chroma/E5 RAG.

**Spec:** Approved Phase 7 architecture plus the user's Phase 7.1 revision request in the current task.

## Global Constraints

- Official SDK only: `mcp>=2,<3`; resolved version is `2.1.1`.
- Exactly three tools: `get_device`, `get_recent_faults`, `search_knowledge`.
- `resources/list`, resource templates, and `prompts/list` must be empty.
- Domain failures are MCP tool execution errors (`is_error=True`), never protocol errors.
- Stable domain codes: `DEVICE_NOT_FOUND`, `RAG_DISABLED`, `RAG_UNAVAILABLE`, `DATABASE_READ_FAILED`.
- Recent faults use `created_at DESC, id DESC`, `1 <= limit <= 5`, and descriptions no longer than 500 characters.
- Knowledge queries are 1..2000 trimmed characters, derive `device_type` from the database, close the DB session before retrieval, and return no more than three matches.
- Preserve `intfloat/multilingual-e5-small`, the existing Chroma collection, existing Top-K behavior, and `RAG_MAX_DISTANCE=0.143`.
- No LiteLLM, LangGraph, diagnosis, write tools, commits, arbitrary SQL, shell/filesystem/HTTP/web tools, MCP chaining, public HTTP transport, auth, or Compose service.
- Do not expose raw exceptions, SQL, secrets, absolute paths, distances, vectors, or arbitrary metadata.

---

### Task 1: Dependency and Shared Source Sanitizer

**Files:**
- Modify: `requirements.txt`
- Create: `app/rag/sources.py`
- Modify: `app/services/diagnosis.py`
- Test: `tests/test_rag_diagnosis.py`

**Interfaces:**
- Produces: `safe_source_document(source: str) -> str | None`.
- Preserves: Diagnosis sources remain safe relative document names plus non-negative chunk indices.

- [ ] Add `mcp>=2,<3` to `requirements.txt` after the already-completed resolver/import/pip-check verification.
- [ ] Add a failing regression test proving Diagnosis source sanitization still rejects absolute paths and traversal after extraction.
- [ ] Run that test and confirm it fails because the shared helper does not exist yet.
- [ ] Move the current private sanitizer, without behavior changes, to:

```python
def safe_source_document(source: str) -> str | None:
    """Return a safe relative POSIX document name or None."""
```

- [ ] Update Diagnosis to import the shared helper and run focused RAG Diagnosis tests.

### Task 2: Typed Read Service and Read-only Boundaries

**Files:**
- Create: `app/mcp/__init__.py`
- Create: `app/mcp/schemas.py`
- Create: `app/mcp/services.py`
- Test: `tests/test_mcp_services.py`

**Interfaces:**
- Produces: `DeviceDTO`, `FaultHistoryItemDTO`, `RecentFaultsResult`, `KnowledgeMatchDTO`, `KnowledgeSearchResult`.
- Produces: `DevicePilotReadService.get_device(device_id)`, `.get_recent_faults(device_id, limit)`, `.search_knowledge(device_id, query)`.
- Consumes: `sessionmaker[Session]`, optional `RetrievalService`, `RAGSettings`, and shared source sanitizer.

- [ ] Write failing tests for Device success/missing, database failure sanitization, session close on success/failure, fault ordering/cap/truncation, no DML, and DB closure before retrieval.
- [ ] Verify failures are due to absent MCP service types.
- [ ] Define strict Pydantic DTOs using only current Device/Fault/RAG fields. Knowledge output is limited to `document`, `chunk_index`, `content`, and guaranteed `equipment_type`.
- [ ] Define internal sanitized domain exceptions carrying only the four stable public codes.
- [ ] Implement database reads using a fresh session in `try/finally`, no `commit`, ORM-to-DTO mapping inside the session, and `rollback`/`close` cleanup.
- [ ] Implement the fault query literally as:

```python
select(models.Fault).where(models.Fault.device_id == device_id).order_by(
    models.Fault.created_at.desc(), models.Fault.id.desc()
).limit(limit)
```

- [ ] Implement knowledge search so device lookup completes and closes before calling the injected retrieval dependency; map at most three safe chunks and omit distance/title/raw metadata.
- [ ] Run focused service tests until green, then run existing Device/Fault/RAG tests.

### Task 3: Official MCP v2 Server and In-process Protocol Tests

**Files:**
- Create: `app/mcp/server.py`
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Produces: `create_mcp_server(...) -> MCPServer` and stdio `main()`.
- Consumes: `DevicePilotReadService` and Task 2 DTOs/errors.

- [ ] Write failing async tests using exactly the modern pattern:

```python
async with Client(mcp) as client:
    tools = await client.list_tools()
    result = await client.call_tool("get_device", {"device_id": 1})
```

- [ ] Cover discovery, exactly three tools, empty resources/templates/prompts, structured content, all input bounds, normal empty results, and `is_error=True` domain failures.
- [ ] Verify the protocol tests fail because the Server factory and tools do not exist.
- [ ] Create `MCPServer("devicepilot", version="0.1.0")`, register only the three tools with structured Pydantic returns, and translate domain exceptions to official `ToolError` with stable `CODE: message` text.
- [ ] Ensure unexpected exceptions become the SDK's generic tool execution error and never leak raw exception text.
- [ ] Provide only `mcp.run(transport="stdio")` from the module entrypoint; do not construct HTTP apps.
- [ ] Run protocol tests through `Client(mcp)` until green.

### Task 4: Real stdio E2E and Documentation

**Files:**
- Create: `scripts/verify_mcp.py`
- Test: `tests/test_mcp_stdio.py`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CURRENT_STATE.md`
- Modify: `docs/DECISIONS.md`

**Interfaces:**
- Produces: a verifier that uses official `Client` with `StdioServerParameters` to start `python -m app.mcp.server`.

- [ ] Write a failing subprocess stdio test that uses the official v2 Client, performs discovery, lists tools/resources/templates/prompts, and calls `get_device` against a temporary SQLite database supplied through `DATABASE_URL`.
- [ ] Verify it fails before the stdio verifier/entrypoint is complete.
- [ ] Implement the verifier and make the subprocess E2E deterministic without RAG model downloads or LiteLLM.
- [ ] Document stdio-only startup, three read tools, external Host/Client/Server boundary, data egress, empty resources/prompts, local LangGraph calls, and deferred remote HTTP/auth.
- [ ] Run focused stdio and documentation-adjacent tests.

### Task 5: Full Verification and Review

**Files:**
- Inspect all Phase 7.1 changes; do not commit.

**Interfaces:**
- Consumes the complete implementation and returns evidence for the implementation report.

- [ ] Run Python compile over `app`, `scripts`, and `tests`.
- [ ] Run `python -m pip check` and record MCP's resolved version.
- [ ] Run the full Backend pytest suite.
- [ ] Run `python -m scripts.evaluate_rag --real` and require 12/12.
- [ ] Run the official stdio verifier.
- [ ] Run `git diff --check` and inspect `git status --short`.
- [ ] Dispatch the required Code Reviewer, fix all blocker/high correctness/security/demo findings with covering tests, and re-run affected verification.