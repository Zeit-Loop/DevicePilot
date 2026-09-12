import hashlib
import re
import unicodedata

from app.rag.types import KnowledgeChunk, KnowledgeDocument


_SEPARATORS = re.compile(r"[\s_\-/]+", re.UNICODE)


def normalize_equipment_type(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return _SEPARATORS.sub(" ", normalized)


def chunk_document(
    document: KnowledgeDocument, *, chunk_size: int, overlap: int
) -> list[KnowledgeChunk]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    content = document.content.strip()
    if not content:
        return []
    equipment_type = normalize_equipment_type(document.equipment_type)
    step = chunk_size - overlap
    chunks: list[KnowledgeChunk] = []
    for chunk_index, start in enumerate(range(0, len(content), step)):
        text = content[start : start + chunk_size]
        if not text:
            break
        identity = "::".join(
            (document.source, equipment_type, str(chunk_index), text)
        )
        chunks.append(
            KnowledgeChunk(
                id=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                source=document.source,
                title=document.title,
                equipment_type=equipment_type,
                chunk_index=chunk_index,
                content=text,
            )
        )
        if start + chunk_size >= len(content):
            break
    return chunks
