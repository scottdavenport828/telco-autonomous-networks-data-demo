"""Incident endpoints."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from tan.agents.sql import SqlClient
from tan.api.deps import get_settings, get_sql_client
from tan.settings import Settings

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


@router.get("")
def list_incidents(
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    rows = sql.query(
        f"""
SELECT
  incident_id, enodeb_id, cell_id, start_ts, end_ts, status, description,
  severity, to_json(kpi_missed) AS kpi_missed_json, created_ts
FROM {settings.incidents_table}
ORDER BY created_ts DESC
LIMIT 200
"""
    )
    for r in rows:
        r["kpi_missed"] = json.loads(r.pop("kpi_missed_json") or "[]")
    return {"rows": rows}


@router.get("/{incident_id}")
def get_incident(
    incident_id: str,
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    rows = sql.query(
        f"""
SELECT
  incident_id, enodeb_id, cell_id, start_ts, end_ts, status, description, severity,
  to_json(kpi_missed) AS kpi_missed_json,
  preliminary_analysis, final_analysis, events, cause, resolution, created_ts
FROM {settings.incidents_table}
WHERE incident_id = '{incident_id}'
"""
    )
    if not rows:
        raise HTTPException(status_code=404, detail="incident not found")

    row = rows[0]
    row["kpi_missed"] = json.loads(row.pop("kpi_missed_json") or "[]")
    return row
