from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import create_database, create_session_factory
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_database(database_url)
    session_factory = create_session_factory(engine)
    app = create_app(session_factory=session_factory, engine=engine)
    with TestClient(app) as test_client:
        yield test_client
