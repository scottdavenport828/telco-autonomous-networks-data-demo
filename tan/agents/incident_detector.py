"""IncidentDetector ChatAgent.

Mirrors `agents/incident_detector/agent.py` from the upstream demo (Google ADK
`LlmAgent` with `get_potential_incidents` and `create_new_incident` tools). The
system prompt is preserved verbatim.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import mlflow
from mlflow.pyfunc import ChatAgent
from mlflow.types.agent import (
    ChatAgentChunk,
    ChatAgentMessage,
    ChatAgentResponse,
    ChatContext,
)

from tan.agents.embeddings import Embedder
from tan.agents.llm import GatewayLLM
from tan.agents.sql import SqlClient
from tan.agents.tools.incident_tools import (
    create_new_incident,
    get_potential_incidents,
)
from tan.settings import SETTINGS, Settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "Get and analyze potential incidents, prioritize based on severity and ask the user "
    "to confirm before creating the new incident."
)

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_potential_incidents",
            "description": (
                "Scan the materialised KPI view for cells violating thresholds. "
                "Returns the list of candidate incidents."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_new_incident",
            "description": (
                "Persist a candidate incident to the incidents table. Use only after the user "
                "has confirmed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "incident_id": {"type": "string"},
                },
                "required": ["incident_id"],
                "additionalProperties": False,
            },
        },
    },
]


class IncidentDetectorAgent(ChatAgent):
    """ChatAgent that detects KPI-violation incidents and persists them on user approval."""

    # Class-level metadata used by the streaming wrapper in `tan/agents/stream.py`
    # so it can drive the loop without importing module-level globals.
    SYSTEM_PROMPT: str = SYSTEM_PROMPT
    TOOL_SPECS: list[dict[str, Any]] = TOOL_SPECS
    MAX_STEPS: int = 8

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        llm: GatewayLLM | None = None,
        sql: SqlClient | None = None,
        embedder: Embedder | None = None,
    ):
        self.settings = settings or SETTINGS
        self.llm = llm or GatewayLLM(self.settings.llm_endpoint)
        self.sql = sql or SqlClient(self.settings.sql_warehouse_id)
        self.embedder = embedder or Embedder(self.settings.embedding_endpoint)

        # Cache the candidate incidents that came back from the most recent
        # get_potential_incidents call so create_new_incident can resolve incident_id.
        self._candidates: dict[str, dict[str, Any]] = {}

    def _llm_chat(self, history: list[dict[str, Any]]) -> dict[str, Any]:
        """Single LLM round trip with this agent's tool specs.

        Both the non-streaming `predict()` and the streaming wrapper in
        `tan/agents/stream.py` go through this helper so they share the same
        request shape and logging.
        """
        return self.llm.chat(history, tools=self.TOOL_SPECS)

    def _execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "get_potential_incidents":
            result = get_potential_incidents(self.sql, self.settings)
            self._candidates = {i["id"]: i for i in result.get("incidents", [])}
            return result
        if name == "create_new_incident":
            incident_id = args["incident_id"]
            candidate = self._candidates.get(incident_id)
            if not candidate:
                return {
                    "status": "error",
                    "reason": f"unknown incident_id {incident_id}; call get_potential_incidents first.",
                }
            return create_new_incident(self.sql, self.settings, incident=candidate)
        return {"status": "error", "reason": f"unknown tool {name}"}

    @mlflow.trace(span_type="AGENT", name="IncidentDetectorAgent.predict")
    def predict(
        self,
        messages: list[ChatAgentMessage],
        context: ChatContext | None = None,
        custom_inputs: dict[str, Any] | None = None,
    ) -> ChatAgentResponse:
        history = [{"role": "system", "content": self.SYSTEM_PROMPT}] + [
            m.model_dump() for m in messages
        ]

        for _step in range(self.MAX_STEPS):  # bound the tool-use loop
            response = self._llm_chat(history)
            choice = response["choices"][0]["message"]
            history.append(choice)

            tool_calls = choice.get("tool_calls") or []
            if not tool_calls:
                content = choice.get("content") or ""
                return ChatAgentResponse(
                    messages=[
                        ChatAgentMessage(id=str(uuid.uuid4()), role="assistant", content=content)
                    ]
                )

            for tc in tool_calls:
                fn = tc["function"]
                args = json.loads(fn.get("arguments") or "{}")
                tool_result = self._execute_tool(fn["name"], args)
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(tool_result, default=str),
                    }
                )

        return ChatAgentResponse(
            messages=[
                ChatAgentMessage(
                    id=str(uuid.uuid4()),
                    role="assistant",
                    content="Tool-use loop limit reached; please retry with a more specific request.",
                )
            ]
        )

    def predict_stream(
        self,
        messages: list[ChatAgentMessage],
        context: ChatContext | None = None,
        custom_inputs: dict[str, Any] | None = None,
    ):
        # Streaming uses the same logic, just yields a single chunk for now.
        result = self.predict(messages, context, custom_inputs)
        for msg in result.messages:
            yield ChatAgentChunk(delta=msg)


# Required when this module is logged via `mlflow.pyfunc.log_model(python_model=<this_file>)`.
AGENT = IncidentDetectorAgent()
mlflow.models.set_model(AGENT)
