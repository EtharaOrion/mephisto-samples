# forge-canary: FORGE-CANARY-47F499A518AD2A66AC8C481E3798DDC4
from __future__ import annotations

import pathlib

import control_lib
import verifier_lib

CONTROL_ID = "CTL_decoy"
KIND = "decoy_or_distractor"
EXPECTATION = (
    "a run that retunes for the announced machine model rotation while ignoring the silent "
    "latency table repin scores below threshold"
)


def build(workspace: pathlib.Path, records: list) -> None:
    control_lib.write_scheduler_tar(workspace, control_lib.reference_source())
    live = verifier_lib.live_registry()
    retuned = dict(live)
    retuned["latencies"] = verifier_lib.live_manifest()["latencies"]
    control_lib.emit_schedule_bundle(
        workspace,
        scheduling_model=retuned,
        declared_digest=live["latency_table_digest"],
        declared_machine_model_id=live["machine_model_id"],
    )
    control_lib.write_reward_log(workspace, records)
