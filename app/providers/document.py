from __future__ import annotations

from pathlib import Path
from typing import Protocol


class DocumentParser(Protocol):
    def parse(self, file_path: str) -> str:
        raise NotImplementedError


class PlainTextDocumentParser:
    def parse(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Input document does not exist: {file_path}")
        return path.read_text(encoding="utf-8")


class DoclingDocumentParser:
    def __init__(self) -> None:
        self._converter = None

    def parse(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Input document does not exist: {file_path}")
        if self._converter is None:
            try:
                from docling.document_converter import DocumentConverter
            except ImportError as exc:
                raise RuntimeError("docling is required for Docling document parsing.") from exc
            self._converter = DocumentConverter()
        result = self._converter.convert(str(path))
        return result.document.export_to_markdown()


class AutoDocumentParser:
    def __init__(self) -> None:
        self._plain_text = PlainTextDocumentParser()
        self._docling = DoclingDocumentParser()

    def parse(self, file_path: str) -> str:
        path = Path(file_path)
        if path.suffix.lower() in {".md", ".markdown", ".txt"}:
            return self._plain_text.parse(file_path)
        return self._docling.parse(file_path)
