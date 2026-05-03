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


def _truthy(value: Any) -> bool:
    """SqlClient auto-coerces "true"/"false" strings to Python bools, but
    the same column may also come back as a raw string on other code paths.
    Accept both."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


@router.get("/state")
def get_state(
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    rows = sql.query(f"SELECT key, value, updated_ts FROM {_table(settings)}")
    state = {r["key"]: r["value"] for r in rows}
    return {
        "enabled": _truthy(state.get("enabled")),
        "raw": {k: (v if isinstance(v, str) else str(v).lower()) for k, v in state.items()},
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
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Run an autopilot stage **inline** in the FastAPI process.

    Originally this triggered the matching DAB job via WorkspaceClient.jobs.run_now,
    but the OBO token in a Databricks App doesn't carry the `jobs` scope and
    Apps doesn't expose a 'jobs' resource binding to grant it. SQL stages are
    fast (1–5s); RCA can take 30–60s but still completes under FastAPI's
    keep-alive. The cron-scheduled jobs continue to run the Spark version.
    """
    from tan.autopilot.inline import detect, rca, remediate, verify

    if stage == "detect":
        return detect(sql, settings)
    if stage == "remediate":
        return remediate(sql, settings)
    if stage == "verify":
        return verify(sql, settings)
    if stage == "rca":
        return rca(sql, settings)
    raise HTTPException(400, f"unknown stage: {stage}")


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
