"""Thin wrapper around the Databricks AI-Gateway-fronted Claude Opus 4.7 endpoint.

The endpoint is created in `resources/serving_endpoints.yml` as an Anthropic
external model. Because AI Gateway exposes the standard OpenAI-style
`llm/v1/chat` task surface, we use OpenAI-compatible request/response shapes.
"""

from __future__ import annotations

from typing import Any

from mlflow.deployments import get_deploy_client


class GatewayLLM:
    """OpenAI-style chat client that targets a Databricks serving endpoint."""

    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self._client = get_deploy_client("databricks")

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        return self._client.predict(endpoint=self.endpoint, inputs=payload)
