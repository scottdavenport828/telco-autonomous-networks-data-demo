"""RcaOrchestrator ChatAgent.

Mirrors `agents/root_cause_analysis/agent.py` from the upstream demo:
* the orchestrator delegates to subagents (rules retrieval, instruction
  generation, analysis, severity classification, prior-incident search,
  internal/external doc retrieval, action execution, report generation).
* In this Databricks port the subagents are flattened into Claude tool-use:
  each subagent maps to one tool call. This keeps tracing clean and avoids
  multi-LLM chains where a single LLM with the right tools is sufficient.

System prompt is preserved verbatim from the upstream RCA agent.
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
    get_incident_info,
    update_incident,
)
from tan.agents.tools.network_tools import (
    get_cell_trace_statistics,
    get_uplink_configuration,
    get_uplink_rssi_level,
    initiate_uplink_configuration_adjustment,
)
from tan.agents.tools.rule_tools import find_rca_rules, prior_incident_search
from tan.agents.vsearch import VectorIndex
from tan.settings import SETTINGS, Settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an agent responsible for root cause analysis of incidents in telecommunication networks.

First, obtain the incident id and retrieve the incident information. Don't proceed until you succeeded.

Then, perform the incident processing using the following steps:
1. Retrieve rules related to this incident.
2. Generate specific agent instructions based on these rules.
3. Perform the root cause analysis of the incident using these instructions.
4. Determine the severity level of the incident. The severity must be HIGH, MEDIUM, or LOW.
5. Retrieve external and internal documentation related to the incident (only those tools may search docs).
6. Search for prior incidents similar to the one being analyzed using prior_incident_search.
7. Review and perform any suggested actions if the user agrees.
8. Generate the final report. The report should contain sections:
   1. Incident description
   2. Root cause analysis
   3. Severity level
   4. Similar prior incidents
   5. Internal documentation
   6. External documentation
   7. Recommendations
   8. References (markdown links)

Finally, display the report. Ask the user if they want to update the incident with this report
(call update_incident only after explicit user confirmation).

Indicate progress before executing every step.
"""


