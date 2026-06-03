from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any

from app.providers.document import DoclingDocumentParser


class DoclingOCRProvider(DoclingDocumentParser):
    """OCR provider backed by Docling's document conversion pipeline."""


class AliyunOCRProvider:
    def __init__(
        self,
        access_key_id_env: str,
        access_key_secret_env: str,
        region_id: str,
        endpoint: str,
    ) -> None:
        self.access_key_id_env = access_key_id_env
        self.access_key_secret_env = access_key_secret_env
        self.region_id = region_id
        self.endpoint = endpoint
        self._client = None

    def recognize_general(self, file_path: str | None = None, url: str | None = None) -> dict[str, Any]:
        if not file_path and not url:
            raise ValueError("Either file_path or url is required.")

        from alibabacloud_ocr_api20210707 import models as ocr_models

        client = self._get_client()
        if file_path:
            with Path(file_path).open("rb") as body:
                request = ocr_models.RecognizeGeneralRequest(body=body)
                response = client.recognize_general(request)
        else:
            request = ocr_models.RecognizeGeneralRequest(url=url)
            response = client.recognize_general(request)
        return response.to_map()

    def extract_text(self, file_path: str | None = None, url: str | None = None) -> str:
        data = self.recognize_general(file_path=file_path, url=url)
        body = data.get("body", {})
        text_parts: list[str] = []
        self._collect_text(body, text_parts)
        return "\n".join(part for part in text_parts if part)

    def _get_client(self):
        if self._client is not None:
            return self._client

        from alibabacloud_ocr_api20210707.client import Client
        from alibabacloud_tea_openapi import models as open_api_models

        access_key_id = os.environ.get(self.access_key_id_env)
        access_key_secret = os.environ.get(self.access_key_secret_env)
        if not access_key_id:
            raise RuntimeError(f"Missing required environment variable: {self.access_key_id_env}")
        if not access_key_secret:
            raise RuntimeError(f"Missing required environment variable: {self.access_key_secret_env}")

        config = open_api_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            region_id=self.region_id,
            endpoint=self.endpoint,
        )
        self._client = Client(config)
        return self._client

    def _collect_text(self, value: Any, output: list[str]) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in {"content", "text", "word", "words", "value"} and isinstance(child, str):
                    output.append(child)
                else:
                    self._collect_text(child, output)
        elif isinstance(value, list):
            for child in value:
                self._collect_text(child, output)
        elif isinstance(value, str) and value.strip().startswith(("{", "[")):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return
            self._collect_text(parsed, output)
