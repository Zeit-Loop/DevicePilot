from datetime import datetime, timezone
from importlib import import_module, util
from types import SimpleNamespace

import app.services.diagnosis as diagnosis_module
import pytest
from sqlalchemy import event, func, select

from app import models, schemas
from app.database import Base, create_database, create_session_factory
from app.rag.types import RetrievedChunk


def test_fault_history_routing_detects_only_explicit_history_semantics() -> None:
    needs_fault_history = getattr(diagnosis_module, "needs_fault_history", None)

    assert callable(needs_fault_history)
    assert needs_fault_history("最近电机又出现间歇性异响") is True
    assert needs_fault_history("The vibration is getting worse than yesterday") is True
    assert needs_fault_history("电机温度达到 95 摄氏度") is False
    assert needs_fault_history("Motor temperature is 95 C") is False
    assert needs_fault_history("The guard rubs against the housing") is False


def test_device_only_path_skips_optional_reads_and_calls_provider_once() -> None:
    spec = util.find_spec("app.services.diagnostic_agent")
    assert spec is not None
    agent_module = import_module("app.services.diagnostic_agent")

    class ForbiddenHistoryReader:
        def get_recent(self, _device_id: int, *, limit: int):
            raise AssertionError("history query must be skipped")

    class RecordingProvider:
        def __init__(self) -> None:
            self.calls = 0

        def diagnose(self, _device, _symptoms, _chunks=None, _faults=None):
            self.calls += 1
            return schemas.DiagnosisResult(
                risk_level="MEDIUM",
                summary="需要检查。",
                possible_causes=["可能存在机械磨损"],
                recommended_checks=["停机后检查"],
                recommended_actions=["确认原因前保持停机"],
            )

    provider = RecordingProvider()
    agent = agent_module.DiagnosticAgent(
        provider=provider,
        fault_history_reader=ForbiddenHistoryReader(),
        retrieval=None,
    )
    device = models.Device(
        id=7,
        name="Cooling Pump",
        device_type="Centrifugal Pump",
        serial_number="PUMP-007",
        location="Plant room",
        status="active",
    )

    state = agent.run(device, "Motor temperature is 95 C")

    assert state["need_fault_history"] is False
    assert state["use_rag"] is False
    assert state["history_status"] is agent_module.HistoryStatus.NOT_REQUESTED
    assert state["retrieval_status"] is agent_module.RetrievalStatus.NOT_REQUESTED
    assert provider.calls == 1
    assert state["diagnosis"].summary == "需要检查。"


def test_enabled_but_unavailable_rag_is_not_marked_not_requested() -> None:
    agent_module = import_module("app.services.diagnostic_agent")

    class Provider:
        def diagnose(self, _device, _symptoms, _chunks=None):
            return schemas.DiagnosisResult(
                risk_level="MEDIUM",
                summary="RAG 不可用，基于设备信息诊断。",
                possible_causes=["需要进一步检查"],
                recommended_checks=["检查当前设备"],
                recommended_actions=["保持安全隔离"],
            )

    agent = agent_module.DiagnosticAgent(
        provider=Provider(),
        fault_history_reader=object(),
        retrieval=None,
        retrieval_requested=True,
    )
    device = models.Device(
        id=8,
        name="Cooling Pump",
        device_type="Centrifugal Pump",
        serial_number="PUMP-008",
        location=None,
        status="active",
    )

    state = agent.run(device, "泵体温度达到 95 摄氏度")

    assert state["use_rag"] is False
    assert state["retrieval_status"] is agent_module.RetrievalStatus.UNAVAILABLE
    assert "knowledge_unavailable" in state["trace"]


