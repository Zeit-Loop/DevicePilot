from collections.abc import Sequence
from pathlib import Path

import chromadb

from app.rag.types import KnowledgeChunk
from app.rag.vector_store import ChromaVectorStore
from scripts import evaluate_rag
from scripts.evaluate_rag import EVALUATION_THRESHOLD, run_evaluation


class TestRealEmbeddings:
    FEATURES = (
        ("高温", "金属摩擦", "汽蚀", "异常振动"),
        ("轴承", "异常噪声", "电机过热并伴随振动"),
        ("读数", "漂移", "跳变", "校准"),
        ("相机", "图像", "断连", "丢失"),
    )

    @classmethod
    def _vector(cls, text: str) -> list[float]:
        vector = [
            1.0 if any(term in text for term in terms) else 0.0
            for terms in cls.FEATURES
        ]
        vector.append(0.0)
        if not any(vector):
            vector[-1] = 1.0
        return vector

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]


class RecordingRealEmbeddings(TestRealEmbeddings):
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.queries: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return self._vector(text)


def _persist_real_evaluation_collection(path: Path, collection_name: str) -> None:
    embeddings = TestRealEmbeddings()
    chunks = [
        KnowledgeChunk(
            id=f"{source}-0",
            source=source,
            title=source,
            equipment_type=equipment_type,
            chunk_index=0,
            content=content,
        )
        for source, equipment_type, content in [
            (
                "centrifugal-pump.md",
                "centrifugal pump",
                "高温、金属摩擦、汽蚀和异常振动排查。",
            ),
            (
                "industrial-motor.md",
                "industrial motor",
                "轴承异常噪声和电机过热并伴随振动排查。",
            ),
            (
                "temperature-sensor.md",
                "temperature sensor",
                "读数漂移、跳变和校准异常排查。",
            ),
            (
                "vision-controller.md",
                "vision controller",
                "相机断连和图像间歇丢失排查。",
            ),
        ]
    ]
    store = ChromaVectorStore(path, collection_name)
    try:
        store.upsert(chunks, embeddings.embed_passages([chunk.content for chunk in chunks]))
    finally:
        store.close()


def test_five_case_deterministic_evaluation_calibrates_threshold(
    tmp_path: Path,
) -> None:
    report = run_evaluation(tmp_path / "chroma")

    assert EVALUATION_THRESHOLD == 0.55
    assert len(report.cases) == 5
    assert report.passed == 5
    assert [case.source for case in report.cases[:4]] == [
        "centrifugal-pump.md",
        "industrial-motor.md",
        "temperature-sensor.md",
        "vision-controller.md",
    ]
    assert all(
        case.distance is not None and case.distance <= EVALUATION_THRESHOLD
        for case in report.cases[:4]
    )
    assert report.cases[4].source is None
    assert report.cases[4].nearest_distance is not None
    assert report.cases[4].nearest_distance > EVALUATION_THRESHOLD


def test_default_cli_remains_deterministic_and_offline(monkeypatch, capsys) -> None:
    def unexpected_real_embedding(_model_name: str) -> RecordingRealEmbeddings:
        raise AssertionError("the default evaluator must not initialize E5")

    monkeypatch.setattr(evaluate_rag, "E5EmbeddingProvider", unexpected_real_embedding)

    assert evaluate_rag.main([]) == 0

    output = capsys.readouterr().out
    assert "pump-cavitation: PASS source=centrifugal-pump.md" in output
    assert "threshold=0.55 passed=5/5" in output


