"""Autopilot enable/disable + run-once endpoints.

The four autopilot jobs (detect / rca / remediate / verify) all check
``autopilot_state.key='enabled'`` before doing any work. This router lets the
React UI flip that flag and (optionally) trigger a one-off run.
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from databricks.sdk import WorkspaceClient
from fastapi import APIRouter, Body, Depends, HTTPException

from tan.agents.sql import SqlClient
from tan.api.deps import get_app_client, get_settings, get_sql_client, get_user_client
from tan.settings import Settings

router = APIRouter(prefix="/api/autopilot", tags=["autopilot"])


def _table(settings: Settings) -> str:
    return f"{settings.catalog}.{settings.schema}.autopilot_state"


@router.get("/state")
def get_state(
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    rows = sql.query(f"SELECT key, value, updated_ts FROM {_table(settings)}")
    state = {r["key"]: r["value"] for r in rows}
    return {
        "enabled": (state.get("enabled", "false") or "false").lower() == "true",
        "raw": state,
    }


@router.post("/state")
def set_state(
    payload: Annotated[dict[str, Any], Body(...)],
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    enabled = bool(payload.get("enabled"))
    sql.execute(
        f"""
MERGE INTO {_table(settings)} t
USING (SELECT 'enabled' AS key, '{str(enabled).lower()}' AS value) s
ON t.key = s.key
WHEN MATCHED THEN UPDATE SET t.value = s.value, t.updated_ts = current_timestamp()
WHEN NOT MATCHED THEN INSERT (key, value, updated_ts) VALUES (s.key, s.value, current_timestamp())
"""
    )
    return {"enabled": enabled}


@router.post("/run/{stage}")
def run_stage(
    stage: str,
    client: Annotated[WorkspaceClient, Depends(get_user_client)],
) -> dict[str, Any]:
    """Trigger a one-off run of an autopilot stage by job name suffix.

    Uses the calling user's identity (OBO). The App service principal is not
    granted list/run permissions on the bundle's jobs, but the user is.
    """
    valid = {"detect", "rca", "remediate", "verify"}
    if stage not in valid:
        raise HTTPException(400, f"stage must be one of {sorted(valid)}")
    suffix = f"telco-rca-autopilot-{stage}"
    matches = [j for j in client.jobs.list() if j.settings and j.settings.name and j.settings.name.endswith(suffix)]
    if not matches:
        raise HTTPException(404, f"no job matching '{suffix}'")
    run = client.jobs.run_now(job_id=matches[0].job_id)
    return {"run_id": run.run_id, "job_id": matches[0].job_id, "stage": stage}


@router.get("/recent")
def recent_actions(
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    rows = sql.query(
        f"""
SELECT id, incident_id, action_name, enodeb_id, cell_id, status,
       applied_ts, verified_ts, result_note, created_ts
FROM {settings.catalog}.{settings.schema}.actions_taken
ORDER BY created_ts DESC
LIMIT 50
"""
    )
    return {"rows": rows}
