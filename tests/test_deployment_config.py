"""Production deployment contract tests."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "compose.production.yml"


def declared_production_compose() -> dict[str, Any]:
    """Resolve only Compose interpolation needed to inspect declared topology."""
    source = COMPOSE_FILE.read_text(encoding="utf-8")
    source = source.replace("${APP_VERSION:?set APP_VERSION}", "phase9-test")
    source = source.replace("${BACKEND_ENV_FILE:-/etc/devicepilot/backend.env}", "/etc/devicepilot/backend.env")
    source = source.replace("${CADDY_ENV_FILE:-/etc/devicepilot/caddy.env}", "/etc/devicepilot/caddy.env")
    source = source.replace("${BACKUP_DIR:-/var/backups/devicepilot}", "/var/backups/devicepilot")
    return yaml.safe_load(source)


def rendered_production_compose() -> dict[str, Any]:
    """Use Compose's JSON model where Docker is available."""
    if not COMPOSE_FILE.exists():
        raise FileNotFoundError(COMPOSE_FILE)
    docker = shutil.which("docker")
    if docker is None:
        return declared_production_compose()
    environment = os.environ | {"APP_VERSION": "phase9-test", "BACKEND_ENV_FILE": "./deploy/.env.production.example", "CADDY_ENV_FILE": "./deploy/.env.production.example"}
    result = subprocess.run(
        [docker, "compose", "--profile", "maintenance", "-f", str(COMPOSE_FILE), "config", "--format", "json"],
        cwd=ROOT, env=environment, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"docker compose config failed: {result.stderr.strip()}")
    return yaml.safe_load(result.stdout)


def service_network_names(service: dict[str, Any]) -> set[str]:
    networks = service.get("networks", [])
    return set(networks if isinstance(networks, list) else networks)


def published_ports(service: dict[str, Any]) -> set[tuple[str, int]]:
    result = set()
    for port in service.get("ports", []):
        if isinstance(port, str):
            published, target = port.split(":")
            result.add((published, int(target)))
        else:
            result.add((str(port["published"]), int(port["target"])))
    return result


def has_volume(service: dict[str, Any], source: str, target: str, read_only: bool = False) -> bool:
    for volume in service.get("volumes", []):
        if isinstance(volume, str):
            parts = volume.split(":")
            if parts[:2] == [source, target] and (not read_only or parts[-1] == "ro"):
                return True
        elif volume["source"] == source and volume["target"] == target and (not read_only or volume.get("read_only") is True):
            return True
    return False


def test_public_edge_cannot_accidentally_publish_application_ports() -> None:
    """Catches a production change that exposes frontend or backend directly."""
    services = rendered_production_compose()["services"]
    assert published_ports(services["caddy"]) == {("80", 80), ("443", 443)}
    assert not services["frontend"].get("ports")
    assert not services["backend"].get("ports")


def test_network_segmentation_prevents_caddy_backend_bypass() -> None:
    """Catches a network change that lets the public proxy reach FastAPI directly."""
    compose = rendered_production_compose()
    services = compose["services"]
    assert service_network_names(services["caddy"]) == {"edge"}
    assert service_network_names(services["frontend"]) == {"edge", "app"}
    assert service_network_names(services["backend"]) == {"app", "egress"}
    assert compose["networks"]["app"]["internal"] is True
    assert compose["networks"]["egress"].get("internal", False) is False


def test_versioned_images_and_production_flags_support_safe_single_node_operation() -> None:
    """Catches mutable images or a production backend that seeds demo data."""
    services = declared_production_compose()["services"]
    backend = services["backend"]
    assert services["backend"]["image"] == "devicepilot-backend:phase9-test"
    assert services["frontend"]["image"] == "devicepilot-frontend:phase9-test"
    assert backend["environment"]["APP_ENV"] == "production"
    assert backend["environment"]["TRUST_PROXY_HEADERS"] == "true"
    assert backend["environment"]["AUTO_SEED_DEMO"] == "false"
    assert backend["environment"]["RAG_KNOWLEDGE_PATH"] == "/app/knowledge"
    assert backend["environment"]["RAG_VECTOR_STORE_PATH"] == "/data/chroma"
    operator_settings = {
        "LLM_MODEL", "LLM_API_BASE", "LLM_TIMEOUT_SECONDS", "RAG_ENABLED",
        "RAG_EMBEDDING_MODEL", "RAG_MAX_DISTANCE", "RAG_TOP_K",
        "RAG_CHUNK_SIZE", "RAG_CHUNK_OVERLAP",
    }
    assert operator_settings.isdisjoint(backend["environment"])
    assert backend.get("deploy", {}).get("replicas", 1) == 1


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker is not installed")
def test_backend_env_file_controls_rag_enabled(tmp_path: Path) -> None:
    """Catches Compose silently overriding an operator's production RAG switch."""
    backend_env = tmp_path / "backend.env"
    backend_env.write_text(
        "LLM_MODEL=deepseek/deepseek-v4-flash\n"
        "LLM_API_KEY=\n"
        "LLM_API_BASE=https://api.deepseek.com\n"
        "LLM_TIMEOUT_SECONDS=20\n"
        "RAG_ENABLED=true\n"
        "RAG_EMBEDDING_MODEL=intfloat/multilingual-e5-small\n"
        "RAG_MAX_DISTANCE=0.143\n"
        "RAG_TOP_K=3\n"
        "RAG_CHUNK_SIZE=600\n"
        "RAG_CHUNK_OVERLAP=80\n",
        encoding="utf-8",
    )
    environment = os.environ | {
        "APP_VERSION": "phase9-test",
        "BACKEND_ENV_FILE": str(backend_env),
        "CADDY_ENV_FILE": "./deploy/.env.production.example",
    }
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "config", "--format", "json"],
        cwd=ROOT, env=environment, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    backend = yaml.safe_load(result.stdout)["services"]["backend"]
    assert backend["environment"]["RAG_ENABLED"] == "true"
    assert backend["environment"]["RAG_MAX_DISTANCE"] == "0.143"