def test_real_cli_uses_configured_persisted_runtime_without_rebuilding(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    vector_path = tmp_path / "persisted-chroma"
    collection_name = "real-evaluation"
    _persist_real_evaluation_collection(vector_path, collection_name)
    constructed: list[RecordingRealEmbeddings] = []

    def make_embeddings(model_name: str) -> RecordingRealEmbeddings:
        embeddings = RecordingRealEmbeddings(model_name)
        constructed.append(embeddings)
        return embeddings

    def unexpected_temporary_directory(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("real mode must not use a temporary directory")

    class UnexpectedIndexer:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("real mode must not rebuild the knowledge index")

    monkeypatch.setenv("RAG_VECTOR_STORE_PATH", str(vector_path))
    monkeypatch.setenv("RAG_CHROMA_PATH", str(tmp_path / "legacy-path"))
    monkeypatch.setenv("RAG_COLLECTION_NAME", collection_name)
    monkeypatch.setenv("RAG_EMBEDDING_MODEL", "recording-e5")
    monkeypatch.setenv("RAG_TOP_K", "2")
    monkeypatch.setenv("RAG_MAX_DISTANCE", "0.55")
    monkeypatch.setattr(evaluate_rag, "E5EmbeddingProvider", make_embeddings)
    monkeypatch.setattr(evaluate_rag, "TemporaryDirectory", unexpected_temporary_directory)
    monkeypatch.setattr(evaluate_rag, "KnowledgeIndexer", UnexpectedIndexer)
    monkeypatch.setattr(
        evaluate_rag,
        "DeterministicEvaluationEmbeddings",
        lambda: (_ for _ in ()).throw(
            AssertionError("real mode must not use deterministic embeddings")
        ),
    )

    assert evaluate_rag.main(["--real"]) == 0

    output = capsys.readouterr().out
    assert "mode=real embedding_model=recording-e5" in output
    assert f"vector_store_path={vector_path}" in output
    assert "collection=real-evaluation collection_count=4 top_k=2 max_distance=0.55" in output
    assert "pump-high-temperature-metal-friction: PASS expected_source=centrifugal-pump.md" in output
    assert "vision-printer-paper-jam: PASS expected_source=none returned_source=none" in output
    assert "decision=accepted" in output
    assert "decision=rejected" in output
    assert "positive_nearest_distance min=0.0 max=0.0 mean=0.0" in output
    assert "negative_nearest_distance min=1.0 max=1.0 mean=1.0" in output
    assert "max_positive_distance=0.0" in output
    assert "min_negative_distance=1.0" in output
    assert len(constructed) == 1
    assert constructed[0].model_name == "recording-e5"
    assert constructed[0].queries == [case.query for case in evaluate_rag.REAL_CASES]


def test_real_measurement_cases_have_twelve_exact_expected_classifications() -> None:
    assert [
        (case.name, case.expected_source)
        for case in evaluate_rag.REAL_CASES
    ] == [
        ("pump-high-temperature-metal-friction", "centrifugal-pump.md"),
        ("pump-cavitation-abnormal-vibration", "centrifugal-pump.md"),
        ("motor-bearing-abnormal-noise", "industrial-motor.md"),
        ("motor-overheating-vibration", "industrial-motor.md"),
        ("sensor-reading-drift", "temperature-sensor.md"),
        ("sensor-reading-jump-calibration", "temperature-sensor.md"),
        ("vision-camera-disconnect", "vision-controller.md"),
        ("vision-intermittent-image-loss", "vision-controller.md"),
        ("pump-office-printer-wifi-toner", None),
        ("motor-browser-webpage", None),
        ("sensor-windows-password", None),
        ("vision-printer-paper-jam", None),
    ]
    assert len(evaluate_rag.CASES) == 5
    assert EVALUATION_THRESHOLD == 0.55


def test_real_distance_statistics_use_literal_nearest_distances() -> None:
    literal_distances = [0.12, 0.22, 0.32, 0.42, 0.52, 0.62, 0.72, 0.82, 1.1, 1.2, 1.3, 1.4]
    results = [
        evaluate_rag.EvaluationCaseResult(
            name=case.name,
            source=case.expected_source,
            distance=None,
            nearest_distance=distance,
            passed=True,
        )
        for case, distance in zip(
            evaluate_rag.REAL_CASES, literal_distances, strict=True
        )
    ]

    statistics = evaluate_rag.real_distance_statistics(results)

    assert statistics.positive_min == 0.12
    assert statistics.positive_max == 0.82
    assert statistics.positive_mean == 0.47
    assert statistics.negative_min == 1.1
    assert statistics.negative_max == 1.4
    assert statistics.negative_mean == 1.25
    assert statistics.max_positive_distance == 0.82
    assert statistics.min_negative_distance == 1.1


def test_real_distance_statistics_reject_missing_nearest_distance() -> None:
    results = [
        evaluate_rag.EvaluationCaseResult(
            name=case.name,
            source=case.expected_source,
            distance=None,
            nearest_distance=None if index == 3 else 0.1,
            passed=True,
        )
        for index, case in enumerate(evaluate_rag.REAL_CASES)
    ]

    try:
        evaluate_rag.real_distance_statistics(results)
    except evaluate_rag.MissingRealEvaluationDistanceError as exc:
        assert str(exc) == "motor-overheating-vibration"
    else:
        raise AssertionError("missing nearest distance must fail real measurement")


def test_real_cli_reports_missing_index_without_creating_or_rebuilding(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    missing_path = tmp_path / "missing-chroma"

    def unexpected_real_embedding(_model_name: str) -> RecordingRealEmbeddings:
        raise AssertionError("a missing index must be detected before E5 initialization")

    class UnexpectedIndexer:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("real mode must not rebuild a missing index")

    monkeypatch.setenv("RAG_VECTOR_STORE_PATH", str(missing_path))
    monkeypatch.setattr(evaluate_rag, "E5EmbeddingProvider", unexpected_real_embedding)
    monkeypatch.setattr(evaluate_rag, "KnowledgeIndexer", UnexpectedIndexer)
    monkeypatch.setattr(
        evaluate_rag,
        "DeterministicEvaluationEmbeddings",
        lambda: (_ for _ in ()).throw(
            AssertionError("real mode must not use deterministic embeddings")
        ),
    )

    assert evaluate_rag.main(["--real"]) == 1

    output = capsys.readouterr().out
    assert "Knowledge index not found." in output
    assert "Run:" in output
    assert "python -m scripts.index_knowledge --rebuild" in output
    assert not missing_path.exists()


def test_real_cli_missing_collection_does_not_create_target_collection(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    vector_path = tmp_path / "persisted-chroma"
    _persist_real_evaluation_collection(vector_path, "existing-collection")
    target_collection = "missing-collection"

    def unexpected_real_embedding(_model_name: str) -> RecordingRealEmbeddings:
        raise AssertionError("a missing collection must be detected before E5 initialization")

    monkeypatch.setenv("RAG_VECTOR_STORE_PATH", str(vector_path))
    monkeypatch.setenv("RAG_COLLECTION_NAME", target_collection)
    monkeypatch.setattr(evaluate_rag, "E5EmbeddingProvider", unexpected_real_embedding)
    monkeypatch.setattr(
        evaluate_rag,
        "DeterministicEvaluationEmbeddings",
        lambda: (_ for _ in ()).throw(
            AssertionError("real mode must not use deterministic embeddings")
        ),
    )

    assert evaluate_rag.main(["--real"]) == 1

    output = capsys.readouterr().out
    assert "Knowledge index not found." in output
    assert "python -m scripts.index_knowledge --rebuild" in output
    client = chromadb.PersistentClient(path=str(vector_path))
    try:
        assert target_collection not in {
            collection.name for collection in client.list_collections()
        }
    finally:
        client.close()
