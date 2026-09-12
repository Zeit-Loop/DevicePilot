import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from mcp import Client, StdioServerParameters


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_TOOL_NAMES = (
    "get_device",
    "get_recent_faults",
    "search_knowledge",
)
MCP_SERVER_ENVIRONMENT_NAMES = (
    "DATABASE_URL",
    "RAG_ENABLED",
    "RAG_KNOWLEDGE_PATH",
    "RAG_VECTOR_STORE_PATH",
    "RAG_CHROMA_PATH",
    "RAG_EMBEDDING_MODEL",
    "RAG_COLLECTION_NAME",
    "RAG_TOP_K",
    "RAG_MAX_DISTANCE",
    "RAG_CHUNK_SIZE",
    "RAG_CHUNK_OVERLAP",
    "RAG_MAX_FILE_BYTES",
)


@dataclass(frozen=True)
class VerificationReport:
    tool_names: tuple[str, ...]
    resources: int
    resource_templates: int
    prompts: int
    device_serial_number: str
    recent_faults: int
    knowledge_matches: int | None


def _validate_discovery(
    tool_names: tuple[str, ...],
    resources: int,
    resource_templates: int,
    prompts: int,
) -> None:
    if (
        tool_names != EXPECTED_TOOL_NAMES
        or resources != 0
        or resource_templates != 0
        or prompts != 0
    ):
        raise RuntimeError("MCP discovery contract mismatch")


async def verify_server(
    *,
    device_id: int,
    command: str = sys.executable,
    cwd: Path = PROJECT_ROOT,
    environment: dict[str, str] | None = None,
    query: str | None = None,
) -> VerificationReport:
    server_environment = {
        name: os.environ[name]
        for name in MCP_SERVER_ENVIRONMENT_NAMES
        if name in os.environ
    }
    server_environment.update(environment or {})
    parameters = StdioServerParameters(
        command=command,
        args=["-m", "app.mcp.server"],
        env=server_environment or None,
        cwd=cwd,
    )
    async with Client(parameters) as client:
        tools = await client.list_tools()
        resources = await client.list_resources()
        templates = await client.list_resource_templates()
        prompts = await client.list_prompts()
        tool_names = tuple(tool.name for tool in tools.tools)
        resource_count = len(resources.resources)
        resource_template_count = len(templates.resource_templates)
        prompt_count = len(prompts.prompts)
        _validate_discovery(
            tool_names,
            resource_count,
            resource_template_count,
            prompt_count,
        )
        device = await client.call_tool("get_device", {"device_id": device_id})
        faults = await client.call_tool(
            "get_recent_faults", {"device_id": device_id, "limit": 5}
        )
        if device.is_error or faults.is_error:
            raise RuntimeError("MCP read verification failed")

        knowledge_matches: int | None = None
        if query is not None:
            knowledge = await client.call_tool(
                "search_knowledge", {"device_id": device_id, "query": query}
            )
            if knowledge.is_error:
                raise RuntimeError("MCP knowledge verification failed")
            knowledge_matches = len(knowledge.structured_content["matches"])

    return VerificationReport(
        tool_names=tool_names,
        resources=resource_count,
        resource_templates=resource_template_count,
        prompts=prompt_count,
        device_serial_number=str(device.structured_content["serial_number"]),
        recent_faults=len(faults.structured_content["faults"]),
        knowledge_matches=knowledge_matches,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify DevicePilot through the official MCP v2 stdio client"
    )
    parser.add_argument("--device-id", type=int, default=1)
    parser.add_argument("--query")
    args = parser.parse_args(argv)
    try:
        report = asyncio.run(
            verify_server(device_id=args.device_id, query=args.query)
        )
    except Exception as exc:
        print(f"MCP verification failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
