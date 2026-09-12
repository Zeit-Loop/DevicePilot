# Phase 3 AI Diagnosis Design

## Diagnosis API contract

`POST /devices/{device_id}/diagnose`

Request:

```json
{"description": "Motor casing is hot and makes a grinding noise."}
```

The backend loads the device by `device_id`; the browser cannot supply trusted device facts. Missing devices return `404`. Descriptions are trimmed, must contain non-whitespace text, and have a bounded length. Successful responses use the structured schema below.

## Service/provider boundary

The FastAPI route loads the database device and delegates to a small diagnosis service. The service builds the diagnostic context and calls one OpenAI provider boundary. The provider uses the official Python SDK Responses API with Pydantic Structured Outputs. `create_app()` accepts only the minimal diagnosis dependency override needed by tests. There is no provider registry or plugin framework.

The prompt treats database device fields as facts and the fault description as an untrusted user report. It forbids invented readings or history, requires uncertainty when evidence is insufficient, prioritizes actionable checks, raises risk for evident hazards, and states that the result is not an onsite inspection or professional repair certification.

## Structured schema

```json
{
  "risk_level": "LOW | MEDIUM | HIGH | CRITICAL",
  "summary": "string",
  "possible_causes": ["string"],
  "recommended_checks": ["string"],
  "recommended_actions": ["string"]
}
```

The provider output and FastAPI response are validated against the same Pydantic result model. Diagnosis results are transient: they are not persisted and do not create Fault records.

## Secret boundary

`OPENAI_API_KEY` and `OPENAI_MODEL` are backend-only environment variables. The default example model is `gpt-5-mini`; the model remains configurable. Missing configuration does not prevent application startup or CRUD use. `.env` remains ignored, `.env.example` contains placeholders only, and no OpenAI credential is exposed through frontend variables, logs, or exception responses.

## Error mapping

- Missing API key/model: safe `503` configuration response.
- Provider authentication failure: safe `502` provider authentication response.
- Rate limit: safe `503` temporary capacity response.
- Timeout/network/provider unavailable: safe `503` temporary availability response.
- Refusal, missing parsed output, or invalid structured response: safe `502` invalid provider response.
- Input validation: FastAPI `422`.
- Missing device: `404`.

Provider exception details and credentials never reach the browser. Logs contain only safe exception categories and no request headers, keys, or complete provider objects.

## Explicit exclusions

No diagnosis history, automatic Fault creation, RAG, LangChain, LangGraph, MCP, autonomous agents, streaming, WebSockets, conversation memory, or Device/Fault CRUD redesign.

## Phase 4 deployment security follow-up

Reassess server-side rate limiting before exposing the diagnosis endpoint beyond a trusted local environment. The review must account for paid-provider cost abuse and provider quota exhaustion; it is intentionally deferred from the local Phase 3 MVP.
