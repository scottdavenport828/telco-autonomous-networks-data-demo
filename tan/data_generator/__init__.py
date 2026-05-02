"""Synthetic streaming data generator for the telco demo.

Reads `cell_profiles` (per-cell column statistics learned from the upstream
fixture) and emits fresh PM rows + cell traces at the source's 15-min cadence.

Three entry points:

* :func:`build_cell_profiles` (profile.py) — one-shot, computes statistics from
  the existing `performance` Delta table and writes them to `cell_profiles`.
* :func:`generate_batch` (generator.py) — writes one tick's worth of rows
  (one per cell) to `performance` and a proportional number of `cell_traces`.
* :func:`active_anomalies` (anomaly.py) — pulls active rows from
  `anomaly_schedule` so the generator can bias the next batch.
"""
