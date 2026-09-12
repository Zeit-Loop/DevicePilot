import argparse

from app.config import RAGSettings
from app.rag.documents import DocumentLoader
from app.rag.embeddings import E5EmbeddingProvider
from app.rag.indexing import KnowledgeIndexer
from app.rag.vector_store import ChromaVectorStore


def format_stats(
    *, inserted: int, updated: int, skipped: int, deleted: int, errors: int
) -> str:
    return (
        f"inserted={inserted} updated={updated} skipped={skipped} "
        f"deleted={deleted} errors={errors}"
    )


def main(
    argv: list[str] | None = None,
    *,
    store_factory: type[ChromaVectorStore] = ChromaVectorStore,
) -> int:
    parser = argparse.ArgumentParser(description="Index DevicePilot knowledge")
    parser.add_argument(
        "--rebuild", action="store_true", help="clear the collection before indexing"
    )
    args = parser.parse_args(argv)
    settings = RAGSettings.from_environment()
    store = store_factory(settings.chroma_path, settings.collection_name)
    try:
        indexer = KnowledgeIndexer(
            DocumentLoader(
                settings.knowledge_path, max_bytes=settings.max_file_bytes
            ),
            E5EmbeddingProvider(settings.embedding_model),
            store,
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
        )
        stats = indexer.index(rebuild=args.rebuild)
        print(format_stats(**stats.as_dict()))
        return 1 if stats.errors else 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
