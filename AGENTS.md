# DevicePilot Agent Guide

## Current Project Priority

The immediate goal is to produce a complete,
demonstrable DevicePilot MVP within a few days.

Prioritize shipping a working end-to-end product over
building a theoretically perfect architecture.

The MVP must include:

- FastAPI backend
- SQLite + SQLAlchemy persistence
- Device management
- Fault records
- React frontend
- Basic AI fault diagnosis
- Docker deployment
- Clear README and demo instructions

Do not introduce the following unless explicitly requested:

- RAG
- LangGraph
- MCP
- microservices
- message queues
- advanced authentication
- complex infrastructure
- premature abstractions

Prefer the simplest implementation that:

1. works correctly
2. is easy to understand
3. can be demonstrated
4. can be extended later


## Project Goal

DevicePilot is an AI-powered device management and
fault-diagnosis platform.

The MVP should demonstrate a complete user flow:

Device management
→
fault recording
→
device detail
→
AI fault diagnosis
→
diagnosis result

The project should be suitable for:

- local demonstration
- GitHub portfolio presentation
- later deployment
- future extension with RAG, Agents and MCP


## Source of Truth

Before substantial work, inspect the actual repository.

Read these files when they exist:

- `README.md`
- `docs/PRODUCT.md`
- `docs/ARCHITECTURE.md`
- `docs/CURRENT_STATE.md`
- `docs/DECISIONS.md`

The repository code is the primary source of truth.

If documentation conflicts with working code:

1. inspect the implementation
2. determine the actual current behavior
3. preserve correct working behavior
4. update stale documentation when appropriate

Do not assume project state from old prompts.


## Codex Project Agents

Project-level Codex agents are available under:

`.codex/agents/`

Use the appropriate specialist when useful.

Primary responsibilities:

- Backend Architect:
  FastAPI, SQLAlchemy, SQLite, API architecture and backend implementation

- Frontend Developer:
  React UI, components, frontend state and API integration

- AI Engineer:
  LLM integration and AI fault-diagnosis functionality

- Code Reviewer:
  review correctness, maintainability and significant implementation issues

- Application Security Engineer:
  secrets, API security, unsafe configuration and common application risks

- Reality Checker:
  verify that the application actually starts and the user flow really works

Do not involve every agent in every task.

Use only the specialists relevant to the current stage.


## Development Workflow

Before modifying code:

1. inspect relevant files
2. understand the existing implementation
3. run `git status`
4. identify code that can be reused
5. avoid overwriting unrelated user changes

Prefer extending the existing project over creating a second parallel implementation.

Do not perform unrelated large-scale refactoring while completing an MVP task.

For ordinary implementation decisions, choose the simplest reliable solution
consistent with the current project.


## Backend Rules

Use:

- FastAPI
- Pydantic
- SQLAlchemy
- SQLite for the MVP
- Python type hints where practical
- clear names and explicit data flow

Keep API schemas and SQLAlchemy ORM models separate.

Keep route handlers understandable.

Introduce service or repository layers only when they provide clear value.

Do not introduce architecture patterns only for appearance.


## API Behavior

Keep API behavior consistent.

Expected behavior should include:

- valid resource retrieval returns success
- resource creation uses an appropriate success status
- missing devices or faults return `404`
- invalid request data should not silently succeed
- unexpected errors must not be hidden as successful responses

Preserve existing API compatibility when practical.


## AI Diagnosis

The MVP AI functionality should remain simple.

The diagnosis flow should use:

- device information
- fault description supplied by the user

The AI response should preferably contain structured information such as:

- risk level
- possible causes
- recommended checks
- recommended actions

Do not add RAG, LangGraph or MCP during the MVP unless explicitly requested.

API keys and provider credentials must come from environment variables.


## Security

Never commit:

- API keys
- passwords
- access tokens
- `.env`
- private credentials

Use `.env` for local secrets.

Provide `.env.example` containing placeholder values only.

Avoid logging sensitive credentials.


## Testing and Validation

Do not consider a task complete only because the code looks correct.

After relevant changes, validate the affected functionality.

When applicable verify:

- backend imports successfully
- FastAPI starts successfully
- database initialization succeeds
- Device CRUD works
- Fault operations work
- expected `404` cases work
- frontend starts
- frontend can reach the backend
- AI diagnosis endpoint works with valid configuration
- automated tests pass

Use Reality Checker for important end-to-end milestones.


## Review Policy

After a major implementation stage, use Code Reviewer.

For the MVP, prioritize fixing:

- blockers
- high-severity correctness problems
- security problems
- issues that break the demo
- obvious data-loss risks

Do not delay the MVP for minor stylistic improvements or speculative refactoring.


## Documentation

When project state changes materially, update documentation when present.

Use:

- `docs/CURRENT_STATE.md` for current implementation status
- `docs/DECISIONS.md` for important architecture decisions
- `docs/ARCHITECTURE.md` for major structural changes
- `README.md` for user-facing setup and demo instructions

Do not duplicate large documentation inside this file.


## Git Safety

Always inspect `git status` before and after meaningful work.

Do not:

- overwrite unrelated user work
- rewrite Git history unless explicitly requested
- commit `.env`
- commit virtual environments
- commit caches
- commit temporary generated files
- commit secrets

Maintain `.gitignore` when required.


## Scope Control

Do not expand a task beyond the requested MVP scope without a clear reason.

Do not independently introduce:

- RAG
- LangGraph
- MCP
- Redis
- Celery
- Kafka
- Kubernetes
- microservices
- advanced authentication
- complex cloud infrastructure

Escalate before:

- replacing the agreed technology stack
- deleting major working functionality
- making destructive database changes
- performing a major architecture rewrite


## Task Completion Report

After completing a meaningful task, report:

- what was implemented
- files created
- files modified
- validation performed
- test results
- important issues found
- remaining limitations
- recommended next step


## Agent Routing

Use specialist agents only when their expertise is relevant.

Preferred routing:

- Backend/API/database work → Backend Architect
- React/UI work → Frontend Developer
- LLM integration → AI Engineer
- implementation review → Code Reviewer
- security review → Application Security Engineer
- end-to-end validation → Reality Checker

Implementation agents may modify files within their assigned scope.

Reviewer, security and validation agents should default to read-only
analysis unless explicitly authorized to make changes.

Do not spawn every available agent for every task.

Avoid parallel write access to overlapping files.