"""Build per-cell column profiles from the existing `performance` Delta table.

The output is a long-form table — one row per (enodeb_id, cell_id, column) —
which is easy to broadcast and easy to extend (we can add new statistics like
quantiles or autocorrelation later without changing the shape).
"""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType


# Columns we DO NOT learn distributions for — they're keys, timestamps, or
# string-encoded aggregates (e.g. comma-joined per-QCI sub-counters).
_EXCLUDED = {
    "enodeb_id",
    "cell_id",
    "measurement_end",
    "ERAB_EstabAddAttNbr_QCI",
    "ERAB_EstabAddSuccNbr_QCI",
    "ERAB_SessionTimeQCI_QCI",
}


def _numeric_columns(df: DataFrame) -> list[str]:
    out: list[str] = []
    for f in df.schema.fields:
        if f.name in _EXCLUDED:
            continue
        if f.dataType.simpleString() in ("int", "bigint", "double", "float"):
            out.append(f.name)
    return out


def build_cell_profiles(
    spark: SparkSession,
    *,
    source_table: str,
    target_table: str,
) -> int:
    """Compute statistics per (enodeb_id, cell_id, column) and write to ``target_table``.

    Returns the number of rows written.
    """
    src = spark.read.table(source_table)
    cols = _numeric_columns(src)
    if not cols:
        raise RuntimeError(f"No numeric columns found in {source_table}")

    # Materialise in long form by stacking each numeric column into (col_name, value).
    stack_args = ", ".join([f"'{c}', cast(`{c}` as double)" for c in cols])
    long_df = src.selectExpr(
        "enodeb_id",
        "cell_id",
        f"stack({len(cols)}, {stack_args}) as (column_name, value)",
    ).where(F.col("value").isNotNull())

    profile = (
        long_df.groupBy("enodeb_id", "cell_id", "column_name")
        .agg(
            F.avg("value").alias("mean"),
            F.stddev("value").alias("std"),
            F.min("value").alias("min_val"),
            F.max("value").alias("max_val"),
            F.expr("percentile_approx(value, 0.10)").cast(DoubleType()).alias("p10"),
            F.expr("percentile_approx(value, 0.90)").cast(DoubleType()).alias("p90"),
        )
        .withColumn("computed_ts", F.current_timestamp())
    )

    # Write idempotently: replace the table contents on each run.
    profile.write.format("delta").mode("overwrite").option(
        "overwriteSchema", "true"
    ).saveAsTable(target_table)
    return profile.count()
