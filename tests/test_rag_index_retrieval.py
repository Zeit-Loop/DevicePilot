from collections.abc import Sequence
from pathlib import Path
import shutil

import pytest

from app.rag.chunking import chunk_document
from app.rag.documents import DocumentLoader
from app.rag.indexing import KnowledgeIndexer
from app.rag.retrieval import RetrievalService
from app.rag.types import KnowledgeChunk, KnowledgeDocument, RetrievedChunk
from app.rag.vector_store import ChromaVectorStore
from scripts import index_knowledge
from scripts.index_knowledge import format_stats


class KeywordEmbeddings:
    KEYWORDS = ("pump", "motor", "sensor", "vision")

    def __init__(self) -> None:
        self.queries: list[str] = []

    def _vector(self, text: str) -> list[float]:
        lowered = text.casefold()
        vector = [1.0 if keyword in lowered else 0.0 for keyword in self.KEYWORDS]
        return vector if any(vector) else [0.5, 0.5, 0.5, 0.5]

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return self._vector(text)

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]


def make_chunk(
    identity: str,
    *,
    source: str,
    equipment_type: str,
    chunk_index: int = 0,
    content: str,
) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=identity,
        source=source,
        title=source,
        equipment_type=equipment_type,
        chunk_index=chunk_index,
        content=content,
    )


def write_document(path: Path, *, equipment_type: str, body: str) -> None:
    path.write_text(
        f"---\ntitle: {path.stem}\nequipment_type: {equipment_type}\n---\n{body}",
        encoding="utf-8",
    )


def test_chroma_collection_explicitly_uses_cosine_and_persists(tmp_path: Path) -> None:
    path = tmp_path / "chroma"
    store = ChromaVectorStore(path, "knowledge_test")
    store.upsert(
        [
            make_chunk(
                "pump-0",
                source="pump.md",
                equipment_type="centrifugal pump",
                content="pump bearing noise",
            )
        ],
        [[1.0, 0.0]],
    )

    reopened = ChromaVectorStore(path, "knowledge_test")

    assert reopened.collection_metadata["hnsw:space"] == "cosine"
    assert reopened.count() == 1
    assert reopened.list_chunks()[0].id == "pump-0"
    store.close()
    reopened.close()


def test_chroma_store_close_releases_persistent_files(tmp_path: Path) -> None:
    path = tmp_path / "closable"
    store = ChromaVectorStore(path, "close_test")

    store.close()
    shutil.rmtree(path)

    assert not path.exists()


def test_stable_identity_changes_only_when_identity_input_changes() -> None:
    base = KnowledgeDocument(
        source="pump.md",
        title="Pump",
        equipment_type="Centrifugal_Pump",
        content="bearing noise",
    )
    same = KnowledgeDocument(
        source="pump.md",
        title="Renamed title",
        equipment_type="centrifugal pump",
        content="bearing noise",
    )
    changed = KnowledgeDocument(
        source="pump.md",
        title="Pump",
        equipment_type="centrifugal pump",
        content="seal leak",
    )

    base_id = chunk_document(base, chunk_size=100, overlap=0)[0].id
    assert chunk_document(same, chunk_size=100, overlap=0)[0].id == base_id
    assert chunk_document(changed, chunk_size=100, overlap=0)[0].id != base_id


def test_indexing_is_idempotent_and_reconciles_changed_and_deleted_sources(
    tmp_path: Path,
) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    pump_path = knowledge / "pump.md"
    motor_path = knowledge / "motor.md"
    write_document(pump_path, equipment_type="Pump", body="pump bearing noise")
    write_document(motor_path, equipment_type="Motor", body="motor winding heat")
    store = ChromaVectorStore(tmp_path / "chroma", "index_test")
    indexer = KnowledgeIndexer(
        DocumentLoader(knowledge),
        KeywordEmbeddings(),
        store,
        chunk_size=100,
        overlap=0,
    )

    first = indexer.index()
    second = indexer.index()
    write_document(pump_path, equipment_type="Pump", body="pump mechanical seal leak")
    changed = indexer.index()
    motor_path.unlink()
    deleted = indexer.index()
    rebuilt = indexer.index(rebuild=True)

    assert first.as_dict() == {
        "inserted": 2,
        "updated": 0,
        "skipped": 0,
        "deleted": 0,
        "errors": 0,
    }
    assert second.as_dict() == {
        "inserted": 0,
        "updated": 0,
        "skipped": 2,
        "deleted": 0,
        "errors": 0,
    }
    assert changed.updated == 1
    assert changed.inserted == 0
    assert deleted.deleted == 1
    assert store.count() == 1
    assert rebuilt.inserted == 1
    assert rebuilt.skipped == 0


