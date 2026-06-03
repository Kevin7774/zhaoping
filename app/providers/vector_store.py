from __future__ import annotations

import atexit
from typing import Callable, Protocol


class VectorStore(Protocol):
    def upsert_chunks(
        self,
        candidate_id: str,
        chunks: list[str],
        embeddings,
        point_id_fn: Callable[[str, int], int],
    ) -> None:
        raise NotImplementedError

    def search(self, query_vector: list[float], top_k: int = 5, filters: dict | None = None) -> list[dict]:
        raise NotImplementedError


class QdrantLocalVectorStore:
    def __init__(self, path: str, collection_name: str, vector_size: int, distance: str = "cosine") -> None:
        self.path = path
        self.collection_name = collection_name
        self.vector_size = vector_size
        self.distance = distance
        self._client = None
        self._close_registered = False

    def upsert_chunks(
        self,
        candidate_id: str,
        chunks: list[str],
        embeddings,
        point_id_fn: Callable[[str, int], int],
    ) -> None:
        from qdrant_client.models import PointStruct

        client = self._get_client()
        points = []
        for index, (chunk, vector) in enumerate(zip(chunks, embeddings)):
            points.append(
                PointStruct(
                    id=point_id_fn(candidate_id, index),
                    vector=vector.tolist(),
                    payload={
                        "candidate_id": candidate_id,
                        "chunk_index": index,
                        "content": chunk,
                    },
                )
            )
        client.upsert(collection_name=self.collection_name, points=points)

    def search(self, query_vector: list[float], top_k: int = 5, filters: dict | None = None) -> list[dict]:
        client = self._get_client()
        query_filter = self._build_filter(filters)

        if hasattr(client, "query_points"):
            result = client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
            points = result.points
        else:
            points = client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )

        return [
            {
                "id": point.id,
                "score": point.score,
                "payload": point.payload or {},
            }
            for point in points
        ]

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import qdrant_client
            from qdrant_client.models import Distance, VectorParams
        except ImportError as exc:
            raise RuntimeError("qdrant-client is required for local vector storage.") from exc

        distance = {
            "cosine": Distance.COSINE,
            "dot": Distance.DOT,
            "euclid": Distance.EUCLID,
        }.get(self.distance.lower())
        if distance is None:
            raise ValueError(f"Unsupported Qdrant distance: {self.distance}")

        self._client = qdrant_client.QdrantClient(path=self.path)
        if not self._close_registered:
            atexit.register(self.close)
            self._close_registered = True
        if not self._client.collection_exists(collection_name=self.collection_name):
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=distance),
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    @staticmethod
    def _build_filter(filters: dict | None):
        if not filters:
            return None
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        return Filter(
            must=[
                FieldCondition(key=key, match=MatchValue(value=value))
                for key, value in filters.items()
            ]
        )
