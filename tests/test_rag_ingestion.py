from pathlib import Path
from typing import Any

import pytest

from app.config import RAGSettings
from app.rag.chunking import chunk_document, normalize_equipment_type
from app.rag.documents import DocumentLoadError, DocumentLoader
from app.rag.embeddings import E5EmbeddingProvider
from app.rag.types import KnowledgeDocument


def write_document(path: Path, *, equipment_type: str, body: str) -> None:
    path.write_text(
        f"---\ntitle: Bearing guide\nequipment_type: {equipment_type}\n---\n{body}",
        encoding="utf-8",
    )


def test_loader_reads_markdown_and_text_with_relative_metadata(tmp_path: Path) -> None:
    write_document(
        tmp_path / "pump.md",
        equipment_type=" Centrifugal_Pump ",
        body="Check the bearing temperature.",
    )
    write_document(
        tmp_path / "motor.txt",
        equipment_type="Industrial Motor",
        body="Inspect the cooling fan.",
    )

    documents = DocumentLoader(tmp_path).load_all()

    assert [(document.source, document.equipment_type) for document in documents] == [
        ("motor.txt", "industrial motor"),
        ("pump.md", "centrifugal pump"),
    ]
    assert documents[1].title == "Bearing guide"
    assert documents[1].content == "Check the bearing temperature."


def test_loader_rejects_unsupported_extension_and_path_traversal(tmp_path: Path) -> None:
    loader = DocumentLoader(tmp_path)
    (tmp_path / "guide.pdf").write_bytes(b"not a pdf")
    outside = tmp_path.parent / "outside.md"
    write_document(outside, equipment_type="Pump", body="outside")

    with pytest.raises(DocumentLoadError, match="unsupported"):
        loader.load("guide.pdf")
    with pytest.raises(DocumentLoadError, match="outside knowledge root"):
        loader.load(outside)


def test_loader_rejects_oversize_and_unreadable_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_document(tmp_path / "large.md", equipment_type="Pump", body="123456789")
    loader = DocumentLoader(tmp_path, max_bytes=20)
    with pytest.raises(DocumentLoadError, match="maximum size"):
        loader.load("large.md")

    write_document(tmp_path / "blocked.md", equipment_type="Pump", body="blocked")
    original_read_text = Path.read_text

    def blocked_read(path: Path, *args: Any, **kwargs: Any) -> str:
        if path.name == "blocked.md":
            raise OSError("access denied")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", blocked_read)
    with pytest.raises(DocumentLoadError, match="could not be read"):
        DocumentLoader(tmp_path).load("blocked.md")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" Centrifugal_Pump ", "centrifugal pump"),
        ("INDUSTRIAL---MOTOR", "industrial motor"),
        ("Ｖｉｓｉｏｎ　Controller", "vision controller"),
    ],
)
def test_equipment_type_normalization_is_unicode_and_separator_stable(
    raw: str, expected: str
) -> None:
    assert normalize_equipment_type(raw) == expected


def test_chunking_is_deterministic_and_preserves_exact_overlap() -> None:
    document = KnowledgeDocument(
        source="pump.md",
        title="Pump",
        equipment_type="centrifugal pump",
        content="abcdefghijklmnopqrstuvwxyz",
    )

    first = chunk_document(document, chunk_size=10, overlap=3)
    second = chunk_document(document, chunk_size=10, overlap=3)

    assert [chunk.content for chunk in first] == [
        "abcdefghij",
        "hijklmnopq",
        "opqrstuvwx",
        "vwxyz",
    ]
    assert [chunk.id for chunk in first] == [chunk.id for chunk in second]
    assert [chunk.chunk_index for chunk in first] == [0, 1, 2, 3]
    assert all(chunk.equipment_type == "centrifugal pump" for chunk in first)


@pytest.mark.parametrize(
    ("chunk_size", "overlap"), [(0, 0), (10, -1), (10, 10), (10, 11)]
)
def test_chunking_rejects_invalid_sizes(chunk_size: int, overlap: int) -> None:
    document = KnowledgeDocument(
        source="pump.md", title="Pump", equipment_type="pump", content="content"
    )
    with pytest.raises(ValueError):
        chunk_document(document, chunk_size=chunk_size, overlap=overlap)


