"""SqlClient-based runners that mirror the Spark autopilot stages.

The four scheduled jobs (detect/remediate/verify/rca) run inside a Databricks
notebook context with Spark available. The FastAPI app doesn't have Spark, but
it does have a SqlClient pointed at the warehouse — so we re-implement each
stage using only Statement Execution + the existing agent classes.

This keeps the on-demand "run now" buttons in the UI fast (no job-api round
trip, no `jobs` scope required on the OBO token) while the periodic cron
schedule still runs the original Spark version.
"""

from __future__ import annotations

from typing import Any

from tan.agents.sql import SqlClient
from tan.settings import Settings


def is_enabled(sql: SqlClient, settings: Settings) -> bool:
    rows = sql.query(
        f"SELECT value FROM {settings.catalog}.{settings.schema}.autopilot_state WHERE key = 'enabled'"
    )
    if not rows:
        return False
    v = rows[0].get("value")
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() == "true"


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------


def detect(sql: SqlClient, settings: Settings) -> dict[str, Any]:
    """Single SQL pass: find violations not already covered by an open incident,
    INSERT one row per (cell, kpi). Returns the count created.
    """
    if not is_enabled(sql, settings):
        return {"stage": "detect", "skipped": "autopilot disabled", "count": 0}

    perf_kpi = settings.perf_kpi_view
    incidents = settings.incidents_table
    erab = settings.erab_success_rate_threshold
    retain = settings.retainability_threshold

    # Count first, then insert (the count CTE is identical to the insert's source,
    # so the operator gets a meaningful number returned without a row.count_changes
    # round-trip).
    new_count_sql = f"""
WITH recent AS (
  SELECT enodeb_id, cell_id,
         AVG(erab_success_rate) AS avg_erab,
         AVG(retainability) AS avg_retain
  FROM {perf_kpi}
  WHERE measurement_end > current_timestamp() - INTERVAL 60 MINUTES
  GROUP BY enodeb_id, cell_id
),
violations AS (
  SELECT enodeb_id, cell_id, 'erab_success_rate' AS kpi
  FROM recent WHERE avg_erab IS NOT NULL AND avg_erab < {erab}
  UNION ALL
  SELECT enodeb_id, cell_id, 'retainability' AS kpi
  FROM recent WHERE avg_retain IS NOT NULL AND avg_retain > {retain}
),
open_incidents AS (
  SELECT cast(enodeb_id AS string) AS enodeb_id,
         cast(cell_id AS string)   AS cell_id,
         k.kpi                     AS kpi
  FROM {incidents}
  LATERAL VIEW INLINE(kpi_missed) k AS kpi, value
  WHERE status IN ('NEW', 'ANALYZED', 'IN_PROGRESS')
)
SELECT COUNT(*) AS n
FROM violations v
LEFT ANTI JOIN open_incidents o
  ON cast(v.enodeb_id AS string) = o.enodeb_id
 AND cast(v.cell_id AS string)   = o.cell_id
 AND v.kpi = o.kpi
"""
    new_count = int(sql.query(new_count_sql)[0]["n"]) if sql.query(new_count_sql) else 0
    if new_count == 0:
        return {"stage": "detect", "count": 0}

    insert_sql = f"""
INSERT INTO {incidents}
WITH recent AS (
  SELECT enodeb_id, cell_id,
         AVG(erab_success_rate) AS avg_erab,
         AVG(retainability) AS avg_retain,
         MIN(measurement_end) AS earliest,
         MAX(measurement_end) AS latest
  FROM {perf_kpi}
  WHERE measurement_end > current_timestamp() - INTERVAL 60 MINUTES
  GROUP BY enodeb_id, cell_id
),
violations AS (
  SELECT enodeb_id, cell_id, 'erab_success_rate' AS kpi, avg_erab AS kpi_value, earliest, latest
  FROM recent WHERE avg_erab IS NOT NULL AND avg_erab < {erab}
  UNION ALL
  SELECT enodeb_id, cell_id, 'retainability' AS kpi, avg_retain AS kpi_value, earliest, latest
  FROM recent WHERE avg_retain IS NOT NULL AND avg_retain > {retain}
),
open_incidents AS (
  SELECT cast(enodeb_id AS string) AS enodeb_id,
         cast(cell_id AS string)   AS cell_id,
         k.kpi                     AS kpi
  FROM {incidents}
  LATERAL VIEW INLINE(kpi_missed) k AS kpi, value
  WHERE status IN ('NEW', 'ANALYZED', 'IN_PROGRESS')
),
new_violations AS (
  SELECT v.*
  FROM violations v
  LEFT ANTI JOIN open_incidents o
    ON cast(v.enodeb_id AS string) = o.enodeb_id
   AND cast(v.cell_id AS string)   = o.cell_id
   AND v.kpi = o.kpi
)
SELECT
  uuid()                                 AS incident_id,
  earliest                               AS start_ts,
  latest                                 AS end_ts,
  'NEW'                                  AS status,
  CASE WHEN kpi = 'erab_success_rate'
       THEN 'ERAB success rate is below {erab:.0f}%'
       ELSE 'Retainability is above {retain}' END                  AS description,
  ARRAY(NAMED_STRUCT('kpi', kpi, 'value', kpi_value))              AS kpi_missed,
  cast(enodeb_id AS string)              AS enodeb_id,
  cast(cell_id AS string)                AS cell_id,
  CAST(NULL AS string)                   AS severity,
  CAST(NULL AS string)                   AS preliminary_analysis,
  CAST(NULL AS string)                   AS final_analysis,
  CAST(NULL AS string)                   AS events,
  CAST(ARRAY() AS array<double>)         AS events_embeddings,
  CAST(NULL AS string)                   AS cause,
  CAST(NULL AS string)                   AS resolution,
  current_timestamp()                    AS created_ts
FROM new_violations
"""
    sql.execute(insert_sql)
    return {"stage": "detect", "count": new_count}


