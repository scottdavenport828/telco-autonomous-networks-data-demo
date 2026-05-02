# Databricks notebook source
# MAGIC %md
# MAGIC # 08_backfill_to_now
# MAGIC
# MAGIC One-shot: bridge the five-month gap between the upstream fixture
# MAGIC (last row 2025-12-05) and now by emitting one synthetic 15-min batch
# MAGIC for every interval in between. Run after `07_build_profile`.
# MAGIC
# MAGIC Cost note — at 19 cells × 96 windows/day × ~150 days that's ~273K
# MAGIC performance rows + ~6× as many cell-trace rows. A serverless cluster
# MAGIC will chew through that in a few minutes.

# COMMAND ----------
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd().parent
sys.path.insert(0, str(REPO_ROOT))

from tan.data_generator.main import cmd_backfill
from tan.settings import SETTINGS

cmd_backfill()

try:
    spark.sql(f"REFRESH MATERIALIZED VIEW {SETTINGS.perf_kpi_view}")
    print(f"refreshed {SETTINGS.perf_kpi_view}")
except Exception as e:
    print(f"REFRESH not allowed here ({e!s}); trying Lakeflow pipeline trigger…")
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    matches = [p for p in w.pipelines.list_pipelines() if p.name and p.name.endswith("telco-rca-performance-kpi")]
    if matches:
        w.pipelines.start_update(pipeline_id=matches[0].pipeline_id)
        print(f"triggered pipeline {matches[0].pipeline_id}")
    else:
        print("no matching Lakeflow pipeline found; trigger it manually after backfill")