def test_rag_settings_parse_and_validate_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RAG_ENABLED", "true")
    monkeypatch.setenv("RAG_KNOWLEDGE_PATH", str(tmp_path / "knowledge"))
    monkeypatch.setenv("RAG_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("RAG_TOP_K", "4")
    monkeypatch.setenv("RAG_MAX_DISTANCE", "0.55")
    monkeypatch.setenv("RAG_CHUNK_SIZE", "600")
    monkeypatch.setenv("RAG_CHUNK_OVERLAP", "80")

    settings = RAGSettings.from_environment()

    assert settings.enabled is True
    assert settings.knowledge_path == tmp_path / "knowledge"
    assert settings.chroma_path == tmp_path / "chroma"
    assert settings.top_k == 4
    assert settings.max_distance == 0.55
    assert (settings.chunk_size, settings.chunk_overlap) == (600, 80)


def test_rag_settings_use_calibrated_production_distance_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAG_MAX_DISTANCE", raising=False)

    assert RAGSettings.from_environment().max_distance == 0.143


def test_rag_settings_prefers_canonical_vector_store_path_and_configures_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical_path = tmp_path / "canonical-chroma"
    legacy_path = tmp_path / "legacy-chroma"
    monkeypatch.setenv("RAG_VECTOR_STORE_PATH", str(canonical_path))
    monkeypatch.setenv("RAG_CHROMA_PATH", str(legacy_path))
    monkeypatch.setenv("RAG_EMBEDDING_MODEL", "custom/e5-model")

    settings = RAGSettings.from_environment()

    assert settings.chroma_path == canonical_path
    assert settings.embedding_model == "custom/e5-model"


def test_rag_settings_falls_back_to_legacy_vector_store_path_when_canonical_blank(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy_path = tmp_path / "legacy-chroma"
    monkeypatch.setenv("RAG_VECTOR_STORE_PATH", "   ")
    monkeypatch.setenv("RAG_CHROMA_PATH", str(legacy_path))

    assert RAGSettings.from_environment().chroma_path == legacy_path


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("RAG_ENABLED", "sometimes"),
        ("RAG_TOP_K", "0"),
        ("RAG_MAX_DISTANCE", "-0.01"),
        ("RAG_MAX_DISTANCE", "2.01"),
        ("RAG_CHUNK_SIZE", "0"),
        ("RAG_CHUNK_OVERLAP", "-1"),
    ],
)
def test_rag_settings_reject_invalid_values(
    name: str, value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        RAGSettings.from_environment()


def test_rag_settings_reject_overlap_not_smaller_than_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAG_CHUNK_SIZE", "100")
    monkeypatch.setenv("RAG_CHUNK_OVERLAP", "100")
    with pytest.raises(ValueError, match="RAG_CHUNK_OVERLAP"):
        RAGSettings.from_environment()


class FakeSentenceTransformer:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], bool]] = []

    def encode(self, texts: list[str], *, normalize_embeddings: bool) -> list[list[float]]:
        self.calls.append((texts, normalize_embeddings))
        return [[float(index), 1.0] for index, _text in enumerate(texts)]


def test_e5_model_is_lazy_and_owns_query_passage_prefixes() -> None:
    constructed: list[str] = []
    model = FakeSentenceTransformer()

    def factory(model_name: str) -> FakeSentenceTransformer:
        constructed.append(model_name)
        return model

    provider = E5EmbeddingProvider(model_factory=factory)
    assert constructed == []

    assert provider.embed_query("bearing noise") == [0.0, 1.0]
    assert provider.embed_passages(["pump guide", "motor guide"]) == [
        [0.0, 1.0],
        [1.0, 1.0],
    ]

    assert constructed == ["intfloat/multilingual-e5-small"]
    assert model.calls == [
        (["query: bearing noise"], True),
        (["passage: pump guide", "passage: motor guide"], True),
    ]
