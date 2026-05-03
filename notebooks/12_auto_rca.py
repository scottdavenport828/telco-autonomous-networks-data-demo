# Databricks notebook source
# MAGIC %md # 12_auto_rca — autopilot stage 2
# COMMAND ----------
# MAGIC %pip install -q mlflow[databricks] databricks-sdk databricks-vectorsearch pydantic
# COMMAND ----------
dbutils.library.restartPython()
# COMMAND ----------
import sys
from pathlib import Path
REPO_ROOT = Path.cwd().parent if "DATABRICKS_RUNTIME_VERSION" in __import__("os").environ else Path(".").resolve()
sys.path.insert(0, str(REPO_ROOT))
from tan.autopilot.main import cmd_rca
cmd_rca()
