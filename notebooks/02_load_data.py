# Databricks notebook source
# MAGIC %md
# MAGIC # 02_load_data
# MAGIC
# MAGIC Uploads CSV/JSON fixtures from the bundled workspace files into the UC volume,
# MAGIC then MERGE-loads into Delta tables. Idempotent — safe to re-run.

# COMMAND ----------
# MAGIC %pip install -q databricks-vectorsearch
# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd().parent
sys.path.insert(0, str(REPO_ROOT))

from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, BooleanType, TimestampType, ArrayType

CATALOG = dbutils.widgets.get("catalog") if dbutils.widgets.getAll() else "srd_vibes_catalog"
SCHEMA = dbutils.widgets.get("schema") if dbutils.widgets.getAll() else "network_intel"
VOLUME = dbutils.widgets.get("volume") if dbutils.widgets.getAll() else "raw"

VOLUME_ROOT = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"
print(f"Volume root: {VOLUME_ROOT}")

# COMMAND ----------
# MAGIC %md ## 1. Stage fixtures into the UC Volume

# COMMAND ----------
def _upload(local_relpath: str, remote_relpath: str):
    src = REPO_ROOT / local_relpath
    dst = f"{VOLUME_ROOT}/{remote_relpath}"
    parent = "/".join(dst.split("/")[:-1])
    dbutils.fs.mkdirs(parent)
    with open(src, "rb") as fh:
        dbutils.fs.put(dst, fh.read().decode("utf-8", errors="replace"), overwrite=True)
    print(f"  uploaded {src} -> {dst}")


_upload("data/performance.csv", "performance.csv")
_upload("data/cell-traces.csv", "cell_traces.csv")

for jp in (REPO_ROOT / "data" / "rca-rules").glob("*.json"):
    _upload(f"data/rca-rules/{jp.name}", f"rca_rules/{jp.name}")

# COMMAND ----------
# MAGIC %md ## 2. Performance — CSV → Delta
# MAGIC
# MAGIC Source CSV uses `MM/DD/YYYY HH24:MI:SS` for `measurement_end` and a header
# MAGIC like `EnodeB_id,cell_id,measurement_end,RRC_ConnEstabAtt_Em,...`. We read with
# MAGIC the target Delta schema (which preserves source casing), parse the timestamp,
# MAGIC and overwrite-replace the Delta partition.

# COMMAND ----------
# Use the CSV header to drive the schema — DO NOT pass an explicit schema.
# The upstream BigQuery schema and the CSV header have different column orders
# (and the CSV is missing a few totals that the BQ schema includes), so reading
# by-position with the BQ schema scrambles the data. inferSchema is fine here
# because the CSV is small (~3.7 MB).
target_perf = f"{CATALOG}.{SCHEMA}.performance"

df = (
    spark.read.option("header", True)
    .option("inferSchema", True)
    .option("timestampFormat", "MM/dd/yyyy HH:mm:ss")
    .csv(f"{VOLUME_ROOT}/performance.csv")
    # Normalise the one column whose case differs from BQ schema convention.
    .withColumnRenamed("EnodeB_id", "enodeb_id")
)

print(f"Performance rows: {df.count()}; cols: {len(df.columns)}")
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(target_perf)

# COMMAND ----------
# MAGIC %md ## 3. Cell traces — CSV → Delta

# COMMAND ----------
target_traces = f"{CATALOG}.{SCHEMA}.cell_traces"

df = (
    spark.read.option("header", True)
    .option("inferSchema", True)
    .option("timestampFormat", "MM/dd/yyyy HH:mm:ss")
    .csv(f"{VOLUME_ROOT}/cell_traces.csv")
)
# Normalise columns to lowercase to match downstream queries.
df = df.toDF(*[c.lower() for c in df.columns])

print(f"Cell-trace rows: {df.count()}; cols: {len(df.columns)}")
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(target_traces)

# COMMAND ----------
# MAGIC %md ## 4. RCA rules — JSON → Delta with `search_text` column for embedding

# COMMAND ----------
import os
from datetime import datetime, timezone

rules_dir = f"{VOLUME_ROOT}/rca_rules"
rule_files = [f.path for f in dbutils.fs.ls(rules_dir) if f.name.endswith(".json")]
print(f"Found {len(rule_files)} rule files")


def _parse_ts(value):
    if not value:
        return None
    # Source format: "2025-12-26 08:30:00 UTC"
    cleaned = value.replace(" UTC", "+0000")
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S%z")
    except ValueError:
        return datetime.fromisoformat(cleaned).astimezone(timezone.utc)


records = []
for fp in rule_files:
    text = dbutils.fs.head(fp, 1024 * 64)  # 64 KiB upper bound
    payload = json.loads(text)
    rule_id = os.path.basename(fp).removesuffix(".json")
    search_text = " ".join(
        filter(
            None,
            [
                payload.get("description"),
                payload.get("processing_rule"),
                payload.get("severity_determination_rule"),
            ],
        )
    )
    records.append(
        {
            "id": rule_id,
            "description": payload["description"],
            "kpi_missed": payload.get("kpi_missed", []),
            "processing_rule": payload["processing_rule"],
            "processing_rule_tools": payload.get("processing_rule_tools", []),
            "severity_determination_rule": payload["severity_determination_rule"],
            "severity_determination_rule_tools": payload.get("severity_determination_rule_tools", []),
            "vendor": payload.get("vendor"),
            "author": payload.get("author"),
            "creation_date": _parse_ts(payload.get("creation_date")),
            "is_current": payload.get("is_current"),
            "search_text": search_text,
        }
    )

target_rules = f"{CATALOG}.{SCHEMA}.rca_rules"
target_schema = spark.read.table(target_rules).schema

df = spark.createDataFrame(records, target_schema)
print(f"RCA rule rows: {df.count()}")

# Use MERGE to support re-runs without duplicating
df.createOrReplaceTempView("rca_rules_src")
spark.sql(
    f"""
    MERGE INTO {target_rules} t
    USING rca_rules_src s
    ON t.id = s.id
    WHEN MATCHED THEN UPDATE SET *
    WHEN NOT MATCHED THEN INSERT *
    """
)

# COMMAND ----------
# MAGIC %md ## 5. Trigger Vector Search index sync

# COMMAND ----------
from databricks.vector_search.client import VectorSearchClient

try:
    VS_ENDPOINT = dbutils.widgets.get("vs_endpoint")
except Exception:
    VS_ENDPOINT = "srd-vibes-vs"

vsc = VectorSearchClient(disable_notice=True)

for index_name in (
    f"{CATALOG}.{SCHEMA}.rca_rules_vs_idx",
    f"{CATALOG}.{SCHEMA}.incidents_vs_idx",
):
    try:
        idx = vsc.get_index(endpoint_name=VS_ENDPOINT, index_name=index_name)
        print(f"Triggering sync for {index_name}")
        idx.sync()
    except Exception as e:
        print(f"  skipping {index_name}: {e}")

print("Data load complete.")
