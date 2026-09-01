# forge-canary: FORGE-CANARY-1BB2B264DB7B36163B3AD778A3401A39
from __future__ import annotations

import pathlib

import control_lib

CONTROL_ID = "CTL_stale_pass_fact_ledger"
KIND = "stale"
EXPECTATION = (
    "a run that keeps the pre M5 declared pass list only pipeline surface scores below "
    "threshold and C_M5_pass_fact_ledger_binding attributes the zero"
)

PRE_M5_REPORT_FIELDS = ("instruction_census_digest",)


def build(workspace: pathlib.Path, records: list) -> None:
    control_lib.write_sources(workspace, control_lib.reference_files())
    control_lib.write_reward_log(workspace, records)
    report = control_lib.honest_report_payload(workspace)
    for field in PRE_M5_REPORT_FIELDS:
        report.pop(field, None)
    control_lib.write_report(workspace, report)
    pipeline = dict(control_lib.honest_pipeline_payload(workspace))
    pipeline.pop("pass_fact_ledger", None)
    control_lib.write_pipeline(workspace, pipeline)
