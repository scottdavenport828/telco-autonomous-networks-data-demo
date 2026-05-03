"""Read autopilot_state table — used by every job to decide whether to run."""

from __future__ import annotations

from pyspark.sql import SparkSession


def is_enabled(spark: SparkSession, *, table: str) -> bool:
    rows = (
        spark.read.table(table)
        .filter("key = 'enabled'")
        .select("value")
        .limit(1)
        .collect()
    )
    if not rows:
        return False
    return str(rows[0].value).lower() == "true"
