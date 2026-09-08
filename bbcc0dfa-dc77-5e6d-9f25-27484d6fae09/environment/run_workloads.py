#!/usr/bin/env python3
"""Workload runner for p9iota_latticestore_workspace_reconstruction.

Executes workload JSONs produced by workload_generator.py against a lattice
CLI binary and records deterministic transcripts: per-step records plus a
final store-state digest (SHA-256 over sorted "relpath file-sha256" lines).
Paths in stderr are normalized (scratch dir -> {W}, inputs dir -> {D}) so
transcripts compare byte-for-byte across hosts.
"""

import hashlib
import json
import subprocess
from pathlib import Path

STEP_TIMEOUT = 300


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_stderr(text: str, scratch: str, inputs: str) -> str:
    return text.replace(scratch, "{W}").replace(inputs, "{D}")


def run_binary(binary, argv, scratch, inputs, out_path=None):
    try:
        proc = subprocess.run(
            [str(binary)] + argv,
            capture_output=True,
            timeout=STEP_TIMEOUT,
        )
        exit_code = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        exit_code, stdout, stderr = -1, b"", "TIMEOUT"
    rec = {
        "exit": exit_code,
        "stdout_sha256": sha256_hex(stdout),
        "stdout_len": len(stdout),
        "stderr": normalize_stderr(stderr, str(scratch), str(inputs)),
        "out_sha256": None,
        "out_len": None,
    }
    if out_path is not None and Path(out_path).is_file():
        blob = Path(out_path).read_bytes()
        rec["out_sha256"] = sha256_hex(blob)
        rec["out_len"] = len(blob)
    return rec


def apply_corrupt(store: Path, step):
    target = store / step["file"]
    if not target.is_file():
        return {"op": "corrupt", "file": step["file"], "applied": False}
    data = bytearray(target.read_bytes())
    skip = step["skip"]
    span = max(1, len(data) - skip)
    applied_offset = skip + (step["offset"] % span)
    if applied_offset >= len(data):
        applied_offset = len(data) - 1
    data[applied_offset] ^= step["xor"]
    target.write_bytes(bytes(data))
    return {
        "op": "corrupt",
        "file": step["file"],
        "applied": True,
        "applied_offset": applied_offset,
        "pre_size": len(data),
        "xor": step["xor"],
    }


def apply_truncate_journal(store: Path, step):
    target = store / "journal.llg"
    if not target.is_file():
        return {"op": "truncate_journal", "applied": False}
    data = target.read_bytes()
    keep = max(0, len(data) - step["drop"])
    target.write_bytes(data[:keep])
    return {
        "op": "truncate_journal",
        "applied": True,
        "pre_size": len(data),
        "drop": step["drop"],
    }


def store_state_digest(store: Path) -> str:
    lines = []
    for path in sorted(store.rglob("*")):
        if path.is_file():
            rel = path.relative_to(store).as_posix()
            lines.append(f"{rel} {sha256_hex(path.read_bytes())}")
    return sha256_hex("\n".join(lines).encode())


def run_workload(binary, workload, inputs_root: Path, scratch: Path):
    wid = workload["id"]
    store = scratch / wid / "store"
    outdir = scratch / wid / "out"
    store.parent.mkdir(parents=True, exist_ok=True)
    outdir.mkdir(parents=True, exist_ok=True)
    inputs = inputs_root / wid
    steps_out = []
    for step in workload["steps"]:
        op = step["op"]
        if op == "init":
            store.mkdir(parents=True, exist_ok=True)
            rec = run_binary(binary, ["init", str(store)], scratch, inputs)
        elif op in ("put", "put_missing"):
            rec = run_binary(binary, ["put", str(store), str(inputs / step["file"])], scratch, inputs)
        elif op in ("get", "get_unknown"):
            out_path = outdir / step["out"]
            rec = run_binary(binary, ["get", str(store), step["id"], str(out_path)], scratch, inputs, out_path)
        elif op == "verify":
            rec = run_binary(binary, ["verify", str(store)], scratch, inputs)
        elif op == "stats":
            rec = run_binary(binary, ["stats", str(store)], scratch, inputs)
        elif op == "raw":
            argv = [
                token.replace("{S}", str(store)).replace("{D}", str(inputs)).replace("{O}", str(outdir))
                for token in step["argv"]
            ]
            rec = run_binary(binary, argv, scratch, inputs)
        elif op == "corrupt":
            rec = apply_corrupt(store, step)
        elif op == "truncate_journal":
            rec = apply_truncate_journal(store, step)
        else:
            raise ValueError(f"unknown op {op}")
        rec["op"] = op
        steps_out.append(rec)
    return {"id": wid, "steps": steps_out, "store_state": store_state_digest(store)}


def run_all(binary, workload_dir, scratch):
    workload_dir = Path(workload_dir)
    scratch = Path(scratch)
    manifest = json.loads((workload_dir / "_manifest.json").read_text())
    inputs_root = workload_dir / "inputs"
    results = {}
    for wid in manifest["workloads"]:
        workload = json.loads((workload_dir / f"{wid}.json").read_text())
        results[wid] = run_workload(binary, workload, inputs_root, scratch)
    return results


if __name__ == "__main__":
    import sys

    binary_arg, dir_arg, scratch_arg, out_arg = sys.argv[1:5]
    recs = run_all(binary_arg, dir_arg, scratch_arg)
    Path(out_arg).write_text(json.dumps(recs, indent=1, sort_keys=True) + "\n")
    print(f"ran {len(recs)} workloads")
