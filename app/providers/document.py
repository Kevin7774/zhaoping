from __future__ import annotations

import shutil
import subprocess
import os
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
        try:
            return self._docling.parse(file_path)
        except Exception as exc:
            if path.suffix.lower() == ".pdf":
                return _parse_pdf_with_pdftotext(file_path, exc)
            raise


def _parse_pdf_with_pdftotext(file_path: str, original_error: Exception) -> str:
    if os.environ.get("ZHAOPING_ALLOW_PDF_TEXT_FALLBACK") != "1":
        raise RuntimeError(
            "Refusing low-quality pdftotext fallback for PDF parsing. "
            "Docling/layout parsing failed; fix the Docling runtime or explicitly set "
            "ZHAOPING_ALLOW_PDF_TEXT_FALLBACK=1 for a temporary local-only import."
        ) from original_error
    if not shutil.which("pdftotext"):
        raise RuntimeError(f"Docling document parsing failed and pdftotext is unavailable: {original_error}") from original_error
    result = subprocess.run(
        ["pdftotext", "-layout", file_path, "-"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Docling document parsing failed and pdftotext failed: {result.stderr[:300] or original_error}"
        ) from original_error
    text = result.stdout.strip()
    if not text:
        raise RuntimeError("PDF parsing produced empty text.") from original_error
    return result.stdout
