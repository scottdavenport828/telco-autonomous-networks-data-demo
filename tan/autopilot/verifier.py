"""Auto-verification: confirm KPI recovery, mark actions VERIFIED, close incidents."""

from __future__ import annotations

from pyspark.sql import SparkSession

from tan.autopilot.state import is_enabled


def verify_and_close(
    spark: SparkSession,
    *,
    catalog: str,
    schema: str,
    erab_threshold: float = 97.0,
    retain_threshold: float = 3.0,
    recovery_windows: int = 1,
) -> tuple[int, int]:
    """For each APPLIED action, check the affected cell's last few KPI windows.
    If the violated KPI is back inside threshold for ``recovery_windows``
    consecutive periods, mark the action VERIFIED and the incident RESOLVED.

    Returns (actions_verified, incidents_closed).
    """
    state_table = f"{catalog}.{schema}.autopilot_state"
    if not is_enabled(spark, table=state_table):
        print("autopilot disabled; skipping verifier")
        return 0, 0

    actions_table = f"{catalog}.{schema}.actions_taken"
    perf_kpi = f"{catalog}.{schema}.performance_kpi"
    incidents_table = f"{catalog}.{schema}.incidents"

    # Find APPLIED actions whose cell has been healthy for the last N
    # post-application windows. Crucially, only KPI rows whose
    # ``measurement_end`` is AFTER the action's ``applied_ts`` count toward
    # recovery — anything earlier is pre-existing data, not evidence of fix.
    eligible = spark.sql(
        f"""
WITH applied AS (
  SELECT id, incident_id, cast(enodeb_id AS string) AS enodeb_id,
         cast(cell_id   AS string) AS cell_id, applied_ts
  FROM {actions_table}
  WHERE status = 'APPLIED'
    AND applied_ts > current_timestamp() - INTERVAL 6 HOURS
),
post_apply AS (
  SELECT a.id, a.incident_id, a.enodeb_id, a.cell_id, a.applied_ts,
         p.measurement_end, p.erab_success_rate, p.retainability,
         row_number() OVER (
           PARTITION BY a.id
           ORDER BY p.measurement_end DESC
         ) AS rn
  FROM applied a
  JOIN {perf_kpi} p
    ON cast(p.enodeb_id AS string) = a.enodeb_id
   AND cast(p.cell_id   AS string) = a.cell_id
  WHERE p.measurement_end > a.applied_ts
),
healthy AS (
  SELECT id AS action_id, incident_id,
         SUM(CASE WHEN (erab_success_rate IS NULL OR erab_success_rate >= {erab_threshold})
                   AND (retainability IS NULL OR retainability <= {retain_threshold})
                  THEN 1 ELSE 0 END) AS healthy_windows,
         COUNT(*) AS total_windows
  FROM post_apply
  WHERE rn <= {recovery_windows}
  GROUP BY id, incident_id
)
SELECT action_id, incident_id
FROM healthy
WHERE healthy_windows = total_windows
  AND total_windows >= {recovery_windows}
"""
    ).collect()

    if not eligible:
        print("autopilot/verifier: no eligible recoveries yet")
        return 0, 0

    action_ids = [r.action_id for r in eligible]
    incident_ids = list({r.incident_id for r in eligible})

    spark.sql(
        f"""
UPDATE {actions_table}
SET status = 'VERIFIED',
    verified_ts = current_timestamp(),
    result_note = 'KPI recovered for the last {recovery_windows} windows'
WHERE id IN ({", ".join(f"'{i}'" for i in action_ids)})
"""
    )
    spark.sql(
        f"""
UPDATE {incidents_table}
SET status = 'RESOLVED',
    end_ts = current_timestamp(),
    resolution = coalesce(resolution, 'Auto-remediated and recovery verified')
WHERE incident_id IN ({", ".join(f"'{i}'" for i in incident_ids)})
"""
    )
    print(
        f"autopilot/verifier: verified {len(action_ids)} actions and closed {len(incident_ids)} incidents"
    )
    return len(action_ids), len(incident_ids)
