"""Observability endpoints — surface AI Gateway + Mosaic AI Agent inference logs.

Reads from two auto-created Delta tables in `srd_vibes_catalog.network_intel`:

* ``gw_inference_payload`` — every call to the ``databricks-claude-opus-4-6``
  endpoint, captured by the Unity AI Gateway inference table feature
  (see ``notebooks/04_apply_ai_gateway.py``).
* ``incident_detector_payload`` — every call to the ``telco-rca-agents``
  serving endpoint, captured by the Mosaic AI Agent Framework auto-capture
  inference table.

Both tables share the same schema (gateway-style):

============================  =====================================
column                        description
============================  =====================================
databricks_request_id          STRING
request_date                   DATE
client_request_id              STRING
request_time                   TIMESTAMP
status_code                    INT
sampling_fraction              DOUBLE
execution_duration_ms          LONG
request                        STRING (JSON-encoded request body)
response                       STRING (JSON-encoded response body)
logging_error_codes            ARRAY<STRING>
served_entity_id               STRING
requester                      STRING
============================  =====================================

There is **no** dedicated ``input_tokens`` / ``output_tokens`` /
``pii_redaction_count`` column. We extract those values from the JSON
``response`` payload (gateway calls only — agent payloads do not include a
``usage`` block). PII / guardrail events surface as 4xx responses where the
``response`` body's ``message`` field mentions ``"guardrail"`` or ``"pii"``.

Every endpoint here is **defensive**: if a query fails (missing table,
missing column, insufficient permissions) we return an empty result set with
an ``error`` field so the UI can degrade gracefully rather than blow up.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from tan.agents.sql import SqlClient
from tan.api.deps import get_settings, get_sql_client
from tan.settings import Settings

router = APIRouter(prefix="/api/obs", tags=["observability"])


# Names of the inference tables. We hard-code them here (rather than threading
# more attributes through ``Settings``) because they are owned by Databricks
# auto-capture, not by the demo.
def _gateway_table(settings: Settings) -> str:
    return f"{settings.catalog}.{settings.schema}.gw_inference_payload"


def _agent_table(settings: Settings) -> str:
    return f"{settings.catalog}.{settings.schema}.incident_detector_payload"


def _safe_query(sql: SqlClient, statement: str) -> tuple[list[dict[str, Any]], str | None]:
    """Run a SQL statement, returning ``(rows, error)``.

    On success returns ``(rows, None)``. On failure returns ``([], message)``
    so the caller can shape a graceful response.
    """
    try:
        return sql.query(statement), None
    except Exception as exc:  # noqa: BLE001 — we genuinely want to swallow + report
        return [], f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# /tokens
# ---------------------------------------------------------------------------


@router.get("/tokens")
def tokens(
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    hours: int = Query(default=24, ge=1, le=168),
) -> dict[str, Any]:
    """Hourly buckets of input + output tokens, sub-totalled by model.

    Tokens are extracted from the gateway response JSON ``usage`` block — the
    agent payload does not surface them. Failed (non-200) requests have no
    usage data so are excluded.
    """
    statement = f"""
WITH parsed AS (
  SELECT
    date_trunc('HOUR', request_time)                                       AS hr,
    coalesce(get_json_object(response, '$.model'), 'unknown')              AS model,
    cast(get_json_object(response, '$.usage.prompt_tokens')     AS BIGINT) AS input_tokens,
    cast(get_json_object(response, '$.usage.completion_tokens') AS BIGINT) AS output_tokens
  FROM {_gateway_table(settings)}
  WHERE request_time > current_timestamp() - INTERVAL {hours} HOURS
    AND status_code = 200
)
SELECT
  hr,
  model,
  sum(coalesce(input_tokens, 0))  AS input_tokens,
  sum(coalesce(output_tokens, 0)) AS output_tokens,
  count(*)                        AS calls
FROM parsed
GROUP BY hr, model
ORDER BY hr ASC, model ASC
"""
    rows, error = _safe_query(sql, statement)
    return {
        "hours": hours,
        "rows": rows,
        "source": "gw_inference_payload",
        "error": error,
    }


# ---------------------------------------------------------------------------
# /latency
# ---------------------------------------------------------------------------


@router.get("/latency")
def latency(
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    hours: int = Query(default=24, ge=1, le=168),
) -> dict[str, Any]:
    """Hourly p50/p95/p99 of ``execution_duration_ms`` across both tables."""
    union_sql = f"""
SELECT request_time, execution_duration_ms, 'gateway' AS source
FROM {_gateway_table(settings)}
WHERE request_time > current_timestamp() - INTERVAL {hours} HOURS
UNION ALL
SELECT request_time, execution_duration_ms, 'agent' AS source
FROM {_agent_table(settings)}
WHERE request_time > current_timestamp() - INTERVAL {hours} HOURS
"""
    statement = f"""
WITH all_calls AS ({union_sql})
SELECT
  date_trunc('HOUR', request_time)                       AS hr,
  source,
  count(*)                                               AS calls,
  percentile(execution_duration_ms, 0.5)                 AS p50,
  percentile(execution_duration_ms, 0.95)                AS p95,
  percentile(execution_duration_ms, 0.99)                AS p99