# ---------------------------------------------------------------------------
# remediate
# ---------------------------------------------------------------------------


def remediate(sql: SqlClient, settings: Settings, max_per_run: int = 10) -> dict[str, Any]:
    if not is_enabled(sql, settings):
        return {"stage": "remediate", "skipped": "autopilot disabled", "count": 0}

    actions = f"{settings.catalog}.{settings.schema}.actions_taken"
    schedule = f"{settings.catalog}.{settings.schema}.anomaly_schedule"
    incidents = settings.incidents_table

    proposed = sql.query(
        f"""
SELECT id, incident_id, enodeb_id, cell_id
FROM {actions}
WHERE status = 'PROPOSED'
ORDER BY created_ts
LIMIT {max_per_run}
"""
    )
    if not proposed:
        return {"stage": "remediate", "count": 0}

    n = 0
    for a in proposed:
        sql.execute(
            f"""
UPDATE {actions}
SET status = 'APPLIED',
    applied_ts = current_timestamp(),
    result_note = 'Healing anomaly scheduled for 30 minutes'
WHERE id = '{a["id"]}'
"""
        )
        sql.execute(
            f"""
INSERT INTO {schedule}
  (id, enodeb_id, cell_id, kpi, start_ts, end_ts, magnitude, note, status, created_ts)
VALUES
  (uuid(), '{a["enodeb_id"]}', '{a["cell_id"]}', 'erab_success_rate',
   current_timestamp(),
   current_timestamp() + INTERVAL 30 MINUTES,
   0.99, 'autopilot heal for action {a["id"]}', 'PENDING', current_timestamp())
"""
        )
        sql.execute(
            f"""
UPDATE {incidents}
SET status = 'IN_PROGRESS'
WHERE incident_id = '{a["incident_id"]}' AND status = 'NEW'
"""
        )
        n += 1
    return {"stage": "remediate", "count": n}


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def verify(sql: SqlClient, settings: Settings, recovery_windows: int = 1) -> dict[str, Any]:
    if not is_enabled(sql, settings):
        return {"stage": "verify", "skipped": "autopilot disabled", "actions": 0, "incidents": 0}

    actions = f"{settings.catalog}.{settings.schema}.actions_taken"
    perf_kpi = settings.perf_kpi_view
    incidents = settings.incidents_table
    erab = settings.erab_success_rate_threshold
    retain = settings.retainability_threshold

    eligible = sql.query(
        f"""
WITH applied AS (
  SELECT id, incident_id, cast(enodeb_id AS string) AS enodeb_id,
         cast(cell_id AS string) AS cell_id, applied_ts
  FROM {actions}
  WHERE status = 'APPLIED'
    AND applied_ts > current_timestamp() - INTERVAL 6 HOURS
),
post_apply AS (
  SELECT a.id, a.incident_id, p.measurement_end,
         p.erab_success_rate, p.retainability,
         row_number() OVER (PARTITION BY a.id ORDER BY p.measurement_end DESC) AS rn
  FROM applied a
  JOIN {perf_kpi} p
    ON cast(p.enodeb_id AS string) = a.enodeb_id
   AND cast(p.cell_id AS string)   = a.cell_id
  WHERE p.measurement_end > a.applied_ts
),
healthy AS (
  SELECT id AS action_id, incident_id,
         SUM(CASE WHEN (erab_success_rate IS NULL OR erab_success_rate >= {erab})
                   AND (retainability IS NULL OR retainability <= {retain})
                  THEN 1 ELSE 0 END) AS healthy_w,
         COUNT(*) AS total_w
  FROM post_apply
  WHERE rn <= {recovery_windows}
  GROUP BY id, incident_id
)
SELECT action_id, incident_id
FROM healthy
WHERE healthy_w = total_w AND total_w >= {recovery_windows}
"""
    )
    if not eligible:
        return {"stage": "verify", "actions": 0, "incidents": 0}

    action_ids = [r["action_id"] for r in eligible]
    incident_ids = list({r["incident_id"] for r in eligible})

    sql.execute(
        f"""
UPDATE {actions}
SET status = 'VERIFIED',
    verified_ts = current_timestamp(),
    result_note = 'KPI recovered for the last {recovery_windows} window(s)'
WHERE id IN ({", ".join(f"'{i}'" for i in action_ids)})
"""
    )
    sql.execute(
        f"""
UPDATE {incidents}
SET status = 'RESOLVED',
    end_ts = current_timestamp(),
    resolution = coalesce(resolution, 'Auto-remediated and recovery verified')
WHERE incident_id IN ({", ".join(f"'{i}'" for i in incident_ids)})
"""
    )
    return {
        "stage": "verify",
        "actions": len(action_ids),
        "incidents": len(incident_ids),
    }


