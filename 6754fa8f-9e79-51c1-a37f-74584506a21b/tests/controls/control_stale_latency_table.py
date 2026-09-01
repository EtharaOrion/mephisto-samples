# forge-canary: FORGE-CANARY-F18CDD9D27957C9FD24743C43CBE6FEC
from __future__ import annotations

import pathlib

import control_lib
import verifier_lib

CONTROL_ID = "CTL_stale_latency_table"
KIND = "stale"
EXPECTATION = (
    "a run that keeps the pre M2 latency table binding scores below threshold and "
    "C_M2_latency_table_binding attributes the zero"
)


def build(workspace: pathlib.Path, records: list) -> None:
    control_lib.write_scheduler_tar(workspace, control_lib.reference_source())
    stale = dict(verifier_lib.live_registry())
    manifest = verifier_lib.live_manifest()
    stale["latencies"] = manifest["latencies"]
    control_lib.emit_schedule_bundle(
        workspace, scheduling_model=stale, declared_digest=manifest["latency_table_digest"]
    )
    control_lib.write_reward_log(workspace, records)
