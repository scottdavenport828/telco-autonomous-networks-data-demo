"""Vector Search helper. Replaces `tools/vertex_ai_search.py`.

``VectorSearchClient()`` doesn't read ``DATABRICKS_CLIENT_ID`` /
``DATABRICKS_CLIENT_SECRET`` automatically, so when this code runs inside the
Databricks App (where those vars carry the SP creds) the default auth chain
falls through to "no token found" and raises ``InvalidInputException``. Pass
them explicitly when present; fall back to the default chain for local dev
or notebooks where the OS-level PAT is available.
"""

from __future__ import annotations

import os
from typing import Any

from databricks.vector_search.client import VectorSearchClient


def _make_client() -> VectorSearchClient:
    host = os.environ.get("DATABRICKS_HOST")
    if host and not host.startswith("https://"):
        host = "https://" + host
    client_id = os.environ.get("DATABRICKS_CLIENT_ID")
    client_secret = os.environ.get("DATABRICKS_CLIENT_SECRET")
    if host and client_id and client_secret:
        return VectorSearchClient(
            workspace_url=host,
            service_principal_client_id=client_id,
            service_principal_client_secret=client_secret,
            disable_notice=True,
        )
    return VectorSearchClient(disable_notice=True)


class VectorIndex:
    def __init__(self, endpoint: str, index_full_name: str):
        self.endpoint = endpoint
        self.index_full_name = index_full_name
        self._client = _make_client()

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
