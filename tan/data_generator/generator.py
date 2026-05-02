"""Synthetic performance + cell_traces row generator.

For every (enodeb_id, cell_id) in `cell_profiles`, sample one row of telco PM
metrics anchored at the cell's learned (mean, std, min, max) per column. Apply
anomaly biases when an active row exists in `anomaly_schedule`. Append the
result to `performance` (and a proportional number of cell traces to
`cell_traces`) as a Delta append.

Decisions baked in:

* Numeric columns are drawn from a truncated normal in [min, max]. This keeps
  values plausible without preserving correlations across columns; that's a
  fair simplification for a demo.
* The QCI 1–9 ERAB Att / Succ / Rel families are *post-processed* so that
  Succ ≤ Att and the resulting `erab_success_rate` matches whatever target
  rate the anomaly engine wants (or the cell's baseline). Same idea for
  retainability.
* `cell_traces` rows reuse the cell's keys and a synthetic UE id, with the
  S1 sig-conn-setup result column biased toward `Failure_*` during anomaly
  windows. The rest of the 74 columns are NULL — the agent's analysis tools
  only read a handful of them.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StructType

from tan.data_generator.anomaly import (
    CellAnomaly,
    active_anomalies,
    apply_to_retainability,
    apply_to_succ_rate,
)


# ---------------------------------------------------------------------------
# Profile cache
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ColumnStats:
    mean: float
    std: float
    min_val: float
    max_val: float
    p10: float | None
    p90: float | None


def load_profiles(
    spark: SparkSession, *, profiles_table: str
) -> dict[tuple[str, str], dict[str, ColumnStats]]:
    """Return ``{(enodeb_id, cell_id): {column: ColumnStats}}``."""
    rows = spark.read.table(profiles_table).collect()
    by_cell: dict[tuple[str, str], dict[str, ColumnStats]] = {}
    for r in rows:
        cell = (str(r.enodeb_id), str(r.cell_id))
        by_cell.setdefault(cell, {})[r.column_name] = ColumnStats(
            mean=float(r.mean) if r.mean is not None else 0.0,
            std=float(r.std) if r.std is not None else 0.0,
            min_val=float(r.min_val) if r.min_val is not None else 0.0,
            max_val=float(r.max_val) if r.max_val is not None else 0.0,
            p10=float(r.p10) if r.p10 is not None else None,
            p90=float(r.p90) if r.p90 is not None else None,
        )
    return by_cell


# ---------------------------------------------------------------------------
# Numeric sampling
# ---------------------------------------------------------------------------


def _sample(stats: ColumnStats, *, rng: random.Random) -> float:
    """Sample a value from a truncated normal in [min_val, max_val]."""
    if stats.std and stats.std > 0:
        for _ in range(8):  # few rejection attempts
            v = rng.gauss(stats.mean, stats.std)
            if stats.min_val <= v <= stats.max_val:
                return v
        return max(stats.min_val, min(stats.max_val, rng.gauss(stats.mean, stats.std)))
    return stats.mean


def _floor_to_15min(ts: datetime) -> datetime:
    minute = (ts.minute // 15) * 15
    return ts.replace(minute=minute, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Core: build one performance row for one cell
# ---------------------------------------------------------------------------


def _build_perf_row(
    enodeb_id: str,
    cell_id: str,
    measurement_end: datetime,
    cell_stats: dict[str, ColumnStats],
    target_schema: StructType,
    anomalies: list[CellAnomaly],
    *,
    rng: random.Random,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "enodeb_id": int(enodeb_id) if enodeb_id.isdigit() else enodeb_id,
        "cell_id": int(cell_id) if cell_id.isdigit() else cell_id,
        "measurement_end": measurement_end,
    }

    # Sample every numeric column we have stats for.
    for col, stats in cell_stats.items():
        v = _sample(stats, rng=rng)
        row[col] = int(round(v)) if abs(v - round(v)) < 1e-9 or stats.max_val < 1e6 and v.is_integer() else v

    # ---- Bias to hit a target ERAB success rate ----------------------------
    att_keys = [f"ERAB_EstabInitAttNbr_QCI{i}" for i in range(1, 10)]
    succ_keys = [f"ERAB_EstabInitSuccNbr_QCI{i}" for i in range(1, 10)]
    att_total = sum(int(row.get(k, 0) or 0) for k in att_keys)
    if att_total > 0:
        baseline_rate = (
            sum(int(row.get(k, 0) or 0) for k in succ_keys) / att_total
            if att_total
            else 0.99
        )
        target_rate = apply_to_succ_rate(anomalies, baseline_rate)
        target_rate = max(0.0, min(1.0, target_rate))
        target_succ_total = int(round(att_total * target_rate))
        # Rebalance succ columns proportionally to att.
        if att_total > 0:
            for sk, ak in zip(succ_keys, att_keys):
                a = int(row.get(ak, 0) or 0)
                row[sk] = int(round(target_succ_total * (a / att_total))) if att_total else 0
                row[sk] = min(row[sk], a)  # never exceed att

    # ---- Bias to hit a target retainability (releases/hour) -----------------
    rel_keys = [f"ERAB_RelActNbr_QCI{i}" for i in range(1, 10)]
    session_time = int(row.get("ERAB_SessionTimeUE", 0) or 0)
    if session_time > 0:
        rel_total = sum(int(row.get(k, 0) or 0) for k in rel_keys)
        baseline_retain = (rel_total / session_time) * 3600.0
        target_retain = apply_to_retainability(anomalies, baseline_retain)
        target_retain = max(0.0, target_retain)
        target_rel_total = int(round((target_retain / 3600.0) * session_time))
        # Spread proportionally; at least 0.
        per_qci = max(0, target_rel_total // 9)
        for k in rel_keys:
            row[k] = per_qci

    return _coerce_to_schema(row, target_schema)


def _coerce_to_schema(row: dict[str, Any], target_schema: StructType) -> dict[str, Any]:
    """Snap a row dict to the target schema's column names + types.

    Adds missing columns as ``None``; casts existing values to the column's
    declared type. ``createDataFrame`` is unforgiving about both ordering and
    type mismatches, so we normalise here.
    """
    out: dict[str, Any] = {}
    for f in target_schema.fields:
        name = f.name
        v = row.get(name)
        if v is None:
            out[name] = None
            continue
        ts = f.dataType.simpleString()
        if ts == "string":
            out[name] = str(v)
        elif ts in ("int", "bigint", "smallint", "tinyint"):
            try:
                out[name] = int(v)
            except (TypeError, ValueError):
                out[name] = None
        elif ts in ("double", "float"):
            try:
                out[name] = float(v)
            except (TypeError, ValueError):
                out[name] = None
        elif ts == "timestamp":
            out[name] = v if isinstance(v, datetime) else None
        elif ts == "boolean":
            out[name] = bool(v)
        else:
            out[name] = v
    return out


# ---------------------------------------------------------------------------
# Cell-trace row builder
# ---------------------------------------------------------------------------


_PROC_TYPES = ["RRC Conn Setup", "S1 Sig Conn Setup", "ERAB Setup", "ERAB Release"]
_OK_OUTCOME = "Success"
_FAIL_OUTCOMES = [
    "Failure_RRC_NotUsed",
    "Failure_S1_Time_Out",
    "Failure_Security",
]


def _build_trace_rows(
    enodeb_id: str,
    cell_id: str,
    measurement_end: datetime,
    target_schema: StructType,
    anomalies: list[CellAnomaly],
    *,
    rng: random.Random,
    n_rows: int = 6,
) -> list[dict[str, Any]]:
    fail_bias = 0.05
    for a in anomalies:
        if a.kpi == "erab_success_rate" and a.magnitude < 1.0:
            fail_bias = max(fail_bias, 1.0 - a.magnitude)

    rows: list[dict[str, Any]] = []
    schema_cols = {f.name: f.dataType.simpleString() for f in target_schema.fields}
    for _ in range(n_rows):
        starttime = measurement_end + timedelta(seconds=rng.randint(0, 14 * 60))
        endtime = starttime + timedelta(seconds=rng.randint(1, 60))
        outcome = (
            rng.choice(_FAIL_OUTCOMES) if rng.random() < fail_bias else _OK_OUTCOME
        )
        row: dict[str, Any] = {c: None for c in schema_cols}
        row["procedure_type"] = rng.choice(_PROC_TYPES)
        row["starttime"] = starttime
        row["endtime"] = endtime
        row["imsi"] = 99900_00000_00000 + rng.randint(0, 99_999_999)
        row["start_enodeb_id"] = enodeb_id
        row["start_cell_id"] = cell_id
        row["end_enodeb_id"] = enodeb_id
        row["end_cell_id"] = cell_id
        row["s1_sig_conn_setup_sig_conn_result"] = outcome
        row["rrc_conn_setup_rrc_result"] = (
            "Success" if outcome == _OK_OUTCOME else "Failure"
        )
        row["initial_ctxt_setup_initial_ctxt_result"] = row["rrc_conn_setup_rrc_result"]
        row["bearer_id"] = rng.randint(1, 8)
        row["qci"] = rng.choice([1, 5, 6, 7, 8, 9])
        rows.append(_coerce_to_schema(row, target_schema))
    return rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_batch(
    spark: SparkSession,
    *,
    perf_table: str,
    traces_table: str,
    profiles_table: str,
    anomaly_table: str,
    measurement_end: datetime | None = None,
    seed: int | None = None,
) -> tuple[int, int]:
    """Generate one tick's worth of rows and append to Delta. Returns (perf_rows, trace_rows)."""
    rng = random.Random(seed)
    me = _floor_to_15min(measurement_end or datetime.now(timezone.utc))

    profiles = load_profiles(spark, profiles_table=profiles_table)
    if not profiles:
        raise RuntimeError(
            f"{profiles_table} is empty — run notebooks/07_build_profile.py first"
        )
    # Use the *end* of the 15-min window (me + 15min) when looking up active
    # anomalies. measurement_end is the window's start; an anomaly that starts
    # mid-window is still active during the window, and the demo experience
    # depends on "click button → next tick reflects it".
    anomalies_by_cell = active_anomalies(
        spark, table=anomaly_table, at=me + timedelta(minutes=15)
    )

    perf_schema = spark.read.table(perf_table).schema
    traces_schema = spark.read.table(traces_table).schema

    perf_rows: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []
    for (enb, cell), stats in profiles.items():
        anomalies = anomalies_by_cell.get((enb, cell), [])
        perf_rows.append(
            _build_perf_row(enb, cell, me, stats, perf_schema, anomalies, rng=rng)
        )
        trace_rows.extend(
            _build_trace_rows(enb, cell, me, traces_schema, anomalies, rng=rng)
        )

    if perf_rows:
        spark.createDataFrame(perf_rows, schema=perf_schema).write.format(
            "delta"
        ).mode("append").saveAsTable(perf_table)
    if trace_rows:
        spark.createDataFrame(trace_rows, schema=traces_schema).write.format(
            "delta"
        ).mode("append").saveAsTable(traces_table)

    return len(perf_rows), len(trace_rows)


