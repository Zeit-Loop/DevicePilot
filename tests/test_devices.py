def create_device(client, **overrides):
    payload = {
        "name": "Cooling Pump 1",
        "device_type": "pump",
        "serial_number": "PUMP-001",
        "location": "Plant A",
        "status": "active",
    }
    payload.update(overrides)
    return client.post("/devices", json=payload)


def test_create_and_retrieve_device(client):
    response = create_device(client)

    assert response.status_code == 201
    created = response.json()
    assert created["id"] > 0
    assert created["name"] == "Cooling Pump 1"
    assert created["serial_number"] == "PUMP-001"
    assert created["created_at"]

    fetched = client.get(f"/devices/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created


def test_list_devices(client):
    create_device(client, name="Pump A", serial_number="P-A")
    create_device(client, name="Pump B", serial_number="P-B")

    response = client.get("/devices")

    assert response.status_code == 200
    assert [device["name"] for device in response.json()] == ["Pump A", "Pump B"]


def test_update_device(client):
    device_id = create_device(client).json()["id"]

    response = client.put(
        f"/devices/{device_id}",
        json={
            "name": "Cooling Pump 1B",
            "device_type": "pump",
            "serial_number": "PUMP-001",
            "location": "Plant B",
            "status": "maintenance",
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Cooling Pump 1B"
    assert response.json()["location"] == "Plant B"
    assert response.json()["status"] == "maintenance"


def test_delete_device(client):
    device_id = create_device(client).json()["id"]

    response = client.delete(f"/devices/{device_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/devices/{device_id}").status_code == 404


def test_missing_device_operations_return_404(client):
    assert client.get("/devices/999").status_code == 404
    assert client.put(
        "/devices/999",
        json={
            "name": "Missing",
            "device_type": "sensor",
            "serial_number": "NONE-1",
            "location": None,
            "status": "active",
        },
    ).status_code == 404
    assert client.delete("/devices/999").status_code == 404


def test_invalid_device_payload_returns_422(client):
    response = create_device(client, name="", serial_number="")

    assert response.status_code == 422



def test_device_payload_trims_required_strings_and_rejects_whitespace(client):
    created = create_device(client, name="  Cooling Pump  ", serial_number="  PUMP-TRIM-001  ")
    assert created.status_code == 201
    assert created.json()["name"] == "Cooling Pump"
    assert created.json()["serial_number"] == "PUMP-TRIM-001"
    assert create_device(client, name="   ", serial_number="PUMP-WS-001").status_code == 422
    assert create_device(client, name="Pump", serial_number="   ").status_code == 422

def test_legacy_whitespace_device_record_remains_readable(client, tmp_path):
    import sqlite3

    with sqlite3.connect(tmp_path / "test.db") as connection:
        cursor = connection.execute(
            """
            INSERT INTO devices
                (name, device_type, serial_number, location, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("   ", "pump", "   ", None, "active", "2026-01-01", "2026-01-01"),
        )
        device_id = cursor.lastrowid

    response = client.get(f"/devices/{device_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "   "
    assert response.json()["serial_number"] == "   "


def test_duplicate_serial_number_returns_422(client):
    assert create_device(client).status_code == 201

    response = create_device(client, name="Duplicate")

    assert response.status_code == 422
