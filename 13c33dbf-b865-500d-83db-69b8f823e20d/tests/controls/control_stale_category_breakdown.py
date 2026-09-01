# forge-canary: FORGE-CANARY-6CAA841C1ADA9B611F786DD993BFAE95
from __future__ import annotations

import pathlib

import control_lib

CONTROL_ID = "CTL_stale_category_breakdown"
KIND = "stale"
EXPECTATION = (
    "a run that keeps the pre M3 aggregate counts only reconciliation surface scores below "
    "threshold and C_M3_category_breakdown_binding attributes the zero"
)

PRE_M3_SURFACE_FIELDS = ("passed_by_category", "unaccelerated_programs", "instruction_census_digest")


def build(workspace: pathlib.Path, records: list) -> None:
    control_lib.write_sources(workspace, control_lib.reference_files())
    control_lib.write_reward_log(workspace, records)
    report = control_lib.honest_report_payload(workspace)
    for field in PRE_M3_SURFACE_FIELDS:
        report.pop(field, None)
    control_lib.write_report(workspace, report)
    control_lib.write_pipeline(workspace, control_lib.honest_pipeline_payload(workspace))
