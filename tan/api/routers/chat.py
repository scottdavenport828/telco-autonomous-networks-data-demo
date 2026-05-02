"""Chat endpoints.

Two routes:

* ``POST /api/chat/{agent}`` — runs the agent **inside this FastAPI process**
  and streams a typed SSE feed (``tool_start``, ``tool_end``,
  ``assistant_message``, ``done``). The frontend's right-side ``ToolTrace``
  panel renders these events as they arrive. We bypass the deployed
  serving endpoint here because the ChatAgent contract doesn't expose
  per-tool boundaries on the wire.

* ``POST /api/chat/{agent}/non-streaming`` — proxies a single request to
  the deployed serving endpoint and returns the final ChatAgent response.
  Kept for environments where SSE is awkward and for backwards compat with
  any tooling that calls the original route.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from databricks.sdk import WorkspaceClient
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse

from tan.agents.incident_detector import IncidentDetectorAgent
from tan.agents.rca_orchestrator import RcaOrchestratorAgent
from tan.agents.stream import stream_predict
from tan.api.deps import get_settings, get_user_client
from tan.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


_AGENT_TO_SERVED_ENTITY = {
    "incident-detector": "incident_detector",
    "rca": "rca_orchestrator",
}


def _agent_factory(agent_id: str) -> Any:
    """Construct a fresh agent instance for each request.

    A new instance is required because `IncidentDetectorAgent` keeps
    `_candidates` state between turns inside one conversation.
    """
    if agent_id == "incident-detector":
        return IncidentDetectorAgent()
    if agent_id == "rca":
        return RcaOrchestratorAgent()
    raise HTTPException(status_code=400, detail=f"unknown agent: {agent_id}")


@router.post("/{agent}")
async def chat(
    agent: str,
    payload: Annotated[dict[str, Any], Body(...)],
) -> Any:
    """Server-side execution + SSE stream of agent lifecycle events."""
    messages = payload.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="messages array is required")

    agent_instance = _agent_factory(agent)

    async def event_stream():
        try:
            async for event in stream_predict(agent_instance, messages):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as exc:  # noqa: BLE001
            logger.exception("streaming agent failed")
            err_event = {
                "type": "assistant_message",
                "id": "stream-error",
                "content": f"Stream error: {exc}",
            }
            yield f"data: {json.dumps(err_event)}\n\n"
        # Final framing event for clients that key off `event: done`.
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        # Disable proxy buffering so events flush as they're produced.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{agent}/non-streaming")
def chat_non_streaming(
    agent: str,
    payload: Annotated[dict[str, Any], Body(...)],
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[WorkspaceClient, Depends(get_user_client)],
) -> dict[str, Any]:
    """Non-streaming variant for environments where SSE is awkward.

    Proxies to the deployed Mosaic AI agent serving endpoint exactly like
    the original implementation, so the same request shape works whether or
    not we're using the in-process streaming path.
    """
    served_entity = _AGENT_TO_SERVED_ENTITY.get(agent)
    if not served_entity:
        raise HTTPException(status_code=400, detail=f"unknown agent: {agent}")

    response = client.serving_endpoints.query(
        name=settings.agent_endpoint,
        messages=payload["messages"],
        # Route to the right served entity behind this endpoint
        extra_params={"model": served_entity},
    )
    return response.as_dict() if hasattr(response, "as_dict") else json.loads(json.dumps(response, default=str))
