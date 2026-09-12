from pathlib import Path
from typing import Any

from app.rag.types import KnowledgeChunk, RetrievedChunk


class ChromaVectorStore:
    def __init__(self, path: Path, collection_name: str) -> None:
        import chromadb

        self.path = path
        self.collection_name = collection_name
        self.path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.path))
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._validate_cosine_collection()

    @classmethod
    def open_existing(cls, path: Path, collection_name: str) -> "ChromaVectorStore":
        import chromadb

        store = cls.__new__(cls)
        store.path = path
        store.collection_name = collection_name
        store.client = chromadb.PersistentClient(path=str(path))
        try:
            store.collection = store.client.get_collection(name=collection_name)
            store._validate_cosine_collection()
        except Exception:
            store.client.close()
            raise
        return store

    def _validate_cosine_collection(self) -> None:
        if (self.collection.metadata or {}).get("hnsw:space") != "cosine":
            raise ValueError("existing Chroma collection is not configured for cosine")

    @property
    def collection_metadata(self) -> dict[str, Any]:
        return dict(self.collection.metadata or {})

    def count(self) -> int:
        return self.collection.count()

    def close(self) -> None:
        self.client.close()

    def upsert(
        self, chunks: list[KnowledgeChunk], embeddings: list[list[float]]
    ) -> None:
        if not chunks:
            return
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have equal lengths")
        self.collection.upsert(
            ids=[chunk.id for chunk in chunks],
            embeddings=embeddings,
            documents=[chunk.content for chunk in chunks],
            metadatas=[
                {
                    "source": chunk.source,
                    "title": chunk.title,
                    "equipment_type": chunk.equipment_type,
                    "chunk_index": chunk.chunk_index,
                }
                for chunk in chunks
            ],
        )

    def delete(self, ids: list[str]) -> None:
        if ids:
            self.collection.delete(ids=ids)

    def clear(self) -> None:
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def list_chunks(self) -> list[KnowledgeChunk]:
        result = self.collection.get(include=["documents", "metadatas"])
        ids = result.get("ids") or []
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        chunks: list[KnowledgeChunk] = []
        for identity, content, metadata in zip(ids, documents, metadatas, strict=True):
            metadata = metadata or {}
            chunks.append(
                KnowledgeChunk(
                    id=str(identity),
                    source=str(metadata["source"]),
                    title=str(metadata["title"]),
                    equipment_type=str(metadata["equipment_type"]),
                    chunk_index=int(metadata["chunk_index"]),
                    content=str(content),
                )
            )
        return sorted(chunks, key=lambda chunk: (chunk.source, chunk.chunk_index))

    def query(
        self,
        embedding: list[float],
        *,
        top_k: int,
        equipment_type: str | None,
    ) -> list[RetrievedChunk]:
        if self.count() == 0:
            return []
        arguments: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": min(top_k, self.count()),
            "include": ["documents", "metadatas", "distances"],
        }
        if equipment_type is not None:
            arguments["where"] = {"equipment_type": equipment_type}
        result = self.collection.query(**arguments)
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        retrieved: list[RetrievedChunk] = []
        for content, metadata, distance in zip(
            documents, metadatas, distances, strict=True
        ):
            metadata = metadata or {}
            retrieved.append(
                RetrievedChunk(
                    content=str(content),
                    source=str(metadata["source"]),
                    title=str(metadata["title"]),
                    equipment_type=str(metadata["equipment_type"]),
                    chunk_index=int(metadata["chunk_index"]),
                    distance=float(distance),
                )
            )
        return retrieved
