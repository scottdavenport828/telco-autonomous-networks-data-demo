"""Compatibility shims for ``mlflow.pyfunc.ChatAgent`` and friends.

Newer mlflow ships ``ChatAgent`` + the ``mlflow.types.agent.*`` message types as
the canonical Mosaic AI Agent Framework contract. Older mlflow (which is what
ships with the Databricks Apps base image at the time of writing) doesn't have
them yet, which kills FastAPI startup with an ImportError before our App can
even serve ``/api/healthz``.

The runtime streaming path (``tan.agents.stream``) only uses these types as
return shapes, so a duck-typed pydantic shim is sufficient. The MLflow
registration path (notebooks/05_register_and_deploy_agent.py) runs in a
Databricks notebook with a freshly-installed recent mlflow, so it picks up the
real classes.
"""

from __future__ import annotations

from typing import Any, Optional

try:  # mlflow >= 2.16 (ish) ships these natively
    from mlflow.pyfunc import ChatAgent  # type: ignore[attr-defined]
    from mlflow.types.agent import (  # type: ignore[import-not-found]
        ChatAgentChunk,
        ChatAgentMessage,
        ChatAgentResponse,
        ChatContext,
    )

    HAS_NATIVE = True
except ImportError:  # pragma: no cover - depends on installed mlflow
    from pydantic import BaseModel, Field

    HAS_NATIVE = False

    class ChatAgent:  # type: ignore[no-redef]
        """Stand-in base class. Real registrations require the native one."""

        def predict(self, messages, context=None, custom_inputs=None):  # noqa: D401
            raise NotImplementedError

        def predict_stream(self, messages, context=None, custom_inputs=None):
            raise NotImplementedError

    class ChatAgentMessage(BaseModel):  # type: ignore[no-redef]
        id: str = ""
        role: str
        content: Optional[str] = None
        name: Optional[str] = None
        tool_calls: Optional[list[dict[str, Any]]] = None
        tool_call_id: Optional[str] = None

        def model_dump(self, *args, **kwargs):
            kwargs.setdefault("exclude_none", True)
            return super().model_dump(*args, **kwargs)

    class ChatAgentResponse(BaseModel):  # type: ignore[no-redef]
        messages: list[ChatAgentMessage] = Field(default_factory=list)

    class ChatAgentChunk(BaseModel):  # type: ignore[no-redef]
        delta: ChatAgentMessage

    class ChatContext(BaseModel):  # type: ignore[no-redef]
        conversation_id: Optional[str] = None
        user_id: Optional[str] = None


__all__ = [
    "ChatAgent",
    "ChatAgentChunk",
    "ChatAgentMessage",
    "ChatAgentResponse",
    "ChatContext",
    "HAS_NATIVE",
]
