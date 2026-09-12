"""Integration tests for the bounded SQLite backup command.

Each test uses SQLite files rather than mocks.  The covered breaks are: losing a
committed row, accepting a corrupt snapshot, publishing a wrong checksum, unsafe
backup placement, replacing a prior backup, leaking a temporary artifact, and a
CLI that hides a failed backup.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys

import pytest

from scripts import backup_sqlite
from scripts.backup_sqlite import backup_database


BACKUP_TIME = datetime(2030, 1, 2, 3, 4, 5)


def create_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE devices (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        connection.execute("INSERT INTO devices (name) VALUES ('Committed pump')")
        connection.commit()
    finally:
        connection.close()


def expected_backup_path(destination: Path) -> Path:
    return destination / "primary-20300102T030405Z.db"


def independent_destination(tmp_path: Path) -> Path:
    """Use a sibling to model a backup mount outside the primary data directory."""
    return tmp_path.parent / f"{tmp_path.name}-backups"


def test_backup_retains_only_committed_rows_in_a_consistent_snapshot(tmp_path: Path) -> None:
    """Fails if the online snapshot loses committed data or includes another transaction."""
    source = tmp_path / "primary.db"
    destination = independent_destination(tmp_path)
    create_database(source)

    with sqlite3.connect(source) as writer:
        writer.execute("BEGIN")
        writer.execute("INSERT INTO devices (name) VALUES ('Uncommitted motor')")

        result = backup_database(source, destination, now=BACKUP_TIME)

    with sqlite3.connect(result.database_path) as restored:
        rows = restored.execute("SELECT name FROM devices ORDER BY id").fetchall()

    assert rows == [("Committed pump",)]


def test_backup_snapshot_passes_sqlite_integrity_check(tmp_path: Path) -> None:
    """Fails if an invalid snapshot is reported as a successful backup."""
    source = tmp_path / "primary.db"
    destination = independent_destination(tmp_path)
    create_database(source)

    result = backup_database(source, destination, now=BACKUP_TIME)

    with sqlite3.connect(result.database_path) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()

    assert integrity == ("ok",)


def test_backup_writes_checksum_for_the_published_database_bytes(tmp_path: Path) -> None:
    """Fails if the published checksum does not authenticate the backup file."""
    source = tmp_path / "primary.db"
    destination = independent_destination(tmp_path)
    create_database(source)

    result = backup_database(source, destination, now=BACKUP_TIME)

    expected_digest = hashlib.sha256(result.database_path.read_bytes()).hexdigest()
    assert result.sha256 == expected_digest
    assert result.checksum_path.read_text(encoding="utf-8") == f"{expected_digest}\n"


def test_cli_returns_nonzero_when_source_database_is_missing(tmp_path: Path) -> None:
    """Fails if an operator sees a successful command for a missing source database."""
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.backup_sqlite",
            "--source",
            str(tmp_path / "missing.db"),
            "--destination",
            str(independent_destination(tmp_path)),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode != 0
    assert completed.stdout == ""


def test_backup_rejects_destination_nested_under_primary_database_directory(tmp_path: Path) -> None:
    """Fails if a backup can be placed on the same primary-data mount by nesting it."""
    source = tmp_path / "primary.db"
    create_database(source)

    with pytest.raises(ValueError, match="destination"):
        backup_database(source, tmp_path / "backups", now=BACKUP_TIME)


def test_existing_final_backup_is_not_overwritten_or_partially_published(tmp_path: Path) -> None:
    """Fails if a name collision replaces an already durable backup."""
    source = tmp_path / "primary.db"
    destination = independent_destination(tmp_path)
    create_database(source)
    destination.mkdir()
    existing = expected_backup_path(destination)
    existing.write_bytes(b"already durable")

    with pytest.raises(FileExistsError):
        backup_database(source, destination, now=BACKUP_TIME)

    assert existing.read_bytes() == b"already durable"
    assert list(destination.iterdir()) == [existing]


def test_failed_backup_removes_every_temporary_artifact(tmp_path: Path) -> None:
    """Fails if a failed SQLite copy leaves a file that could be mistaken for a backup."""
    source = tmp_path / "primary.db"
    source.write_text("not a SQLite database", encoding="utf-8")
    destination = independent_destination(tmp_path)

    with pytest.raises(sqlite3.DatabaseError):
        backup_database(source, destination, now=BACKUP_TIME)

    assert list(destination.iterdir()) == []


def test_source_deleted_after_validation_is_never_recreated_as_a_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fails if the source check/open race lets SQLite create a replacement DB."""
    source = tmp_path / "primary.db"
    destination = independent_destination(tmp_path)
    real_is_file = Path.is_file

    def report_stale_source_validation(path: Path) -> bool:
        return True if path == source else real_is_file(path)

    monkeypatch.setattr(Path, "is_file", report_stale_source_validation)

    with pytest.raises(FileNotFoundError):
        backup_database(source, destination, now=BACKUP_TIME)

    assert not source.exists()
    assert not destination.exists()


