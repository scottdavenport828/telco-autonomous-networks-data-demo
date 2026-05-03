# Databricks notebook source
# MAGIC %md # 13_auto_remediate — autopilot stage 3
# COMMAND ----------
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd().parent
sys.path.insert(0, str(REPO_ROOT))
from tan.autopilot.main import cmd_remediate
cmd_remediate()
