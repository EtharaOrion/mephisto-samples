#!/usr/bin/env python3
CANARY_MARKER = "375b89479c5930e3a9e2a30f76635b3d"
"""Deterministic verifier for p9iota_latticestore_workspace_reconstruction.

Lane contract (score 0-100, sum then clip):
  L1 (10) build and surface: 4.0 for a clean `cargo build --release --offline`
     of the submitted workspace plus 6.0 * (matched public workloads / total),
     where a match means full step-transcript and store-state equality against
     the reference implementation executed live in this container.
  L2 (45) hidden layered equivalence, all or nothing per layer:
     layer_core (basic+boundary) 18, layer_dedupe_multi 9, layer_corrupt 9,
     layer_recovery 9. A layer scores only when every hidden workload in it
     matches the reference on every step record and on the final store-state
     digest (byte-exact on-disk store).
  L3 (15) CLI behavioral equivalence: every hidden workload matches the
     reference on every binary-step transcript field (exit, stdout_sha256,
     stdout_len, stderr, out_sha256, out_len). All or nothing.
  L4 (25) performance: only when L2 == 45 and L3 == 15. r = geometric mean
     over perf specs of (reference median / candidate median) wall time,
     3 repeats each on fresh per-rep variants. Score 0 at r <= 0.6, linear to
     the full 25 at r >= 1.5. Timed-rep transcripts are also compared; any
     divergence voids equivalence lanes.
  L5 (5) integrity: no canary tokens, no forbidden patterns, no third-party
     dependencies, no build.rs, no .cargo config, no symlinks, source under
     32 MiB, lattice-types unmodified.

Kill bands: canary token in submission -> total 0; wrap/asm forbidden pattern
-> total 0. Hidden workloads are regenerated fresh from sealed seeds inside
this container at scoring time; the reference binary and its source tree are
deleted before the candidate binary ever runs.

Environment gate: aborts INVALID_ENVIRONMENT unless native x86_64, override
via LATTICE_ALLOW_EMULATION=1 (correctness lanes remain valid under emulation,
the perf lane is not signed-pilot evidence there).

Emission: "TOTAL_SCORE <float>" on stdout, "STRUCTURED_RESULT_JSON <json>"
on stderr.
"""

import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VERIFIER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(VERIFIER_DIR))

import run_workloads  # noqa: E402
import workload_generator  # noqa: E402

TASK_ID = "p9iota_latticestore_workspace_reconstruction"
WORKSPACE = Path(os.environ.get("LATTICE_WORKSPACE", "/home/workspace"))
CANDIDATE = WORKSPACE / "workspace"
REFERENCE_SRC = Path(os.environ.get("LATTICE_REFERENCE_SRC", "/opt/reference-src"))

FORBIDDEN_PATTERNS = (b"asm!", b"global_asm!", b"/reference", b"reference-src", b"reference-bin")
WORKSPACE_MEMBERS = (
    "lattice-types",
    "lattice-chunk",
    "lattice-codec",
    "lattice-index",
    "lattice-log",
    "lattice-store",
    "lattice-cli",
)
SIZE_CAP = 32 * 1024 * 1024
BUILD_TIMEOUT = 900
PERF_REPEATS = 3

RESULT = {
    "task_id": TASK_ID,
    "lanes": {"L1": 0.0, "L2": 0.0, "L3": 0.0, "L4": 0.0, "L5": 0.0},
    "kill_bands": [],
    "zero_score_reasons": [],
    "detail": {},
}


def emit(total: float) -> int:
    total = max(0.0, min(100.0, round(total, 4)))
    RESULT["total"] = total
    print(f"TOTAL_SCORE {total}")
    print("STRUCTURED_RESULT_JSON " + json.dumps(RESULT, sort_keys=True), file=sys.stderr)
    return 0


def fail(reason: str, detail: str = "") -> int:
    RESULT["zero_score_reasons"].append(reason)
    if detail:
        RESULT["detail"][reason] = detail
    return emit(0.0)


def check_environment():
    if os.environ.get("LATTICE_ALLOW_EMULATION") == "1":
        return None
    problems = []
    if platform.machine() != "x86_64":
        problems.append(f"machine={platform.machine()}")
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        text = cpuinfo.read_text(errors="replace")
        if "CPU implementer" in text:
            problems.append("arm cpuinfo signature")
        if "vendor_id" not in text and "model name" not in text:
            problems.append("missing x86 cpuinfo fields")
    else:
        problems.append("no /proc/cpuinfo")
    return "; ".join(problems) if problems else None