# ---------------------------------------------------------------------------
# rca — invokes the agent class directly (no Spark needed by the agent)
# ---------------------------------------------------------------------------


def rca(sql: SqlClient, settings: Settings, max_per_run: int = 1) -> dict[str, Any]:
    """Run one RCA pass inline. Default max_per_run=1: agent loops take
    30–60s and FastAPI keep-alive starts to look bad past 90s. The cron
    job picks up the rest in the background."""
    if not is_enabled(sql, settings):
        return {"stage": "rca", "skipped": "autopilot disabled", "count": 0}

    pending = sql.query(
        f"""
SELECT incident_id
FROM {settings.incidents_table}
WHERE status = 'NEW' AND preliminary_analysis IS NULL
ORDER BY created_ts
LIMIT {max_per_run}
"""
    )
    if not pending:
        return {"stage": "rca", "count": 0, "pending_remaining": 0}

    from tan.agents._chat_compat import ChatAgentMessage  # noqa: PLC0415
    from tan.agents.rca_orchestrator import RcaOrchestratorAgent  # noqa: PLC0415

    agent = RcaOrchestratorAgent()
    successes: list[str] = []
    failures: list[dict[str, str]] = []
    for r in pending:
        prompt = (
            f"Analyse incident {r['incident_id']}. Skip every user-confirmation "
            "prompt and run all RCA steps. When finished, call update_incident "
            "with the final report, severity, events, cause, and resolution. "
            "Then stop."
        )
        try:
            agent.predict([ChatAgentMessage(role="user", content=prompt)])
            successes.append(r["incident_id"])
        except Exception as exc:  # noqa: BLE001
            failures.append(
                {"incident_id": r["incident_id"], "error": f"{type(exc).__name__}: {exc}"[:400]}
            )

    remaining_rows = sql.query(
        f"SELECT COUNT(*) AS n FROM {settings.incidents_table} WHERE status = 'NEW' AND preliminary_analysis IS NULL"
    )
    pending_remaining = int(remaining_rows[0]["n"]) if remaining_rows else 0

    return {
        "stage": "rca",
        "count": len(successes),
        "succeeded": successes,
        "failed": failures,
        "pending_remaining": pending_remaining,
    }
