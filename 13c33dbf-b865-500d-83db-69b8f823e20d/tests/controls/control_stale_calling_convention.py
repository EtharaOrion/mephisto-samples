# forge-canary: FORGE-CANARY-22582D8CBA73BFC7E63DCE10B60DAC9D
from __future__ import annotations

import pathlib

import control_lib

CONTROL_ID = "CTL_stale_calling_convention"
KIND = "stale"
EXPECTATION = (
    "a submission that keeps the pre M2 stack slot calling convention scores below threshold "
    "and C_M2_calling_convention_binding attributes the zero"
)


def _pin_stack_convention(files: dict) -> dict:
    files["lowering.py"] = files["lowering.py"].replace(
        '        self.argument_registers = [int(name[1:]) for name in abi["argument_registers"]]\n'
        '        self.home_registers = sorted(int(name[1:]) for name in abi["callee_saved"])',
        '        self.argument_registers = []\n'
        '        self.home_registers = [8, 9, 10, 11, 12, 13]',
    )
    return files


def build(workspace: pathlib.Path, records: list) -> None:
    control_lib.write_sources(workspace, control_lib.reference_files(_pin_stack_convention))
    control_lib.write_reward_log(workspace, records)
    control_lib.honest_artifacts(workspace)
