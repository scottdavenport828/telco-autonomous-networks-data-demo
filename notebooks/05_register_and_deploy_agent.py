# Databricks notebook source
# MAGIC %md
# MAGIC # 05_register_and_deploy_agent
# MAGIC
# MAGIC Logs the `incident_detector` and `rca_orchestrator` ChatAgents to MLflow,
# MAGIC registers them in Unity Catalog, and deploys them to a single shared
# MAGIC serving endpoint via `databricks.agents.deploy()`. Both agents are bundled
# MAGIC into one served model that routes by message metadata, so the app only
# MAGIC needs to manage one endpoint.

# COMMAND ----------
# MAGIC %pip install -q mlflow[databricks] databricks-agents databricks-sdk databricks-vectorsearch pydantic
# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
import os
import sys
from pathlib import Path

REPO_ROOT = Path.cwd().parent if "DATABRICKS_RUNTIME_VERSION" in os.environ else Path(".").resolve()
sys.path.insert(0, str(REPO_ROOT))

CATALOG = dbutils.widgets.get("catalog") if dbutils.widgets.getAll() else "srd_vibes_catalog"
SCHEMA = dbutils.widgets.get("schema") if dbutils.widgets.getAll() else "network_intel"
LLM_ENDPOINT = dbutils.widgets.get("llm_endpoint") if dbutils.widgets.getAll() else "databricks-claude-opus-4-7"
EMBEDDING_ENDPOINT = dbutils.widgets.get("embedding_endpoint") if dbutils.widgets.getAll() else "databricks-gte-large-en"
VS_ENDPOINT = dbutils.widgets.get("vs_endpoint") if dbutils.widgets.getAll() else "srd-vibes-vs"
RULES_INDEX = dbutils.widgets.get("rules_index") if dbutils.widgets.getAll() else "rca_rules_vs_idx"
INCIDENTS_INDEX = dbutils.widgets.get("incidents_index") if dbutils.widgets.getAll() else "incidents_vs_idx"
AGENT_ENDPOINT = dbutils.widgets.get("agent_endpoint") if dbutils.widgets.getAll() else "telco-rca-agents"

# Pick the smallest serverless warehouse we can find
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
warehouses = list(w.warehouses.list())
WAREHOUSE_ID = next(
    (wh.id for wh in warehouses if wh.warehouse_type and "PRO" in str(wh.warehouse_type) and wh.enable_serverless_compute),
    warehouses[0].id if warehouses else None,
)
print(f"Using warehouse: {WAREHOUSE_ID}")

PERF_TABLE = f"{CATALOG}.{SCHEMA}.performance"
CELL_TRACES_TABLE = f"{CATALOG}.{SCHEMA}.cell_traces"
INCIDENTS_TABLE = f"{CATALOG}.{SCHEMA}.incidents"
RULES_INDEX_FULL = f"{CATALOG}.{SCHEMA}.{RULES_INDEX}"
INCIDENTS_INDEX_FULL = f"{CATALOG}.{SCHEMA}.{INCIDENTS_INDEX}"

# Make settings visible to the logged model at inference time
os.environ.update(
    {
        "CATALOG": CATALOG,
        "SCHEMA": SCHEMA,
        "LLM_ENDPOINT": LLM_ENDPOINT,
        "EMBEDDING_ENDPOINT": EMBEDDING_ENDPOINT,
        "VS_ENDPOINT": VS_ENDPOINT,
        "RULES_INDEX": RULES_INDEX,
        "INCIDENTS_INDEX": INCIDENTS_INDEX,
        "SQL_WAREHOUSE_ID": WAREHOUSE_ID,
    }
)

# COMMAND ----------
# MAGIC %md ## 1. Register IncidentDetectorAgent

# COMMAND ----------
from tan.agents.register import log_and_register

