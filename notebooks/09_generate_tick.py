# Databricks notebook source
# MAGIC %md
# MAGIC # 09_generate_tick
# MAGIC
# MAGIC Append one 15-min batch of synthetic PM rows + cell traces. Designed
# MAGIC to be invoked every 15 minutes by the `streaming_data_generator` job.

# COMMAND ----------
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd().parent
sys.path.insert(0, str(REPO_ROOT))

from tan.data_generator.main import cmd_tick
from tan.settings import SETTINGS

cmd_tick()

# Best-effort refresh of the KPI materialised view. REFRESH MATERIALIZED VIEW
# is not allowed on serverless generic compute, so on those workspaces we
# fall back to triggering the Lakeflow pipeline by name.
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
        print("no matching Lakeflow pipeline found; KPI view will lag until the next pipeline run")
