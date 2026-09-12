from tests.test_devices import create_device


def create_fault(client, device_id, **overrides):
    payload = {
        "title": "High motor temperature",
        "description": "Motor temperature reached 95 C",
        "severity": "high",
        "status": "open",
    }
    payload.update(overrides)
    return client.post(f"/devices/{device_id}/faults", json=payload)


def test_create_fault_and_get_fault_history(client):
    device_id = create_device(client).json()["id"]

    created_response = create_fault(client, device_id)

    assert created_response.status_code == 201
    created = created_response.json()
    assert created["device_id"] == device_id
    assert created["severity"] == "high"
    assert created["created_at"]

    history = client.get(f"/devices/{device_id}/faults")
    assert history.status_code == 200
    assert history.json() == [created]

    fetched = client.get(f"/faults/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created


def test_fault_operations_for_missing_resources_return_404(client):
    assert create_fault(client, 999).status_code == 404
    assert client.get("/devices/999/faults").status_code == 404
    assert client.get("/faults/999").status_code == 404


def test_invalid_fault_payload_returns_422(client):
    device_id = create_device(client).json()["id"]

    response = create_fault(client, device_id, title="", description="")

    assert response.status_code == 422



def test_fault_payload_trims_required_strings_and_rejects_whitespace(client):
    device_id = create_device(client).json()["id"]
    created = create_fault(client, device_id, title="  High temperature  ", description="  Housing reached 95 C  ")
    assert created.status_code == 201
    assert created.json()["title"] == "High temperature"
    assert created.json()["description"] == "Housing reached 95 C"
    assert create_fault(client, device_id, title="   ").status_code == 422
    assert create_fault(client, device_id, description="   ").status_code == 422

def test_legacy_whitespace_fault_record_remains_readable(client, tmp_path):
    import sqlite3

    device_id = create_device(client).json()["id"]
    with sqlite3.connect(tmp_path / "test.db") as connection:
        cursor = connection.execute(
            """
            INSERT INTO faults
                (device_id, title, description, severity, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (device_id, "   ", "   ", "medium", "open", "2026-01-01"),
        )
        fault_id = cursor.lastrowid

    response = client.get(f"/faults/{fault_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "   "
    assert response.json()["description"] == "   "


def test_deleting_device_cascades_to_faults(client):
    device_id = create_device(client).json()["id"]
    fault_id = create_fault(client, device_id).json()["id"]

    assert client.delete(f"/devices/{device_id}").status_code == 204
    assert client.get(f"/faults/{fault_id}").status_code == 404


def test_fault_status_lifecycle_preserves_history(client):
    device_id = create_device(client).json()["id"]
    original = create_fault(client, device_id).json()
    for status in ("investigating", "resolved", "open"):
        response = client.patch(f"/faults/{original['id']}", json={"status": status})
        assert response.status_code == 200
        assert response.json() == {**original, "status": status}
        assert client.get(f"/devices/{device_id}/faults").json() == [response.json()]


def test_patch_missing_fault_returns_404(client):
    assert client.patch("/faults/999", json={"status": "resolved"}).status_code == 404


def test_patch_rejects_invalid_or_extra_fields(client):
    device_id = create_device(client).json()["id"]
    original = create_fault(client, device_id).json()
    for payload in ({}, {"status": None}, {"status": "closed"},
                    {"status": "resolved", "id": 999},
                    {"status": "resolved", "device_id": 999},
                    {"status": "resolved", "title": "changed"}):
        assert client.patch(f"/faults/{original['id']}", json=payload).status_code == 422
        assert client.get(f"/faults/{original['id']}").json() == original


def test_delete_fault_only_removes_target(client):
    device_id = create_device(client).json()["id"]
    target = create_fault(client, device_id).json()
    retained = create_fault(client, device_id, title="Other fault").json()
    response = client.delete(f"/faults/{target['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/faults/{target['id']}").status_code == 404
    assert client.delete(f"/faults/{target['id']}").status_code == 404
    assert client.get(f"/devices/{device_id}").status_code == 200
    assert client.get(f"/devices/{device_id}/faults").json() == [retained]


def test_failed_fault_mutations_roll_back(client, monkeypatch):
    import pytest
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import Session

    device_id = create_device(client).json()["id"]
    original = create_fault(client, device_id).json()
    real_rollback = Session.rollback
    rolled_back = []

    def failed_commit(session):
        session.flush()
        raise SQLAlchemyError("Test transaction failure")

    def record_rollback(session):
        rolled_back.append(session)
        real_rollback(session)

    monkeypatch.setattr(Session, "commit", failed_commit)
    monkeypatch.setattr(Session, "rollback", record_rollback)
    for method, kwargs in ((client.patch, {"json": {"status": "resolved"}}),
                           (client.delete, {})):
        with pytest.raises(SQLAlchemyError, match="Test transaction failure"):
            method(f"/faults/{original['id']}", **kwargs)
        assert client.get(f"/faults/{original['id']}").json() == original
    assert len(rolled_back) == 2
