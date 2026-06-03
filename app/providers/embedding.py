from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    @property
    def vector_size(self) -> int:
        raise NotImplementedError

    def embed_texts(self, texts: list[str]):
        raise NotImplementedError


class SentenceTransformerEmbeddingProvider:
    def __init__(
        self,
        model_name: str,
        vector_size: int,
        device: str = "auto",
        batch_size: int = 8,
        show_progress_bar: bool = True,
    ) -> None:
        self.model_name = model_name
        self._vector_size = vector_size
        self.device = self._resolve_device(device)
        self.batch_size = batch_size
        self.show_progress_bar = show_progress_bar
        self._model = None

    @property
    def vector_size(self) -> int:
        return self._vector_size

    def embed_texts(self, texts: list[str]):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError("sentence-transformers is required for local embedding.") from exc
            self._model = SentenceTransformer(self.model_name, device=self.device)

        embeddings = self._model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=self.show_progress_bar,
        )
        if embeddings.shape[1] != self.vector_size:
            raise ValueError(f"Expected {self.vector_size}-dim embeddings, got {embeddings.shape[1]}.")
        return embeddings

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device != "auto":
            return device
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("torch is required for automatic device selection.") from exc

        if torch.cuda.is_available():
            print(f"正在配置开发设备。当前核心算力硬件: {torch.cuda.get_device_name(0)}")
            return "cuda"
        print("未检测到 CUDA，当前使用 CPU。MVP 可运行，但 4090 加速未启用。")
        return "cpu"