FROM all_calls
GROUP BY hr, source
ORDER BY hr ASC, source ASC
"""
    rows, error = _safe_query(sql, statement)
    return {
        "hours": hours,
        "rows": rows,
        "threshold_ms": 5000,
        "error": error,
    }


# ---------------------------------------------------------------------------
# /recent
# ---------------------------------------------------------------------------


@router.get("/recent")
def recent(
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """Last N calls across both tables, joined into a unified shape.

    No raw user content is returned — only metadata (timestamps, token
    counts, model name, status, request id).
    """
    statement = f"""
WITH gw AS (
  SELECT
    request_time                                                             AS ts,
    'gateway'                                                                AS source,
    coalesce(get_json_object(response, '$.model'), 'unknown')                AS model,
    execution_duration_ms                                                    AS latency_ms,
    cast(get_json_object(response, '$.usage.prompt_tokens')     AS BIGINT)   AS input_tokens,
    cast(get_json_object(response, '$.usage.completion_tokens') AS BIGINT)   AS output_tokens,
    status_code                                                              AS status,
    databricks_request_id                                                    AS request_id,
    requester                                                                AS requester
  FROM {_gateway_table(settings)}
),
agt AS (
  SELECT
    request_time                                                             AS ts,
    'agent'                                                                  AS source,
    'telco-rca-agents'                                                       AS model,
    execution_duration_ms                                                    AS latency_ms,
    cast(NULL AS BIGINT)                                                     AS input_tokens,
    cast(NULL AS BIGINT)                                                     AS output_tokens,
    status_code                                                              AS status,
    databricks_request_id                                                    AS request_id,
    requester                                                                AS requester
  FROM {_agent_table(settings)}
)
SELECT * FROM (
  SELECT * FROM gw
  UNION ALL
  SELECT * FROM agt
)
ORDER BY ts DESC
LIMIT {limit}
"""
    rows, error = _safe_query(sql, statement)
    return {"rows": rows, "error": error}


# ---------------------------------------------------------------------------
# /pii
# ---------------------------------------------------------------------------


@router.get("/pii")
def pii(
    sql: Annotated[SqlClient, Depends(get_sql_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    hours: int = Query(default=24, ge=1, le=168),
) -> dict[str, Any]:
    """Counts of PII / guardrail events plus the last 5 redacted samples.

    The AI Gateway ``inference_table`` schema does **not** expose explicit
    redaction counters. Guardrail blocks surface as 4xx responses whose
    JSON ``message`` field mentions ``guardrail`` or ``pii``. We classify
    direction (``input`` vs ``output``) by inspecting the message body.

    No raw user content is returned — only metadata + the guardrail message
    string itself, which is the platform's own description of the block.
    """
    # Only count *actual* PII/guardrail blocks. The earlier filter also
    # matched generic request-validation errors that mention "guardrail"
    # in the failure preamble (e.g. "input guardrail request failure: Bad
    # request: json: unknown field …"). Those are schema parse errors, not
    # PII redactions, and they pollute the redaction counter.
    pii_filter = """
status_code >= 400
AND LOWER(coalesce(get_json_object(response, '$.message'), '')) LIKE '%pii%'
AND LOWER(coalesce(get_json_object(response, '$.message'), ''))
    NOT LIKE '%bad request%'
"""
    bucket_sql = f"""
WITH events AS (
  SELECT
    date_trunc('HOUR', request_time) AS hr,
    CASE
      WHEN LOWER(coalesce(get_json_object(response, '$.message'), '')) LIKE '%input%'  THEN 'input'
      WHEN LOWER(coalesce(get_json_object(response, '$.message'), '')) LIKE '%output%' THEN 'output'
      ELSE 'input'
    END AS direction
  FROM {_gateway_table(settings)}
  WHERE request_time > current_timestamp() - INTERVAL {hours} HOURS
    AND ({pii_filter})
)
SELECT hr, direction, count(*) AS events
FROM events
GROUP BY hr, direction
ORDER BY hr ASC, direction ASC
"""
    sample_sql = f"""
SELECT
  request_time                                            AS ts,
  databricks_request_id                                   AS request_id,
  status_code                                             AS status,
  CASE
    WHEN LOWER(coalesce(get_json_object(response, '$.message'), '')) LIKE '%input%'  THEN 'input'
    WHEN LOWER(coalesce(get_json_object(response, '$.message'), '')) LIKE '%output%' THEN 'output'
    ELSE 'input'
  END                                                     AS direction,
  -- truncate platform message to 240 chars; do NOT include any payload content
  substring(coalesce(get_json_object(response, '$.message'), ''), 1, 240) AS message
FROM {_gateway_table(settings)}
WHERE request_time > current_timestamp() - INTERVAL {hours} HOURS
  AND ({pii_filter})
ORDER BY request_time DESC
LIMIT 5
"""
    buckets, b_err = _safe_query(sql, bucket_sql)
    samples, s_err = _safe_query(sql, sample_sql)

    total = sum(int(r.get("events", 0) or 0) for r in buckets)
    by_direction = {"input": 0, "output": 0}
    for r in buckets:
        d = (r.get("direction") or "input").lower()
        if d in by_direction:
            by_direction[d] += int(r.get("events", 0) or 0)

    return {
        "hours": hours,
        "total": total,
        "by_direction": by_direction,
        "buckets": buckets,
        "samples": samples,
        "error": b_err or s_err,
    }
