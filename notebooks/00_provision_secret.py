# Databricks notebook source
# MAGIC %md
# MAGIC # 00_provision_secret
# MAGIC
# MAGIC One-time helper. Creates the `telco-rca` secret scope and stores the
# MAGIC Anthropic API key the AI Gateway endpoint will use to call Claude Opus 4.7.
# MAGIC
# MAGIC **Run interactively from a workspace user**, not from a job (jobs cannot
# MAGIC create new secret scopes when the workspace is in CSE mode).

# COMMAND ----------
SCOPE = "telco-rca"
KEY = "anthropic_api_key"

# Paste the key from https://console.anthropic.com (or pull from a vault).
api_key = dbutils.secrets.get(scope=SCOPE, key=KEY) if False else input("Paste ANTHROPIC_API_KEY (sk-ant-...): ")

# COMMAND ----------
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

scopes = {s.name for s in w.secrets.list_scopes()}
if SCOPE not in scopes:
    w.secrets.create_scope(scope=SCOPE)
    print(f"Created scope: {SCOPE}")
else:
    print(f"Scope {SCOPE} already exists")

w.secrets.put_secret(scope=SCOPE, key=KEY, string_value=api_key)
print(f"Stored secret {SCOPE}/{KEY}")
