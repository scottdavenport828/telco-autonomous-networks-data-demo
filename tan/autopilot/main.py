"""Job entrypoints — one function per autopilot stage."""

from __future__ import annotations

from pyspark.sql import SparkSession

from tan.autopilot.detector import DetectorConfig, detect_and_create
from tan.autopilot.rca import analyse_pending_incidents
from tan.autopilot.remediator import apply_proposed_actions
from tan.autopilot.verifier import verify_and_close
from tan.settings import SETTINGS


def _spark() -> SparkSession:
    return SparkSession.builder.getOrCreate()  # type: ignore[attr-defined]


def cmd_detect() -> None:
    n = detect_and_create(
        _spark(),
        config=DetectorConfig(
            catalog=SETTINGS.catalog,
            schema=SETTINGS.schema,
            erab_threshold=SETTINGS.erab_success_rate_threshold,
            retain_threshold=SETTINGS.retainability_threshold,
        ),
    )
    print(f"detector: {n} new incidents")


def cmd_rca() -> None:
    n = analyse_pending_incidents(_spark(), catalog=SETTINGS.catalog, schema=SETTINGS.schema)
    print(f"rca: {n} incidents analysed")


def cmd_remediate() -> None:
    n = apply_proposed_actions(_spark(), catalog=SETTINGS.catalog, schema=SETTINGS.schema)
    print(f"remediator: {n} actions applied")


def cmd_verify() -> None:
    actions, incidents = verify_and_close(
        _spark(),
        catalog=SETTINGS.catalog,
        schema=SETTINGS.schema,
        erab_threshold=SETTINGS.erab_success_rate_threshold,
        retain_threshold=SETTINGS.retainability_threshold,
    )
    print(f"verifier: verified {actions} actions, closed {incidents} incidents")
