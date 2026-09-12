from pathlib import Path

from app.rag.chunking import normalize_equipment_type
from app.rag.types import KnowledgeDocument


class DocumentLoadError(ValueError):
    pass


class DocumentLoader:
    SUPPORTED_EXTENSIONS = frozenset({".md", ".txt"})

    def __init__(self, root: Path, *, max_bytes: int = 1_000_000) -> None:
        self.root = root.resolve()
        self.max_bytes = max_bytes

    def paths(self) -> list[Path]:
        if not self.root.exists():
            return []
        return sorted(
            (
                path
                for path in self.root.rglob("*")
                if path.is_file() and path.suffix.lower() in self.SUPPORTED_EXTENSIONS
            ),
            key=lambda path: path.relative_to(self.root).as_posix(),
        )

    def load_all(self) -> list[KnowledgeDocument]:
        return [self.load(path) for path in self.paths()]

    def load(self, path: str | Path) -> KnowledgeDocument:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        candidate = candidate.resolve()
        if not candidate.is_relative_to(self.root):
            raise DocumentLoadError("document is outside knowledge root")
        if candidate.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise DocumentLoadError("unsupported document extension")
        try:
            size = candidate.stat().st_size
        except OSError as exc:
            raise DocumentLoadError("document could not be read") from exc
        if size > self.max_bytes:
            raise DocumentLoadError("document exceeds maximum size")
        try:
            raw = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise DocumentLoadError("document could not be read as UTF-8") from exc

        metadata, content = self._parse_frontmatter(raw)
        title = metadata.get("title", "").strip()
        equipment_type = normalize_equipment_type(
            metadata.get("equipment_type", "")
        )
        if not title or not equipment_type or not content.strip():
            raise DocumentLoadError(
                "document requires title, equipment_type, and non-empty content"
            )
        return KnowledgeDocument(
            source=candidate.relative_to(self.root).as_posix(),
            title=title,
            equipment_type=equipment_type,
            content=content.strip(),
        )

    @staticmethod
    def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
        lines = raw.lstrip("\ufeff").splitlines()
        if not lines or lines[0].strip() != "---":
            raise DocumentLoadError("document requires front matter")
        metadata: dict[str, str] = {}
        end_index: int | None = None
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_index = index
                break
            key, separator, value = line.partition(":")
            if not separator:
                raise DocumentLoadError("invalid front matter")
            metadata[key.strip().casefold()] = value.strip()
        if end_index is None:
            raise DocumentLoadError("unterminated front matter")
        return metadata, "\n".join(lines[end_index + 1 :])
