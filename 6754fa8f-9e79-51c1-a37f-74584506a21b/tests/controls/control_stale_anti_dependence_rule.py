# forge-canary: FORGE-CANARY-5E66977EB92CE4DFF49566BA6EF73BDC
from __future__ import annotations

import pathlib

import control_lib
import verifier_lib

CONTROL_ID = "CTL_stale_anti_dependence_rule"
KIND = "stale"
EXPECTATION = (
    "a run that keeps the pre M6 late_landing_relaxed anti dependence rule and hoists an "
    "overwriting operation above a pending reader on the consumer latency slack scores below "
    "threshold and C_M6_anti_dependence_rule_binding attributes the zero"
)


def build(workspace: pathlib.Path, records: list) -> None:
    control_lib.write_scheduler_tar(workspace, control_lib.reference_source())
    stale = dict(verifier_lib.live_registry())
    manifest = verifier_lib.live_manifest()
    stale["war_rule"] = manifest["war_rule"]
    control_lib.emit_schedule_bundle(
        workspace,
        scheduling_model=stale,
        declared_war_rule=manifest["war_rule"],
    )
    control_lib.write_reward_log(workspace, records)
