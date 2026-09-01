# forge-canary: FORGE-CANARY-C4CDF9EBB33965998B2D609A6897A25C
from __future__ import annotations

import pathlib

import control_lib
import verifier_lib

CONTROL_ID = "CTL_stale_register_pressure"
KIND = "stale"
EXPECTATION = (
    "a run that keeps the pre M5 unbounded register liveness assumption, declaring no "
    "architectural_register_ceiling or the pre repin value and emitting a deeply overlapped "
    "schedule whose recomputed peak liveness exceeds the live ceiling, scores below threshold "
    "and C_M5_register_pressure_binding attributes the zero"
)


def build(workspace: pathlib.Path, records: list) -> None:
    control_lib.write_scheduler_tar(workspace, control_lib.reference_source())
    stale = dict(verifier_lib.live_registry())
    stale.pop("architectural_register_ceiling", None)
    stale.pop("architectural_register_ceiling_pre", None)
    manifest = verifier_lib.live_manifest()
    control_lib.emit_schedule_bundle(
        workspace,
        scheduling_model=stale,
        declared_register_ceiling=manifest.get("architectural_register_ceiling"),
    )
    control_lib.write_reward_log(workspace, records)
