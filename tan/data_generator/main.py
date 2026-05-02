"""Job entrypoint for the streaming data generator.

The Databricks Job invokes this via ``notebooks/09_generate_tick.py`` for the
recurring path, or ``notebooks/08_backfill_to_now.py`` for the one-shot path.
This module exists so both notebooks share a single setup pathway.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pyspark.sql import SparkSession

from tan.data_generator.generator import backfill, generate_batch
from tan.data_generator.profile import build_cell_profiles
from tan.settings import SETTINGS


def _spark() -> SparkSession:
    return SparkSession.builder.getOrCreate()  # type: ignore[attr-defined]


def cmd_build_profile() -> None:
    n = build_cell_profiles(
        _spark(),
        source_table=SETTINGS.perf_table,
        target_table=f"{SETTINGS.catalog}.{SETTINGS.schema}.cell_profiles",
    )
    print(f"profiled {n} (cell, column) rows")


def cmd_tick(measurement_end: datetime | None = None) -> None:
    perf, traces = generate_batch(
        _spark(),
        perf_table=SETTINGS.perf_table,
        traces_table=SETTINGS.cell_traces_table,
        profiles_table=f"{SETTINGS.catalog}.{SETTINGS.schema}.cell_profiles",
        anomaly_table=f"{SETTINGS.catalog}.{SETTINGS.schema}.anomaly_schedule",
        measurement_end=measurement_end,
    )
    print(f"appended {perf} perf rows + {traces} trace rows")


def cmd_backfill(until: datetime | None = None) -> None:
    perf, traces = backfill(
        _spark(),
        perf_table=SETTINGS.perf_table,
        traces_table=SETTINGS.cell_traces_table,
        profiles_table=f"{SETTINGS.catalog}.{SETTINGS.schema}.cell_profiles",
        anomaly_table=f"{SETTINGS.catalog}.{SETTINGS.schema}.anomaly_schedule",
        until=until or datetime.now(timezone.utc),
    )
    print(f"backfill complete: {perf} perf rows + {traces} trace rows")