def test_history_branch_loads_once_and_bounds_provider_context() -> None:
    agent_module = import_module("app.services.diagnostic_agent")

    class RecordingHistoryReader:
        def __init__(self) -> None:
            self.calls: list[tuple[int, int]] = []

        def get_recent(self, device_id: int, *, limit: int):
            self.calls.append((device_id, limit))
            return [
                agent_module.FaultContext(
                    title=f"Fault {index}",
                    description=str(index) * 600,
                    severity="high",
                    status="open",
                    created_at=datetime(2026, 8, index + 1, tzinfo=timezone.utc),
                )
                for index in range(6)
            ]

    class RecordingProvider:
        def __init__(self) -> None:
            self.faults = None

        def diagnose(self, _device, _symptoms, _chunks=None, faults=None):
            self.faults = faults
            return schemas.DiagnosisResult(
                risk_level="HIGH",
                summary="存在重复故障。",
                possible_causes=["历史故障可能相关"],
                recommended_checks=["比较历史记录"],
                recommended_actions=["安排现场检查"],
            )

    reader = RecordingHistoryReader()
    provider = RecordingProvider()
    agent = agent_module.DiagnosticAgent(
        provider=provider,
        fault_history_reader=reader,
        retrieval=None,
    )
    device = models.Device(
        id=9,
        name="Drive Motor",
        device_type="Industrial Motor",
        serial_number="MOTOR-009",
        location="Line A",
        status="maintenance",
    )

    state = agent.run(device, "最近电机又出现间歇性异响")

    assert reader.calls == [(9, 5)]
    assert state["history_status"] is agent_module.HistoryStatus.LOADED
    assert len(state["recent_faults"]) == 5
    assert provider.faults == list(state["recent_faults"])
    assert all(len(fault.description) == 500 for fault in provider.faults)


@pytest.mark.parametrize(
    ("reader_result", "expected_status", "expected_event"),
    [
        ([], "EMPTY", "fault_history_empty"),
        (RuntimeError("private database detail"), "UNAVAILABLE", "fault_history_unavailable"),
    ],
)
def test_history_empty_or_failure_has_distinct_status_and_still_diagnoses(
    reader_result, expected_status: str, expected_event: str
) -> None:
    agent_module = import_module("app.services.diagnostic_agent")

    class HistoryReader:
        def __init__(self) -> None:
            self.calls = 0

        def get_recent(self, _device_id: int, *, limit: int):
            self.calls += 1
            assert limit == 5
            if isinstance(reader_result, Exception):
                raise reader_result
            return reader_result

    class Provider:
        def __init__(self) -> None:
            self.calls = 0

        def diagnose(self, _device, _symptoms, _chunks=None, faults=None):
            self.calls += 1
            assert faults in (None, [])
            return schemas.DiagnosisResult(
                risk_level="MEDIUM",
                summary="历史信息不可用，基于当前症状诊断。",
                possible_causes=["需要进一步检查"],
                recommended_checks=["检查当前设备状态"],
                recommended_actions=["保持安全隔离"],
            )

    reader = HistoryReader()
    provider = Provider()
    agent = agent_module.DiagnosticAgent(
        provider=provider,
        fault_history_reader=reader,
        retrieval=None,
    )
    device = models.Device(
        id=11,
        name="Drive Motor",
        device_type="Industrial Motor",
        serial_number="MOTOR-011",
        location=None,
        status="active",
    )

    state = agent.run(device, "上次维修后再次出现异响")

    assert reader.calls == 1
    assert provider.calls == 1
    assert state["history_status"] is getattr(agent_module.HistoryStatus, expected_status)
    assert state["recent_faults"] == ()
    assert expected_event in state["trace"]


def test_rag_branch_runs_once_and_rebuilds_safe_sources() -> None:
    agent_module = import_module("app.services.diagnostic_agent")
    chunks = [
        RetrievedChunk(
            content="检查轴承温度。",
            source="industrial-motor.md",
            title="Motor guide",
            equipment_type="industrial motor",
            chunk_index=2,
            distance=0.1,
        ),
        RetrievedChunk(
            content="重复内容。",
            source="industrial-motor.md",
            title="Motor guide",
            equipment_type="industrial motor",
            chunk_index=2,
            distance=0.11,
        ),
        RetrievedChunk(
            content="不安全来源。",
            source="../private/manual.md",
            title="Private",
            equipment_type="industrial motor",
            chunk_index=0,
            distance=0.05,
        ),
    ]

    class ForbiddenHistoryReader:
        def get_recent(self, _device_id: int, *, limit: int):
            raise AssertionError("history query must be skipped")

    class Retrieval:
        def __init__(self) -> None:
            self.calls = []

        def retrieve(self, device_type: str, symptoms: str):
            self.calls.append((device_type, symptoms))
            return chunks

    class Provider:
        def __init__(self) -> None:
            self.calls = 0
            self.chunks = None

        def diagnose(self, _device, _symptoms, retrieved=None, _faults=None):
            self.calls += 1
            self.chunks = retrieved
            return schemas.DiagnosisResult(
                risk_level="HIGH",
                summary="需要检查轴承。",
                possible_causes=["轴承磨损"],
                recommended_checks=["检查轴承温度"],
                recommended_actions=["确认前保持停机"],
                sources=[
                    schemas.DiagnosisSource(
                        document="model-invented.md", chunk_index=99
                    )
                ],
            )

    retrieval = Retrieval()
    provider = Provider()
    agent = agent_module.DiagnosticAgent(
        provider=provider,
        fault_history_reader=ForbiddenHistoryReader(),
        retrieval=retrieval,
    )
    device = models.Device(
        id=13,
        name="Drive Motor",
        device_type="Industrial Motor",
        serial_number="MOTOR-013",
        location="Line B",
        status="active",
    )

    state = agent.run(device, "电机出现高温和研磨声")

    assert retrieval.calls == [("Industrial Motor", "电机出现高温和研磨声")]
    assert provider.calls == 1
    assert provider.chunks == chunks
    assert state["retrieval_status"] is agent_module.RetrievalStatus.LOADED
    assert state["diagnosis"].sources == [
        schemas.DiagnosisSource(document="industrial-motor.md", chunk_index=2)
    ]


