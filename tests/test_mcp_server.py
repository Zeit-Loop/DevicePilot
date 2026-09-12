import asyncio
from pathlib import Path
from types import SimpleNamespace

from mcp import Client
from sqlalchemy.orm import Session

from app import models
from app.database import Base, create_database, create_session_factory
from app.mcp.server import create_mcp_server
from app.mcp.services import DevicePilotReadService
from app.rag.types import RetrievedChunk


def make_protocol_service(tmp_path, *, rag_enabled=True, retrieval_factory=None):
    engine = create_database(f"sqlite:///{tmp_path / 'mcp-protocol.db'}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        device = models.Device(
            name="Cooling Pump",
            device_type="Centrifugal Pump",
            serial_number="MCP-PUMP-001",
            location="Plant room",
            status="active",
        )
        session.add(device)
        session.commit()
        session.refresh(device)
        device_id = device.id
    return DevicePilotReadService(
        factory,
        rag_enabled=rag_enabled,
        retrieval_factory=retrieval_factory,
    ), device_id


def test_protocol_discovery_lists_exact_tools_and_empty_optional_primitives(tmp_path) -> None:
    service, _device_id = make_protocol_service(tmp_path, rag_enabled=False)
    mcp = create_mcp_server(service)

    async def scenario() -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            resources = await client.list_resources()
            templates = await client.list_resource_templates()
            prompts = await client.list_prompts()

        assert {tool.name for tool in tools.tools} == {
            "get_device",
            "get_recent_faults",
            "search_knowledge",
        }
        assert len(tools.tools) == 3
        assert all(tool.annotations.read_only_hint for tool in tools.tools)
        assert all(tool.annotations.destructive_hint is False for tool in tools.tools)
        assert all(tool.annotations.open_world_hint is False for tool in tools.tools)
        assert resources.resources == []
        assert templates.resource_templates == []
        assert prompts.prompts == []

    asyncio.run(scenario())


def test_get_device_returns_structured_content_and_missing_is_tool_error(tmp_path) -> None:
    service, device_id = make_protocol_service(tmp_path, rag_enabled=False)
    mcp = create_mcp_server(service)

    async def scenario() -> None:
        async with Client(mcp) as client:
            found = await client.call_tool("get_device", {"device_id": device_id})
            missing = await client.call_tool(
                "get_device", {"device_id": device_id + 999}
            )

        assert found.is_error is False
        assert found.structured_content["serial_number"] == "MCP-PUMP-001"
        assert missing.is_error is True
        assert "DEVICE_NOT_FOUND" in missing.content[0].text
        assert "Traceback" not in missing.content[0].text

    asyncio.run(scenario())


def test_tool_input_schemas_and_runtime_validation_enforce_bounds(tmp_path) -> None:
    service, device_id = make_protocol_service(tmp_path, rag_enabled=False)
    mcp = create_mcp_server(service)

    async def scenario() -> None:
        async with Client(mcp) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            bad_device = await client.call_tool("get_device", {"device_id": 0})
            bad_low = await client.call_tool(
                "get_recent_faults", {"device_id": device_id, "limit": 0}
            )
            bad_high = await client.call_tool(
                "get_recent_faults", {"device_id": device_id, "limit": 6}
            )
            bad_empty = await client.call_tool(
                "search_knowledge", {"device_id": device_id, "query": "   "}
            )
            bad_long = await client.call_tool(
                "search_knowledge", {"device_id": device_id, "query": "x" * 2001}
            )

        limit_schema = tools["get_recent_faults"].input_schema["properties"]["limit"]
        query_schema = tools["search_knowledge"].input_schema["properties"]["query"]
        assert limit_schema["minimum"] == 1
        assert limit_schema["maximum"] == 5
        assert query_schema["minLength"] == 1
        assert query_schema["maxLength"] == 2000
        assert all(
            result.is_error
            for result in (bad_device, bad_low, bad_high, bad_empty, bad_long)
        )

    asyncio.run(scenario())


def test_recent_faults_and_search_use_structured_success_results(tmp_path) -> None:
    class Retrieval:
        def retrieve(self, _device_type: str, query: str) -> list[RetrievedChunk]:
            if query == "irrelevant":
                return []
            return [
                RetrievedChunk(
                    content="Inspect the pump bearing.",
                    source="centrifugal-pump.md",
                    title="not exposed",
                    equipment_type="centrifugal pump",
                    chunk_index=0,
                    distance=0.1,
                )
            ]

    service, device_id = make_protocol_service(
        tmp_path, retrieval_factory=lambda: Retrieval()
    )
    mcp = create_mcp_server(service)

    async def scenario() -> None:
        async with Client(mcp) as client:
            faults = await client.call_tool(
                "get_recent_faults", {"device_id": device_id}
            )
            positive = await client.call_tool(
                "search_knowledge", {"device_id": device_id, "query": "bearing"}
            )
            irrelevant = await client.call_tool(
                "search_knowledge", {"device_id": device_id, "query": "irrelevant"}
            )

        assert faults.is_error is False
        assert faults.structured_content == {"device_id": device_id, "faults": []}
        assert positive.is_error is False
        assert positive.structured_content["matches"] == [
            {
                "document": "centrifugal-pump.md",
                "chunk_index": 0,
                "content": "Inspect the pump bearing.",
                "equipment_type": "centrifugal pump",
            }
        ]
        assert irrelevant.is_error is False
        assert irrelevant.structured_content == {"device_id": device_id, "matches": []}

    asyncio.run(scenario())