def test_persistence_and_backup_are_isolated_from_the_running_application() -> None:
    """Catches backup access being granted to the application or data being ephemeral."""
    compose = rendered_production_compose()
    services = compose["services"]
    assert has_volume(services["backend"], "devicepilot_data", "/data")
    assert compose["volumes"]["devicepilot_data"]["name"] == "devicepilot_data"
    backup = services["backup"]
    assert backup["profiles"] == ["maintenance"]
    assert backup["user"] == "10001:10001"
    assert has_volume(backup, "devicepilot_data", "/data", read_only=True)
    assert any((volume.get("target") if isinstance(volume, dict) else volume.split(":")[1]) == "/backups" for volume in backup["volumes"])


def test_container_hardening_and_logs_remain_bounded() -> None:
    """Catches removal of backend controls that protect the SQLite service."""
    backend = rendered_production_compose()["services"]["backend"]
    assert backend["user"] == "10001:10001"
    assert backend["security_opt"] == ["no-new-privileges:true"]
    assert backend["cap_drop"] == ["ALL"]
    assert backend["read_only"] is True
    assert backend["tmpfs"] == ["/tmp:rw,noexec,nosuid,size=64m"]
    assert backend["logging"] == {"driver": "local", "options": {"max-size": "10m", "max-file": "3"}}


def test_deployment_has_no_unapproved_services_or_docker_socket() -> None:
    """Catches remote MCP, database, Chroma, or Docker-socket additions."""
    services = rendered_production_compose()["services"]
    assert set(services) == {"caddy", "frontend", "backend", "backup"}
    volume_sources = [volume.get("source", "") if isinstance(volume, dict) else volume for service in services.values() for volume in service.get("volumes", [])]
    assert not any("docker.sock" in volume for volume in volume_sources)


def test_production_env_files_stay_outside_the_repository_by_default() -> None:
    """Catches production secret paths being replaced with repository-local files."""
    services = declared_production_compose()["services"]
    assert services["backend"]["env_file"] == ["/etc/devicepilot/backend.env"]
    assert services["caddy"]["env_file"] == ["/etc/devicepilot/caddy.env"]


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker is not installed")
def test_compose_requires_an_explicit_application_version() -> None:
    """Catches a fallback version that would make rollback images mutable."""
    result = subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), "config"], cwd=ROOT, env={key: value for key, value in os.environ.items() if key != "APP_VERSION"}, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "APP_VERSION" in result.stderr

def test_rendered_compose_does_not_hide_docker_configuration_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches tests silently accepting a failed Docker Compose render."""
    monkeypatch.setattr(shutil, "which", lambda _name: "docker")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="invalid compose"
        ),
    )

    with pytest.raises(RuntimeError, match="invalid compose"):
        rendered_production_compose()


def test_caddy_healthcheck_probes_the_running_local_service() -> None:
    """Catches a Caddy healthcheck that only validates a binary is installed."""
    caddy = declared_production_compose()["services"]["caddy"]
    assert caddy["healthcheck"]["test"] == [
        "CMD-SHELL",
        "wget -q -O /dev/null http://127.0.0.1:2019/config/ || exit 1",
    ]
@pytest.mark.skipif(
    os.getenv("RUN_DOCKER_PROXY_TESTS") != "1",
    reason="set RUN_DOCKER_PROXY_TESTS=1 to run Docker proxy verification",
)
def test_runtime_proxy_boundary_verifier() -> None:
    """Catches Caddy/nginx changes that expose forged XFF or upstream auth."""
    result = subprocess.run(
        ["python", "-m", "scripts.verify_proxy_boundary"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "direct nginx XFF values preserved" in result.stdout

def test_topology_tests_use_static_declaration_only_when_docker_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a Docker-less developer environment raising from an undefined result."""
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    assert rendered_production_compose() == declared_production_compose()


def test_dummy_caddy_hash_uses_a_single_quoted_literal_env_value() -> None:
    """Catches interpolation corrupting the bcrypt hash before container start."""
    lines = (ROOT / "deploy" / ".env.production.example").read_text(
        encoding="utf-8"
    ).splitlines()
    value = next(line for line in lines if line.startswith("BASIC_AUTH_PASSWORD_HASH="))
    assert value.startswith("BASIC_AUTH_PASSWORD_HASH='$2a$14$")
    assert value.endswith("'")


def test_proxy_verifier_uses_the_compose_application_version() -> None:
    """Catches CI building one frontend tag while the verifier runs another."""
    source = (ROOT / "scripts" / "verify_proxy_boundary.py").read_text(
        encoding="utf-8"
    )
    assert 'os.getenv("APP_VERSION", "phase9-test")' in source
    assert '"image": frontend_image' in source
