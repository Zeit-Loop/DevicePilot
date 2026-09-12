import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.rag.types import RetrievedChunk
from app.services.diagnosis import diagnosis_sources, needs_fault_history


diagnosis_logger = logging.getLogger("app.services.diagnosis")


class HistoryStatus(str, Enum):
    NOT_REQUESTED = "not_requested"
    EMPTY = "empty"
    LOADED = "loaded"
    UNAVAILABLE = "unavailable"


class RetrievalStatus(str, Enum):
    NOT_REQUESTED = "not_requested"
    EMPTY = "empty"
    LOADED = "loaded"
    UNAVAILABLE = "unavailable"


class DiagnosisWorkflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeviceContext:
    name: str
    device_type: str
    serial_number: str
    location: str | None
    status: str


@dataclass(frozen=True)
class FaultContext:
    title: str
    description: str
    severity: str
    status: str
    created_at: datetime


class FaultHistoryReader(Protocol):
    def get_recent(self, device_id: int, *, limit: int) -> list[FaultContext]: ...


class SQLAlchemyFaultHistoryReader:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_recent(self, device_id: int, *, limit: int) -> list[FaultContext]:
        statement = (
            select(models.Fault)
            .where(models.Fault.device_id == device_id)
            .order_by(models.Fault.created_at.desc(), models.Fault.id.desc())
            .limit(limit)
        )
        faults = self.session.scalars(statement).all()
        return [
            FaultContext(
                title=fault.title,
                description=fault.description[:500],
                severity=str(fault.severity),
                status=str(fault.status),
                created_at=fault.created_at,
            )
            for fault in faults
        ]


class DiagnosticState(TypedDict):
    device_id: int
    symptoms: str
    device_context: DeviceContext
    need_fault_history: bool
    use_rag: bool
    history_status: HistoryStatus
    retrieval_status: RetrievalStatus
    recent_faults: tuple[FaultContext, ...]
    retrieved_chunks: tuple[RetrievedChunk, ...]
    diagnosis: schemas.DiagnosisResult | None
    sources: tuple[schemas.DiagnosisSource, ...]
    trace: tuple[str, ...]


