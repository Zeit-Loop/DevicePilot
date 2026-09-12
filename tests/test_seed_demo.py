from sqlalchemy import func, select
from fastapi.testclient import TestClient

from app import models
from app.database import Base, create_database, create_session_factory
from app.main import create_app
from scripts.seed_demo import seed_demo_data


def test_seed_demo_data_is_portfolio_ready_and_idempotent(tmp_path) -> None:
    engine = create_database(f"sqlite:///{tmp_path / 'seed.db'}")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    first = seed_demo_data(session_factory)
    second = seed_demo_data(session_factory)

    with session_factory() as session:
        devices = session.scalars(select(models.Device).order_by(models.Device.id)).all()
        fault_count = session.scalar(select(func.count(models.Fault.id)))

    assert first == (4, 3)
    assert second == (0, 0)
    assert {device.status for device in devices} == {
        "active",
        "inactive",
        "maintenance",
    }
    assert {device.device_type for device in devices} == {
        "Centrifugal Pump",
        "Temperature Sensor",
        "Industrial Motor",
        "Vision Controller",
    }
    assert fault_count == 3


def test_production_startup_with_auto_seed_disabled_leaves_database_empty(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTO_SEED_DEMO", "false")
    engine = create_database(f"sqlite:///{tmp_path / 'production-empty.db'}")
    session_factory = create_session_factory(engine)

    with TestClient(create_app(session_factory=session_factory, engine=engine)):
        pass

    with session_factory() as session:
        assert session.scalar(select(func.count(models.Device.id))) == 0


def test_auto_seed_demo_populates_development_startup_idempotently(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTO_SEED_DEMO", "true")
    engine = create_database(f"sqlite:///{tmp_path / 'development-seed.db'}")
    session_factory = create_session_factory(engine)
    app = create_app(session_factory=session_factory, engine=engine)

    with TestClient(app), TestClient(app):
        pass

    with session_factory() as session:
        assert session.scalar(select(func.count(models.Device.id))) == 4
        assert session.scalar(select(func.count(models.Fault.id))) == 3
