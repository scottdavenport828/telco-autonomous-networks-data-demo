"""Thin wrapper around the native FMAPI `databricks-claude-opus-4-7` endpoint.

The endpoint exposes the standard OpenAI-style `llm/v1/chat` surface, so we
use OpenAI-compatible request/response shapes. Unity AI Gateway features
(rate limits, usage tracking, inference table, PII guardrails) are applied
to this endpoint by `notebooks/04_apply_ai_gateway.py`.

The PII guardrail is strict about request schema — it rejects any field that
is not part of the OpenAI chat contract (e.g. the `id` field that
`ChatAgentMessage.model_dump()` emits). `_clean_message()` strips those out.
"""

from __future__ import annotations

from typing import Any

from mlflow.deployments import get_deploy_client

# Fields the FMAPI / AI Gateway accepts on a chat message.
_ALLOWED_FIELDS = {"role", "content", "name", "tool_calls", "tool_call_id"}


def _clean_message(msg: dict[str, Any]) -> dict[str, Any]:
    cleaned = {k: v for k, v in msg.items() if k in _ALLOWED_FIELDS and v is not None}
    if "tool_calls" in cleaned:
        # tool_calls is a list of {id, type, function:{name, arguments}}; pass through
        # unchanged but ensure inner dicts are also clean dicts (not Pydantic objects).
        cleaned["tool_calls"] = [
            {
                "id": tc.get("id"),
                "type": tc.get("type", "function"),
                "function": {
                    "name": tc.get("function", {}).get("name"),
                    "arguments": tc.get("function", {}).get("arguments", ""),
                },
            }
            for tc in cleaned["tool_calls"]
        ]
    return cleaned


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
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        # Note: Claude Opus 4.7 has extended thinking and does not accept
        # `temperature`. We omit it so the same code path works on opus-4-7,
        # opus-4-6, sonnet-4-6, etc.
        payload: dict[str, Any] = {
            "messages": [_clean_message(m) for m in messages],
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        return self._client.predict(endpoint=self.endpoint, inputs=payload)
