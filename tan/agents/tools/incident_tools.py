"""Tools for the incident lifecycle: detection, creation, retrieval, updates."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import mlflow

from tan.agents.embeddings import Embedder
from tan.agents.sql import SqlClient
from tan.settings import Settings

logger = logging.getLogger(__name__)


@mlflow.trace(span_type="TOOL", name="get_potential_incidents")
def get_potential_incidents(sql: SqlClient, settings: Settings) -> dict[str, Any]:
    """Scan the materialised KPI view for cells that violate thresholds and group them into candidate incidents.

    Returns one row per (enodeb_id, cell_id, kpi) covering a contiguous violation window.
    """
    query = f"""
WITH kpi_metadata AS (
  SELECT * FROM (VALUES
    ('erab_success_rate', 'ERAB success rate is below {settings.erab_success_rate_threshold:.0f}%'),
    ('retainability', 'Retainability is above {settings.retainability_threshold}')
  ) AS t(kpi, description)
),
missed_kpis AS (
  SELECT
    p.enodeb_id, p.cell_id, p.measurement_end,
    m.kpi,
    CASE
      WHEN m.kpi = 'erab_success_rate' THEN p.erab_success_rate
      WHEN m.kpi = 'retainability' THEN p.retainability
    END AS kpi_value
  FROM {settings.perf_kpi_view} p
  CROSS JOIN kpi_metadata m
  WHERE
    (m.kpi = 'erab_success_rate' AND p.erab_success_rate < {settings.erab_success_rate_threshold})
    OR (m.kpi = 'retainability' AND p.retainability > {settings.retainability_threshold})
),
aggregated AS (
  SELECT
    enodeb_id, cell_id, kpi,
    MIN(measurement_end) AS started,
    MAX(measurement_end) AS ended,
    AVG(kpi_value) AS kpi_value
  FROM missed_kpis
  GROUP BY enodeb_id, cell_id, kpi
)
SELECT
  a.enodeb_id, a.cell_id, m.description, a.kpi, a.kpi_value, a.started, a.ended
FROM aggregated a
JOIN kpi_metadata m USING (kpi)
ORDER BY a.kpi_value
"""
    rows = sql.query(query)

    incidents = [
        {
            "id": str(uuid.uuid4()),
            "enodeb_id": r["enodeb_id"],
            "cell_id": r["cell_id"],
            "description": r["description"],
            "kpi": r["kpi"],
            "kpi_value": r["kpi_value"],
            "start_ts": r["started"],
            "end_ts": r["ended"],
            "status": "NEW",
        }
        for r in rows
    ]

    logger.info("get_potential_incidents found %d candidates", len(incidents))
    return {"status": "success", "count": len(incidents), "incidents": incidents}


@mlflow.trace(span_type="TOOL", name="create_new_incident")
def create_new_incident(
    sql: SqlClient,
    settings: Settings,
    *,
    incident: dict[str, Any],
) -> dict[str, Any]:
    """Persist a candidate incident from `get_potential_incidents` to the `incidents` Delta table."""
    statement = f"""
INSERT INTO {settings.incidents_table} (
  incident_id, start_ts, end_ts, status, description,
  kpi_missed, enodeb_id, cell_id, created_ts
) VALUES (
  :incident_id, :start_ts, :end_ts, :status, :description,
  ARRAY(NAMED_STRUCT('kpi', :kpi, 'value', :kpi_value)),
  :enodeb_id, :cell_id, current_timestamp()
)
"""
    parameters = [
        {"name": "incident_id", "value": incident["id"]},
        {"name": "start_ts", "value": str(incident["start_ts"])},
        {"name": "end_ts", "value": str(incident["end_ts"])},
        {"name": "status", "value": incident.get("status", "NEW")},
        {"name": "description", "value": incident["description"]},
        {"name": "kpi", "value": incident["kpi"]},
        {"name": "kpi_value", "value": float(incident["kpi_value"]), "type": "DOUBLE"},
        {"name": "enodeb_id", "value": incident.get("enodeb_id") or ""},
        {"name": "cell_id", "value": incident.get("cell_id") or ""},
    ]
    sql.execute(statement, parameters=parameters)
    return {"status": "success", "incident_id": incident["id"]}


@mlflow.trace(span_type="TOOL", name="get_incident_info")
def get_incident_info(
    sql: SqlClient, settings: Settings, *, incident_id: str
) -> dict[str, Any]:
    rows = sql.query(
        f"""
SELECT
  incident_id, enodeb_id, cell_id, start_ts, end_ts, status, description,
  to_json(kpi_missed) AS kpi_missed_json,
  severity, preliminary_analysis, final_analysis, events, cause, resolution
FROM {settings.incidents_table}
WHERE incident_id = '{incident_id}'
"""
    )
    if not rows:
        return {"status": "not_found", "incident_id": incident_id}

    r = rows[0]
    return {
        "status": "success",
        "incident": {
            **r,
            "kpi_missed": json.loads(r.pop("kpi_missed_json") or "[]"),
        },
    }


@mlflow.trace(span_type="TOOL", name="update_incident")
def update_incident(
    sql: SqlClient,
    settings: Settings,
    embedder: Embedder,
    *,
    incident_id: str,
    report: str,
    severity: str,
    events: str,
    cause: str | None = None,
    resolution: str | None = None,
) -> dict[str, Any]:
    """Update an incident with the final RCA report; embed the events for future similarity search."""
    embedding = embedder.embed(events) if events else []
    embedding_literal = "ARRAY(" + ", ".join(f"CAST({v} AS DOUBLE)" for v in embedding) + ")" if embedding else "ARRAY()"

    sql.execute(
        f"""
UPDATE {settings.incidents_table} SET
  status = 'ANALYZED',
  preliminary_analysis = $$ {report.replace('$$', '$ $')} $$,
  severity = '{severity}',
  events = $$ {events.replace('$$', '$ $')} $$,
  events_embeddings = {embedding_literal},
  cause = {('$$ ' + cause.replace('$$', '$ $') + ' $$') if cause else 'NULL'},
  resolution = {('$$ ' + resolution.replace('$$', '$ $') + ' $$') if resolution else 'NULL'}
WHERE incident_id = '{incident_id}'
"""
    )
    return {"status": "success", "incident_id": incident_id}
