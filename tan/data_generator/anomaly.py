"""Anomaly schedule: read active anomalies and translate them into per-cell biases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from pyspark.sql import SparkSession


@dataclass
class CellAnomaly:
    enodeb_id: str
    cell_id: str
    kpi: str  # 'erab_success_rate' | 'retainability'
    magnitude: float


def active_anomalies(
    spark: SparkSession, *, table: str, at: datetime
) -> dict[tuple[str, str], list[CellAnomaly]]:
    """Return anomalies whose [start_ts, end_ts) window contains ``at``.

    Result is keyed by ``(enodeb_id, cell_id)`` so the generator can look up
    a cell's anomalies in O(1).
    """
    rows = (
        spark.read.table(table)
        .filter("status IN ('PENDING', 'ACTIVE')")
        .filter(f"start_ts <= TIMESTAMP'{at.strftime('%Y-%m-%d %H:%M:%S')}'")
        .filter(f"end_ts > TIMESTAMP'{at.strftime('%Y-%m-%d %H:%M:%S')}'")
        .select("enodeb_id", "cell_id", "kpi", "magnitude")
        .collect()
    )

    out: dict[tuple[str, str], list[CellAnomaly]] = {}
    for r in rows:
        key = (str(r.enodeb_id), str(r.cell_id))
        out.setdefault(key, []).append(
            CellAnomaly(
                enodeb_id=str(r.enodeb_id),
                cell_id=str(r.cell_id),
                kpi=r.kpi,
                magnitude=float(r.magnitude),
            )
        )
    return out


def apply_to_succ_rate(anomalies: Iterable[CellAnomaly], baseline: float) -> float:
    """Return the success-rate value the generator should target for this tick."""
    for a in anomalies:
        if a.kpi == "erab_success_rate":
            # magnitude is the target rate (0..1 or 0..100). Treat <= 1 as fraction.
            return a.magnitude if a.magnitude <= 1.0 else a.magnitude / 100.0
    return baseline


def apply_to_retainability(anomalies: Iterable[CellAnomaly], baseline: float) -> float:
    """Return the retainability value (releases/hour) the generator should target."""
    for a in anomalies:
        if a.kpi == "retainability":
            return a.magnitude
    return baseline
