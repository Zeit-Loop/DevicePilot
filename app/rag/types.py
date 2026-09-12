from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeDocument:
    source: str
    title: str
    equipment_type: str
    content: str


@dataclass(frozen=True)
class KnowledgeChunk:
    id: str
    source: str
    title: str
    equipment_type: str
    chunk_index: int
    content: str


@dataclass(frozen=True)
class RetrievedChunk:
    content: str
    source: str
    title: str
    equipment_type: str
    chunk_index: int
    distance: float
