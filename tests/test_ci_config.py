"""Phase 9.1 CI and operations documentation contracts."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def workflow() -> tuple[str, dict[str, object]]:
    source = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    return source, yaml.load(source, Loader=yaml.BaseLoader)


def test_ci_is_read_only_and_has_no_deployment_authority() -> None:
    source, parsed = workflow()

    assert parsed["on"] == {"push": {"branches": ["main"]}, "pull_request": ""}
    assert parsed["permissions"] == {"contents": "read"}
    lowered = source.lower()
    for forbidden in (
        "pull_request_target",
        "docker push",
        "ssh",
        "appleboy/",
        "secrets.",
        "kubectl ",
        "scp ",
        "rsync ",
    ):
        assert forbidden not in lowered


def test_ci_runs_all_required_validation_jobs_with_dummy_values() -> None:
    source, parsed = workflow()

    jobs = parsed["jobs"]
    assert set(jobs) == {"backend", "frontend", "production-containers"}
    assert "python -m pytest -q" in source
    assert "python -m compileall -q app scripts tests" in source
    assert "python -m pip check" in source
    assert "pnpm install --frozen-lockfile" in source
    assert "pnpm test" in source
    assert "pnpm typecheck" in source
    assert "pnpm build" in source
    assert "compose.production.yml config --quiet" in source
    assert "--entrypoint caddy caddy" in source
    assert "validate --config /etc/caddy/Caddyfile" in source
    assert "compose.production.yml build backend frontend" in source
    assert "python3 -m scripts.verify_proxy_boundary" in source
    assert "./deploy/.env.production.example" in source


def test_operations_docs_cover_release_secrets_recovery_and_exclusions() -> None:
    production = (ROOT / "docs" / "PRODUCTION_DEPLOYMENT.md").read_text(
        encoding="utf-8"
    )
    decisions = (ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")

    for required in (
        "/etc/devicepilot/backend.env",
        "/etc/devicepilot/caddy.env",
        "0600",
        "APP_VERSION",
        "7 daily, 4 weekly, and 3 monthly",
        "encrypted off-host",
        "scripts.seed_demo",
        "application rollback",
        "scripts.verify_proxy_boundary",
        "no remote MCP",
    ):
        assert required.lower() in production.lower()
    assert "CI validates and builds but never deploys" in decisions


def test_production_example_is_explicitly_unignored() -> None:
    rules = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "!deploy/.env.production.example" in rules