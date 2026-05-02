"""MLflow `log_model` entrypoint for the two ChatAgents.

Usage (from a notebook, see `notebooks/05_register_and_deploy_agent.py`):

    from tan.agents.register import log_and_register
    log_and_register(
        catalog="telco_demo", schema="network_intel",
        model_name="incident_detector",
        agent_module="tan.agents.incident_detector",
        agent_class="IncidentDetectorAgent",
    )
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import mlflow
from mlflow.models.resources import (
    DatabricksFunction,
    DatabricksServingEndpoint,
    DatabricksSQLWarehouse,
    DatabricksTable,
    DatabricksVectorSearchIndex,
)


def _agent_resources(
    *,
    llm_endpoint: str,
    embedding_endpoint: str,
    warehouse_id: str,
    perf_table: str,
    cell_traces_table: str,
    incidents_table: str,
    rules_index: str,
    incidents_index: str,
) -> list[Any]:
    return [
        DatabricksServingEndpoint(endpoint_name=llm_endpoint),
        DatabricksServingEndpoint(endpoint_name=embedding_endpoint),
        DatabricksSQLWarehouse(warehouse_id=warehouse_id),
        DatabricksTable(table_name=perf_table),
        DatabricksTable(table_name=cell_traces_table),
        DatabricksTable(table_name=incidents_table),
        DatabricksVectorSearchIndex(index_name=rules_index),
        DatabricksVectorSearchIndex(index_name=incidents_index),
    ]


def log_and_register(
    *,
    repo_root: str,
    agent_module_path: str,
    agent_class_path: str,
    registered_model_name: str,
    llm_endpoint: str,
    embedding_endpoint: str,
    warehouse_id: str,
    perf_table: str,
    cell_traces_table: str,
    incidents_table: str,
    rules_index: str,
    incidents_index: str,
) -> str:
    """Log the agent as an MLflow model and register it to Unity Catalog.

    `agent_module_path` is the absolute filesystem path to the agent module;
    `agent_class_path` is the dotted class to instantiate (e.g. `tan.agents.incident_detector:IncidentDetectorAgent`).

    Returns the registered model URI (e.g. `models:/catalog.schema.model_name/3`).
    """
    mlflow.set_registry_uri("databricks-uc")

    resources = _agent_resources(
        llm_endpoint=llm_endpoint,
        embedding_endpoint=embedding_endpoint,
        warehouse_id=warehouse_id,
        perf_table=perf_table,
        cell_traces_table=cell_traces_table,
        incidents_table=incidents_table,
        rules_index=rules_index,
        incidents_index=incidents_index,
    )

    with mlflow.start_run(run_name=f"register-{registered_model_name}") as run:
        mlflow.pyfunc.log_model(
            artifact_path="agent",
            python_model=agent_module_path,
            code_paths=[str(Path(repo_root) / "tan")],
            registered_model_name=registered_model_name,
            resources=resources,
            extra_pip_requirements=[
                "databricks-sdk>=0.40.0",
                "databricks-agents>=0.18.0",
                "databricks-vectorsearch>=0.49",
                "mlflow[databricks]>=2.20.0",
                "pydantic>=2.7",
            ],
        )

        # The pyfunc model artifact is at runs:/<run>/agent
        model_uri = f"runs:/{run.info.run_id}/agent"
    return model_uri
