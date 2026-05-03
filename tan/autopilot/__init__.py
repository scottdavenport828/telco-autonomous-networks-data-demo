"""Autonomous triage + remediation closed loop.

Four stages, each invoked from its own notebook on a schedule:

1. ``detector.detect_and_create()`` — pure SQL, scans `performance_kpi` for
   threshold violations, dedupes against open incidents, inserts new ones.
2. ``rca.analyse_pending_incidents()`` — runs `RcaOrchestratorAgent` against
   any incident with no `final_analysis`, writes the report back via the
   agent's own `update_incident` tool.
3. ``remediator.apply_proposed_actions()`` — promotes PROPOSED actions to
   APPLIED and schedules a self-healing anomaly entry that pushes the cell's
   KPI back toward baseline.
4. ``verifier.verify_and_close()`` — checks recovered cells, marks actions
   VERIFIED and incidents RESOLVED.

All four read ``autopilot_state`` first and short-circuit if `enabled='false'`.
"""

from __future__ import annotations