class DiagnosticAgent:
    def __init__(
        self,
        *,
        provider: Any,
        fault_history_reader: FaultHistoryReader,
        retrieval: Any | None,
        retrieval_requested: bool | None = None,
    ) -> None:
        self.provider = provider
        self.fault_history_reader = fault_history_reader
        self.retrieval = retrieval
        self.retrieval_requested = (
            retrieval is not None
            if retrieval_requested is None
            else retrieval_requested
        )
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(DiagnosticState)
        builder.add_node("plan_context", self._plan_context)
        builder.add_node("load_recent_faults", self._load_recent_faults)
        builder.add_node("retrieve_knowledge", self._retrieve_knowledge)
        builder.add_node("generate_diagnosis", self._generate_diagnosis)
        builder.add_node("finalize_result", self._finalize_result)
        builder.add_edge(START, "plan_context")
        builder.add_conditional_edges(
            "plan_context",
            self._after_plan,
            {
                "history": "load_recent_faults",
                "rag": "retrieve_knowledge",
                "diagnose": "generate_diagnosis",
            },
        )
        builder.add_conditional_edges(
            "load_recent_faults",
            self._after_history,
            {"rag": "retrieve_knowledge", "diagnose": "generate_diagnosis"},
        )
        builder.add_edge("retrieve_knowledge", "generate_diagnosis")
        builder.add_edge("generate_diagnosis", "finalize_result")
        builder.add_edge("finalize_result", END)
        return builder.compile()

    def _plan_context(self, state: DiagnosticState) -> dict[str, Any]:
        unavailable = self.retrieval_requested and self.retrieval is None
        trace = (*state["trace"], "context_planned")
        update: dict[str, Any] = {
            "need_fault_history": needs_fault_history(state["symptoms"]),
            "use_rag": self.retrieval_requested and self.retrieval is not None,
            "trace": trace,
        }
        if unavailable:
            update["retrieval_status"] = RetrievalStatus.UNAVAILABLE
            update["trace"] = (*trace, "knowledge_unavailable")
        return update

    @staticmethod
    def _after_plan(state: DiagnosticState) -> str:
        if state["need_fault_history"]:
            return "history"
        return "rag" if state["use_rag"] else "diagnose"

    @staticmethod
    def _after_history(state: DiagnosticState) -> str:
        return "rag" if state["use_rag"] else "diagnose"

    def _load_recent_faults(self, state: DiagnosticState) -> dict[str, Any]:
        try:
            faults = self.fault_history_reader.get_recent(
                state["device_id"], limit=5
            )
        except Exception:
            return {
                "recent_faults": (),
                "history_status": HistoryStatus.UNAVAILABLE,
                "trace": (*state["trace"], "fault_history_unavailable"),
            }
        bounded = tuple(
            FaultContext(
                title=fault.title,
                description=fault.description[:500],
                severity=fault.severity,
                status=fault.status,
                created_at=fault.created_at,
            )
            for fault in faults[:5]
        )
        status = HistoryStatus.LOADED if bounded else HistoryStatus.EMPTY
        event = "fault_history_loaded" if bounded else "fault_history_empty"
        return {
            "recent_faults": bounded,
            "history_status": status,
            "trace": (*state["trace"], event),
        }

    def _retrieve_knowledge(self, state: DiagnosticState) -> dict[str, Any]:
        try:
            chunks = tuple(
                self.retrieval.retrieve(
                    state["device_context"].device_type, state["symptoms"]
                )
            )
        except Exception as exc:
            diagnosis_logger.warning(
                "RAG retrieval failed retrieval_fallback_reason=%s; "
                "continuing without reference context",
                type(exc).__name__,
            )
            return {
                "retrieved_chunks": (),
                "retrieval_status": RetrievalStatus.UNAVAILABLE,
                "trace": (*state["trace"], "knowledge_unavailable"),
            }
        status = RetrievalStatus.LOADED if chunks else RetrievalStatus.EMPTY
        event = "knowledge_retrieved" if chunks else "knowledge_empty"
        accepted_sources = sorted(
            source.document for source in diagnosis_sources(chunks)
        )
        diagnosis_logger.info(
            "RAG retrieval completed retrieval_result_count=%d accepted_sources=%s",
            len(chunks),
            ",".join(accepted_sources) or "none",
        )
        return {
            "retrieved_chunks": chunks,
            "retrieval_status": status,
            "trace": (*state["trace"], event),
        }

    def _generate_diagnosis(self, state: DiagnosticState) -> dict[str, Any]:
        provider_args = (
            state["device_context"],
            state["symptoms"],
            list(state["retrieved_chunks"]),
        )
        if state["recent_faults"]:
            diagnosis = self.provider.diagnose(
                *provider_args, list(state["recent_faults"])
            )
        else:
            diagnosis = self.provider.diagnose(*provider_args)
        return {
            "diagnosis": diagnosis,
            "trace": (*state["trace"], "diagnosis_generated"),
        }

    @staticmethod
    def _finalize_result(state: DiagnosticState) -> dict[str, Any]:
        if state["diagnosis"] is None:
            raise DiagnosisWorkflowError("diagnosis result is missing")
        sources = diagnosis_sources(state["retrieved_chunks"])
        result = state["diagnosis"].model_copy(update={"sources": sources})
        return {
            "diagnosis": result,
            "sources": tuple(sources),
            "trace": (*state["trace"], "result_finalized"),
        }

    def run(self, device: models.Device, symptoms: str) -> DiagnosticState:
        initial: DiagnosticState = {
            "device_id": device.id,
            "symptoms": symptoms,
            "device_context": DeviceContext(
                name=device.name,
                device_type=device.device_type,
                serial_number=device.serial_number,
                location=device.location,
                status=str(device.status),
            ),
            "need_fault_history": False,
            "use_rag": False,
            "history_status": HistoryStatus.NOT_REQUESTED,
            "retrieval_status": RetrievalStatus.NOT_REQUESTED,
            "recent_faults": (),
            "retrieved_chunks": (),
            "diagnosis": None,
            "sources": (),
            "trace": (),
        }
        return self.graph.invoke(initial)

    def diagnose(
        self, device: models.Device, symptoms: str
    ) -> schemas.DiagnosisResult:
        state = self.run(device, symptoms)
        diagnosis = state["diagnosis"]
        if diagnosis is None:
            raise DiagnosisWorkflowError("diagnosis result is missing")
        return diagnosis
