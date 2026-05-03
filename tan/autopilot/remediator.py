"""Auto-remediation: apply PROPOSED actions and schedule a self-healing anomaly.

The agent's analyzer subagent records suggested actions in `actions_taken`
(via the modified `initiate_uplink_configuration_adjustment` tool). The
remediator promotes them PROPOSED -> APPLIED and writes a "healing"
anomaly_schedule row that pushes the cell's KPI back toward (or above) baseline
for the next ~30 minutes — the streaming generator picks it up on the next tick.

Real-network analogue: this would actually call into the OSS to adjust uplink
power. For demo, biasing the synthetic feed back to healthy values closes the
visual loop.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from pyspark.sql import SparkSession

from tan.autopilot.state import is_enabled


def apply_proposed_actions(
    spark: SparkSession, *, catalog: str, schema: str, max_per_run: int = 10
) -> int:
    state_table = f"{catalog}.{schema}.autopilot_state"
    if not is_enabled(spark, table=state_table):
        print("autopilot disabled; skipping remediator")
        return 0

    actions_table = f"{catalog}.{schema}.actions_taken"
    anomaly_table = f"{catalog}.{schema}.anomaly_schedule"
    incidents_table = f"{catalog}.{schema}.incidents"

    proposed = (
        spark.read.table(actions_table)
        .filter("status = 'PROPOSED'")
        .orderBy("created_ts")
        .limit(max_per_run)
        .collect()
    )
    if not proposed:
        print("autopilot/remediator: no PROPOSED actions")
        return 0

    now = datetime.now(timezone.utc)
    end = now + timedelta(minutes=30)
    n = 0
    for a in proposed:
        # Schedule a healing anomaly: target a healthy ERAB rate (0.99) or low
        # retainability (1.0). Heuristic — use the action's recorded KPI when
        # available; fall back to ERAB.
        kpi = "erab_success_rate"
        magnitude = 0.99
        # Mark APPLIED.
        spark.sql(
            f"""
UPDATE {actions_table}
SET status = 'APPLIED',
    applied_ts = current_timestamp(),
    result_note = 'Healing anomaly scheduled until {end.strftime('%Y-%m-%d %H:%M:%S')}'
WHERE id = '{a.id}'
"""
        )
        # Insert healing entry into anomaly_schedule.
        heal_id = str(uuid.uuid4())
        spark.sql(
            f"""
INSERT INTO {anomaly_table}
  (id, enodeb_id, cell_id, kpi, start_ts, end_ts, magnitude, note, status, created_ts)
VALUES
  ('{heal_id}', '{a.enodeb_id}', '{a.cell_id}', '{kpi}',
   current_timestamp(), TIMESTAMP'{end.strftime('%Y-%m-%d %H:%M:%S')}',
   {magnitude}, 'autopilot heal for action {a.id}', 'PENDING', current_timestamp())
"""
        )
        # Move incident to IN_PROGRESS so the operator sees activity.
        spark.sql(
            f"""
UPDATE {incidents_table}
SET status = 'IN_PROGRESS'
WHERE incident_id = '{a.incident_id}' AND status = 'NEW'
"""
        )
        n += 1
        print(f"autopilot/remediator: applied action {a.id} on {a.enodeb_id}/{a.cell_id}")
    return n
