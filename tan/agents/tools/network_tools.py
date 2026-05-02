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
def initiate_uplink_configuration_adjustment(*, enodeb_id: str, cell_id: str) -> dict[str, Any]:
    """Stub for an automated remediation action."""
    return {
        "status": "success",
        "details": (
            "Uplink adjustment request has been issued. It can take up to an hour for "
            "the changes to take effect."
        ),
    }