incident_model_uri = log_and_register(
    repo_root=str(REPO_ROOT),
    agent_module_path=str(REPO_ROOT / "tan" / "agents" / "incident_detector.py"),
    agent_class_path="tan.agents.incident_detector:IncidentDetectorAgent",
    registered_model_name=f"{CATALOG}.{SCHEMA}.incident_detector",
    llm_endpoint=LLM_ENDPOINT,
    embedding_endpoint=EMBEDDING_ENDPOINT,
    warehouse_id=WAREHOUSE_ID,
    perf_table=PERF_TABLE,
    cell_traces_table=CELL_TRACES_TABLE,
    incidents_table=INCIDENTS_TABLE,
    rules_index=RULES_INDEX_FULL,
    incidents_index=INCIDENTS_INDEX_FULL,
)
print(f"Registered incident_detector at {incident_model_uri}")

# COMMAND ----------
# MAGIC %md ## 2. Register RcaOrchestratorAgent

# COMMAND ----------
rca_model_uri = log_and_register(
    repo_root=str(REPO_ROOT),
    agent_module_path=str(REPO_ROOT / "tan" / "agents" / "rca_orchestrator.py"),
    agent_class_path="tan.agents.rca_orchestrator:RcaOrchestratorAgent",
    registered_model_name=f"{CATALOG}.{SCHEMA}.rca_orchestrator",
    llm_endpoint=LLM_ENDPOINT,
    embedding_endpoint=EMBEDDING_ENDPOINT,
    warehouse_id=WAREHOUSE_ID,
    perf_table=PERF_TABLE,
    cell_traces_table=CELL_TRACES_TABLE,
    incidents_table=INCIDENTS_TABLE,
    rules_index=RULES_INDEX_FULL,
    incidents_index=INCIDENTS_INDEX_FULL,
)
print(f"Registered rca_orchestrator at {rca_model_uri}")

# COMMAND ----------
# MAGIC %md ## 3. Deploy both to a single serving endpoint

# COMMAND ----------
from databricks import agents
from mlflow.tracking import MlflowClient

client = MlflowClient(registry_uri="databricks-uc")

incident_latest = client.get_latest_versions(name=f"{CATALOG}.{SCHEMA}.incident_detector")[0]
rca_latest = client.get_latest_versions(name=f"{CATALOG}.{SCHEMA}.rca_orchestrator")[0]

# Deploy each agent as its own served entity behind a single endpoint, with
# 50/50 split — the FastAPI router invokes by name path (`/api/chat/incident-detector`
# vs `/api/chat/rca`) and selects the served entity via the `model` field.
deployment = agents.deploy(
    model_name=f"{CATALOG}.{SCHEMA}.incident_detector",
    model_version=incident_latest.version,
    endpoint_name=AGENT_ENDPOINT,
    scale_to_zero=True,
    environment_vars={
        "CATALOG": CATALOG,
        "SCHEMA": SCHEMA,
        "LLM_ENDPOINT": LLM_ENDPOINT,
        "EMBEDDING_ENDPOINT": EMBEDDING_ENDPOINT,
        "VS_ENDPOINT": VS_ENDPOINT,
        "RULES_INDEX": RULES_INDEX,
        "INCIDENTS_INDEX": INCIDENTS_INDEX,
        "SQL_WAREHOUSE_ID": WAREHOUSE_ID,
    },
)

rca_deployment = agents.deploy(
    model_name=f"{CATALOG}.{SCHEMA}.rca_orchestrator",
    model_version=rca_latest.version,
    endpoint_name=AGENT_ENDPOINT,
    scale_to_zero=True,
    environment_vars={
        "CATALOG": CATALOG,
        "SCHEMA": SCHEMA,
        "LLM_ENDPOINT": LLM_ENDPOINT,
        "EMBEDDING_ENDPOINT": EMBEDDING_ENDPOINT,
        "VS_ENDPOINT": VS_ENDPOINT,
        "RULES_INDEX": RULES_INDEX,
        "INCIDENTS_INDEX": INCIDENTS_INDEX,
        "SQL_WAREHOUSE_ID": WAREHOUSE_ID,
    },
)

print("Deployed:")
print(f"  endpoint: {deployment.endpoint_name}")
print(f"  incident_detector served entity: {deployment.served_entity_name}")
print(f"  rca_orchestrator served entity: {rca_deployment.served_entity_name}")
