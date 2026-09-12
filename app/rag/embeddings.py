from collections.abc import Callable, Sequence
from typing import Any, Protocol


class EmbeddingProvider(Protocol):
    def embed_query(self, text: str) -> list[float]: ...

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...


ModelFactory = Callable[[str], Any]


def _default_model_factory(model_name: str) -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def _as_vectors(value: Any) -> list[list[float]]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [[float(component) for component in row] for row in value]


class E5EmbeddingProvider:
    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-small",
        *,
        model_factory: ModelFactory | None = None,
    ) -> None:
        self.model_name = model_name
        self.model_factory = model_factory or _default_model_factory
        self._model: Any | None = None

    def _get_model(self) -> Any:
        if self._model is None:
            self._model = self.model_factory(self.model_name)
        return self._model

    def embed_query(self, text: str) -> list[float]:
        return self._encode([f"query: {text}"])[0]

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._encode([f"passage: {text}" for text in texts])

    def _encode(self, texts: list[str]) -> list[list[float]]:
        encoded = self._get_model().encode(texts, normalize_embeddings=True)
        return _as_vectors(encoded)
