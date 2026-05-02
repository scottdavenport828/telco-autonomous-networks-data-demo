"""Anomaly schedule CRUD.

Lets the demo operator inject a scheduled KPI degradation on a specific cell.
The streaming data generator reads `anomaly_schedule` on every tick and
biases the next batch toward the requested target value, which is what gives
the demo its "click here, watch the agents catch it" loop.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException

from tan.agents.sql import SqlClient
from tan.api.deps import get_settings, get_sql_client
from tan.settings import Settings

router = APIRouter(prefix="/api/anomaly", tags=["anomaly"])


_VALID_KPIS = {"erab_success_rate", "retainability"}


def _table(settings: Settings) -> str:
    return f"{settings.catalog}.{settings.schema}.anomaly_schedule"


@router.get("")
def list_anomalies(
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    rows = sql.query(
        f"""
SELECT id, enodeb_id, cell_id, kpi, start_ts, end_ts, magnitude, note, status, created_ts
FROM {_table(settings)}
WHERE end_ts > current_timestamp() - INTERVAL 24 HOURS
ORDER BY created_ts DESC
LIMIT 50
"""
    )
    return {"rows": rows}


@router.post("")
def create_anomaly(
    payload: Annotated[dict[str, Any], Body(...)],
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Insert an anomaly. Body shape::

        {
          "enodeb_id": "2",
          "cell_id": "22312",
          "kpi": "erab_success_rate" | "retainability",
          "magnitude": 0.85,           # target KPI value
          "duration_minutes": 60,      # optional, default 60
          "note": "..."                # optional
        }
    """
    enodeb_id = str(payload.get("enodeb_id", "")).strip()
    cell_id = str(payload.get("cell_id", "")).strip()
    kpi = str(payload.get("kpi", "")).strip()
    if not enodeb_id or not cell_id:
        raise HTTPException(400, "enodeb_id and cell_id are required")
    if kpi not in _VALID_KPIS:
        raise HTTPException(400, f"kpi must be one of {sorted(_VALID_KPIS)}")
    try:
        magnitude = float(payload["magnitude"])
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(400, f"magnitude must be a number: {e}") from e

    duration = int(payload.get("duration_minutes") or 60)
    if duration <= 0 or duration > 24 * 60:
        raise HTTPException(400, "duration_minutes must be in (0, 1440]")

    now = datetime.now(timezone.utc)
    end = now + timedelta(minutes=duration)
    aid = str(uuid.uuid4())
    note = payload.get("note") or ""

    statement = f"""
INSERT INTO {_table(settings)}
  (id, enodeb_id, cell_id, kpi, start_ts, end_ts, magnitude, note, status, created_ts)
VALUES
  (:id, :enodeb_id, :cell_id, :kpi, :start_ts, :end_ts, :magnitude, :note, 'PENDING', current_timestamp())
"""
    sql.execute(
        statement,
        parameters=[
            {"name": "id", "value": aid},
            {"name": "enodeb_id", "value": enodeb_id},
            {"name": "cell_id", "value": cell_id},
            {"name": "kpi", "value": kpi},
            {"name": "start_ts", "value": now.strftime("%Y-%m-%d %H:%M:%S")},
            {"name": "end_ts", "value": end.strftime("%Y-%m-%d %H:%M:%S")},
            {"name": "magnitude", "value": magnitude, "type": "DOUBLE"},
            {"name": "note", "value": note},
        ],
    )
    return {
        "id": aid,
        "enodeb_id": enodeb_id,
        "cell_id": cell_id,
        "kpi": kpi,
        "start_ts": now.isoformat(),
        "end_ts": end.isoformat(),
        "magnitude": magnitude,
        "note": note,
        "status": "PENDING",
    }


@router.delete("/{anomaly_id}")
def cancel_anomaly(
    anomaly_id: str,
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    sql.execute(
        f"UPDATE {_table(settings)} SET end_ts = current_timestamp(), status = 'COMPLETED' WHERE id = :id",
        parameters=[{"name": "id", "value": anomaly_id}],
    )
    return {"id": anomaly_id, "status": "COMPLETED"}
