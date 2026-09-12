# Phase 5 RAG Knowledge Base Design

## Scope

Add a bounded, local RAG enhancement to the existing DevicePilot diagnosis flow. The only supported source formats are Markdown and TXT. This phase does not add LangGraph, agents, MCP, web search, memory, hybrid retrieval, reranking, Graph RAG, cloud vector databases, or an upload UI.

## Architecture

```text
DocumentLoader
  -> deterministic chunker
  -> EmbeddingProvider
  -> ChromaVectorStore
  -> RetrievalService
  -> Diagnosis Service
  -> LiteLLM
```

The retrieval layer is independent of LiteLLM. The Diagnosis Service combines trusted database device facts, the untrusted user report, and retrieved reference chunks. Retrieval failure degrades to the existing non-RAG diagnosis and returns an empty `sources` array.

## Decisions

- Use `intfloat/multilingual-e5-small`; `EmbeddingProvider` alone applies `query: ` and `passage: ` prefixes.
- Load the real model lazily only for indexing or production retrieval. Tests use deterministic fake embeddings and never download a model.
- Use persistent Chroma under `data/chroma/`, separate from SQLite.
- Normalize equipment types deterministically by Unicode/case normalization and separator/whitespace folding; do not build a taxonomy.
- Filter by normalized equipment type first. A minimal unfiltered fallback is allowed only when strict filtering returns no candidates.
- Use the collection's explicitly configured cosine distance. Smaller distance is more relevant. Calibrate the configurable maximum-distance threshold with the five deterministic evaluation cases and document the result.
- Stable chunk identity includes source, normalized equipment type, chunk index, and content. Normal indexing reconciles each source so changed and removed chunks do not remain stale; `--rebuild` clears the collection first.
- Sources are generated only from retrieval metadata and contain `document` and `chunk_index`.
- Retrieved documents are untrusted reference data. Their instructions are never followed, and trusted database facts win on conflict.

## Acceptance

All requested loader, chunking, indexing, retrieval, diagnosis, source, failure-degradation, regression, frontend, Docker, security, and five-case evaluation checks must pass without internet access or a paid LLM during automated tests.
