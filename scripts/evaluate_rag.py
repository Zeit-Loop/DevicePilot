import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from tempfile import TemporaryDirectory

from chromadb.errors import NotFoundError

from app.config import PROJECT_ROOT, RAGSettings
from app.rag.chunking import normalize_equipment_type
from app.rag.documents import DocumentLoader
from app.rag.embeddings import E5EmbeddingProvider
from app.rag.indexing import KnowledgeIndexer
from app.rag.retrieval import RetrievalService
from app.rag.types import RetrievedChunk
from app.rag.vector_store import ChromaVectorStore


EVALUATION_THRESHOLD = 0.55


class KnowledgeIndexNotFoundError(RuntimeError):
    pass


class MissingRealEvaluationDistanceError(RuntimeError):
    pass


class DeterministicEvaluationEmbeddings:
    """Small fixed feature space used only for repeatable offline evaluation."""

    FEATURES = (
        ("汽蚀", "碎石"),
        ("研磨", "轴承"),
        ("漂移", "读数"),
        ("相机", "掉线"),
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


@dataclass(frozen=True)
class EvaluationCase:
    name: str
    device_type: str
    query: str
    expected_source: str | None


@dataclass(frozen=True)
class EvaluationCaseResult:
    name: str
    source: str | None
    distance: float | None
    nearest_distance: float | None
    passed: bool


@dataclass(frozen=True)
class EvaluationReport:
    cases: list[EvaluationCaseResult]

    @property
    def passed(self) -> int:
        return sum(case.passed for case in self.cases)


CASES = (
    EvaluationCase(
        "pump-cavitation",
        "Centrifugal Pump",
        "泵入口附近出现汽蚀和碎石撞击声",
        "centrifugal-pump.md",
    ),
    EvaluationCase(
        "motor-bearing",
        "Industrial Motor",
        "电机轴承位置发出研磨声",
        "industrial-motor.md",
    ),
    EvaluationCase(
        "sensor-drift",
        "Temperature Sensor",
        "温度读数持续漂移",
        "temperature-sensor.md",
    ),
    EvaluationCase(
        "vision-camera",
        "Vision Controller",
        "相机频繁掉线",
        "vision-controller.md",
    ),
    EvaluationCase(
        "irrelevant-office-printer",
        "Centrifugal Pump",
        "办公打印机缺纸，如何更换硒鼓",
        None,
    ),
)


REAL_CASES = (
    EvaluationCase(
        "pump-high-temperature-metal-friction",
        "Centrifugal Pump",
        "高温并伴有金属摩擦声",
        "centrifugal-pump.md",
    ),
    EvaluationCase(
        "pump-cavitation-abnormal-vibration",
        "Centrifugal Pump",
        "出现汽蚀和异常振动",
        "centrifugal-pump.md",
    ),
    EvaluationCase(
        "motor-bearing-abnormal-noise",
        "Industrial Motor",
        "轴承出现异常噪声",
        "industrial-motor.md",
    ),
    EvaluationCase(
        "motor-overheating-vibration",
        "Industrial Motor",
        "电机过热并伴随振动",
        "industrial-motor.md",
    ),
    EvaluationCase(
        "sensor-reading-drift",
        "Temperature Sensor",
        "读数持续漂移",
        "temperature-sensor.md",
    ),
    EvaluationCase(
        "sensor-reading-jump-calibration",
        "Temperature Sensor",
        "读数突然跳变，校准异常",
        "temperature-sensor.md",
    ),
    EvaluationCase(
        "vision-camera-disconnect",
        "Vision Controller",
        "相机断连",
        "vision-controller.md",
    ),
    EvaluationCase(
        "vision-intermittent-image-loss",
        "Vision Controller",
        "图像间歇丢失",
        "vision-controller.md",
    ),
    EvaluationCase(
        "pump-office-printer-wifi-toner",
        "Centrifugal Pump",
        "办公室打印机 Wi-Fi 无法连接，需要更换硒鼓",
        None,
    ),
    EvaluationCase(
        "motor-browser-webpage",
        "Industrial Motor",
        "浏览器无法打开网页",
        None,
    ),
    EvaluationCase(
        "sensor-windows-password",
        "Temperature Sensor",
        "员工忘记 Windows 登录密码",
        None,
    ),
    EvaluationCase(
        "vision-printer-paper-jam",
        "Vision Controller",
        "打印机卡纸",
        None,
    ),
)


def run_evaluation(chroma_path: Path) -> EvaluationReport:
    embeddings = DeterministicEvaluationEmbeddings()
    store = ChromaVectorStore(chroma_path, "rag_evaluation")
    try:
        indexer = KnowledgeIndexer(
            DocumentLoader(PROJECT_ROOT / "knowledge"),
            embeddings,
            store,
            chunk_size=600,
            overlap=80,
        )
        stats = indexer.index(rebuild=True)
        if stats.errors:
            raise RuntimeError(f"evaluation indexing failed: {stats.errors} errors")
        retrieval = RetrievalService(
            embeddings,
            store,
            top_k=3,
            max_distance=EVALUATION_THRESHOLD,
        )
        results: list[EvaluationCaseResult] = []
        for case in CASES:
            raw = store.query(
                embeddings.embed_query(case.query),
                top_k=3,
                equipment_type=normalize_equipment_type(case.device_type),
            )
            retrieved = retrieval.retrieve(case.device_type, case.query)
            source = retrieved[0].source if retrieved else None
            distance = retrieved[0].distance if retrieved else None
            nearest_distance = raw[0].distance if raw else None
            results.append(
                EvaluationCaseResult(
                    name=case.name,
                    source=source,
                    distance=distance,
                    nearest_distance=nearest_distance,
                    passed=source == case.expected_source,
                )
            )
        return EvaluationReport(results)
    finally:
        store.close()


class RecordingQueryableVectorStore:
    def __init__(self, store: ChromaVectorStore) -> None:
        self.store = store
        self.last_candidates: list[RetrievedChunk] = []

    def query(
        self,
        embedding: list[float],
        *,
        top_k: int,
        equipment_type: str | None,
    ) -> list[RetrievedChunk]:
        self.last_candidates = self.store.query(
            embedding,
            top_k=top_k,
            equipment_type=equipment_type,
        )
        return self.last_candidates


@dataclass(frozen=True)
class RealDistanceStatistics:
    positive_min: float
    positive_max: float
    positive_mean: float
    negative_min: float
    negative_max: float
    negative_mean: float
    max_positive_distance: float
    min_negative_distance: float


def real_distance_statistics(
    results: list[EvaluationCaseResult],
) -> RealDistanceStatistics:
    if len(results) != len(REAL_CASES):
        raise ValueError("real evaluation result count does not match measurement cases")
    positive_distances: list[float] = []
    negative_distances: list[float] = []
    for case, result in zip(REAL_CASES, results, strict=True):
        if result.nearest_distance is None:
            raise MissingRealEvaluationDistanceError(case.name)
        if case.expected_source is None:
            negative_distances.append(result.nearest_distance)
        else:
            positive_distances.append(result.nearest_distance)
    return RealDistanceStatistics(
        positive_min=min(positive_distances),
        positive_max=max(positive_distances),
        positive_mean=fmean(positive_distances),
        negative_min=min(negative_distances),
        negative_max=max(negative_distances),
        negative_mean=fmean(negative_distances),
        max_positive_distance=max(positive_distances),
        min_negative_distance=min(negative_distances),
    )


def run_real_evaluation(settings: RAGSettings) -> EvaluationReport:
    if not settings.chroma_path.exists():
        raise KnowledgeIndexNotFoundError

    store: ChromaVectorStore | None = None
    try:
        try:
            store = ChromaVectorStore.open_existing(
                settings.chroma_path, settings.collection_name
            )
        except NotFoundError as exc:
            raise KnowledgeIndexNotFoundError from exc
        collection_count = store.count()
        if collection_count == 0:
            raise KnowledgeIndexNotFoundError

        embeddings = E5EmbeddingProvider(settings.embedding_model)
        recording_store = RecordingQueryableVectorStore(store)
        retrieval = RetrievalService(
            embeddings,
            recording_store,
            top_k=settings.top_k,
            max_distance=settings.max_distance,
        )
        print(
            "mode=real "
            f"embedding_model={settings.embedding_model} "
            f"vector_store_path={settings.chroma_path} "
            f"collection={settings.collection_name} "
            f"collection_count={collection_count} "
            f"top_k={settings.top_k} "
            f"max_distance={settings.max_distance}"
        )
        results: list[EvaluationCaseResult] = []
        for case in REAL_CASES:
            retrieved = retrieval.retrieve(case.device_type, case.query)
            source = retrieved[0].source if retrieved else None
            distance = retrieved[0].distance if retrieved else None
            nearest_distance = (
                recording_store.last_candidates[0].distance
                if recording_store.last_candidates
                else None
            )
            results.append(
                EvaluationCaseResult(
                    name=case.name,
                    source=source,
                    distance=distance,
                    nearest_distance=nearest_distance,
                    passed=source == case.expected_source,
                )
            )
        return EvaluationReport(results)
    finally:
        if store is not None:
            store.close()


def _print_missing_index_message() -> None:
    print("Knowledge index not found.")
    print("Run:")
    print("python -m scripts.index_knowledge --rebuild")


def _print_real_report(report: EvaluationReport) -> None:
    for case, result in zip(REAL_CASES, report.cases, strict=True):
        print(
            f"{result.name}: {'PASS' if result.passed else 'FAIL'} "
            f"expected_source={case.expected_source or 'none'} "
            f"returned_source={result.source or 'none'} "
            f"accepted_distance={result.distance if result.distance is not None else 'rejected'} "
            f"nearest_distance={result.nearest_distance} "
            f"decision={'accepted' if result.distance is not None else 'rejected'}"
        )
    statistics = real_distance_statistics(report.cases)
    print(
        f"threshold={report.cases and 'configured'} "
        f"passed={report.passed}/{len(report.cases)}"
    )
    print(
        "positive_nearest_distance "
        f"min={statistics.positive_min} "
        f"max={statistics.positive_max} "
        f"mean={statistics.positive_mean}"
    )
    print(
        "negative_nearest_distance "
        f"min={statistics.negative_min} "
        f"max={statistics.negative_max} "
        f"mean={statistics.negative_mean}"
    )
    print(f"max_positive_distance={statistics.max_positive_distance}")
    print(f"min_negative_distance={statistics.min_negative_distance}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate DevicePilot RAG retrieval")
    parser.add_argument(
        "--real",
        action="store_true",
        help="evaluate the configured persisted production RAG index",
    )
    args = parser.parse_args(argv)
    if args.real:
        try:
            settings = RAGSettings.from_environment()
        except ValueError as exc:
            print(f"RAG configuration error: {exc}")
            return 1
        try:
            report = run_real_evaluation(settings)
        except KnowledgeIndexNotFoundError:
            _print_missing_index_message()
            return 1
        try:
            _print_real_report(report)
        except MissingRealEvaluationDistanceError as exc:
            print(f"Real evaluation failed: nearest distance unavailable for {exc}")
            return 1
        return 0 if report.passed == len(report.cases) else 1

    with TemporaryDirectory(prefix="devicepilot-rag-eval-") as directory:
        report = run_evaluation(Path(directory))
    for case in report.cases:
        print(
            f"{case.name}: {'PASS' if case.passed else 'FAIL'} "
            f"source={case.source or 'none'} "
            f"distance={case.distance if case.distance is not None else 'rejected'} "
            f"nearest={case.nearest_distance}"
        )
    print(
        f"threshold={EVALUATION_THRESHOLD} passed={report.passed}/{len(report.cases)}"
    )
    return 0 if report.passed == len(report.cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
