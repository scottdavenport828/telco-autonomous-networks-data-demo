"""SQL execution helper. Replaces `agents/.../tools/bigquery_util.py`.

Uses the Databricks SDK Statement Execution API against a serverless SQL
warehouse. The warehouse ID is provided via `SQL_WAREHOUSE_ID` env var (the
Databricks App resource binding sets this automatically).
"""

from __future__ import annotations

from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem, StatementState


def _coerce(value: Any) -> Any:
    """Statement Execution returns everything as strings; do light coercion."""
    if value is None or not isinstance(value, str):
        return value
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    try:
        if "." in value or "e" in value.lower():
            return float(value)
        return int(value)
    except ValueError:
        return value


class SqlClient:
    def __init__(self, warehouse_id: str, *, workspace: WorkspaceClient | None = None):
        if not warehouse_id:
            raise ValueError("warehouse_id is required (set SQL_WAREHOUSE_ID)")
        self.warehouse_id = warehouse_id
        self.w = workspace or WorkspaceClient()

    def query(self, sql: str, *, parameters: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        """Run a SQL statement and return rows as list[dict].

        ``parameters`` accepts a list of {"name", "value", "type"?} dicts; we
        convert them to ``StatementParameterListItem`` because the SDK calls
        ``.as_dict()`` on each item internally and a raw dict would explode
        with ``'dict' object has no attribute 'as_dict'``.
        """
        sdk_params = None
        if parameters:
            sdk_params = [
                StatementParameterListItem(
                    name=p["name"],
                    value=None if p.get("value") is None else str(p["value"]),
                    type=p.get("type"),
                )
                for p in parameters
            ]

        result = self.w.statement_execution.execute_statement(
            warehouse_id=self.warehouse_id,
            statement=sql,
            wait_timeout="50s",
            parameters=sdk_params,
        )

        state = result.status.state
        if state in (StatementState.PENDING, StatementState.RUNNING):
            result = self.w.statement_execution.get_statement(result.statement_id)
            while result.status.state in (StatementState.PENDING, StatementState.RUNNING):
                result = self.w.statement_execution.get_statement(result.statement_id)
            state = result.status.state

        if state != StatementState.SUCCEEDED:
            err = result.status.error.message if result.status.error else "unknown"
            raise RuntimeError(f"SQL failed ({state}): {err}\nSQL: {sql}")

        manifest = result.manifest
        data = result.result
        if not manifest or not data or not data.data_array:
            return []

        cols = [c.name for c in manifest.schema.columns]
        rows: list[dict[str, Any]] = []
        for row in data.data_array:
            rows.append({col: _coerce(val) for col, val in zip(cols, row)})
        return rows

    def execute(self, sql: str, *, parameters: list[dict[str, Any]] | None = None) -> None:
        """Run a SQL statement and discard the result (for INSERT/UPDATE/MERGE)."""
        self.query(sql, parameters=parameters)
