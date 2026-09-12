import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app import config
from app.config import Settings
from app.database import create_database, create_session_factory
from app.main import create_app


def test_settings_parse_deployment_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:////data/devicepilot.db")
    monkeypatch.setenv(
        "CORS_ORIGINS", "https://devicepilot.example, https://admin.example "
    )
    monkeypatch.setenv("DIAGNOSIS_RATE_LIMIT_PER_MINUTE", "7")
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")

    settings = Settings.from_environment()

    assert settings.database_url == "sqlite:////data/devicepilot.db"
    assert settings.cors_origins == (
        "https://devicepilot.example",
        "https://admin.example",
    )
    assert settings.diagnosis_rate_limit_per_minute == 7
    assert settings.trust_proxy_headers is True


def test_settings_default_to_local_database_without_permissive_cors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "DATABASE_URL",
        "CORS_ORIGINS",
        "DIAGNOSIS_RATE_LIMIT_PER_MINUTE",
        "TRUST_PROXY_HEADERS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_environment()

    assert settings.database_url.endswith("/data/devicepilot.db")
    assert settings.cors_origins == ()
    assert settings.diagnosis_rate_limit_per_minute == 5
    assert settings.trust_proxy_headers is False


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_settings_reject_invalid_rate_limit(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("DIAGNOSIS_RATE_LIMIT_PER_MINUTE", value)

    with pytest.raises(ValueError, match="DIAGNOSIS_RATE_LIMIT_PER_MINUTE"):
        Settings.from_environment()


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        (
            {
                "LLM_MODEL": "deepseek/deepseek-v4-flash",
                "LLM_API_KEY": "deepseek-test-key",
                "LLM_API_BASE": "https://api.deepseek.com",
            },
            (
                "deepseek/deepseek-v4-flash",
                "deepseek-test-key",
                "https://api.deepseek.com",
            ),
        ),
        (
            {
                "LLM_MODEL": "openai/gpt-5-mini",
                "LLM_API_KEY": "openai-test-key",
                "LLM_API_BASE": "",
            },
            ("openai/gpt-5-mini", "openai-test-key", None),
        ),
        (
            {
                "LLM_MODEL": "ollama/llama3.1",
                "LLM_API_KEY": "",
                "LLM_API_BASE": "http://localhost:11434",
            },
            ("ollama/llama3.1", None, "http://localhost:11434"),
        ),
    ],
)
def test_llm_settings_parse_provider_independent_configuration(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
    expected: tuple[str, str | None, str | None],
) -> None:
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "12.5")

    settings = config.LLMSettings.from_environment()

    assert (settings.model, settings.api_key, settings.api_base) == expected
    assert settings.timeout_seconds == 12.5


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_llm_settings_reject_invalid_timeout(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", value)

    with pytest.raises(ValueError, match="LLM_TIMEOUT_SECONDS"):
        config.LLMSettings.from_environment()


def test_rag_enabled_intent_survives_other_invalid_rag_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAG_ENABLED", "true")
    monkeypatch.setenv("RAG_COLLECTION_NAME", "")
    enabled_from_environment = getattr(
        config.RAGSettings, "enabled_from_environment", None
    )

    assert callable(enabled_from_environment)
    assert enabled_from_environment() is True
    with pytest.raises(ValueError, match="RAG_COLLECTION_NAME"):
        config.RAGSettings.from_environment()


def test_production_disables_interactive_api_documentation(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    engine = create_database(f"sqlite:///{tmp_path / 'production-docs.db'}")
    app = create_app(session_factory=create_session_factory(engine), engine=engine)

    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_production_defaults_demo_seeding_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("AUTO_SEED_DEMO", raising=False)

    settings = Settings.from_environment()

    assert settings.production is True
    assert settings.auto_seed_demo is False


def test_auto_seed_demo_remains_explicitly_configurable_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTO_SEED_DEMO", "true")

    assert Settings.from_environment().auto_seed_demo is True


@pytest.mark.parametrize("value", ["", "staging", "Production"])
def test_settings_rejects_unsupported_app_environments(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("APP_ENV", value)

    with pytest.raises(ValueError, match="APP_ENV"):
        Settings.from_environment()


def test_liveness_does_not_query_the_database(tmp_path) -> None:
    engine = create_database(f"sqlite:///{tmp_path / 'live.db'}")
    app = create_app(session_factory=create_session_factory(engine), engine=engine)
    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _many) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        with TestClient(app) as client:
            response = client.get("/health/live")
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert statements == []


def test_readiness_executes_a_cheap_sqlite_probe(tmp_path) -> None:
    engine = create_database(f"sqlite:///{tmp_path / 'ready.db'}")
    app = create_app(session_factory=create_session_factory(engine), engine=engine)
    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _many) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        with TestClient(app) as client:
            response = client.get("/health/ready")
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert statements == ["SELECT 1"]


def test_readiness_hides_database_failures(tmp_path) -> None:
    engine = create_database(f"sqlite:///{tmp_path / 'unavailable.db'}")

    def unavailable_session_factory():
        raise RuntimeError("database connection details must stay private")

    app = create_app(session_factory=unavailable_session_factory, engine=engine)

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not ready"}
