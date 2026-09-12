from collections.abc import Callable
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.mcp.schemas import (
    DeviceDTO,
    FaultHistoryItemDTO,
    KnowledgeMatchDTO,
    KnowledgeSearchResult,
    RecentFaultsResult,
)
from app.rag.sources import safe_source_document
from app.rag.types import RetrievedChunk


class ReadServiceError(Exception):
    code = "READ_SERVICE_ERROR"

    def __init__(self) -> None:
        super().__init__(self.code)


class DeviceNotFound(ReadServiceError):
    code = "DEVICE_NOT_FOUND"


class RagDisabled(ReadServiceError):
    code = "RAG_DISABLED"


class RagUnavailable(ReadServiceError):
    code = "RAG_UNAVAILABLE"


class DatabaseReadFailed(ReadServiceError):
    code = "DATABASE_READ_FAILED"


class RetrievalProvider(Protocol):
    def retrieve(self, device_type: str, query: str) -> list[RetrievedChunk]: ...


SessionFactory = Callable[[], Session]
RetrievalFactory = Callable[[], RetrievalProvider]


class DevicePilotReadService:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        rag_enabled: bool,
        retrieval_factory: RetrievalFactory | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._rag_enabled = rag_enabled
        self._retrieval_factory = retrieval_factory
        self._retrieval: RetrievalProvider | None = None

    def get_device(self, device_id: int) -> DeviceDTO:
        return self._read_device(device_id)

    def get_recent_faults(self, device_id: int, *, limit: int) -> RecentFaultsResult:
        session = self._open_session()
        try:
            if session.get(models.Device, device_id) is None:
                raise DeviceNotFound()
            statement = (
                select(models.Fault)
                .where(models.Fault.device_id == device_id)
                .order_by(models.Fault.created_at.desc(), models.Fault.id.desc())
                .limit(limit)
            )
            faults = session.scalars(statement).all()
            return RecentFaultsResult(
                device_id=device_id,
                faults=[
                    FaultHistoryItemDTO(
                        id=fault.id,
                        device_id=fault.device_id,
                        title=fault.title,
                        description=fault.description[:500],
                        severity=fault.severity,
                        status=fault.status,
                        created_at=fault.created_at,
                    )
                    for fault in faults
                ],
            )
        except DeviceNotFound:
            raise
        except Exception as exc:
            raise DatabaseReadFailed() from exc
        finally:
            session.close()

    def search_knowledge(self, device_id: int, query: str) -> KnowledgeSearchResult:
        device = self._read_device(device_id)
        if not self._rag_enabled:
            raise RagDisabled()
        retrieval = self._get_retrieval()
        try:
            chunks = retrieval.retrieve(device.device_type, query)
        except Exception as exc:
            raise RagUnavailable() from exc

        matches: list[KnowledgeMatchDTO] = []
        for chunk in chunks:
            document = safe_source_document(chunk.source)
            if document is None:
                continue
            matches.append(
                KnowledgeMatchDTO(
                    document=document,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    equipment_type=chunk.equipment_type,
                )
            )
            if len(matches) == 3:
                break
        return KnowledgeSearchResult(device_id=device_id, matches=matches)

    def _read_device(self, device_id: int) -> DeviceDTO:
        session = self._open_session()
        try:
            device = session.get(models.Device, device_id)
            if device is None:
                raise DeviceNotFound()
            return DeviceDTO(
                id=device.id,
                name=device.name,
                device_type=device.device_type,
                serial_number=device.serial_number,
                location=device.location,
                status=device.status,
                created_at=device.created_at,
                updated_at=device.updated_at,
            )
        except DeviceNotFound:
            raise
        except Exception as exc:
            raise DatabaseReadFailed() from exc
        finally:
            session.close()

    def _open_session(self) -> Session:
        try:
            return self._session_factory()
        except Exception as exc:
            raise DatabaseReadFailed() from exc

    def _get_retrieval(self) -> RetrievalProvider:
        if self._retrieval is not None:
            return self._retrieval
        if self._retrieval_factory is None:
            raise RagUnavailable()
        try:
            self._retrieval = self._retrieval_factory()
        except Exception as exc:
            raise RagUnavailable() from exc
        return self._retrieval