def _tool_spec(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


TOOL_SPECS: list[dict[str, Any]] = [
    _tool_spec(
        "get_incident_info",
        "Retrieve incident details (start/end, KPIs, enodeb/cell) by id.",
        {"incident_id": {"type": "string"}},
        ["incident_id"],
    ),
    _tool_spec(
        "find_rca_rules",
        "Retrieve RCA rules whose kpi_missed list intersects the violated KPIs.",
        {
            "missed_kpis": {"type": "array", "items": {"type": "string"}},
            "description": {"type": "string"},
        },
        ["missed_kpis"],
    ),
    _tool_spec(
        "get_cell_trace_statistics",
        "Group cell-trace S1 signalling outcomes for a cell over the incident window.",
        {
            "enodeb_id": {"type": "string"},
            "cell_id": {"type": "string"},
            "start_ts": {"type": "string", "description": "ISO-8601 timestamp"},
            "end_ts": {"type": "string", "description": "ISO-8601 timestamp"},
        },
        ["enodeb_id", "cell_id", "start_ts", "end_ts"],
    ),
    _tool_spec(
        "get_uplink_rssi_level",
        "Read the current uplink RSSI level for a cell (dBm).",
        {"enodeb_id": {"type": "string"}, "cell_id": {"type": "string"}},
        ["enodeb_id", "cell_id"],
    ),
    _tool_spec(
        "get_uplink_configuration",
        "Read the cell's uplink power configuration (pZeroNominalPucch / pZeroNominalPusch).",
        {"enodeb_id": {"type": "string"}, "cell_id": {"type": "string"}},
        ["enodeb_id", "cell_id"],
    ),
    _tool_spec(
        "initiate_uplink_configuration_adjustment",
        "Issue an automated uplink-power adjustment. Only call after user approval.",
        {"enodeb_id": {"type": "string"}, "cell_id": {"type": "string"}},
        ["enodeb_id", "cell_id"],
    ),
    _tool_spec(
        "prior_incident_search",
        "Vector-search for historical incidents whose events are semantically similar.",
        {"events_text": {"type": "string"}, "k": {"type": "integer"}},
        ["events_text"],
    ),
    _tool_spec(
        "update_incident",
        "Persist the final RCA outcome to the incidents table. Call only after user confirmation.",
        {
            "incident_id": {"type": "string"},
            "report": {"type": "string"},
            "severity": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
            "events": {"type": "string"},
            "cause": {"type": "string"},
            "resolution": {"type": "string"},
        },
        ["incident_id", "report", "severity", "events"],
    ),
]


class RcaOrchestratorAgent(ChatAgent):
    # Class-level metadata used by the streaming wrapper in `tan/agents/stream.py`
    # so it can drive the loop without importing module-level globals.
    SYSTEM_PROMPT: str = SYSTEM_PROMPT
    TOOL_SPECS: list[dict[str, Any]] = TOOL_SPECS
    MAX_STEPS: int = 20

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        llm: GatewayLLM | None = None,
        sql: SqlClient | None = None,
        embedder: Embedder | None = None,
        rules_index: VectorIndex | None = None,
        incidents_index: VectorIndex | None = None,
    ):
        self.settings = settings or SETTINGS
        self.llm = llm or GatewayLLM(self.settings.llm_endpoint)
        self.sql = sql or SqlClient(self.settings.sql_warehouse_id)
        self.embedder = embedder or Embedder(self.settings.embedding_endpoint)
        self.rules_index = rules_index or VectorIndex(
            self.settings.vs_endpoint, self.settings.rules_index_full
        )
        self.incidents_index = incidents_index or VectorIndex(
            self.settings.vs_endpoint, self.settings.incidents_index_full
        )

    def _llm_chat(self, history: list[dict[str, Any]]) -> dict[str, Any]:
        """Single LLM round trip with this agent's tool specs.

        Both the non-streaming `predict()` and the streaming wrapper in
        `tan/agents/stream.py` go through this helper so they share the same
        request shape and logging.
        """
        return self.llm.chat(history, tools=self.TOOL_SPECS)

    def _execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "get_incident_info":
            return get_incident_info(self.sql, self.settings, incident_id=args["incident_id"])
        if name == "find_rca_rules":
            return find_rca_rules(
                self.rules_index,
                missed_kpis=args.get("missed_kpis", []),
                description=args.get("description", ""),
            )
        if name == "get_cell_trace_statistics":
            return get_cell_trace_statistics(self.sql, self.settings, **args)
        if name == "get_uplink_rssi_level":
            return get_uplink_rssi_level(**args)
        if name == "get_uplink_configuration":
            return get_uplink_configuration(**args)
        if name == "initiate_uplink_configuration_adjustment":
            return initiate_uplink_configuration_adjustment(**args)
        if name == "prior_incident_search":
            return prior_incident_search(
                self.incidents_index,
                self.embedder,
                events_text=args["events_text"],
                k=args.get("k", self.settings.similarity_search_max_results),
                cutoff=self.settings.similarity_search_cutoff,
            )
        if name == "update_incident":
            return update_incident(
                self.sql,
                self.settings,
                self.embedder,
                incident_id=args["incident_id"],
                report=args["report"],
                severity=args["severity"],
                events=args["events"],
                cause=args.get("cause"),
                resolution=args.get("resolution"),
            )
        return {"status": "error", "reason": f"unknown tool {name}"}

    @mlflow.trace(span_type="AGENT", name="RcaOrchestratorAgent.predict")
    def predict(
        self,
        messages: list[ChatAgentMessage],
        context: ChatContext | None = None,
        custom_inputs: dict[str, Any] | None = None,
    ) -> ChatAgentResponse:
        history = [{"role": "system", "content": self.SYSTEM_PROMPT}] + [
            m.model_dump() for m in messages
        ]

        for _step in range(self.MAX_STEPS):
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
        result = self.predict(messages, context, custom_inputs)
        for msg in result.messages:
            yield ChatAgentChunk(delta=msg)


AGENT = RcaOrchestratorAgent()
mlflow.models.set_model(AGENT)
