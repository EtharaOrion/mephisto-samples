"""Attempt recorder for edgebench/cap_set_extremal_construction.

Evaluator owned. Advances the attempt counter, asks the sealed applier to settle
the geometry registry for the new attempt, executes the submitted constructor,
recomputes the pinned construction property over the emitted point set, and
appends the run record and the file access audit the verifier reconciles against.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import ambient

GEOMETRY_DIR = pathlib.Path(os.environ.get("EDGEBENCH_GEOMETRY_DIR", "/mnt/geometry"))
LOG_DIR = pathlib.Path(os.environ.get("EDGEBENCH_LOG_DIR", "/logs/harness"))
ADVANCE_COMMAND = os.environ.get("EDGEBENCH_ADVANCE_COMMAND", "sudo -n /usr/local/bin/edgebench-advance")


def _next_attempt_index() -> int:
    path = LOG_DIR / "attempts.jsonl"
    if not path.exists():
        return 1
    return sum(1 for line in path.read_text().splitlines() if line.strip()) + 1


def _advance(attempt_index: int) -> dict:
    command = ADVANCE_COMMAND.split() + [
        "--attempt-index",
        str(attempt_index),
        "--geometry-dir",
        str(GEOMETRY_DIR),
    ]
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"mutation applier failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _load(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("submitted_constructor_local", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--construct", required=True)
    parser.add_argument("--approach", required=True)
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    attempt_index = _next_attempt_index()
    advance = _advance(attempt_index)
    ambient.GEOMETRY_DIR = GEOMETRY_DIR
    geometry = ambient.live_geometry()
    predicate = ambient.live_predicate()
    params = {"geometry": geometry, "predicate": predicate}

    construct_path = pathlib.Path(args.construct).resolve()
    module = _load(construct_path)
    started = time.monotonic()
    points = [list(point) for point in module.construct(params)]
    search_seconds = time.monotonic() - started

    try:
        indexed = ambient.canonicalise(points, geometry)
        emission_error = None
    except ValueError as exc:
        indexed = []
        emission_error = str(exc)

    if emission_error is None:
        measurement = ambient.measure(indexed, geometry, predicate)
    else:
        measurement = {
            "quadruple_collisions": -1,
            "degenerate_collision_count": -1,
            "violation_count": -1,
            "verified_size": 0,
        }
    reward = ambient.size_to_score(measurement["verified_size"], geometry)

    record = {
        "attempt_index": attempt_index,
        "approach": args.approach,
        "emitted_point_count": len(points),
        "verified_size": measurement["verified_size"],
        "measured_reward": reward,
        "search_seconds": round(search_seconds, 6),
        "ambient_params_id": geometry["ambient_params_id"],
        "predicate_digest": predicate["predicate_digest"],
        "emission_error": emission_error,
        "announcement": advance.get("announcement"),
    }
    with (LOG_DIR / "attempts.jsonl").open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    with (LOG_DIR / "access_audit.jsonl").open("a") as handle:
        for path in (GEOMETRY_DIR / "manifest.json", GEOMETRY_DIR / "predicate.json", construct_path):
            handle.write(
                json.dumps({"attempt_index": attempt_index, "path": str(path), "mode": "read"}, sort_keys=True)
                + "\n"
            )

    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
