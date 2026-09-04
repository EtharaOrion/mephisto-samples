"""Compiled deterministic rubric tests. GENERATED - do not hand-edit."""
from pathlib import Path

REWARD_PATH = Path("/logs/verifier/reward.txt")


def test_reward_file_exists() -> None:
    assert REWARD_PATH.exists(), f"missing {REWARD_PATH}"


def test_reward_in_unit_interval() -> None:
    v = float(REWARD_PATH.read_text().strip())
    assert 0.0 <= v <= 1.0, f"reward {v} outside [0, 1]"
