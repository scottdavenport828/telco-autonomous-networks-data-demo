# Databricks notebook source
# MAGIC %md # 14_auto_verify — autopilot stage 4
# COMMAND ----------
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd().parent
sys.path.insert(0, str(REPO_ROOT))
from tan.autopilot.main import cmd_verify
cmd_verify()
