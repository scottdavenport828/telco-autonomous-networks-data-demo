"""Vector Search helper. Replaces `tools/vertex_ai_search.py`."""

from __future__ import annotations

from typing import Any

from databricks.vector_search.client import VectorSearchClient


class VectorIndex:
    def __init__(self, endpoint: str, index_full_name: str):
        self.endpoint = endpoint
        self.index_full_name = index_full_name
        self._client = VectorSearchClient(disable_notice=True)

    def _index(self):
        return self._client.get_index(endpoint_name=self.endpoint, index_name=self.index_full_name)

    def query_text(
        self,
        query_text: str,
        *,
        columns: list[str],
        num_results: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        result = self._index().similarity_search(
            query_text=query_text,
            columns=columns,
            num_results=num_results,
            filters=filters,
        )
        return _flatten(result)


def _flatten(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten Vector Search result into a list of column dicts."""
    manifest = result.get("manifest", {})
    columns = [c["name"] for c in manifest.get("columns", [])]
    rows = result.get("result", {}).get("data_array", [])
    return [dict(zip(columns, row)) for row in rows]
