"""Streaming wrapper around the agents' tool-use loop.

The deployed Mosaic AI agent endpoint is invoked by `predict()` and returns a
single `ChatAgentResponse`. For the workbench UI we want to surface every
tool call in real time so the right-hand `ToolTrace` pane can render a live
timeline. Streaming through `serving_endpoints.query()` is fiddly because the
ChatAgent contract doesn't expose the per-tool boundary on the wire.

Solution: re-execute the same agent classes **inside** the FastAPI process
for the streaming path, using the same SDK clients, and yield typed events
as the loop progresses. Both `IncidentDetectorAgent` and `RcaOrchestratorAgent`
expose ``_llm_chat(history)`` (single round trip) and ``_execute_tool(name,
args)`` helpers that we drive here while emitting one event per boundary.

Event shapes (each yielded as a ``dict``):

* ``{"type": "tool_start", "id": <call_id>, "name": <tool>, "args": <obj>, "ts_ms": <int>}``
* ``{"type": "tool_end",   "id": <call_id>, "result": <obj>, "elapsed_ms": <int>, "status": "ok"|"error", "error": <str?>}``
* ``{"type": "assistant_message", "content": <str>, "id": <uuid>}``
* ``{"type": "done"}``
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


def _build_history(agent: Any, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prepend the system prompt and normalise the inbound chat messages."""
    return [{"role": "system", "content": agent.SYSTEM_PROMPT}] + [
        {k: v for k, v in m.items() if v is not None} for m in messages
    ]


async def stream_predict(
    agent: Any,
    messages: list[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """Drive ``agent``'s tool-use loop and yield lifecycle events.

    The agent is expected to expose ``SYSTEM_PROMPT``, ``MAX_STEPS``,
    ``_llm_chat(history)``, and ``_execute_tool(name, args)``. Both
    ``IncidentDetectorAgent`` and ``RcaOrchestratorAgent`` provide these
    after the refactor.
    """
    history = _build_history(agent, messages)
    max_steps = agent.MAX_STEPS

    loop = asyncio.get_event_loop()

    for _step_idx in range(max_steps):
        try:
            response = await loop.run_in_executor(None, agent._llm_chat, history)
        except Exception as exc:
            logger.exception("LLM call failed during streaming")
            yield {
                "type": "assistant_message",
                "id": str(uuid.uuid4()),
                "content": f"LLM error: {exc}",
            }
            yield {"type": "done"}
            return

        choice = response["choices"][0]["message"]
        history.append(choice)

        tool_calls = choice.get("tool_calls") or []

        if not tool_calls:
            content = choice.get("content") or ""
            yield {
                "type": "assistant_message",
                "id": str(uuid.uuid4()),
                "content": content,
            }
            yield {"type": "done"}
            return

        # The model asked for one or more tool calls; run them sequentially so
        # the trace pane can render `running` before flipping to `ok`/`error`.
        for tc in tool_calls:
            fn = tc.get("function", {})
            tool_name = fn.get("name", "<unknown>")
            tool_call_id = tc.get("id") or str(uuid.uuid4())
            raw_args = fn.get("arguments") or "{}"
            try:
                parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                parsed_args = {"_raw": raw_args}

            yield {
                "type": "tool_start",
                "id": tool_call_id,
                "name": tool_name,
                "args": parsed_args,
                "ts_ms": int(time.time() * 1000),
            }

            started = time.perf_counter()
            try:
                tool_result = await loop.run_in_executor(
                    None, agent._execute_tool, tool_name, parsed_args
                )
                status = "ok"
                error: str | None = None
            except Exception as exc:  # noqa: BLE001
                logger.exception("tool %s failed", tool_name)
                tool_result = {"status": "error", "reason": str(exc)}
                status = "error"
                error = str(exc)

            elapsed_ms = int((time.perf_counter() - started) * 1000)

            history.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(tool_result, default=str),
                }
            )

            yield {
                "type": "tool_end",
                "id": tool_call_id,
                "result": tool_result,
                "elapsed_ms": elapsed_ms,
                "status": status,
                "error": error,
            }

    # Loop budget exhausted without a final assistant message.
    yield {
        "type": "assistant_message",
        "id": str(uuid.uuid4()),
        "content": "Tool-use loop limit reached; please retry with a more specific request.",
    }
    yield {"type": "done"}
