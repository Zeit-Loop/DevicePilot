"""Create a consistent, checksummed SQLite backup without copying a live database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from uuid import uuid4


CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class BackupResult:
    """The two published backup artifacts and the digest authenticating the database."""

    database_path: Path
    checksum_path: Path
    sha256: str


def _as_utc_timestamp(now: datetime | None) -> str:
    timestamp = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone(timezone.utc)
    return timestamp.strftime("%Y%m%dT%H%M%SZ")


def _is_nested(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as backup_file:
        while chunk := backup_file.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDWR)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_destination_directory(destination_dir: Path) -> None:
    """Persist final directory entries where the operating system supports it."""
    if os.name != "posix":
        return
    descriptor = os.open(destination_dir, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _file_identity(path: Path) -> tuple[int, int]:
    metadata = path.stat()
    return metadata.st_dev, metadata.st_ino


def _remove_if_present(path: Path | None) -> None:
    if path is not None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _publish_without_overwrite(
    temporary_path: Path, final_path: Path
) -> None:
    """Publish one artifact atomically, refusing to clobber a prior backup.

    A hard link is an atomic same-filesystem publication operation that fails if
    ``final_path`` exists.  The temporary name is removed only after the final
    path exists, so there is never a partially written final file.
    """

    os.link(temporary_path, final_path)
    temporary_path.unlink()


def backup_database(
    source: Path, destination_dir: Path, now: datetime | None = None
) -> BackupResult:
    """Back up ``source`` through SQLite's online API into an independent directory.

    ``destination_dir`` is intentionally a required operational boundary: callers
    must point it at a separately persisted backup mount, never a subdirectory of
    the source database directory.
    """

    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"source database does not exist: {source_path}")
    source_identity = _file_identity(source_path)

    source_directory = source_path.parent
    destination_path = Path(destination_dir).expanduser().resolve()
    if _is_nested(destination_path, source_directory):
        raise ValueError("destination directory must not be inside the source database directory")

    destination_path.mkdir(parents=True, exist_ok=True)
    if not destination_path.is_dir():
        raise NotADirectoryError(f"destination is not a directory: {destination_path}")

    timestamp = _as_utc_timestamp(now)
    database_path = destination_path / f"{source_path.stem}-{timestamp}.db"
    checksum_path = database_path.with_suffix(".sha256")
    if database_path.exists() or checksum_path.exists():
        raise FileExistsError("a final backup artifact already exists for this timestamp")

    temporary_database: Path | None = None
    temporary_checksum: Path | None = None
    source_connection: sqlite3.Connection | None = None
    destination_connection: sqlite3.Connection | None = None

    try:
        with tempfile.NamedTemporaryFile(
            dir=destination_path,
            prefix=f".{source_path.stem}-{timestamp}-",
            suffix=f"-{uuid4().hex}.tmp",
            delete=False,
        ) as temporary_file:
            temporary_database = Path(temporary_file.name)

        source_uri = f"{source_path.as_uri()}?mode=ro"
        source_connection = sqlite3.connect(source_uri, uri=True)
        try:
            if _file_identity(source_path) != source_identity:
                raise RuntimeError("source database changed while opening")
        except FileNotFoundError as error:
            raise RuntimeError("source database changed while opening") from error
        destination_connection = sqlite3.connect(temporary_database)
        source_connection.backup(destination_connection)
        integrity = destination_connection.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            raise sqlite3.DatabaseError("SQLite integrity_check did not return ok")
        destination_connection.close()
        destination_connection = None
        source_connection.close()
        source_connection = None

        _fsync(temporary_database)
        os.chmod(temporary_database, 0o600)
        _fsync(temporary_database)
        sha256 = _checksum(temporary_database)

        temporary_checksum = destination_path / (
            f".{database_path.name}-{uuid4().hex}.tmp"
        )
        with temporary_checksum.open("x", encoding="utf-8", newline="\n") as checksum_file:
            checksum_file.write(f"{sha256}\n")
            checksum_file.flush()
            os.fsync(checksum_file.fileno())
        os.chmod(temporary_checksum, 0o600)
        _fsync(temporary_checksum)

        _publish_without_overwrite(temporary_checksum, checksum_path)
        temporary_checksum = None
        _publish_without_overwrite(temporary_database, database_path)
        temporary_database = None
        _fsync_destination_directory(destination_path)
        return BackupResult(database_path, checksum_path, sha256)
    finally:
        if destination_connection is not None:
            destination_connection.close()
        if source_connection is not None:
            source_connection.close()
        _remove_if_present(temporary_checksum)
        _remove_if_present(temporary_database)


def _parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="SQLite database to snapshot")
    parser.add_argument(
        "--destination",
        required=True,
        type=Path,
        help="independently persisted directory for backup artifacts",
    )
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    args = _parse_arguments(arguments)
    try:
        result = backup_database(args.source, args.destination)
    except Exception as error:
        print(f"backup failed: {error}", file=sys.stderr)
        return 1

    print(result.database_path)
    print(result.checksum_path)
    print(result.sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
