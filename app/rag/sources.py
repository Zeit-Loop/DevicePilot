from pathlib import PurePosixPath


def safe_source_document(source: str) -> str | None:
    """Return a safe relative POSIX document path for external metadata."""
    normalized = source.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or ":" in path.parts[0]
    ):
        return None
    return path.as_posix()
