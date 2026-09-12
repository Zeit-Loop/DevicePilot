from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.database import Base, create_database, create_session_factory
from app.mcp.services import (
    DatabaseReadFailed,
    DeviceNotFound,
    DevicePilotReadService,
    RagDisabled,
    RagUnavailable,
)
from app.rag.types import RetrievedChunk


def make_service_database(tmp_path):
    engine = create_database(f"sqlite:///{tmp_path / 'mcp-services.db'}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        device = models.Device(
            name="Drive Motor",
            device_type="Industrial Motor",
            serial_number="MCP-MOTOR-001",
            location="Line A",
            status="maintenance",
        )
        session.add(device)
        session.commit()
        session.refresh(device)
        device_id = device.id
    return engine, factory, device_id


def test_get_device_returns_current_model_fields_and_missing_is_domain_error(tmp_path) -> None:
    _engine, factory, device_id = make_service_database(tmp_path)
    service = DevicePilotReadService(factory, rag_enabled=False)

    result = service.get_device(device_id)

    assert result.model_dump(mode="json") == {
        "id": device_id,
        "name": "Drive Motor",
        "device_type": "Industrial Motor",
        "serial_number": "MCP-MOTOR-001",
        "location": "Line A",
        "status": "maintenance",
        "created_at": result.created_at.isoformat(),
        "updated_at": result.updated_at.isoformat(),
    }
    with pytest.raises(DeviceNotFound, match="^DEVICE_NOT_FOUND$"):
        service.get_device(device_id + 999)


def test_database_failures_are_sanitized_and_session_is_closed() -> None:
    closed: list[bool] = []

    class FailingSession:
        def get(self, *_args):
            raise RuntimeError("secret SQL and C:/private/devicepilot.db")

        def close(self) -> None:
            closed.append(True)

    service = DevicePilotReadService(lambda: FailingSession(), rag_enabled=False)

    with pytest.raises(DatabaseReadFailed, match="^DATABASE_READ_FAILED$") as caught:
        service.get_device(1)

    assert closed == [True]
    assert "secret" not in str(caught.value).casefold()
    assert "C:/" not in str(caught.value)


def test_recent_faults_are_latest_five_and_descriptions_are_truncated(tmp_path) -> None:
    engine, factory, device_id = make_service_database(tmp_path)
    base = datetime(2026, 9, 1, tzinfo=timezone.utc)
    with factory() as session:
        for index in range(7):
            session.add(
                models.Fault(
                    device_id=device_id,
                    title=f"Fault {index}",
                    description=str(index) * 600,
                    severity="high",
                    status="open",
                    created_at=base + timedelta(minutes=index // 2),
                )
            )
        session.commit()

    statements: list[str] = []

    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.strip().split(None, 1)[0].upper())

    event.listen(engine, "before_cursor_execute", record)
    try:
        result = DevicePilotReadService(factory, rag_enabled=False).get_recent_faults(
            device_id, limit=5
        )
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert [fault.title for fault in result.faults] == [
        "Fault 6",
        "Fault 5",
        "Fault 4",
        "Fault 3",
        "Fault 2",
    ]
    assert all(len(fault.description) == 500 for fault in result.faults)
    assert statements == ["SELECT", "SELECT"]


def test_empty_recent_faults_is_a_success(tmp_path) -> None:
    _engine, factory, device_id = make_service_database(tmp_path)

    result = DevicePilotReadService(factory, rag_enabled=False).get_recent_faults(
        device_id, limit=5
    )

    assert result.device_id == device_id
    assert result.faults == []


def test_search_closes_database_session_before_retrieval_and_caps_safe_matches(tmp_path) -> None:
    engine, base_factory, device_id = make_service_database(tmp_path)
    close_events: list[bool] = []

    class RecordingSession(Session):
        def close(self) -> None:
            close_events.append(True)
            super().close()

    factory = sessionmaker(
        bind=engine, class_=RecordingSession, autoflush=False, expire_on_commit=False
    )

    class Retrieval:
        def retrieve(self, device_type: str, query: str) -> list[RetrievedChunk]:
            assert close_events == [True]
            assert (device_type, query) == ("Industrial Motor", "bearing heat")
            return [
                RetrievedChunk(
                    content=f"content {index}",
                    source=("../private.md" if index == 0 else f"manual-{index}.md"),
                    title="Existing title is deliberately not exposed",
                    equipment_type="industrial motor",
                    chunk_index=index,
                    distance=0.1,
                )
                for index in range(5)
            ]

    service = DevicePilotReadService(
        factory, rag_enabled=True, retrieval_factory=lambda: Retrieval()
    )

    result = service.search_knowledge(device_id, "bearing heat")

    assert len(result.matches) == 3
    assert [match.document for match in result.matches] == [
        "manual-1.md",
        "manual-2.md",
        "manual-3.md",
    ]
    assert result.matches[0].model_dump() == {
        "document": "manual-1.md",
        "chunk_index": 1,
        "content": "content 1",
        "equipment_type": "industrial motor",
    }
    assert "title" not in result.matches[0].model_dump()
    assert "distance" not in result.matches[0].model_dump()


def test_search_empty_is_success_and_rag_states_are_distinct(tmp_path) -> None:
    _engine, factory, device_id = make_service_database(tmp_path)

    class EmptyRetrieval:
        def retrieve(self, _device_type: str, _query: str) -> list[RetrievedChunk]:
            return []

    empty = DevicePilotReadService(
        factory, rag_enabled=True, retrieval_factory=lambda: EmptyRetrieval()
    ).search_knowledge(device_id, "irrelevant printer query")
    assert empty.matches == []

    with pytest.raises(RagDisabled, match="^RAG_DISABLED$"):
        DevicePilotReadService(factory, rag_enabled=False).search_knowledge(
            device_id, "bearing"
        )

    unavailable = DevicePilotReadService(
        factory,
        rag_enabled=True,
        retrieval_factory=lambda: (_ for _ in ()).throw(
            RuntimeError("secret C:/data/chroma")
        ),
    )
    with pytest.raises(RagUnavailable, match="^RAG_UNAVAILABLE$") as caught:
        unavailable.search_knowledge(device_id, "bearing")
    assert "secret" not in str(caught.value).casefold()
    assert "C:/" not in str(caught.value)


def test_all_three_service_operations_issue_only_select_statements(tmp_path) -> None:
    engine, factory, device_id = make_service_database(tmp_path)
    with factory() as session:
        session.add(
            models.Fault(
                device_id=device_id,
                title="Read-only proof",
                description="No write should occur while reading this fault.",
                severity="low",
                status="open",
            )
        )
        session.commit()

    class EmptyRetrieval:
        def retrieve(self, _device_type: str, _query: str) -> list[RetrievedChunk]:
            return []

    statements: list[str] = []

    def reject_dml(_conn, _cursor, statement, _parameters, _context, _many):
        operation = statement.lstrip().split(None, 1)[0].upper()
        statements.append(operation)
        if operation in {"INSERT", "UPDATE", "DELETE"}:
            raise AssertionError(f"unexpected DML operation: {operation}")

    service = DevicePilotReadService(
        factory, rag_enabled=True, retrieval_factory=lambda: EmptyRetrieval()
    )
    event.listen(engine, "before_cursor_execute", reject_dml)
    try:
        service.get_device(device_id)
        service.get_recent_faults(device_id, limit=5)
        service.search_knowledge(device_id, "bearing")
    finally:
        event.remove(engine, "before_cursor_execute", reject_dml)

    assert statements
    assert set(statements) == {"SELECT"}
