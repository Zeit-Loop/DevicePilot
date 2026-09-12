import os
import subprocess
import sys
from pathlib import Path
from threading import Event, Thread
from time import monotonic

from sqlalchemy import event, text

from app.database import create_database


def test_default_database_path_is_independent_of_working_directory(tmp_path: Path):
    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project_root)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.database import DATABASE_PATH; print(DATABASE_PATH)",
        ],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert Path(result.stdout.strip()) == project_root / "data" / "devicepilot.db"


def test_configured_sqlite_parent_is_created_on_demand(tmp_path: Path) -> None:
    database_path = tmp_path / "mounted-data" / "devicepilot.db"

    engine = create_database(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    assert database_path.exists()


def test_default_sqlite_timeout_waits_for_a_short_lived_write_lock(
    tmp_path: Path,
) -> None:
    engine = create_database(f"sqlite:///{tmp_path / 'busy-timeout.db'}")
    writer_insert_attempted = Event()
    writer_finished = Event()
    writer_errors: list[Exception] = []
    attempt_times: list[float] = []
    finish_times: list[float] = []

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE records (id INTEGER PRIMARY KEY)"))

    lock_holder = engine.connect()
    lock_holder.execute(text("BEGIN IMMEDIATE"))
    lock_holder.execute(text("INSERT INTO records (id) VALUES (1)"))

    def record_contended_insert(_conn, _cursor, statement, _parameters, _context, _many) -> None:
        if statement == "INSERT INTO records (id) VALUES (2)":
            attempt_times.append(monotonic())
            writer_insert_attempted.set()

    event.listen(engine, "before_cursor_execute", record_contended_insert)

    def write_after_lock_release() -> None:
        try:
            with engine.begin() as connection:
                connection.execute(text("INSERT INTO records (id) VALUES (2)"))
        except Exception as exc:
            writer_errors.append(exc)
        finally:
            finish_times.append(monotonic())
            writer_finished.set()

    writer = Thread(target=write_after_lock_release)
    try:
        assert lock_holder.scalar(text("PRAGMA busy_timeout")) > 0
        writer.start()
        assert writer_insert_attempted.wait(timeout=1)
        assert not writer_finished.wait(timeout=0.1)

        lock_holder.commit()
        writer.join(timeout=3)
    finally:
        event.remove(engine, "before_cursor_execute", record_contended_insert)
        lock_holder.close()

    with engine.connect() as connection:
        rows = connection.scalar(text("SELECT COUNT(*) FROM records"))

    assert not writer.is_alive()
    assert writer_errors == []
    assert finish_times[0] - attempt_times[0] >= 0.1
    assert rows == 2