def backfill(
    spark: SparkSession,
    *,
    perf_table: str,
    traces_table: str,
    profiles_table: str,
    anomaly_table: str,
    until: datetime | None = None,
    hours: int = 48,
    step_minutes: int = 15,
    traces_per_cell_per_tick: int = 1,
) -> tuple[int, int]:
    """Generate ``hours`` of synthetic data ending at ``until`` and write in
    one big append per table.

    A single ``spark.createDataFrame`` + ``write.append`` is dramatically
    cheaper than running ``generate_batch`` (which does its own write) once
    per tick — at 15-min cadence over multiple days that would mean 10K+
    write operations. We collect everything in memory first and flush at
    the end. ``hours`` defaults to 48 because the dashboard's "last 24h"
    view is what the demo really needs; bump it up if you want a longer
    history for Observability charts.
    """
    until = _floor_to_15min(until or datetime.now(timezone.utc))
    start = until - timedelta(hours=hours) + timedelta(minutes=step_minutes)
    start = _floor_to_15min(start)

    profiles = load_profiles(spark, profiles_table=profiles_table)
    if not profiles:
        raise RuntimeError(
            f"{profiles_table} is empty — run notebooks/07_build_profile.py first"
        )
    perf_schema = spark.read.table(perf_table).schema
    traces_schema = spark.read.table(traces_table).schema

    perf_rows: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []

    cursor = start
    n_batches = 0
    while cursor <= until:
        rng = random.Random(int(cursor.timestamp()))
        anomalies_by_cell = active_anomalies(spark, table=anomaly_table, at=cursor)
        for (enb, cell), stats in profiles.items():
            cell_anomalies = anomalies_by_cell.get((enb, cell), [])
            perf_rows.append(
                _build_perf_row(enb, cell, cursor, stats, perf_schema, cell_anomalies, rng=rng)
            )
            trace_rows.extend(
                _build_trace_rows(
                    enb,
                    cell,
                    cursor,
                    traces_schema,
                    cell_anomalies,
                    rng=rng,
                    n_rows=traces_per_cell_per_tick,
                )
            )
        n_batches += 1
        cursor += timedelta(minutes=step_minutes)

    print(f"backfill: built {len(perf_rows)} perf rows + {len(trace_rows)} trace rows across {n_batches} batches; writing…")

    if perf_rows:
        spark.createDataFrame(perf_rows, schema=perf_schema).write.format(
            "delta"
        ).mode("append").saveAsTable(perf_table)
    if trace_rows:
        spark.createDataFrame(trace_rows, schema=traces_schema).write.format(
            "delta"
        ).mode("append").saveAsTable(traces_table)

    return len(perf_rows), len(trace_rows)
