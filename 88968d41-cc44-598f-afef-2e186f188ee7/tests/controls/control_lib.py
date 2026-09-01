# forge-canary: FORGE-CANARY-1254CEC55E3E94C4E944B7B7CCD8B8F1
from __future__ import annotations

import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
TESTS = HERE.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS / "checkers"))
sys.path.insert(0, str(TESTS / "private"))

import registry
import verifier_lib

CONTROL_UUID = "00000000-0000-4000-8000-000000000000"
CONTROL_ATTEMPT_INDEX = 40
SYNTHETIC_ATTEMPTS = 40

CONSTRUCTOR_TEMPLATE = '''"""{banner}"""

from __future__ import annotations

AMBIENT_PARAMS_ID = {ambient_params_id!r}
PREDICATE_DIGEST = {predicate_digest!r}

POINTS = {points!r}


def construct(params: dict) -> list:
    return [list(point) for point in POINTS]
'''


def prepare_geometry(root: pathlib.Path, attempt_index: int) -> dict:
    state = registry.resolve_state(attempt_index)
    geometry_dir = root / "mnt" / "geometry"
    geometry_dir.mkdir(parents=True, exist_ok=True)
    (geometry_dir / "manifest.json").write_text(json.dumps(state["geometry"], indent=2, sort_keys=True) + "\n")
    (geometry_dir / "predicate.json").write_text(json.dumps(state["predicate"], indent=2, sort_keys=True) + "\n")
    verifier_lib.GEOMETRY_DIR = geometry_dir
    os.environ["EDGEBENCH_GEOMETRY_DIR"] = str(geometry_dir)
    for key in [key for key in verifier_lib._MEMO if key.startswith("recompute:")]:
        verifier_lib._MEMO.pop(key)
    return state


def synthesize_harness(root: pathlib.Path, attempts: int = SYNTHETIC_ATTEMPTS) -> list:
    log_dir = root / "logs" / "harness"
    log_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for index in range(1, attempts + 1):
        records.append(
            {
                "attempt_index": index,
                "approach": f"candidate construction family {index}",
                "measured_reward": round(index * 0.004, 6),
                "search_seconds": 12.5,
            }
        )
    (log_dir / "attempts.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records))
    (log_dir / "access_audit.jsonl").write_text(
        "".join(
            json.dumps(
                {"attempt_index": r["attempt_index"], "path": "/mnt/geometry/manifest.json", "mode": "read"},
                sort_keys=True,
            )
            + "\n"
            for r in records
        )
    )
    verifier_lib.LOG_DIR = log_dir
    return records


def points_from(packed: list, ambient: dict) -> list:
    return [registry.unpack_point(value, ambient["dimension"]) for value in packed]


def build_points(ambient: dict, predicate: dict, limit: int | None = None) -> list:
    order = registry.enumerate_ambient(ambient)
    if limit is not None:
        order = order[:limit]
    return points_from(registry.greedy(ambient, predicate, order), ambient)


def write_constructor(workspace: pathlib.Path, points: list, ambient_params_id: str, predicate_digest: str, banner: str) -> pathlib.Path:
    workspace.mkdir(parents=True, exist_ok=True)
    path = workspace / f"{CONTROL_UUID}_D1_construct.py"
    path.write_text(
        CONSTRUCTOR_TEMPLATE.format(
            banner=banner,
            ambient_params_id=ambient_params_id,
            predicate_digest=predicate_digest,
            points=[list(point) for point in points],
        )
    )
    return path


def write_bundle(workspace: pathlib.Path, payload: dict) -> None:
    (workspace / f"{CONTROL_UUID}_D2_construction_bundle.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )


def write_reward_log(workspace: pathlib.Path, records: list) -> None:
    lines = [
        json.dumps(
            {
                "attempt_index": record["attempt_index"],
                "approach": record["approach"],
                "measured_reward": record["measured_reward"],
            },
            sort_keys=True,
        )
        for record in records
    ]
    (workspace / f"{CONTROL_UUID}_D3_reward_log.jsonl").write_text("\n".join(lines) + "\n")


def honest_bundle(points: list, ambient: dict, predicate: dict, geometry: dict) -> dict:
    indexed = registry.canonicalise(points, ambient)
    return {
        "ambient_params_id": geometry["ambient_params_id"],
        "predicate_digest": predicate["predicate_digest"],
        "point_count": len(points),
        "points": [list(point) for point in points],
        "certificate": registry.certificate(indexed, ambient, predicate, geometry),
        "search_seconds": 12.5,
    }
