"""Chat endpoints — proxy SSE streams from the agent serving endpoint to the React frontend."""

from __future__ import annotations

import json
from typing import Annotated, Any

from databricks.sdk import WorkspaceClient
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse

from tan.api.deps import get_settings, get_user_client
from tan.settings import Settings

router = APIRouter(prefix="/api/chat", tags=["chat"])


_AGENT_TO_SERVED_ENTITY = {
    "incident-detector": "incident_detector",
    "rca": "rca_orchestrator",
}


@router.post("/{agent}")
def chat(
    agent: str,
    payload: Annotated[dict[str, Any], Body(...)],
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[WorkspaceClient, Depends(get_user_client)],
) -> Any:
    served_entity = _AGENT_TO_SERVED_ENTITY.get(agent)
    if not served_entity:
        raise HTTPException(status_code=400, detail=f"unknown agent: {agent}")

    messages = payload.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="messages array is required")

    # ChatAgent endpoints accept {"messages": [...], "model": "<served_entity>"}
    request_payload = {"messages": messages, "model": served_entity}

    def event_stream():
        # The Databricks SDK's serving_endpoints client doesn't yet expose a
        # streaming helper for ChatAgent; we POST directly via the http client
        # that the SDK already authenticates.
        api_client = client.api_client
        path = f"/serving-endpoints/{settings.agent_endpoint}/served-models/{served_entity}/invocations"
        with api_client.do(
            "POST",
            path,
            body={"input": request_payload, "stream": True},
            stream=True,
        ) as response:
            for line in response.iter_lines():
                if not line:
                    continue
                yield f"data: {line.decode('utf-8')}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{agent}/non-streaming")
def chat_non_streaming(
    agent: str,
    payload: Annotated[dict[str, Any], Body(...)],
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[WorkspaceClient, Depends(get_user_client)],
) -> dict[str, Any]:
    """Non-streaming variant for environments where SSE is awkward."""
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
