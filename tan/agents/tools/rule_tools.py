"""Vector Search tools — RCA rules retrieval and prior-incident similarity search."""

from __future__ import annotations

import logging
from typing import Any

import mlflow

from tan.agents.embeddings import Embedder
from tan.agents.sql import SqlClient
from tan.agents.vsearch import VectorIndex
from tan.settings import Settings

logger = logging.getLogger(__name__)


@mlflow.trace(span_type="TOOL", name="find_rca_rules")
def find_rca_rules(
    rules_index: VectorIndex,
    *,
    missed_kpis: list[str],
    description: str,
    k: int = 5,
) -> dict[str, Any]:
    """Search the RCA rules index for entries that match the violated KPIs.

    The upstream demo filtered the Vertex AI Search datastore by
    `kpi_missed: ANY(...)`. We pass the same filter to Databricks Vector Search.
    """
    filter_clause = {"kpi_missed": missed_kpis} if missed_kpis else None

    query_text = description or " ".join(missed_kpis) or "telco rca"
    rows = rules_index.query_text(
        query_text=query_text,
        columns=[
            "id",
            "description",
            "processing_rule",
            "processing_rule_tools",
            "severity_determination_rule",
            "severity_determination_rule_tools",
            "vendor",
            "author",
        ],
        num_results=k,
        filters=filter_clause,
    )

    return {
        "status": "success" if rows else "no_results",
        "count": len(rows),
        "rules": rows,
    }


@mlflow.trace(span_type="TOOL", name="prior_incident_search")
def prior_incident_search(
    incidents_index: VectorIndex,
    embedder: Embedder,
    *,
    events_text: str,
    k: int = 5,
    cutoff: float = 0.5,
) -> dict[str, Any]:
    """Find historical incidents whose `events` text is semantically similar."""
    rows = incidents_index.query_text(
        query_text=events_text,
        columns=[
            "incident_id",
            "start_ts",
            "end_ts",
            "status",
            "description",
            "events",
            "enodeb_id",
            "cell_id",
            "cause",
            "severity",
            "final_analysis",
            "preliminary_analysis",
            "resolution",
        ],
        num_results=k,
    )

    # Vector Search returns a `score` column; keep only rows above the cutoff.
    matches = [r for r in rows if r.get("score", 1.0) >= cutoff]
    return {
        "status": "success" if matches else "no_matches",
        "count": len(matches),
        "prior_incidents": matches,
    }