@pytest.mark.parametrize(
    ("retrieval_result", "expected_status", "expected_event"),
    [
        ([], "EMPTY", "knowledge_empty"),
        (RuntimeError("private vector path"), "UNAVAILABLE", "knowledge_unavailable"),
    ],
)
def test_rag_empty_or_failure_has_distinct_status_and_still_diagnoses(
    retrieval_result, expected_status: str, expected_event: str
) -> None:
    agent_module = import_module("app.services.diagnostic_agent")

    class ForbiddenHistoryReader:
        def get_recent(self, _device_id: int, *, limit: int):
            raise AssertionError("history query must be skipped")

    class Retrieval:
        def __init__(self) -> None:
            self.calls = 0

        def retrieve(self, _device_type: str, _symptoms: str):
            self.calls += 1
            if isinstance(retrieval_result, Exception):
                raise retrieval_result
            return retrieval_result

    class Provider:
        def __init__(self) -> None:
            self.calls = 0

        def diagnose(self, _device, _symptoms, chunks=None, _faults=None):
            self.calls += 1
            assert chunks == []
            return schemas.DiagnosisResult(
                risk_level="MEDIUM",
                summary="基于当前设备信息诊断。",
                possible_causes=["需要进一步检查"],
                recommended_checks=["检查设备状态"],
                recommended_actions=["保持安全隔离"],
            )

    retrieval = Retrieval()
    provider = Provider()
    agent = agent_module.DiagnosticAgent(
        provider=provider,
        fault_history_reader=ForbiddenHistoryReader(),
        retrieval=retrieval,
    )
    device = models.Device(
        id=15,
        name="Cooling Pump",
        device_type="Centrifugal Pump",
        serial_number="PUMP-015",
        location=None,
        status="active",
    )

    state = agent.run(device, "泵体温度达到 95 摄氏度")

    assert retrieval.calls == 1
    assert provider.calls == 1
    assert state["retrieval_status"] is getattr(
        agent_module.RetrievalStatus, expected_status
    )
    assert state["retrieved_chunks"] == ()
    assert expected_event in state["trace"]
    assert state["diagnosis"].sources == []


def test_litellm_provider_adds_bounded_untrusted_history_in_one_call() -> None:
    agent_module = import_module("app.services.diagnostic_agent")
    calls = []
    result = schemas.DiagnosisResult(
        risk_level="HIGH",
        summary="存在重复故障。",
        possible_causes=["轴承可能反复磨损"],
        recommended_checks=["比较历史故障"],
        recommended_actions=["停机检查"],
    )

    def completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=result.model_dump_json()))]
        )

    provider = diagnosis_module.LiteLLMDiagnosisProvider(
        model="deepseek/deepseek-v4-flash",
        api_key="not-real",
        api_base="https://example.invalid",
        timeout_seconds=5,
        completion_fn=completion,
        supports_schema_fn=lambda **_kwargs: False,
    )
    device = models.Device(
        id=17,
        name="Drive Motor",
        device_type="Industrial Motor",
        serial_number="MOTOR-017",
        location="Line C",
        status="maintenance",
    )
    faults = [
        agent_module.FaultContext(
            title=f"Historical fault {index}",
            description=chr(65 + index) * 600,
            severity="high",
            status="open",
            created_at=datetime(2026, 8, index + 1, tzinfo=timezone.utc),
        )
        for index in range(6)
    ]

    provider.diagnose(device, "最近再次出现异响", [], faults)

    assert len(calls) == 1
    system_prompt = calls[0]["messages"][0]["content"].casefold()
    assert "recent fault history" in system_prompt
    assert "any untrusted section" in system_prompt
    prompt = calls[0]["messages"][1]["content"]
    assert "[UNTRUSTED_RECENT_FAULTS]" in prompt
    assert "Historical fault 4" in prompt
    assert "Historical fault 5" not in prompt
    assert "A" * 500 in prompt
    assert "A" * 501 not in prompt


