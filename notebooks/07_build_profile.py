# Databricks notebook source
# MAGIC %md
# MAGIC # 07_build_profile
# MAGIC
# MAGIC One-shot: derive per-(cell, column) statistics from the existing
# MAGIC `performance` Delta table and write them to `cell_profiles`. Re-runnable.
# MAGIC The streaming generator then samples new rows from these distributions.

# COMMAND ----------
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd().parent
sys.path.insert(0, str(REPO_ROOT))

from tan.data_generator.main import cmd_build_profile

cmd_build_profile()
