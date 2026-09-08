"""Execute a rasterlab binary over a generated workload manifest.

Records, per workload: exit code, stdout bytes, stderr bytes, and the
sha256 of any produced output container. The resulting transcript.json
is the unit of byte-level differential comparison between reference and
candidate binaries.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def run_one(binary: Path, spec: dict, workdir: Path, outdir: Path) -> dict:
    wid = spec["id"]
    argv = [str(binary)]
    out_path = outdir / f"{wid}.out.rlr"
    for token in spec["argv"]:
        if token == "{in}":
            argv.append(str(workdir / f"{wid}.rlr"))
        elif token == "{out}":
            argv.append(str(out_path))
        elif token == "{missing}":
            argv.append(str(workdir / f"{wid}.does_not_exist.rlr"))
        else:
            argv.append(token)
    proc = subprocess.run(argv, capture_output=True, timeout=120)
    record = {
        "id": wid,
        "exit": proc.returncode,
        "stdout_sha256": hashlib.sha256(proc.stdout).hexdigest(),
        "stderr": proc.stderr.decode("utf-8", "replace")
        .replace(str(workdir), "{W}")
        .replace(str(outdir), "{O}"),
        "stdout_len": len(proc.stdout),
    }
    if out_path.exists():
        record["out_sha256"] = hashlib.sha256(out_path.read_bytes()).hexdigest()
        record["out_len"] = out_path.stat().st_size
    return record


def run_all(binary: Path, workdir: Path, outdir: Path) -> list[dict]:
    manifest = json.loads((workdir / "_manifest.json").read_text())
    outdir.mkdir(parents=True, exist_ok=True)
    return [run_one(binary, spec, workdir, outdir) for spec in manifest]


if __name__ == "__main__":
    binary_arg = Path(sys.argv[1])
    workdir_arg = Path(sys.argv[2])
    outdir_arg = Path(sys.argv[3])
    transcript = run_all(binary_arg, workdir_arg, outdir_arg)
    transcript_path = outdir_arg / "_transcript.json"
    transcript_path.write_text(json.dumps(transcript, indent=1, sort_keys=True))
    print(f"wrote {transcript_path} ({len(transcript)} workloads)")
