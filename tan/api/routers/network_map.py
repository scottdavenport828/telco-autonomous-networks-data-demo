"""Network map endpoints — cells with KPI status, recent activity feed.

The Map page needs three things:
* a one-shot list of cell sites with their geography + the latest KPI status
  (so it can colour each sector); served by ``GET /api/map/cells``.
* a stream of activity events (anomalies, agent tool calls, incidents) so it
  can animate the map; served by ``GET /api/map/events`` (SSE) with
  ``window`` + ``cap_per_sec`` query params for the visual-density controls.
* a list of currently-active anomalies so the page can mark affected cells
  even when the user opens the page mid-anomaly; served by
  ``GET /api/map/anomalies``.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from tan.agents.sql import SqlClient
from tan.api.deps import get_settings, get_sql_client
from tan.settings import Settings

router = APIRouter(prefix="/api/map", tags=["network_map"])


@router.get("/cells")
def cells(
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """All cell sites with their latest KPI status (last 15 min window)."""
    rows = sql.query(
        f"""
WITH latest AS (
  SELECT enodeb_id, cell_id, erab_success_rate, retainability,
         row_number() OVER (PARTITION BY enodeb_id, cell_id ORDER BY measurement_end DESC) AS rn,
         measurement_end
  FROM {settings.perf_kpi_view}
  WHERE measurement_end > current_timestamp() - INTERVAL 24 HOURS
)
SELECT
  s.enodeb_id, s.cell_id, s.site_name,
  s.lat, s.lon, s.azimuth, s.range_m, s.radio, s.band,
  s.mcc, s.mnc, s.network_name, s.is_active,
  l.erab_success_rate, l.retainability, l.measurement_end AS latest_ts
FROM {settings.catalog}.{settings.schema}.cell_sites s
LEFT JOIN latest l
  ON cast(s.enodeb_id AS string) = cast(l.enodeb_id AS string)
 AND cast(s.cell_id   AS string) = cast(l.cell_id   AS string)
 AND l.rn = 1
"""
    )
    return {
        "rows": rows,
        "thresholds": {
            "erab_success_rate_min": settings.erab_success_rate_threshold,
            "retainability_max": settings.retainability_threshold,
        },
    }


@router.get("/anomalies")
def anomalies(
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    rows = sql.query(
        f"""
SELECT id, enodeb_id, cell_id, kpi, magnitude, start_ts, end_ts, status
FROM {settings.catalog}.{settings.schema}.anomaly_schedule
WHERE end_ts > current_timestamp()
ORDER BY start_ts DESC
LIMIT 50
"""
    )
    return {"rows": rows}


_VALID_WINDOWS = {"5m": 5, "15m": 15, "1h": 60, "24h": 24 * 60}


@router.get("/events")
async def events(
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    window: str = Query(default="15m"),
    cap_per_sec: float = Query(default=4.0, ge=0.1, le=100.0),
    poll_seconds: int = Query(default=5, ge=2, le=30),
) -> Any:
    """SSE feed of activity events (agent calls, anomaly creates, incidents).

    Replays everything in the chosen ``window`` once on connect, then keeps the
    connection open and tails the same tables every ``poll_seconds``. The
    client throttles rendering by ``cap_per_sec`` (separate from the server
    poll cadence) so it controls how busy the map looks.
    """
    minutes = _VALID_WINDOWS.get(window, 15)
    since_filter = f"current_timestamp() - INTERVAL {minutes} MINUTES"

    def _fetch_since(ts_iso: str) -> list[dict[str, Any]]:
        gw = sql.query(
            f"""
SELECT request_time AS ts,
       'agent_call' AS kind,
       databricks_request_id AS id,
       execution_duration_ms AS latency_ms,
       cast(get_json_object(response, '$.usage.prompt_tokens') AS bigint) AS in_tokens,
       cast(get_json_object(response, '$.usage.completion_tokens') AS bigint) AS out_tokens,
       status_code,
       NULL AS enodeb_id,
       NULL AS cell_id,
       NULL AS magnitude,
       NULL AS kpi
FROM {settings.catalog}.{settings.schema}.gw_inference_payload
WHERE request_time > TIMESTAMP'{ts_iso}'
ORDER BY request_time
LIMIT 200
"""
        )
        an = sql.query(
            f"""
SELECT created_ts AS ts,
       'anomaly' AS kind,
       id,
       NULL AS latency_ms,
       NULL AS in_tokens,
       NULL AS out_tokens,
       NULL AS status_code,
       enodeb_id, cell_id, magnitude, kpi
FROM {settings.catalog}.{settings.schema}.anomaly_schedule
WHERE created_ts > TIMESTAMP'{ts_iso}'
ORDER BY created_ts
LIMIT 200
"""
        )
        inc = sql.query(
            f"""
SELECT created_ts AS ts,
       'incident' AS kind,
       incident_id AS id,
       NULL AS latency_ms,
       NULL AS in_tokens,
       NULL AS out_tokens,
       NULL AS status_code,
       cast(enodeb_id AS string) AS enodeb_id,
       cast(cell_id AS string) AS cell_id,
       NULL AS magnitude,
       NULL AS kpi
FROM {settings.incidents_table}
WHERE created_ts > TIMESTAMP'{ts_iso}'
ORDER BY created_ts
LIMIT 200
"""
        )
        merged = gw + an + inc
        merged.sort(key=lambda r: r.get("ts") or "")
        return merged

    # Initial replay anchor: window minutes ago.
    initial_anchor = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    async def event_stream():
        anchor = initial_anchor
        # Initial backfill (replay window).
        try:
            initial = _fetch_since(anchor)
            for ev in initial:
                yield f"data: {json.dumps(ev, default=str)}\n\n"
                if ev.get("ts"):
                    anchor = str(ev["ts"]).replace("T", " ").rstrip("Z")[:19]
        except Exception as exc:  # noqa: BLE001
            yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"

        # Live tail.
        while True:
            await asyncio.sleep(poll_seconds)
            try:
                new = _fetch_since(anchor)
            except Exception as exc:  # noqa: BLE001
                yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"
                continue
            for ev in new:
                yield f"data: {json.dumps(ev, default=str)}\n\n"
                if ev.get("ts"):
                    anchor = str(ev["ts"]).replace("T", " ").rstrip("Z")[:19]
            yield ": keepalive\n\n"

    # cap_per_sec is honoured client-side (it only affects animation pacing).
    _ = cap_per_sec
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
