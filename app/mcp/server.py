from __future__ import annotations

from typing import Annotated, Callable

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field, StringConstraints

from app.config import RAGSettings, Settings
from app.database import create_database, create_session_factory
from app.mcp.schemas import DeviceDTO, KnowledgeSearchResult, RecentFaultsResult
from app.mcp.services import DevicePilotReadService, ReadServiceError


DeviceId = Annotated[int, Field(gt=0)]
FaultLimit = Annotated[int, Field(ge=1, le=5)]
KnowledgeQuery = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


PUBLIC_ERROR_MESSAGES = {
    "DEVICE_NOT_FOUND": "Device not found",
    "RAG_DISABLED": "Knowledge retrieval is disabled",
    "RAG_UNAVAILABLE": "Knowledge retrieval is unavailable",
    "DATABASE_READ_FAILED": "Database read failed",
}

READ_ONLY_TOOL_ANNOTATIONS = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)


def _tool_error(error: ReadServiceError) -> ToolError:
    message = PUBLIC_ERROR_MESSAGES.get(error.code, "Read operation failed")
    return ToolError(f"{error.code}: {message}")


def create_mcp_server(service: DevicePilotReadService) -> MCPServer:
    mcp = MCPServer(
        "devicepilot",
        description="Bounded read-only DevicePilot interoperability server",
        version="0.1.0",
    )

    @mcp.tool(
        description="Get one DevicePilot device by its database identifier.",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
    )
    def get_device(device_id: DeviceId) -> DeviceDTO:
        try:
            return service.get_device(device_id)
        except ReadServiceError as exc:
            raise _tool_error(exc) from None

    @mcp.tool(
        description="Get up to five most recent faults for one device.",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
    )
    def get_recent_faults(
        device_id: DeviceId, limit: FaultLimit = 5
    ) -> RecentFaultsResult:
        try:
            return service.get_recent_faults(device_id, limit=limit)
        except ReadServiceError as exc:
            raise _tool_error(exc) from None

    @mcp.tool(
        description="Search the existing DevicePilot knowledge index for a device.",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
    )
    def search_knowledge(
        device_id: DeviceId, query: KnowledgeQuery
    ) -> KnowledgeSearchResult:
        try:
            return service.search_knowledge(device_id, query)
        except ReadServiceError as exc:
            raise _tool_error(exc) from None

    return mcp


def _retrieval_factory():
    rag = RAGSettings.from_environment()
    from app.rag.embeddings import E5EmbeddingProvider
    from app.rag.retrieval import RetrievalService
    from app.rag.vector_store import ChromaVectorStore

    return RetrievalService(
        E5EmbeddingProvider(rag.embedding_model),
        ChromaVectorStore.open_existing(rag.chroma_path, rag.collection_name),
        top_k=rag.top_k,
        max_distance=rag.max_distance,
    )


def create_default_read_service() -> DevicePilotReadService:
    settings = Settings.from_environment()
    engine = create_database(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        rag_enabled = RAGSettings.enabled_from_environment()
    except ValueError:
        # Keep the protocol boundary available; the first search maps invalid RAG
        # configuration to the stable RAG_UNAVAILABLE execution error.
        rag_enabled = True
    return DevicePilotReadService(
        session_factory,
        rag_enabled=rag_enabled,
        retrieval_factory=_retrieval_factory,
    )


def main(service_factory: Callable[[], DevicePilotReadService] = create_default_read_service) -> None:
    create_mcp_server(service_factory()).run(transport="stdio")


if __name__ == "__main__":
    main()
