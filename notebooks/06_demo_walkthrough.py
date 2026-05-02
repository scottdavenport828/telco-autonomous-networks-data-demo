# Databricks notebook source
# MAGIC %md
# MAGIC # 06_demo_walkthrough
# MAGIC
# MAGIC End-to-end smoke test that mirrors the upstream demo's user flow:
# MAGIC 1. Sanity-check Delta tables and the KPI view
# MAGIC 2. Run the `incident_detector` against the KPI view (programmatic)
# MAGIC 3. Persist the first candidate incident
# MAGIC 4. Run the `rca_orchestrator` end-to-end on that incident
# MAGIC 5. Read back the updated incident record

# COMMAND ----------
import os
import sys
from pathlib import Path

REPO_ROOT = Path.cwd().parent if "DATABRICKS_RUNTIME_VERSION" in os.environ else Path(".").resolve()
sys.path.insert(0, str(REPO_ROOT))

from mlflow.types.agent import ChatAgentMessage

from tan.agents.incident_detector import IncidentDetectorAgent
from tan.agents.rca_orchestrator import RcaOrchestratorAgent
from tan.settings import SETTINGS

print(f"Catalog/schema: {SETTINGS.catalog}.{SETTINGS.schema}")
print(f"LLM endpoint: {SETTINGS.llm_endpoint}")
print(f"VS endpoint: {SETTINGS.vs_endpoint}")

# COMMAND ----------
# MAGIC %md ## 1. Spot-check the data layer

# COMMAND ----------
display(spark.sql(f"SELECT COUNT(*) AS n FROM {SETTINGS.perf_table}"))
display(spark.sql(f"SELECT COUNT(*) AS n FROM {SETTINGS.cell_traces_table}"))
display(spark.sql(f"SELECT COUNT(*) AS n FROM {SETTINGS.rca_rules_table}"))
display(
    spark.sql(
        f"""
SELECT enodeb_id, cell_id,
       SUM(CASE WHEN erab_success_rate < {SETTINGS.erab_success_rate_threshold} THEN 1 ELSE 0 END) AS erab_violations,
       SUM(CASE WHEN retainability > {SETTINGS.retainability_threshold} THEN 1 ELSE 0 END) AS retain_violations
FROM {SETTINGS.perf_kpi_view}
GROUP BY enodeb_id, cell_id
HAVING erab_violations + retain_violations > 0
ORDER BY erab_violations + retain_violations DESC
"""
    )
)

# COMMAND ----------
# MAGIC %md ## 2. Run the incident detector

# COMMAND ----------
detector = IncidentDetectorAgent()
detector_response = detector.predict(
    [ChatAgentMessage(role="user", content="Check if there are any new incidents and list them by KPI value.")]
)
for m in detector_response.messages:
    print(f"[{m.role}] {m.content}\n")

# COMMAND ----------
# MAGIC %md ## 3. Persist the first candidate
# MAGIC
# MAGIC The agent leaves the candidate list in `detector._candidates`. Pick the most
# MAGIC severe one and persist it.

# COMMAND ----------
candidates = list(detector._candidates.values())
assert candidates, "No KPI violations detected — re-run notebooks 01/02 to load fixtures."
candidate = candidates[0]
print(f"Persisting candidate: {candidate}")

confirm_response = detector.predict(
    [
        ChatAgentMessage(role="user", content="Check if there are any new incidents."),
        ChatAgentMessage(
            role="assistant",
            content="Found candidate incidents. Confirm to create.",
        ),
        ChatAgentMessage(
            role="user",
            content=f"Yes, please create incident {candidate['id']}.",
        ),
    ]
)
for m in confirm_response.messages:
    print(f"[{m.role}] {m.content}\n")

# COMMAND ----------
# MAGIC %md ## 4. Run RCA on the new incident

# COMMAND ----------
rca = RcaOrchestratorAgent()
rca_response = rca.predict(
    [
        ChatAgentMessage(
            role="user",
            content=f"Analyse incident {candidate['id']}. Skip user confirmations and run all steps.",
        )
    ]
)
for m in rca_response.messages:
    print(f"[{m.role}] {m.content}\n")

# COMMAND ----------
# MAGIC %md ## 5. Read the updated incident record

# COMMAND ----------
display(
    spark.sql(
        f"""
SELECT incident_id, status, severity, description, cause, resolution,
       LENGTH(events) AS events_len,
       LENGTH(preliminary_analysis) AS report_len
FROM {SETTINGS.incidents_table}
WHERE incident_id = '{candidate['id']}'
"""
    )
)
