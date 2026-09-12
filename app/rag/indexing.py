from dataclasses import dataclass

from app.rag.chunking import chunk_document
from app.rag.documents import DocumentLoadError, DocumentLoader
from app.rag.embeddings import EmbeddingProvider
from app.rag.types import KnowledgeChunk
from app.rag.vector_store import ChromaVectorStore


@dataclass
class IndexStats:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    deleted: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "deleted": self.deleted,
            "errors": self.errors,
        }


class KnowledgeIndexer:
    def __init__(
        self,
        loader: DocumentLoader,
        embeddings: EmbeddingProvider,
        store: ChromaVectorStore,
        *,
        chunk_size: int,
        overlap: int,
    ) -> None:
        self.loader = loader
        self.embeddings = embeddings
        self.store = store
        self.chunk_size = chunk_size
        self.overlap = overlap

    def index(self, *, rebuild: bool = False) -> IndexStats:
        stats = IndexStats()
        if rebuild:
            self.store.clear()
        existing = self.store.list_chunks()
        existing_by_slot = {
            (chunk.source, chunk.chunk_index): chunk for chunk in existing
        }
        candidate_paths = self.loader.paths()
        candidate_sources = {
            path.relative_to(self.loader.root).as_posix() for path in candidate_paths
        }

        for path in candidate_paths:
            try:
                document = self.loader.load(path)
                chunks = chunk_document(
                    document, chunk_size=self.chunk_size, overlap=self.overlap
                )
                pending: list[KnowledgeChunk] = []
                replaced_ids: list[str] = []
                inserted_count = 0
                updated_count = 0
                for chunk in chunks:
                    previous = existing_by_slot.get(
                        (chunk.source, chunk.chunk_index)
                    )
                    if previous is not None and previous.id == chunk.id:
                        stats.skipped += 1
                    else:
                        pending.append(chunk)
                        if previous is None:
                            inserted_count += 1
                        else:
                            updated_count += 1
                            replaced_ids.append(previous.id)
                if pending:
                    vectors = self.embeddings.embed_passages(
                        [chunk.content for chunk in pending]
                    )
                    self.store.upsert(pending, vectors)
                    self.store.delete(replaced_ids)
                    stats.inserted += inserted_count
                    stats.updated += updated_count

                current_slots = {
                    (chunk.source, chunk.chunk_index) for chunk in chunks
                }
                surplus = [
                    chunk.id
                    for chunk in existing
                    if chunk.source == document.source
                    and (chunk.source, chunk.chunk_index) not in current_slots
                ]
                self.store.delete(surplus)
                stats.deleted += len(surplus)
            except DocumentLoadError:
                stats.errors += 1
                stale_ids = [
                    chunk.id
                    for chunk in existing
                    if chunk.source
                    == path.relative_to(self.loader.root).as_posix()
                ]
                self.store.delete(stale_ids)
                stats.deleted += len(stale_ids)
            except Exception:
                stats.errors += 1

        removed = [
            chunk.id
            for chunk in existing
            if chunk.source not in candidate_sources
        ]
        self.store.delete(removed)
        stats.deleted += len(removed)
        return stats