def test_indexer_counts_bad_documents_without_aborting_valid_ones(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    write_document(knowledge / "valid.md", equipment_type="Pump", body="pump bearing")
    (knowledge / "bad.md").write_text("missing front matter", encoding="utf-8")
    indexer = KnowledgeIndexer(
        DocumentLoader(knowledge),
        KeywordEmbeddings(),
        ChromaVectorStore(tmp_path / "chroma", "error_test"),
        chunk_size=100,
        overlap=0,
    )

    stats = indexer.index()

    assert stats.inserted == 1
    assert stats.errors == 1


def test_indexer_removes_stale_chunks_when_an_existing_source_becomes_invalid(
    tmp_path: Path,
) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    source = knowledge / "pump.md"
    write_document(source, equipment_type="Pump", body="pump bearing")
    store = ChromaVectorStore(tmp_path / "chroma", "invalid_source_test")
    indexer = KnowledgeIndexer(
        DocumentLoader(knowledge),
        KeywordEmbeddings(),
        store,
        chunk_size=100,
        overlap=0,
    )

    assert indexer.index().inserted == 1
    source.write_text("missing front matter", encoding="utf-8")

    stats = indexer.index()

    assert stats.errors == 1
    assert stats.deleted == 1
    assert store.count() == 0


def test_indexer_does_not_claim_insertions_when_embedding_fails(
    tmp_path: Path,
) -> None:
    class FailingEmbeddings(KeywordEmbeddings):
        def embed_passages(self, _texts: Sequence[str]) -> list[list[float]]:
            raise RuntimeError("embedding unavailable")

    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    write_document(knowledge / "pump.md", equipment_type="Pump", body="pump bearing")
    store = ChromaVectorStore(tmp_path / "chroma", "embedding_error_test")
    indexer = KnowledgeIndexer(
        DocumentLoader(knowledge),
        FailingEmbeddings(),
        store,
        chunk_size=100,
        overlap=0,
    )

    stats = indexer.index()

    assert stats.inserted == 0
    assert stats.updated == 0
    assert stats.errors == 1
    assert store.count() == 0


def test_cli_stats_include_every_counter() -> None:
    assert format_stats(
        inserted=1, updated=2, skipped=3, deleted=4, errors=5
    ) == "inserted=1 updated=2 skipped=3 deleted=4 errors=5"


@pytest.mark.parametrize("should_fail", [False, True])
def test_index_cli_closes_its_vector_store_on_success_and_failure(
    monkeypatch: pytest.MonkeyPatch, should_fail: bool
) -> None:
    closed: list[bool] = []

    class RecordingStore:
        def __init__(self, _path: Path, _collection_name: str) -> None:
            pass

        def close(self) -> None:
            closed.append(True)

    class RecordingIndexer:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def index(self, *, rebuild: bool) -> object:
            assert rebuild is False
            if should_fail:
                raise RuntimeError("indexing failed")
            return type(
                "Stats",
                (),
                {
                    "errors": 0,
                    "as_dict": lambda self: {
                        "inserted": 1,
                        "updated": 0,
                        "skipped": 0,
                        "deleted": 0,
                        "errors": 0,
                    },
                },
            )()

    class RecordingEmbeddings:
        def __init__(self, _model_name: str) -> None:
            pass

    monkeypatch.setattr(index_knowledge, "KnowledgeIndexer", RecordingIndexer)
    monkeypatch.setattr(index_knowledge, "E5EmbeddingProvider", RecordingEmbeddings)
    settings = type(
        "Settings",
        (),
        {
            "knowledge_path": Path("knowledge"),
            "max_file_bytes": 1_000_000,
            "embedding_model": "recording-e5",
            "chroma_path": Path("chroma"),
            "collection_name": "knowledge",
            "chunk_size": 600,
            "chunk_overlap": 80,
        },
    )()
    monkeypatch.setattr(
        index_knowledge.RAGSettings,
        "from_environment",
        classmethod(lambda _cls: settings),
    )

    if should_fail:
        with pytest.raises(RuntimeError, match="indexing failed"):
            index_knowledge.main([], store_factory=RecordingStore)
    else:
        assert index_knowledge.main([], store_factory=RecordingStore) == 0

    assert closed == [True]


@pytest.mark.parametrize(
    ("device_type", "description", "expected_source"),
    [
        ("Centrifugal_Pump", "pump cavitation noise", "pump.md"),
        ("Industrial Motor", "motor bearing heat", "motor.md"),
        ("Temperature Sensor", "sensor reading drift", "sensor.md"),
        ("Vision Controller", "vision camera offline", "vision.md"),
    ],
)
def test_retrieval_returns_demo_device_specific_hit(
    tmp_path: Path,
    device_type: str,
    description: str,
    expected_source: str,
) -> None:
    chunks = [
        make_chunk(
            f"{keyword}-0",
            source=f"{keyword}.md",
            equipment_type=equipment,
            content=f"{keyword} troubleshooting guide",
        )
        for keyword, equipment in [
            ("pump", "centrifugal pump"),
            ("motor", "industrial motor"),
            ("sensor", "temperature sensor"),
            ("vision", "vision controller"),
        ]
    ]
    embeddings = KeywordEmbeddings()
    store = ChromaVectorStore(tmp_path / "chroma", "retrieval_test")
    store.upsert(chunks, embeddings.embed_passages([chunk.content for chunk in chunks]))
    service = RetrievalService(
        embeddings, store, top_k=2, max_distance=0.55
    )

    results = service.retrieve(device_type, description)

    assert results[0].source == expected_source
    assert results[0].equipment_type == device_type.replace("_", " ").casefold()
    assert embeddings.queries == [description]


def test_retrieval_applies_top_k_and_threshold(tmp_path: Path) -> None:
    embeddings = KeywordEmbeddings()
    store = ChromaVectorStore(tmp_path / "chroma", "threshold_test")
    chunks = [
        make_chunk(
            f"pump-{index}",
            source="pump.md",
            equipment_type="pump",
            chunk_index=index,
            content=content,
        )
        for index, content in enumerate(
            ["pump bearing", "pump seal", "unrelated procedure"]
        )
    ]
    store.upsert(chunks, embeddings.embed_passages([chunk.content for chunk in chunks]))

    results = RetrievalService(
        embeddings, store, top_k=1, max_distance=0.2
    ).retrieve("pump", "pump noise")

    assert len(results) == 1
    assert results[0].distance <= 0.2
    assert results[0].content in {"pump bearing", "pump seal"}


def test_retrieval_returns_empty_for_missing_index_and_rejected_distance(
    tmp_path: Path,
) -> None:
    embeddings = KeywordEmbeddings()
    empty = ChromaVectorStore(tmp_path / "empty", "empty_test")
    assert RetrievalService(
        embeddings, empty, top_k=3, max_distance=0.55
    ).retrieve("pump", "pump noise") == []

    store = ChromaVectorStore(tmp_path / "chroma", "reject_test")
    chunk = make_chunk(
        "pump-0",
        source="pump.md",
        equipment_type="pump",
        content="motor-only information",
    )
    store.upsert([chunk], embeddings.embed_passages([chunk.content]))

    assert RetrievalService(
        embeddings, store, top_k=3, max_distance=0.1
    ).retrieve("pump", "pump noise") == []


class RecordingStore:
    def __init__(self) -> None:
        self.filters: list[str | None] = []

    def query(
        self,
        embedding: list[float],
        *,
        top_k: int,
        equipment_type: str | None,
    ) -> list[RetrievedChunk]:
        self.filters.append(equipment_type)
        return []


def test_retrieval_normalizes_device_filter_and_uses_unfiltered_fallback() -> None:
    store = RecordingStore()
    service = RetrievalService(
        KeywordEmbeddings(), store, top_k=3, max_distance=0.55
    )

    assert service.retrieve(" Industrial_Motor ", "motor heat") == []
    assert store.filters == ["industrial motor", None]
