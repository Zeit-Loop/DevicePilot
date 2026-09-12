from typing import Protocol

from app.rag.chunking import normalize_equipment_type
from app.rag.embeddings import EmbeddingProvider
from app.rag.types import RetrievedChunk


class QueryableVectorStore(Protocol):
    def query(
        self,
        embedding: list[float],
        *,
        top_k: int,
        equipment_type: str | None,
    ) -> list[RetrievedChunk]: ...


class RetrievalService:
    def __init__(
        self,
        embeddings: EmbeddingProvider,
        store: QueryableVectorStore,
        *,
        top_k: int,
        max_distance: float,
    ) -> None:
        self.embeddings = embeddings
        self.store = store
        self.top_k = top_k
        self.max_distance = max_distance

    def retrieve(
        self, device_type: str, description: str
    ) -> list[RetrievedChunk]:
        query_embedding = self.embeddings.embed_query(description)
        normalized_type = normalize_equipment_type(device_type)
        candidates = self.store.query(
            query_embedding,
            top_k=self.top_k,
            equipment_type=normalized_type,
        )
        if not candidates:
            candidates = self.store.query(
                query_embedding,
                top_k=self.top_k,
                equipment_type=None,
            )
        return [
            chunk
            for chunk in candidates[: self.top_k]
            if chunk.distance <= self.max_distance
        ]