def test_source_replaced_between_validation_and_open_is_not_backed_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fails if a valid replacement can be snapshotted through the checked pathname."""
    source = tmp_path / "primary.db"
    replacement = tmp_path / "replacement.db"
    destination = independent_destination(tmp_path)
    create_database(source)
    create_database(replacement)
    connection = sqlite3.connect(replacement)
    try:
        connection.execute("INSERT INTO devices (name) VALUES ('Replacement pump')")
        connection.commit()
    finally:
        connection.close()
    real_connect = backup_sqlite.sqlite3.connect
    replaced = False

    def replace_before_source_open(
        database: object, *args: object, **kwargs: object
    ) -> sqlite3.Connection:
        nonlocal replaced
        if not replaced and str(database).startswith(source.as_uri()):
            source.unlink()
            replacement.replace(source)
            replaced = True
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(backup_sqlite.sqlite3, "connect", replace_before_source_open)

    with pytest.raises(RuntimeError, match="source database changed"):
        backup_database(source, destination, now=BACKUP_TIME)

    assert replaced is True
    with sqlite3.connect(source) as connection:
        assert connection.execute("SELECT name FROM devices ORDER BY id").fetchall() == [
            ("Committed pump",),
            ("Replacement pump",),
        ]
    assert list(destination.iterdir()) == []


@pytest.mark.skipif(os.name != "posix", reason="Unix mode bits are a POSIX contract")
def test_published_backup_artifacts_are_private_to_the_backend_user(tmp_path: Path) -> None:
    """Fails if a final database or digest becomes group/world-readable."""
    source = tmp_path / "primary.db"
    destination = independent_destination(tmp_path)
    create_database(source)

    result = backup_database(source, destination, now=BACKUP_TIME)

    assert stat.S_IMODE(result.database_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(result.checksum_path.stat().st_mode) == 0o600


def test_link_publish_keeps_its_final_when_temp_unlink_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fails if cleanup rolls back a final that was already atomically published."""
    temporary = tmp_path / "temporary.db"
    final = tmp_path / "final.db"
    temporary.write_bytes(b"snapshot")
    real_unlink = Path.unlink
    failed = False

    def fail_temporary_unlink(path: Path, *args: object, **kwargs: object) -> None:
        nonlocal failed
        if path == temporary and not failed:
            failed = True
            raise OSError("injected temp unlink failure")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_temporary_unlink)

    with pytest.raises(OSError, match="injected temp unlink failure"):
        backup_sqlite._publish_without_overwrite(temporary, final)

    assert temporary.exists()
    assert final.read_bytes() == b"snapshot"


def test_link_publish_never_deletes_a_concurrent_final_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fails if cleanup removes a different file published after the link operation."""
    temporary = tmp_path / "temporary.db"
    final = tmp_path / "final.db"
    temporary.write_bytes(b"snapshot")
    real_unlink = Path.unlink

    def replace_final_then_fail_temp_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path == temporary:
            real_unlink(final)
            final.write_bytes(b"concurrent replacement")
            raise OSError("injected temp unlink failure")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", replace_final_then_fail_temp_unlink)

    with pytest.raises(OSError, match="injected temp unlink failure"):
        backup_sqlite._publish_without_overwrite(temporary, final)

    assert final.read_bytes() == b"concurrent replacement"
    assert temporary.exists()


def test_link_publish_never_unlinks_a_post_link_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fails if recovery unlinks a final name after another writer replaces it."""
    temporary = tmp_path / "temporary.db"
    final = tmp_path / "final.db"
    temporary.write_bytes(b"snapshot")
    real_link = backup_sqlite.os.link
    real_unlink = Path.unlink

    def link_then_replace(source: object, destination: object, *args: object, **kwargs: object) -> None:
        real_link(source, destination, *args, **kwargs)
        real_unlink(Path(destination))
        Path(destination).write_bytes(b"post-link replacement")

    def fail_temporary_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path == temporary:
            raise OSError("injected temp unlink failure")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(backup_sqlite.os, "link", link_then_replace)
    monkeypatch.setattr(Path, "unlink", fail_temporary_unlink)

    with pytest.raises(OSError, match="injected temp unlink failure"):
        backup_sqlite._publish_without_overwrite(temporary, final)

    assert final.read_bytes() == b"post-link replacement"
    assert temporary.exists()


def test_database_final_publish_failure_keeps_source_and_leaves_only_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fails if database publication precedes checksum or alters primary data on failure."""
    source = tmp_path / "primary.db"
    destination = independent_destination(tmp_path)
    create_database(source)
    database_final = expected_backup_path(destination)
    checksum_final = database_final.with_suffix(".sha256")
    real_link = backup_sqlite.os.link

    def fail_database_final_link(source_path: object, final_path: object, *args: object, **kwargs: object) -> None:
        if Path(final_path) == database_final:
            raise OSError("injected database final publication failure")
        real_link(source_path, final_path, *args, **kwargs)

    monkeypatch.setattr(backup_sqlite.os, "link", fail_database_final_link)

    with pytest.raises(OSError, match="injected database final publication failure"):
        backup_database(source, destination, now=BACKUP_TIME)

    assert not database_final.exists()
    assert checksum_final.exists()
    with sqlite3.connect(source) as connection:
        assert connection.execute("SELECT name FROM devices").fetchall() == [("Committed pump",)]


def test_backup_syncs_the_destination_directory_before_reporting_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fails if final links are not durably recorded before a successful result."""
    source = tmp_path / "primary.db"
    destination = independent_destination(tmp_path)
    create_database(source)
    synced_directories: list[Path] = []
    monkeypatch.setattr(
        backup_sqlite,
        "_fsync_destination_directory",
        lambda path: synced_directories.append(path),
        raising=False,
    )

    backup_database(source, destination, now=BACKUP_TIME)

    assert synced_directories == [destination]
