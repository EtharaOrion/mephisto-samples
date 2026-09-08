#!/usr/bin/env python3
"""Local public-probe checker for the rasterlab candidate.

Usage: python3 verify_local.py [path-to-candidate-binary]

Runs every probe in public_probes/_manifest.json against the candidate
binary and compares exit code, stdout, stderr, and output-container bytes
with the recorded reference results in public_probes/expected/. Passing
here is necessary but NOT sufficient: the hidden scoring set is larger,
regenerated fresh at verification time, and any single mismatch there
zeroes the equivalence and performance lanes.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBES = HERE / "public_probes"
EXPECTED = PROBES / "expected"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_probe(binary, spec, workdir, outdir):
    wid = spec["id"]
    argv = [binary]
    for tok in spec["argv"]:
        if tok == "{in}":
            argv.append(str(workdir / f"{wid}.rlr"))
        elif tok == "{out}":
            argv.append(str(outdir / f"{wid}.out.rlr"))
        elif tok == "{missing}":
            argv.append(str(workdir / f"{wid}.does_not_exist.rlr"))
        else:
            argv.append(tok)
    proc = subprocess.run(argv, capture_output=True, timeout=120)
    stderr = proc.stderr.decode("utf-8", "replace")
    stderr = stderr.replace(str(workdir), "{W}").replace(str(outdir), "{O}")
    rec = {
        "id": wid,
        "exit": proc.returncode,
        "stdout_sha256": sha256(proc.stdout),
        "stdout_len": len(proc.stdout),
        "stderr": stderr,
    }
    outfile = outdir / f"{wid}.out.rlr"
    if outfile.exists():
        data = outfile.read_bytes()
        rec["out_sha256"] = sha256(data)
        rec["out_len"] = len(data)
    return rec


def main():
    binary = sys.argv[1] if len(sys.argv) > 1 else "candidate/target/release/rasterlab"
    binary = str(Path(binary).resolve())
    if not Path(binary).exists():
        print(f"candidate binary not found: {binary}")
        print("build it first: cd candidate && cargo build --release")
        return 2

    manifest = json.loads((PROBES / "_manifest.json").read_text())
    expected = {
        r["id"]: r
        for r in json.loads((EXPECTED / "_transcript.json").read_text())
    }

    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        outdir = Path(tmp)
        for spec in manifest["workloads"] if isinstance(manifest, dict) else manifest:
            wid = spec["id"]
            got = run_probe(binary, spec, PROBES, outdir)
            want = expected[wid]
            diffs = []
            for key in ("exit", "stdout_sha256", "stdout_len", "stderr", "out_sha256", "out_len"):
                if want.get(key) != got.get(key):
                    diffs.append(f"{key}: want={want.get(key)!r} got={got.get(key)!r}")
            if diffs:
                failures += 1
                print(f"FAIL {wid}")
                for d in diffs:
                    print(f"  {d}")
            else:
                print(f"ok   {wid}")

    total = len(expected)
    print(f"\n{total - failures}/{total} public probes match")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
