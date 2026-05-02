"""BigQuery JSON schema → Spark/Delta DDL translator.

Source repo (`infrastructure/terraform/bigquery-schema/*.json`) defined tables in
BigQuery JSON-schema format. We preserve those files verbatim in `data/schemas/`
and translate them at setup time so the Delta tables match the source schema
exactly (column names, order, nullability).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# BigQuery → Spark type mapping. We collapse INT64/INTEGER → BIGINT and
# FLOAT/FLOAT64 → DOUBLE since Spark treats them as the same physical types.
_BQ_TO_SPARK = {
    "STRING": "STRING",
    "string": "STRING",
    "INT64": "BIGINT",
    "INTEGER": "BIGINT",
    "FLOAT": "DOUBLE",
    "FLOAT64": "DOUBLE",
    "BOOL": "BOOLEAN",
    "BOOLEAN": "BOOLEAN",
    "TIMESTAMP": "TIMESTAMP",
    "DATETIME": "TIMESTAMP",
    "DATE": "DATE",
    "BYTES": "BINARY",
}


def _spark_type(field: dict[str, Any]) -> str:
    bq_type = field["type"]
    mode = field.get("mode", "NULLABLE")

    if bq_type == "RECORD":
        struct_body = ", ".join(
            f"{f['name']}: {_spark_type(f)}" for f in field.get("fields", [])
        )
        sub = f"STRUCT<{struct_body}>"
    else:
        sub = _BQ_TO_SPARK.get(bq_type)
        if not sub:
            raise ValueError(f"unmapped BigQuery type: {bq_type!r}")

    return f"ARRAY<{sub}>" if mode == "REPEATED" else sub


def column_specs(schema_path: str | Path) -> list[tuple[str, str, bool]]:
    """Return [(name, spark_type, nullable), ...]."""
    fields = json.loads(Path(schema_path).read_text())
    return [
        (
            f["name"],
            _spark_type(f),
            f.get("mode", "NULLABLE") != "REQUIRED",
        )
        for f in fields
    ]


def create_table_sql(
    full_table_name: str,
    schema_path: str | Path,
    *,
    partition_by: list[str] | None = None,
    cluster_by: list[str] | None = None,
    properties: dict[str, str] | None = None,
) -> str:
    """Build a Spark `CREATE TABLE ... USING DELTA` statement from a BQ JSON schema."""
    cols = column_specs(schema_path)
    col_defs = ",\n  ".join(
        f"`{name}` {dtype}{' NOT NULL' if not nullable else ''}"
        for name, dtype, nullable in cols
    )

    parts = [f"CREATE TABLE IF NOT EXISTS {full_table_name} (\n  {col_defs}\n) USING DELTA"]

    if partition_by:
        parts.append("PARTITIONED BY (" + ", ".join(partition_by) + ")")
    if cluster_by:
        parts.append("CLUSTER BY (" + ", ".join(cluster_by) + ")")

    if properties:
        kv = ",\n  ".join(f"'{k}' = '{v}'" for k, v in properties.items())
        parts.append(f"TBLPROPERTIES (\n  {kv}\n)")

    return "\n".join(parts)