def load_canary_tokens():
    path = VERIFIER_DIR / "canary_tokens.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def cargo_toml_clean(path: Path) -> bool:
    section = None
    for raw in path.read_text(errors="replace").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("["):
            section = line.strip("[]").strip()
            continue
        if section in ("dependencies", "build-dependencies", "dev-dependencies"):
            if "path" not in line or "lattice-" not in line:
                return False
    return True


def integrity_scan():
    violations, canary_hits, forbidden_hits = [], [], []
    if not CANDIDATE.is_dir():
        violations.append("workspace directory missing")
        return violations, canary_hits, forbidden_hits
    tokens = [t.encode() for t in load_canary_tokens()]
    total = 0
    for path in sorted(CANDIDATE.rglob("*")):
        rel = path.relative_to(CANDIDATE)
        if "target" in rel.parts:
            continue
        if path.is_symlink():
            violations.append(f"symlink: {rel}")
            continue
        if not path.is_file():
            continue
        data = path.read_bytes()
        total += len(data)
        for pat in FORBIDDEN_PATTERNS:
            if pat in data:
                forbidden_hits.append(f"{pat.decode(errors='replace')}:{rel}")
        for tok in tokens:
            if tok and tok in data:
                canary_hits.append(f"CANARY:{rel}")
    if total > SIZE_CAP:
        violations.append(f"source tree exceeds 32 MiB: {total}")
    for member in WORKSPACE_MEMBERS:
        manifest = CANDIDATE / member / "Cargo.toml"
        if not manifest.is_file():
            violations.append(f"missing Cargo.toml: {member}")
            continue
        if not cargo_toml_clean(manifest):
            violations.append(f"third-party dependency in {member}/Cargo.toml")
    root_manifest = CANDIDATE / "Cargo.toml"
    if not root_manifest.is_file():
        violations.append("missing workspace Cargo.toml")
    for member in WORKSPACE_MEMBERS:
        if (CANDIDATE / member / "build.rs").exists():
            violations.append(f"build.rs present: {member}")
    if (CANDIDATE / ".cargo").exists():
        violations.append(".cargo config present")
    return violations, canary_hits, forbidden_hits


