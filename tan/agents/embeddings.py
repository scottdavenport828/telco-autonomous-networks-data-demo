"""Embeddings via Databricks Foundation Model API.

Replaces `tools/embeddings.py` (Vertex AI `gemini-embedding-001`). Default
endpoint is `databricks-gte-large-en` (1024-dim).
"""

from __future__ import annotations

from mlflow.deployments import get_deploy_client


class Embedder:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self._client = get_deploy_client("databricks")

    def embed(self, text: str) -> list[float]:
        response = self._client.predict(endpoint=self.endpoint, inputs={"input": text})
        # FMAPI embedding response: {"data": [{"embedding": [...], "index": 0}], ...}
        return response["data"][0]["embedding"]
