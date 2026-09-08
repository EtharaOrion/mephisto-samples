import os


def test_reward_file_exists():
    assert os.path.exists("/logs/verifier/reward.txt"), "reward.txt missing"


def test_reward_in_unit_interval():
    with open("/logs/verifier/reward.txt", "r") as f:
        v = float(f.read().strip())
    assert 0.0 <= v <= 1.0, f"reward {v} outside [0,1]"
