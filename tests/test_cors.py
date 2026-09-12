from pathlib import Path

from fastapi.testclient import TestClient

from app.database import create_database, create_session_factory
from app.main import create_app


def test_only_explicit_frontend_origin_is_allowed(tmp_path: Path) -> None:
    engine = create_database(f"sqlite:///{tmp_path / 'cors.db'}")
    app = create_app(
        session_factory=create_session_factory(engine),
        engine=engine,
        cors_origins=("https://devicepilot.example",),
    )

    with TestClient(app) as client:
        response = client.get(
            "/devices", headers={"Origin": "https://devicepilot.example"}
        )
        rejected = client.get(
            "/devices", headers={"Origin": "https://untrusted.example"}
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://devicepilot.example"
    assert "access-control-allow-origin" not in rejected.headers
