import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app import models
from app.database import Base, create_database, create_session_factory
from scripts.verify_mcp import _validate_discovery, verify_server


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_verifier_rejects_discovery_outside_phase_7_contract() -> None:
    _validate_discovery(
        ("get_device", "get_recent_faults", "search_knowledge"), 0, 0, 0
    )

    with pytest.raises(RuntimeError, match="MCP discovery contract mismatch"):
        _validate_discovery(
            ("delete_device", "get_device", "get_recent_faults", "search_knowledge"),
            0,
            0,
            0,
        )
    with pytest.raises(RuntimeError, match="MCP discovery contract mismatch"):
        _validate_discovery(
            ("get_device", "get_recent_faults", "search_knowledge"), 1, 0, 0
        )


def seed_stdio_database(tmp_path: Path) -> tuple[str, int]:
    database_path = tmp_path / "mcp-stdio.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_database(database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        device = models.Device(
            name="Stdio Pump",
            device_type="Centrifugal Pump",
            serial_number="MCP-STDIO-001",
            location="Test bay",
            status="active",
        )
        session.add(device)
        session.commit()
        session.refresh(device)
        device_id = device.id
    engine.dispose()
    return database_url, device_id


def test_official_client_connects_to_real_stdio_subprocess_without_writes(
    tmp_path, monkeypatch
) -> None:
    database_url, device_id = seed_stdio_database(tmp_path)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("RAG_ENABLED", "false")

    report = asyncio.run(
        verify_server(
            device_id=device_id,
            command=sys.executable,
            cwd=PROJECT_ROOT,
        )
    )

    assert report.tool_names == (
        "get_device",
        "get_recent_faults",
        "search_knowledge",
    )
    assert report.resources == 0
    assert report.resource_templates == 0
    assert report.prompts == 0
    assert report.device_serial_number == "MCP-STDIO-001"

    engine = create_database(database_url)
    factory = create_session_factory(engine)
    with factory() as session:
        assert session.scalar(select(func.count(models.Device.id))) == 1
        assert session.scalar(select(func.count(models.Fault.id))) == 0
    engine.dispose()


def test_importing_stdio_server_does_not_load_e5_or_litellm() -> None:
    code = (
        "import sys; import app.mcp.server; "
        "assert 'sentence_transformers' not in sys.modules; "
        "assert 'litellm' not in sys.modules"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