def test_sqlalchemy_history_reader_returns_latest_five_without_writes(tmp_path) -> None:
    agent_module = import_module("app.services.diagnostic_agent")
    reader_type = getattr(agent_module, "SQLAlchemyFaultHistoryReader", None)
    assert reader_type is not None
    engine = create_database(f"sqlite:///{tmp_path / 'agent-history.db'}")
    Base.metadata.create_all(bind=engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        device = models.Device(
            name="Drive Motor",
            device_type="Industrial Motor",
            serial_number="MOTOR-HISTORY",
            location="Line D",
            status="maintenance",
        )
        session.add(device)
        session.flush()
        for index in range(7):
            session.add(
                models.Fault(
                    device_id=device.id,
                    title=f"Fault {index}",
                    description=str(index) * 600,
                    severity="high",
                    status="open",
                    created_at=datetime(2026, 8, index + 1, tzinfo=timezone.utc),
                )
            )
        session.commit()

        statements = []

        def record_statement(_conn, _cursor, statement, _parameters, _context, _many):
            statements.append(statement.strip().split(None, 1)[0].upper())

        event.listen(engine, "before_cursor_execute", record_statement)
        try:
            faults = reader_type(session).get_recent(device.id, limit=5)
        finally:
            event.remove(engine, "before_cursor_execute", record_statement)

        assert [fault.title for fault in faults] == [
            "Fault 6",
            "Fault 5",
            "Fault 4",
            "Fault 3",
            "Fault 2",
        ]
        assert all(len(fault.description) == 500 for fault in faults)
        assert statements == ["SELECT"]
        assert session.scalar(select(func.count(models.Fault.id))) == 7


def test_default_diagnose_device_uses_request_session_for_history(
    tmp_path, monkeypatch
) -> None:
    engine = create_database(f"sqlite:///{tmp_path / 'default-agent.db'}")
    Base.metadata.create_all(bind=engine)
    session_factory = create_session_factory(engine)
    captured_faults = []

    class Provider:
        def __init__(self, **_kwargs) -> None:
            pass

        def diagnose(self, _device, _symptoms, _chunks=None, faults=None):
            captured_faults.extend(faults or [])
            return schemas.DiagnosisResult(
                risk_level="HIGH",
                summary="重复故障需要检查。",
                possible_causes=["历史故障可能相关"],
                recommended_checks=["检查历史记录"],
                recommended_actions=["停机检查"],
            )

    monkeypatch.setattr(diagnosis_module, "LiteLLMDiagnosisProvider", Provider)
    monkeypatch.setattr(
        diagnosis_module.LLMSettings,
        "from_environment",
        classmethod(
            lambda _cls: SimpleNamespace(
                model="test/provider",
                api_key="not-real",
                api_base=None,
                timeout_seconds=1.0,
            )
        ),
    )
    monkeypatch.setattr(
        diagnosis_module.RAGSettings,
        "from_environment",
        classmethod(
            lambda _cls: SimpleNamespace(
                enabled=False,
                chroma_path="unused",
                collection_name="unused",
                embedding_model="unused",
                top_k=3,
                max_distance=0.143,
            )
        ),
    )
    with session_factory() as session:
        device = models.Device(
            name="Drive Motor",
            device_type="Industrial Motor",
            serial_number="MOTOR-DEFAULT",
            location="Line E",
            status="maintenance",
        )
        session.add(device)
        session.flush()
        session.add(
            models.Fault(
                device_id=device.id,
                title="Repeated vibration",
                description="Vibration returned after maintenance",
                severity="high",
                status="open",
            )
        )
        session.commit()

        result = diagnosis_module.diagnose_device(
            device, "维修后再次出现振动", session
        )

    assert result.summary == "重复故障需要检查。"
    assert [fault.title for fault in captured_faults] == ["Repeated vibration"]


def test_default_wiring_preserves_rag_request_when_settings_are_invalid(
    monkeypatch,
) -> None:
    captured_requested = []
    result = schemas.DiagnosisResult(
        risk_level="MEDIUM",
        summary="RAG 配置不可用，安全降级。",
        possible_causes=["需要进一步检查"],
        recommended_checks=["检查设备状态"],
        recommended_actions=["检查 RAG 配置"],
    )

    class Provider:
        def __init__(self, **_kwargs) -> None:
            pass

    class RecordingAgent:
        def __init__(
            self,
            *,
            provider,
            fault_history_reader,
            retrieval,
            retrieval_requested,
        ) -> None:
            captured_requested.append(retrieval_requested)
            assert retrieval is None

        def diagnose(self, _device, _symptoms):
            return result

    monkeypatch.setattr(diagnosis_module, "LiteLLMDiagnosisProvider", Provider)
    monkeypatch.setattr(
        diagnosis_module.LLMSettings,
        "from_environment",
        classmethod(
            lambda _cls: SimpleNamespace(
                model="test/provider",
                api_key="not-real",
                api_base=None,
                timeout_seconds=1.0,
            )
        ),
    )
    monkeypatch.setenv("RAG_ENABLED", "true")
    monkeypatch.setenv("RAG_COLLECTION_NAME", "")
    agent_module = import_module("app.services.diagnostic_agent")
    monkeypatch.setattr(agent_module, "DiagnosticAgent", RecordingAgent)
    device = models.Device(
        id=22,
        name="Cooling Pump",
        device_type="Centrifugal Pump",
        serial_number="PUMP-022",
        location=None,
        status="active",
    )

    actual = diagnosis_module.diagnose_device(device, "泵体高温", object())

    assert actual == result
    assert captured_requested == [True]


def test_history_and_rag_path_calls_each_capability_once() -> None:
    agent_module = import_module("app.services.diagnostic_agent")

    class HistoryReader:
        def __init__(self) -> None:
            self.calls = 0

        def get_recent(self, _device_id: int, *, limit: int):
            self.calls += 1
            return [
                agent_module.FaultContext(
                    title="Previous vibration",
                    description="Intermittent vibration",
                    severity="high",
                    status="open",
                    created_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
                )
            ]

    class Retrieval:
        def __init__(self) -> None:
            self.calls = 0

        def retrieve(self, _device_type: str, _symptoms: str):
            self.calls += 1
            return []

    class Provider:
        def __init__(self) -> None:
            self.calls = 0

        def diagnose(self, _device, _symptoms, _chunks=None, _faults=None):
            self.calls += 1
            return schemas.DiagnosisResult(
                risk_level="HIGH",
                summary="需要综合历史检查。",
                possible_causes=["重复机械问题"],
                recommended_checks=["比较历史故障"],
                recommended_actions=["停机检查"],
            )

    history = HistoryReader()
    retrieval = Retrieval()
    provider = Provider()
    agent = agent_module.DiagnosticAgent(
        provider=provider,
        fault_history_reader=history,
        retrieval=retrieval,
    )
    device = models.Device(
        id=21,
        name="Drive Motor",
        device_type="Industrial Motor",
        serial_number="MOTOR-021",
        location="Line F",
        status="maintenance",
    )

    state = agent.run(device, "最近又出现间歇性振动")

    assert history.calls == 1
    assert retrieval.calls == 1
    assert provider.calls == 1
    assert state["history_status"] is agent_module.HistoryStatus.LOADED
    assert state["retrieval_status"] is agent_module.RetrievalStatus.EMPTY


def test_compiled_graph_is_acyclic_and_has_no_checkpointer() -> None:
    agent_module = import_module("app.services.diagnostic_agent")
    agent = agent_module.DiagnosticAgent(
        provider=object(), fault_history_reader=object(), retrieval=None
    )
    graph = agent.graph.get_graph()
    adjacency = {node: [] for node in graph.nodes}
    for edge in graph.edges:
        adjacency[edge.source].append(edge.target)

    visiting = set()
    visited = set()

    def visit(node: str) -> None:
        assert node not in visiting, f"graph cycle reaches {node}"
        if node in visited:
            return
        visiting.add(node)
        for target in adjacency[node]:
            visit(target)
        visiting.remove(node)
        visited.add(node)

    visit("__start__")

    assert visited == set(graph.nodes)
    assert agent.graph.checkpointer is None
