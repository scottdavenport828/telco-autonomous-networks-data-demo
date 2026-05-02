"""KPI endpoints — feed the dashboard charts and violation overlays."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from tan.agents.sql import SqlClient
from tan.api.deps import get_settings, get_sql_client
from tan.settings import Settings

router = APIRouter(prefix="/api/kpis", tags=["kpis"])


@router.get("")
def list_kpis(
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    enodeb_id: str | None = Query(default=None),
    cell_id: str | None = Query(default=None),
    limit: int = Query(default=2000, ge=1, le=20000),
) -> dict[str, Any]:
    where = []
    if enodeb_id:
        where.append(f"enodeb_id = '{enodeb_id}'")
    if cell_id:
        where.append(f"cell_id = '{cell_id}'")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows = sql.query(
        f"""
SELECT enodeb_id, cell_id, measurement_end, erab_success_rate, retainability
FROM {settings.perf_kpi_view}
{where_sql}
ORDER BY measurement_end
LIMIT {limit}
"""
    )
    return {
        "thresholds": {
            "erab_success_rate_min": settings.erab_success_rate_threshold,
            "retainability_max": settings.retainability_threshold,
        },
        "rows": rows,
    }


@router.get("/violations")
def list_violations(
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    rows = sql.query(
        f"""
SELECT
  enodeb_id, cell_id,
  COUNT(*) AS violation_windows,
  MIN(measurement_end) AS first_seen,
  MAX(measurement_end) AS last_seen,
  AVG(erab_success_rate) AS avg_erab_success_rate,
  AVG(retainability) AS avg_retainability
FROM {settings.perf_kpi_view}
WHERE erab_success_rate < {settings.erab_success_rate_threshold}
   OR retainability > {settings.retainability_threshold}
GROUP BY enodeb_id, cell_id
ORDER BY violation_windows DESC
"""
    )
    return {"rows": rows}
