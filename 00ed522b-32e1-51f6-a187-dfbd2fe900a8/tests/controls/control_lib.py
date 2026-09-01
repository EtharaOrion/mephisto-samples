# forge-canary: FORGE-CANARY-8C9E0B8D2FBCC6E24B34F86E4C4C76B9
from __future__ import annotations

import io
import json
import os
import pathlib
import sys
import tarfile

HERE = pathlib.Path(__file__).resolve().parent
TESTS = HERE.parent
BUNDLE = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS / "checkers"))

import registry
import verifier_lib

CONTROL_UUID = "00000000-0000-4000-8000-000000000000"
REFERENCE_TREE = BUNDLE / "solution" / "reference_nester"
SYNTHETIC_ATTEMPTS = 48


def prepare_mounts(root: pathlib.Path, attempt_index: int) -> dict:
    state = registry.resolve_state(attempt_index)
    instance_dir = root / "mnt" / "instances"
    authority_dir = root / "mnt" / "authority"
    instance_dir.mkdir(parents=True, exist_ok=True)
    authority_dir.mkdir(parents=True, exist_ok=True)
    (instance_dir / "manifest.json").write_text(json.dumps(state["manifest"], indent=2, sort_keys=True) + "\n")
    (authority_dir / "authority.json").write_text(json.dumps(state["authority"], indent=2, sort_keys=True) + "\n")
    verifier_lib.INSTANCE_DIR = instance_dir
    verifier_lib.AUTHORITY_DIR = authority_dir
    os.environ["EDGEBENCH_INSTANCE_DIR"] = str(instance_dir)
    os.environ["EDGEBENCH_AUTHORITY_DIR"] = str(authority_dir)
    verifier_lib._MEMO.clear()
    return state


def synthesize_harness(root: pathlib.Path, attempts: int = SYNTHETIC_ATTEMPTS) -> list[dict]:
    log_dir = root / "logs" / "harness"
    log_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for index in range(1, attempts + 1):
        records.append(
            {
                "attempt_index": index,
                "approach": f"candidate nesting configuration {index}",
                "measured_reward": round(0.02 * index, 6),
                "graded_feasible_instances": 4,
            }
        )
    (log_dir / "attempts.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records))
    (log_dir / "access_audit.jsonl").write_text(
        "".join(
            json.dumps(
                {"attempt_index": r["attempt_index"], "path": "/mnt/instances/public/public-000", "mode": "read"},
                sort_keys=True,
            )
            + "\n"
            for r in records
        )
    )
    verifier_lib.LOG_DIR = log_dir
    return records


def build_nester_tar(destination: pathlib.Path, patches: dict | None = None) -> pathlib.Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "w") as archive:
        for path in sorted((REFERENCE_TREE / "nester").rglob("*")):
            if not path.is_file() or path.suffix != ".py":
                continue
            text = path.read_text()
            for old, new in (patches or {}).get(path.name, []):
                if old not in text:
                    raise SystemExit(f"control patch anchor absent in {path.name}: {old[:48]}")
                text = text.replace(old, new)
            payload = text.encode("utf-8")
            info = tarfile.TarInfo(name=str(path.relative_to(REFERENCE_TREE)))
            info.size = len(payload)
            info.mtime = 0
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(payload))
    return destination


def write_nester(workspace: pathlib.Path, patches: dict | None = None) -> pathlib.Path:
    workspace.mkdir(parents=True, exist_ok=True)
    return build_nester_tar(workspace / f"{CONTROL_UUID}_D1_nester_src.tar", patches)


def public_rows(tar_path: pathlib.Path, label: str) -> list[dict]:
    sweep = verifier_lib.sweep(tar_path, verifier_lib.public_family(), label)
    if not sweep.get("ok"):
        raise SystemExit(f"control public sweep failed: {sweep.get('error')} {sweep.get('detail')}")
    rows = []
    for record in sweep["records"]:
        row = dict(record["payload"])
        row["solve_seconds"] = record["solve_seconds"]
        rows.append(row)
    return rows


def write_bundle(workspace: pathlib.Path, rows: list[dict]) -> None:
    (workspace / f"{CONTROL_UUID}_D2_placement_bundle.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    )


def write_reward_log(workspace: pathlib.Path, records: list[dict]) -> None:
    (workspace / f"{CONTROL_UUID}_D3_reward_log.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "attempt_index": record["attempt_index"],
                    "approach": record["approach"],
                    "measured_reward": record["measured_reward"],
                },
                sort_keys=True,
            )
            + "\n"
            for record in records
        )
    )