def test_domain_failures_are_sanitized_is_error_results(tmp_path) -> None:
    disabled, device_id = make_protocol_service(tmp_path, rag_enabled=False)
    unavailable, unavailable_id = make_protocol_service(
        tmp_path / "unavailable",
        retrieval_factory=lambda: (_ for _ in ()).throw(
            RuntimeError("secret key at C:/data/chroma")
        ),
    )

    class FailingSession(Session):
        def get(self, *_args):
            raise RuntimeError("SELECT secret FROM C:/private/devicepilot.db")

    database_failed = DevicePilotReadService(
        lambda: FailingSession(), rag_enabled=False
    )

    async def call(service, name, arguments):
        async with Client(create_mcp_server(service)) as client:
            return await client.call_tool(name, arguments)

    disabled_result = asyncio.run(
        call(disabled, "search_knowledge", {"device_id": device_id, "query": "x"})
    )
    unavailable_result = asyncio.run(
        call(
            unavailable,
            "search_knowledge",
            {"device_id": unavailable_id, "query": "x"},
        )
    )
    database_result = asyncio.run(
        call(database_failed, "get_device", {"device_id": 1})
    )

    assert "RAG_DISABLED" in disabled_result.content[0].text
    assert "RAG_UNAVAILABLE" in unavailable_result.content[0].text
    assert "DATABASE_READ_FAILED" in database_result.content[0].text
    for result in (disabled_result, unavailable_result, database_result):
        assert result.is_error is True
        text = result.content[0].text
        assert "secret" not in text.casefold()
        assert "C:/" not in text
        assert "SELECT" not in text


def test_unexpected_tool_failure_is_a_sanitized_is_error_result() -> None:
    class UnexpectedFailureService:
        def get_device(self, _device_id: int):
            raise RuntimeError("secret SQL at C:/private/devicepilot.db")

    async def scenario():
        async with Client(create_mcp_server(UnexpectedFailureService())) as client:
            return await client.call_tool("get_device", {"device_id": 1})

    result = asyncio.run(scenario())

    assert result.is_error is True
    text = result.content[0].text
    assert "Error executing tool get_device" in text
    assert "secret" not in text.casefold()
    assert "SQL" not in text
    assert "C:/" not in text
    assert "Traceback" not in text


def test_search_query_is_trimmed_before_retrieval(tmp_path) -> None:
    queries: list[str] = []

    class Retrieval:
        def retrieve(self, _device_type: str, query: str) -> list[RetrievedChunk]:
            queries.append(query)
            return []

    service, device_id = make_protocol_service(
        tmp_path, retrieval_factory=lambda: Retrieval()
    )

    async def scenario():
        async with Client(create_mcp_server(service)) as client:
            return await client.call_tool(
                "search_knowledge", {"device_id": device_id, "query": "  bearing  "}
            )

    result = asyncio.run(scenario())

    assert result.is_error is False
    assert queries == ["bearing"]


def test_default_retrieval_factory_reuses_exact_rag_configuration(monkeypatch) -> None:
    import app.mcp.server as server_module

    settings = SimpleNamespace(
        embedding_model="intfloat/multilingual-e5-small",
        chroma_path=Path("configured/chroma"),
        collection_name="devicepilot_knowledge",
        top_k=3,
        max_distance=0.143,
    )
    calls: dict[str, object] = {}
    sentinel = object()

    class FakeEmbeddingProvider:
        def __init__(self, model_name: str) -> None:
            calls["embedding_model"] = model_name

    class FakeVectorStore:
        @classmethod
        def open_existing(cls, path: Path, collection_name: str):
            calls["vector_store"] = (path, collection_name)
            return "vector-store"

    class FakeRetrievalService:
        def __new__(cls, embedding, vector_store, *, top_k, max_distance):
            calls["retrieval"] = (embedding, vector_store, top_k, max_distance)
            return sentinel

    monkeypatch.setattr(
        server_module.RAGSettings,
        "from_environment",
        classmethod(lambda cls: settings),
    )
    monkeypatch.setattr(
        "app.rag.embeddings.E5EmbeddingProvider", FakeEmbeddingProvider
    )
    monkeypatch.setattr("app.rag.vector_store.ChromaVectorStore", FakeVectorStore)
    monkeypatch.setattr("app.rag.retrieval.RetrievalService", FakeRetrievalService)

    result = server_module._retrieval_factory()

    assert result is sentinel
    assert calls["embedding_model"] == "intfloat/multilingual-e5-small"
    assert calls["vector_store"] == (
        Path("configured/chroma"),
        "devicepilot_knowledge",
    )
    embedding, vector_store, top_k, max_distance = calls["retrieval"]
    assert isinstance(embedding, FakeEmbeddingProvider)
    assert vector_store == "vector-store"
    assert top_k == 3
    assert max_distance == 0.143
