"""Auto-RCA: run RcaOrchestratorAgent against any incident missing a final report.

We re-use the production agent class — same tool surface, same MLflow tracing,
same AI Gateway path. The difference vs a Workbench user typing "Analyse incident X"
is just the prompt: we tell the agent to skip user-confirmation prompts.
"""

from __future__ import annotations

from pyspark.sql import SparkSession

from tan.autopilot.state import is_enabled


def analyse_pending_incidents(
    spark: SparkSession, *, catalog: str, schema: str, max_per_run: int = 5
) -> int:
    """For each incident with status='NEW' AND final_analysis IS NULL, run RCA.

    Returns the number of incidents analysed.
    """
    state_table = f"{catalog}.{schema}.autopilot_state"
    if not is_enabled(spark, table=state_table):
        print("autopilot disabled; skipping RCA")
        return 0

    incidents = f"{catalog}.{schema}.incidents"
    pending = (
        spark.read.table(incidents)
        .filter("status = 'NEW'")
        .filter("preliminary_analysis IS NULL")
        .orderBy("created_ts")
        .limit(max_per_run)
        .select("incident_id")
        .collect()
    )
    if not pending:
        print("autopilot/rca: nothing to analyse")
        return 0

    # Defer the import so the notebook doesn't fail if the agent module itself
    # has a transient issue — it'll still log the incident IDs that needed RCA.
    from mlflow.types.agent import ChatAgentMessage  # noqa: PLC0415

    from tan.agents.rca_orchestrator import RcaOrchestratorAgent  # noqa: PLC0415

    agent = RcaOrchestratorAgent()
    n = 0
    for r in pending:
        prompt = (
            f"Analyse incident {r.incident_id}. Skip every user-confirmation prompt and "
            f"run all RCA steps. When finished, call update_incident with the final "
            f"report, severity, events, cause, and resolution. Then stop."
        )
        try:
            agent.predict([ChatAgentMessage(role="user", content=prompt)])
            n += 1
            print(f"autopilot/rca: analysed {r.incident_id}")
        except Exception as exc:  # noqa: BLE001
            print(f"autopilot/rca: failed for {r.incident_id}: {exc}")
    return n
