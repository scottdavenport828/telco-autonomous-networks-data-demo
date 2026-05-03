"""Auto-detection: scan `performance_kpi` for violations, create new incidents.

This is pure SQL — we don't round-trip the LLM here. The user-facing
`incident_detector` agent does the same thing on demand; the autopilot path
runs deterministically on a schedule for incidents that don't need a human
in the loop. The dedupe rule is "one open incident per (enodeb, cell, kpi)" —
the verifier closes incidents when the cell recovers, which lets the
detector pick up genuinely new violations on the same cell later.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from pyspark.sql import SparkSession

from tan.autopilot.state import is_enabled


@dataclass
class DetectorConfig:
    catalog: str
    schema: str
    erab_threshold: float = 97.0  # below = violation
    retain_threshold: float = 3.0  # above = violation
    window_minutes: int = 60


def detect_and_create(spark: SparkSession, *, config: DetectorConfig) -> int:
    """Insert new incidents for every (enodeb, cell, kpi) currently in violation
    that doesn't already have an open incident. Returns the number created.
    """
    state_table = f"{config.catalog}.{config.schema}.autopilot_state"
    if not is_enabled(spark, table=state_table):
        print("autopilot disabled; skipping detector")
        return 0

    perf_kpi = f"{config.catalog}.{config.schema}.performance_kpi"
    incidents = f"{config.catalog}.{config.schema}.incidents"

    # Find currently-violating (cell, kpi) pairs — averaged over the recent window —
    # that don't already have an open incident.
    candidates = spark.sql(
        f"""
WITH recent AS (
  SELECT enodeb_id, cell_id,
         AVG(erab_success_rate) AS avg_erab,
         AVG(retainability) AS avg_retain,
         MIN(measurement_end) AS earliest,
         MAX(measurement_end) AS latest
  FROM {perf_kpi}
  WHERE measurement_end > current_timestamp() - INTERVAL {config.window_minutes} MINUTES
  GROUP BY enodeb_id, cell_id
),
violations AS (
  SELECT enodeb_id, cell_id, 'erab_success_rate' AS kpi,
         avg_erab AS kpi_value, earliest, latest
  FROM recent
  WHERE avg_erab IS NOT NULL AND avg_erab < {config.erab_threshold}
  UNION ALL
  SELECT enodeb_id, cell_id, 'retainability' AS kpi,
         avg_retain AS kpi_value, earliest, latest
  FROM recent
  WHERE avg_retain IS NOT NULL AND avg_retain > {config.retain_threshold}
),
open_incidents AS (
  SELECT cast(enodeb_id AS string) AS enodeb_id,
         cast(cell_id AS string) AS cell_id,
         k.kpi AS kpi
  FROM {incidents}
  LATERAL VIEW INLINE(kpi_missed) k AS kpi, value
  WHERE status IN ('NEW', 'ANALYZED', 'IN_PROGRESS')
)
SELECT v.*
FROM violations v
LEFT ANTI JOIN open_incidents o
  ON cast(v.enodeb_id AS string) = o.enodeb_id
 AND cast(v.cell_id AS string) = o.cell_id
 AND v.kpi = o.kpi
"""
    ).collect()

    if not candidates:
        return 0

    rows = []
    for r in candidates:
        rows.append(
            (
                str(uuid.uuid4()),
                r.earliest,
                r.latest,
                "NEW",
                f"{'ERAB success rate below ' + str(config.erab_threshold) + '%' if r.kpi == 'erab_success_rate' else 'Retainability above ' + str(config.retain_threshold)}",
                [(r.kpi, float(r.kpi_value))],
                str(r.enodeb_id),
                str(r.cell_id),
                None,  # severity — set by RCA stage
                None,  # preliminary_analysis
                None,  # final_analysis
                None,  # events
                [],    # events_embeddings
                None,  # cause
                None,  # resolution
                datetime.now(timezone.utc),
            )
        )

    target_schema = spark.read.table(incidents).schema
    df = spark.createDataFrame(rows, schema=target_schema)
    df.write.format("delta").mode("append").saveAsTable(incidents)
    print(f"autopilot/detector: created {len(rows)} incidents")
    return len(rows)
