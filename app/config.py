import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_URL = f"sqlite:///{(PROJECT_ROOT / 'data' / 'devicepilot.db').as_posix()}"
DEFAULT_KNOWLEDGE_PATH = PROJECT_ROOT / "knowledge"
DEFAULT_CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"
DEFAULT_RAG_EMBEDDING_MODEL = "intfloat/multilingual-e5-small"


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


def _non_negative_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a non-negative integer") from exc
    if value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _cosine_distance(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be between 0 and 2") from exc
    if not 0 <= value <= 2:
        raise ValueError(f"{name} must be between 0 and 2")
    return value


def _boolean(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


@dataclass(frozen=True)
class Settings:
    database_url: str
    cors_origins: tuple[str, ...]
    diagnosis_rate_limit_per_minute: int
    trust_proxy_headers: bool
    production: bool
    auto_seed_demo: bool

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv()
        app_environment = os.getenv("APP_ENV", "development").strip()
        if app_environment not in {"development", "production"}:
            raise ValueError("APP_ENV must be development or production")
        origins = tuple(
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "").split(",")
            if origin.strip()
        )
        return cls(
            database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL).strip()
            or DEFAULT_DATABASE_URL,
            cors_origins=origins,
            diagnosis_rate_limit_per_minute=_positive_int(
                "DIAGNOSIS_RATE_LIMIT_PER_MINUTE", 5
            ),
            trust_proxy_headers=_boolean("TRUST_PROXY_HEADERS"),
            production=app_environment == "production",
            auto_seed_demo=_boolean("AUTO_SEED_DEMO", default=False),
        )


@dataclass(frozen=True)
class LLMSettings:
    model: str
    api_key: str | None
    api_base: str | None
    timeout_seconds: float

    @classmethod
    def from_environment(cls) -> "LLMSettings":
        load_dotenv()
        api_key = os.getenv("LLM_API_KEY", "").strip()
        api_base = os.getenv("LLM_API_BASE", "").strip()
        return cls(
            model=os.getenv("LLM_MODEL", "").strip(),
            api_key=api_key or None,
            api_base=api_base or None,
            timeout_seconds=_positive_float("LLM_TIMEOUT_SECONDS", 20.0),
        )


@dataclass(frozen=True)
class RAGSettings:
    enabled: bool
    knowledge_path: Path
    chroma_path: Path
    embedding_model: str
    collection_name: str
    top_k: int
    max_distance: float
    chunk_size: int
    chunk_overlap: int
    max_file_bytes: int

    @classmethod
    def enabled_from_environment(cls) -> bool:
        load_dotenv()
        return _boolean("RAG_ENABLED")

    @classmethod
    def from_environment(cls) -> "RAGSettings":
        load_dotenv()
        chunk_size = _positive_int("RAG_CHUNK_SIZE", 600)
        chunk_overlap = _non_negative_int("RAG_CHUNK_OVERLAP", 80)
        if chunk_overlap >= chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE")
        collection_name = os.getenv(
            "RAG_COLLECTION_NAME", "devicepilot_knowledge"
        ).strip()
        if not collection_name:
            raise ValueError("RAG_COLLECTION_NAME must not be empty")
        embedding_model = os.getenv(
            "RAG_EMBEDDING_MODEL", DEFAULT_RAG_EMBEDDING_MODEL
        ).strip()
        if not embedding_model:
            raise ValueError("RAG_EMBEDDING_MODEL must not be empty")
        vector_store_path = os.getenv("RAG_VECTOR_STORE_PATH", "").strip()
        chroma_path = vector_store_path or os.getenv("RAG_CHROMA_PATH", "").strip()
        return cls(
            enabled=_boolean("RAG_ENABLED"),
            knowledge_path=Path(
                os.getenv("RAG_KNOWLEDGE_PATH", str(DEFAULT_KNOWLEDGE_PATH)).strip()
                or DEFAULT_KNOWLEDGE_PATH
            ),
            chroma_path=Path(chroma_path or DEFAULT_CHROMA_PATH),
            embedding_model=embedding_model,
            collection_name=collection_name,
            top_k=_positive_int("RAG_TOP_K", 3),
            max_distance=_cosine_distance("RAG_MAX_DISTANCE", 0.143),
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            max_file_bytes=_positive_int("RAG_MAX_FILE_BYTES", 1_000_000),
        )
