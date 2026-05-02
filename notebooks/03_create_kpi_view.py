# Databricks notebook source
# MAGIC %md
# MAGIC # 03_create_kpi_view
# MAGIC
# MAGIC Lakeflow Declarative Pipeline that materialises the `performance_kpi` view
# MAGIC equivalent to the source's BigQuery materialised view
# MAGIC (`infrastructure/terraform/bigquery-schema/performance_kpi.sql.tftpl`).
# MAGIC
# MAGIC Anomaly thresholds (preserved from upstream):
# MAGIC * `erab_success_rate < 97`  (% of QCI 1–9 initial E-RAB establishments succeeded)
# MAGIC * `retainability > 3`        (active E-RABs released per hour of session time)

# COMMAND ----------
import dlt
from pyspark.sql import functions as F

CATALOG = spark.conf.get("catalog", "srd_vibes_catalog")
SCHEMA = spark.conf.get("schema", "network_intel")
SOURCE = f"{CATALOG}.{SCHEMA}.performance"


@dlt.table(
    name="performance_kpi",
    comment="Per-cell, per-window E-RAB success rate and retainability KPIs.",
)
def performance_kpi():
    df = spark.read.table(SOURCE)
    erab_succ_cols = [F.coalesce(F.col(f"ERAB_EstabInitSuccNbr_QCI{i}"), F.lit(0)) for i in range(1, 10)]
    erab_att_cols = [F.coalesce(F.col(f"ERAB_EstabInitAttNbr_QCI{i}"), F.lit(0)) for i in range(1, 10)]
    erab_rel_cols = [F.coalesce(F.col(f"ERAB_RelActNbr_QCI{i}"), F.lit(0)) for i in range(1, 10)]

    succ = sum(erab_succ_cols)
    att = sum(erab_att_cols)
    rel = sum(erab_rel_cols)

    # Source data has rows with `ERAB_SessionTimeUE <= 0` and occasional
    # negative `ERAB_RelActNbr_QCI*`, which produce nonsensical retainability
    # values (huge negatives or infinities). Null those out so dashboards and
    # downstream agents only see physically plausible numbers.
    safe_session = F.when(F.col("ERAB_SessionTimeUE") > 0, F.col("ERAB_SessionTimeUE").cast("double"))
    safe_succ_rate = succ * F.lit(100.0) / F.when(att == 0, None).otherwise(att.cast("double"))
    raw_retain = rel.cast("double") / safe_session * F.lit(3600.0)
    safe_retain = F.when((raw_retain >= 0) & (raw_retain < 1000), raw_retain)

    return (
        df.select(
            "enodeb_id",
            "cell_id",
            "measurement_end",
            safe_succ_rate.alias("erab_success_rate"),
            safe_retain.alias("retainability"),
        )
    )