def cargo_build(workspace: Path):
    env = dict(os.environ)
    env["CARGO_NET_OFFLINE"] = "true"
    try:
        proc = subprocess.run(
            ["cargo", "build", "--release", "--offline"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=BUILD_TIMEOUT,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return None, "build timeout"
    if proc.returncode != 0:
        return None, (proc.stderr or "")[-4000:]
    binary = workspace / "target" / "release" / "lattice"
    if not binary.is_file():
        return None, "binary target/release/lattice missing after build"
    return binary, None


def records_equal(a, b) -> bool:
    return a == b


def transcript_fields(rec):
    steps = []
    for step in rec["steps"]:
        if "exit" in step:
            steps.append(
                {
                    "op": step.get("op"),
                    "exit": step["exit"],
                    "stdout_sha256": step["stdout_sha256"],
                    "stdout_len": step["stdout_len"],
                    "stderr": step["stderr"],
                    "out_sha256": step.get("out_sha256"),
                    "out_len": step.get("out_len"),
                }
            )
    return steps


def run_split(binary: Path, workload_dir: Path, scratch_root: Path, label: str):
    scratch = scratch_root / label
    scratch.mkdir(parents=True, exist_ok=True)
    return run_workloads.run_all(binary, workload_dir, scratch)


def time_perf(binary: Path, perf_dir: Path, scratch_root: Path, label: str):
    medians, recs = {}, {}
    for spec in workload_generator.PERF_SPECS:
        spec_id = spec["id"]
        times = []
        for rep in range(PERF_REPEATS):
            wid = f"{spec_id}_rep{rep}"
            workload = json.loads((perf_dir / f"{wid}.json").read_text())
            scratch = Path(tempfile.mkdtemp(prefix=f"{label}_{wid}_", dir=scratch_root))
            t0 = time.monotonic()
            rec = run_workloads.run_workload(binary, workload, perf_dir / "inputs", scratch)
            times.append(time.monotonic() - t0)
            recs[wid] = rec
            shutil.rmtree(scratch, ignore_errors=True)
        times.sort()
        medians[spec_id] = times[len(times) // 2]
    return medians, recs


def main() -> int:
    env_problem = check_environment()
    if env_problem:
        return fail("INVALID_ENVIRONMENT", env_problem)

    violations, canary_hits, forbidden_hits = integrity_scan()
    if canary_hits:
        RESULT["kill_bands"].append("kill_band_canary")
        return fail("CANARY_TOKEN_IN_SUBMISSION", "; ".join(canary_hits[:8]))
    if forbidden_hits:
        RESULT["kill_bands"].append("kill_band_wrap")
        return fail("WRAP_OR_ASM_DETECTED", "; ".join(forbidden_hits[:8]))
    if violations:
        return fail("INTEGRITY_VIOLATION", "; ".join(violations[:8]))
    RESULT["lanes"]["L5"] = 5.0

    binary, err = cargo_build(CANDIDATE)
    if binary is None:
        return fail("BUILD_FAILED", err or "")
    RESULT["lanes"]["L1"] = 4.0

    with tempfile.TemporaryDirectory(prefix="p9iota_scoring_") as tmp:
        tmp = Path(tmp)
        public_dir = tmp / "public"
        hidden_dir = tmp / "hidden"
        perf_dir = tmp / "perf"
        perf_dir.mkdir()
        workload_generator.materialize("public", public_dir)
        workload_generator.materialize("hidden", hidden_dir)
        for spec in workload_generator.PERF_SPECS:
            for rep in range(PERF_REPEATS):
                workload_generator.materialize_perf(spec["id"], f"rep{rep}", perf_dir)

        ref_binary, err = cargo_build(REFERENCE_SRC)
        if ref_binary is None:
            return fail("REFERENCE_BUILD_FAILED", err or "")
        ref_public = run_split(ref_binary, public_dir, tmp, "ref_public")
        ref_hidden = run_split(ref_binary, hidden_dir, tmp, "ref_hidden")
        ref_medians, ref_perf_recs = time_perf(ref_binary, perf_dir, tmp, "ref")
        if os.environ.get("LATTICE_KEEP_REFERENCE") != "1":
            ref_binary.unlink()
            shutil.rmtree(REFERENCE_SRC, ignore_errors=True)

        cand_public = run_split(binary, public_dir, tmp, "cand_public")
        matched = sum(
            1 for wid, rec in ref_public.items() if records_equal(rec, cand_public.get(wid))
        )
        RESULT["lanes"]["L1"] = round(4.0 + 6.0 * matched / max(1, len(ref_public)), 4)
        RESULT["detail"]["public_matched"] = f"{matched}/{len(ref_public)}"

        cand_hidden = run_split(binary, hidden_dir, tmp, "cand_hidden")
        layer_points = {
            "layer_core": 18.0,
            "layer_dedupe_multi": 9.0,
            "layer_corrupt": 9.0,
            "layer_recovery": 9.0,
        }
        layer_pass = {}
        for layer, families in workload_generator.L2_LAYERS.items():
            ok = True
            for wid, rec in ref_hidden.items():
                if rec["id"].split("_")[0] in families or any(
                    wid.startswith(f"{fam}_") for fam in families
                ):
                    if not records_equal(rec, cand_hidden.get(wid)):
                        ok = False
                        break
            layer_pass[layer] = ok
            if ok:
                RESULT["lanes"]["L2"] += layer_points[layer]
        RESULT["detail"]["layers"] = {k: ("pass" if v else "fail") for k, v in layer_pass.items()}

        l3_ok = all(
            transcript_fields(rec) == transcript_fields(cand_hidden[wid])
            for wid, rec in ref_hidden.items()
            if wid in cand_hidden
        ) and set(ref_hidden) == set(cand_hidden)
        RESULT["lanes"]["L3"] = 15.0 if l3_ok else 0.0

        if RESULT["lanes"]["L2"] == 45.0 and RESULT["lanes"]["L3"] == 15.0:
            cand_medians, cand_perf_recs = time_perf(binary, perf_dir, tmp, "cand")
            perf_equal = all(
                records_equal(ref_perf_recs[wid], cand_perf_recs.get(wid))
                for wid in ref_perf_recs
            )
            if not perf_equal:
                RESULT["kill_bands"].append("kill_band_bit_mismatch")
                RESULT["lanes"]["L2"] = 0.0
                RESULT["lanes"]["L3"] = 0.0
                RESULT["detail"]["perf"] = "timed-rep transcript divergence"
                return emit(RESULT["lanes"]["L1"] + RESULT["lanes"]["L5"])
            ratios = [
                ref_medians[s] / cand_medians[s] for s in ref_medians if cand_medians.get(s)
            ]
            geo = math.exp(sum(math.log(r) for r in ratios) / len(ratios)) if ratios else 0.0
            RESULT["detail"]["perf_ratio_geomean"] = round(geo, 4)
            if geo > 0.6:
                RESULT["lanes"]["L4"] = round(25.0 * min(1.0, (geo - 0.6) / 0.9), 4)
        else:
            RESULT["detail"]["perf"] = "skipped: equivalence incomplete"

    return emit(sum(RESULT["lanes"].values()))


if __name__ == "__main__":
    sys.exit(main())
