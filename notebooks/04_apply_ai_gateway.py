# Databricks notebook source
# MAGIC %md
# MAGIC # 04_apply_ai_gateway
# MAGIC
# MAGIC Applies Unity AI Gateway features to the native FMAPI endpoint
# MAGIC `databricks-claude-opus-4-6`. No Anthropic API key required — the endpoint
# MAGIC is provided by Databricks as a pay-per-token service.
# MAGIC
# MAGIC Features applied:
# MAGIC * **Rate limits** — 200 calls/min per endpoint
# MAGIC * **Usage tracking** — token counts in `system.serving.served_entities`
# MAGIC * **Inference table** — request/response logging to a Delta table
# MAGIC   `<catalog>.<schema>.gw_inference_payload`
# MAGIC * **Guardrails** — PII detection on input and output
# MAGIC
# MAGIC Run this once after `01_setup`. Re-run to update the configuration.
# MAGIC Verify in the workspace UI under **Serving > Unity AI Gateway**.

# COMMAND ----------
CATALOG = dbutils.widgets.get("catalog") if dbutils.widgets.getAll() else "srd_vibes_catalog"
SCHEMA = dbutils.widgets.get("schema") if dbutils.widgets.getAll() else "network_intel"
LLM_ENDPOINT = dbutils.widgets.get("llm_endpoint") if dbutils.widgets.getAll() else "databricks-claude-opus-4-6"

print(f"Applying AI Gateway config to endpoint: {LLM_ENDPOINT}")
print(f"Inference table target: {CATALOG}.{SCHEMA}.gw_inference_*")

# COMMAND ----------
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

ai_gateway_payload = {
    "usage_tracking_config": {"enabled": True},
    "inference_table_config": {
        "enabled": True,
        "catalog_name": CATALOG,
        "schema_name": SCHEMA,
        "table_name_prefix": "gw_inference",
    },
    "rate_limits": [
        {"calls": 200, "renewal_period": "minute", "key": "endpoint"}
    ],
    "guardrails": {
        "input": {"pii": {"behavior": "BLOCK"}},
        "output": {"pii": {"behavior": "BLOCK"}},
    },
}

response = w.api_client.do(
    "PUT",
    f"/api/2.0/serving-endpoints/{LLM_ENDPOINT}/ai-gateway",
    body=ai_gateway_payload,
)

print("AI Gateway config applied.")
print("Response:", response)
