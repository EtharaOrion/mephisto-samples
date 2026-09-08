#!/usr/bin/env python3
"""Local pre-submission checker for the LatticeStore task.

Runs the public probe workloads against your built `lattice` binary and compares only the final store-state digest of each workload against the shipped expected digests. This is a coarse check: it does not validate command stdout, stderr, or exit codes, and the hidden workloads are regenerated fresh at scoring time. Passing every public probe here is necessary but far from sufficient.

Usage: python3 verify_local.py [path/to/lattice-binary]
Default binary path: workspace/target/release/lattice
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBES = HERE / "public_probes"

sys.path.insert(0, str(HERE))
import run_workloads  # noqa: E402


def main() -> int:
    binary = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "workspace" / "target" / "release" / "lattice"
    if not binary.is_file():
        print(f"binary not found: {binary}")
        return 1
    expected = json.loads((PROBES / "expected" / "_transcript.json").read_text())
    with tempfile.TemporaryDirectory(prefix="lattice-local-") as scratch:
        actual = run_workloads.run_all(str(binary), PROBES, Path(scratch))
    matched = 0
    total = 0
    for wid in sorted(expected):
        total += 1
        exp_state = expected[wid].get("store_state")
        act = actual.get(wid)
        if act is not None and act.get("store_state") == exp_state:
            matched += 1
            continue
        print(f"FAIL {wid}")
        if act is None:
            print("  missing transcript")
        else:
            print(f"  store_state differs: expected {exp_state} got {act.get('store_state')}")
    print(f"{matched}/{total} public probes match")
    return 0 if matched == total else 1


if __name__ == "__main__":
    sys.exit(main())
