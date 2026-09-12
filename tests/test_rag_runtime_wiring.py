import logging
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.services.diagnosis as diagnosis_module
from app import schemas
from app.database import create_database, create_session_factory
from app.main import create_app
from app.rag.types import RetrievedChunk


DIAGNOSIS_RESULT = schemas.DiagnosisResult(
    risk_level="HIGH",
    summary="需要停机检查。",
    possible_causes=["可能存在机械摩擦"],
    recommended_checks=["隔离能源后检查轴承"],
    recommended_actions=["确认原因前保持停机"],
)


class FakeDiagnosisProvider:
    def diagnose(
        self,
        _device: Any,
        _description: str,
        _retrieved_chunks: list[RetrievedChunk] | None = None,
    ) -> schemas.DiagnosisResult:
        return DIAGNOSIS_RESULT


class DeterministicRetrieval:
    def __init__(
        self,
        chunks: list[RetrievedChunk] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.chunks = chunks or []
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def retrieve(self, device_type: str, description: str) -> list[RetrievedChunk]:
        self.calls.append((device_type, description))
        if self.error is not None:
            raise self.error
        return self.chunks


def _rag_settings(*, enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        enabled=enabled,
        chroma_path=PurePosixPath("/data/chroma"),
        collection_name="devicepilot_knowledge",
        embedding_model="intfloat/multilingual-e5-small",
        top_k=3,
        max_distance=0.143,
    )


def _client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    rag_enabled: bool,
    retrieval: DeterministicRetrieval,
) -> TestClient:
    monkeypatch.setattr(
        diagnosis_module.LLMSettings,
        "from_environment",
        classmethod(
            lambda _cls: SimpleNamespace(
                model="test/provider",
                api_key="not-a-real-key",
                api_base=None,
                timeout_seconds=1.0,
            )
        ),
    )
    monkeypatch.setattr(
        diagnosis_module.RAGSettings,
        "from_environment",
        classmethod(lambda _cls: _rag_settings(enabled=rag_enabled)),
    )
    monkeypatch.setattr(
        diagnosis_module,
        "LiteLLMDiagnosisProvider",
        lambda **_kwargs: FakeDiagnosisProvider(),
    )

    def retrieval_factory(
        chroma_path: str,
        collection_name: str,
        embedding_model: str,
        top_k: int,
        max_distance: float,
    ) -> DeterministicRetrieval:
        assert chroma_path == "/data/chroma"
        assert collection_name == "devicepilot_knowledge"
        assert embedding_model == "intfloat/multilingual-e5-small"
        assert top_k == 3
        assert max_distance == 0.143
        return retrieval

    monkeypatch.setattr(
        diagnosis_module, "_default_retrieval_service", retrieval_factory
    )
    engine = create_database(f"sqlite:///{tmp_path / 'runtime-wiring.db'}")
    session_factory = create_session_factory(engine)
    return TestClient(create_app(session_factory=session_factory, engine=engine))


def _create_pump(client: TestClient) -> int:
    response = client.post(
        "/devices",
        json={
            "name": "Cooling Pump",
            "device_type": "Centrifugal Pump",
            "serial_number": "PUMP-RUNTIME-001",
            "location": "Plant room",
            "status": "active",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _diagnose(client: TestClient, device_id: int):
    return client.post(
        f"/devices/{device_id}/diagnose",
        json={"description": "设备温度升高并伴随金属摩擦声"},
    )


def test_create_app_enabled_rag_returns_retrieval_metadata_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    retrieval = DeterministicRetrieval(
        [
            RetrievedChunk(
                content="泵轴承摩擦会导致温升。",
                source="centrifugal-pump.md",
                title="离心泵故障排查",
                equipment_type="centrifugal pump",
                chunk_index=0,
                distance=0.1,
            )
        ]
    )

    with _client(
        tmp_path, monkeypatch, rag_enabled=True, retrieval=retrieval
    ) as client:
        response = _diagnose(client, _create_pump(client))

    assert response.status_code == 200
    assert response.json()["sources"] == [
        {"document": "centrifugal-pump.md", "chunk_index": 0}
    ]
    assert retrieval.calls == [
        ("Centrifugal Pump", "设备温度升高并伴随金属摩擦声")
    ]


def test_create_app_enabled_rag_omits_sources_when_retrieval_rejects_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    retrieval = DeterministicRetrieval()

    with _client(
        tmp_path, monkeypatch, rag_enabled=True, retrieval=retrieval
    ) as client:
        response = _diagnose(client, _create_pump(client))

    assert response.status_code == 200
    assert "sources" not in response.json()


def test_create_app_retrieval_failure_degrades_without_leaking_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    retrieval = DeterministicRetrieval(
        error=RuntimeError("secret vector path and internal details")
    )
    caplog.set_level(logging.WARNING, logger="app.services.diagnosis")

    with _client(
        tmp_path, monkeypatch, rag_enabled=True, retrieval=retrieval
    ) as client:
        response = _diagnose(client, _create_pump(client))

    assert response.status_code == 200
    assert "sources" not in response.json()
    assert "secret" not in response.text.casefold()
    assert "retrieval_fallback_reason=RuntimeError" in caplog.text
    assert "secret vector path" not in caplog.text


def test_create_app_disabled_rag_does_not_call_retrieval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    retrieval = DeterministicRetrieval(
        error=AssertionError("disabled RAG must not call retrieval")
    )

    with _client(
        tmp_path, monkeypatch, rag_enabled=False, retrieval=retrieval
    ) as client:
        response = _diagnose(client, _create_pump(client))

    assert response.status_code == 200
    assert "sources" not in response.json()
    assert retrieval.calls == []


def test_runtime_wiring_logs_safe_rag_state_without_sensitive_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    retrieval = DeterministicRetrieval()
    caplog.set_level(logging.INFO, logger="app.services.diagnosis")

    with _client(
        tmp_path, monkeypatch, rag_enabled=True, retrieval=retrieval
    ) as client:
        response = _diagnose(client, _create_pump(client))

    assert response.status_code == 200
    log_text = caplog.text
    assert "rag_enabled=true" in log_text
    assert "retrieval_service=configured" in log_text
    assert "collection=devicepilot_knowledge" in log_text
    assert "retrieval_result_count=0" in log_text
    assert "设备温度升高" not in log_text
    assert "not-a-real-key" not in log_text
