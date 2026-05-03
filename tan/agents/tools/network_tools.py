"""RAN diagnostic helpers — cell-trace stats and uplink configuration.

Mirrors `agents/root_cause_analysis/tools/analysis_tools.py` from the upstream
demo. The uplink helpers return synthetic but plausible values, exactly as in
the source demo (real network-element APIs are out of scope).
"""

from __future__ import annotations

import logging
from typing import Any

import mlflow

from tan.agents.sql import SqlClient
from tan.settings import Settings

logger = logging.getLogger(__name__)


@mlflow.trace(span_type="TOOL", name="get_cell_trace_statistics")
def get_cell_trace_statistics(
    sql: SqlClient,
    settings: Settings,
    *,
    enodeb_id: str,
    cell_id: str,
    start_ts: str,
    end_ts: str,
) -> dict[str, Any]:
    """Group cell-trace S1 signalling outcomes for a given cell over an incident window."""
    query = f"""
SELECT
  s1_sig_conn_setup_sig_conn_result AS connection_outcome,
  COUNT(*) AS number_of_outcomes
FROM {settings.cell_traces_table}
WHERE start_enodeb_id = '{enodeb_id}'
  AND start_cell_id = '{cell_id}'
  AND starttime >= TIMESTAMP '{start_ts}'
  AND endtime   <= TIMESTAMP '{end_ts}'
GROUP BY s1_sig_conn_setup_sig_conn_result
ORDER BY number_of_outcomes DESC
"""
    rows = sql.query(query)

    stats = [
        {
            "connection_outcome": r.get("connection_outcome") or "OTHER",
            "count": int(r["number_of_outcomes"]),
        }
        for r in rows
    ]
    summary = ", ".join(f"{s['connection_outcome']}: {s['count']}" for s in stats) or "no traces"
    return {
        "status": "success" if stats else "no_data",
        "cell_trace_statistics": stats,
        "summary": summary,
    }


@mlflow.trace(span_type="TOOL", name="get_uplink_rssi_level")
def get_uplink_rssi_level(*, enodeb_id: str, cell_id: str) -> dict[str, Any]:
    """Stub returning a fixed RSSI value, matching the upstream demo semantics."""
    return {"status": "success", "uplink_signal_strength_dbm": "-100"}


@mlflow.trace(span_type="TOOL", name="get_uplink_configuration")
def get_uplink_configuration(*, enodeb_id: str, cell_id: str) -> dict[str, Any]:
    """Stub returning fixed uplink config values, matching the upstream demo semantics."""
    return {
        "status": "success",
        "pZeroNominalPucch": "-110",
        "pZeroNominalPusch": "-94",
    }


@mlflow.trace(span_type="TOOL", name="initiate_uplink_configuration_adjustment")
def initiate_uplink_configuration_adjustment(
    sql: SqlClient,
    settings: Settings,
    *,
    enodeb_id: str,
    cell_id: str,
    incident_id: str | None = None,
) -> dict[str, Any]:
    """Record a PROPOSED remediation action in `actions_taken`.

    The autopilot remediator promotes PROPOSED -> APPLIED on its next run and
    schedules a healing anomaly_schedule entry; the verifier closes the loop
    once the cell's KPI recovers. When called from the human Workbench path
    the row still lands as PROPOSED — pause the autopilot toggle to keep it
    that way and apply manually if you want a hold-and-confirm flow.
    """
    import json
    import uuid

    action_id = str(uuid.uuid4())
    sql.execute(
        f"""
INSERT INTO {settings.catalog}.{settings.schema}.actions_taken
  (id, incident_id, action_name, parameters, enodeb_id, cell_id, status, created_ts)
VALUES
  (:id, :incident_id, :action_name, :parameters, :enodeb_id, :cell_id, 'PROPOSED', current_timestamp())
""",
        parameters=[
            {"name": "id", "value": action_id},
            {"name": "incident_id", "value": incident_id or ""},
            {"name": "action_name", "value": "uplink_configuration_adjustment"},
            {"name": "parameters", "value": json.dumps({"enodeb_id": enodeb_id, "cell_id": cell_id})},
            {"name": "enodeb_id", "value": str(enodeb_id)},
            {"name": "cell_id", "value": str(cell_id)},
        ],
    )
    return {
        "status": "success",
        "action_id": action_id,
        "details": (
            "Uplink adjustment proposed. Autopilot will apply it on the next "
            "remediator tick and verify recovery automatically."
        ),
    }
