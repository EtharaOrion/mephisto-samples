#!/usr/bin/env python3
CANARY_MARKER = "CANARY-ae02b28455447e910e375a971a260c30"
"""p8theta_rasterlab_bitexact_rewrite hidden verifier.

Contract (seed/contract.yaml, delivery block):
  L1 max 10  build + public-probe byte conformance
  L2 max 45  bit-exact hidden pixel workloads (zero tolerance)
  L3 max 15  hidden CLI behavioral equivalence (transcripts)
  L4 max 25  performance ratio vs reference C scalar, gated on perfect L2+L3
  L5 max  5  integrity (no canary hits, no wrap/link/invoke traces)
  kill bands: hidden mismatch -> L2=L3=L4=0 (structural cap 15);
              canary hit / wrap detection -> total 0.

Environment-validity gate: scoring requires native x86_64. Emulated or
non-x86 hosts abort with machine-readable INVALID_ENVIRONMENT instead of
emitting a confounded performance score (EdgeBench platform lesson).

Emits: 'TOTAL_SCORE <float>' on stdout, 'STRUCTURED_RESULT_JSON <json>'
on stderr. Never mounts private artifacts into the agent workspace.
"""
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VERIFIER_DIR = Path(__file__).resolve().parent
WORKSPACE = Path(os.environ.get("RASTERLAB_WORKSPACE", "/home/workspace"))
CANDIDATE = WORKSPACE / "candidate"
REFERENCE_SRC = Path(os.environ.get("RASTERLAB_REFERENCE_SRC", "/opt/reference-src"))

sys.path.insert(0, str(VERIFIER_DIR))
import run_workloads  # noqa: E402
import workload_generator  # noqa: E402

PIXEL_FAMILIES = {"convert", "resize_up", "resize_down", "chain", "perf"}
CLI_FAMILIES = {"metadata", "errors"}
COMPARE_FIELDS = ("exit", "stdout_sha256", "stdout_len", "stderr", "out_sha256", "out_len")
FORBIDDEN_PATTERNS = (b"asm!", b"global_asm!", b"/reference", b"rasterlab-src")
PERF_REPEATS = 3
BUILD_TIMEOUT = 600

RESULT = {
    "task_id": "p8theta_rasterlab_bitexact_rewrite",
    "lanes": {"L1": 0.0, "L2": 0.0, "L3": 0.0, "L4": 0.0, "L5": 0.0},
    "kill_bands": [],
    "zero_score_reasons": [],
    "detail": {},
}


def emit(total):
    RESULT["total"] = round(max(0.0, min(100.0, total)), 4)
    print(f"TOTAL_SCORE {RESULT['total']}")
    print("STRUCTURED_RESULT_JSON " + json.dumps(RESULT, sort_keys=True), file=sys.stderr)
    return 0


def fail(reason, detail=""):
    RESULT["zero_score_reasons"].append({"reason": reason, "detail": detail})
    return emit(0.0)


def check_environment():
    machine = platform.machine()
    if machine != "x86_64":
        return f"machine={machine}, need x86_64"
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        text = cpuinfo.read_text(errors="replace")
        if "CPU implementer" in text:
            return "ARM cpuinfo markers present (emulation suspected)"
        if "vendor_id" not in text and "model name" not in text:
            return "cpuinfo lacks x86 identity fields (emulation suspected)"
    return None


def load_canary_tokens():
    path = VERIFIER_DIR / "canary_tokens.json"
    if path.exists():
        return [t.encode() for t in json.loads(path.read_text())]
    return []


def integrity_scan():
    violations = []
    if not CANDIDATE.is_dir():
        return ["candidate/ directory missing"]
    tokens = load_canary_tokens()
    total_bytes = 0
    for p in sorted(CANDIDATE.rglob("*")):
        rel = p.relative_to(CANDIDATE)
        if p.is_symlink():
            violations.append(f"symlink not allowed: {rel}")
            continue
        if not p.is_file():
            continue
        if "target" in rel.parts:
            continue
        data = p.read_bytes()
        total_bytes += len(data)
        for pat in FORBIDDEN_PATTERNS:
            if pat in data:
                violations.append(f"forbidden pattern {pat.decode()} in {rel}")
        for tok in tokens:
            if tok in data:
                violations.append(f"CANARY:{rel}")
    if total_bytes > 32 * 1024 * 1024:
        violations.append(f"submission too large: {total_bytes} bytes")
    cargo_toml = CANDIDATE / "Cargo.toml"
    if not cargo_toml.exists():
        violations.append("candidate/Cargo.toml missing")
    else:
        in_deps = False
        for line in cargo_toml.read_text(errors="replace").splitlines():
            s = line.strip()
            if s.startswith("["):
                in_deps = s in ("[dependencies]", "[build-dependencies]")
                continue
            if in_deps and s and not s.startswith("#"):
                violations.append(f"third-party dependency declared: {s}")
    if (CANDIDATE / "build.rs").exists():
        violations.append("build.rs not allowed")
    if (CANDIDATE / ".cargo").exists():
        violations.append(".cargo config not allowed")
    return violations


def build_candidate():
    env = dict(os.environ, CARGO_NET_OFFLINE="true")
    proc = subprocess.run(
        ["cargo", "build", "--release", "--offline"],
        cwd=CANDIDATE, capture_output=True, timeout=BUILD_TIMEOUT, env=env,
    )
    if proc.returncode != 0:
        return None, proc.stderr.decode("utf-8", "replace")[-4000:]
    binary = CANDIDATE / "target" / "release" / "rasterlab"
    if not binary.exists():
        return None, "target/release/rasterlab not produced"
    return binary, None


def build_reference(dest):
    proc = subprocess.run(["make", "-C", str(REFERENCE_SRC)], capture_output=True, timeout=BUILD_TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError("reference build failed: " + proc.stderr.decode("utf-8", "replace")[-2000:])
    built = REFERENCE_SRC / "rasterlab"
    shutil.copy2(built, dest)
    dest.chmod(0o755)
    return dest


def transcripts(binary, workdir, outdir):
    recs = run_workloads.run_all(str(binary), Path(workdir), Path(outdir))
    return {r["id"]: r for r in recs}


def compare(expected, got):
    mismatches = []
    for wid, want in expected.items():
        have = got.get(wid, {})
        for field in COMPARE_FIELDS:
            if want.get(field) != have.get(field):
                mismatches.append({"id": wid, "field": field})
    return mismatches


def materialize_perf_variants(spec, workdir):
    """Write one fresh input variant per timing rep (same format, dims and
    pattern as the base perf workload, rep-specific seed). Distinct bytes per
    rep make cross-rep output caching useless, closing the timing-cache hack
    recorded in seed/adversarial.yaml (H1)."""
    inp = spec["input"]
    for rep in range(PERF_REPEATS):
        key = f"{spec['seed']}|perfrep|{rep}"
        blob = workload_generator.build_rlr(
            inp["fmt"], inp["w"], inp["h"], inp["pattern"], key)
        (Path(workdir) / f"{spec['id']}__rep{rep}.rlr").write_bytes(blob)


def time_binary(binary, spec, workdir, scratch):
    """Time PERF_REPEATS runs, one distinct variant input each, and return
    (median_seconds, per-rep transcript records). Records are compared
    reference-vs-candidate so a candidate cannot emit fast garbage while
    being timed (H1 fix, second prong)."""
    times = []
    recs = []
    for rep in range(PERF_REPEATS):
        rspec = {**spec, "id": f"{spec['id']}__rep{rep}"}
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            t0 = time.perf_counter()
            rec = run_workloads.run_one(str(binary), rspec, Path(workdir), Path(tmp))
            times.append(time.perf_counter() - t0)
            recs.append(rec)
    return statistics.median(times), recs


def main():
    env_problem = check_environment()
    if env_problem and os.environ.get("RASTERLAB_ALLOW_EMULATION") != "1":
        return fail("INVALID_ENVIRONMENT", env_problem)

    violations = integrity_scan()
    canary_hits = [v for v in violations if v.startswith("CANARY:")]
    if canary_hits:
        RESULT["kill_bands"].append("kill_band_canary")
        return fail("CANARY_TOKEN_IN_SUBMISSION", ";".join(canary_hits))
    wrap_hits = [v for v in violations if "forbidden pattern" in v]
    if wrap_hits:
        RESULT["kill_bands"].append("kill_band_wrap")
        return fail("WRAP_OR_ASM_DETECTED", ";".join(wrap_hits))
    if violations:
        return fail("INTEGRITY_VIOLATION", ";".join(violations))
    RESULT["lanes"]["L5"] = 5.0

    binary, err = build_candidate()
    if binary is None:
        return fail("BUILD_FAILED", err)
    RESULT["lanes"]["L1"] = 4.0

    scratch = Path(tempfile.mkdtemp(prefix="rlv_"))
    pub_dir = scratch / "public"
    hid_dir = scratch / "hidden"
    workload_generator.materialize("public", pub_dir)
    workload_generator.materialize("hidden", hid_dir)
    pub_manifest = json.loads((pub_dir / "_manifest.json").read_text())
    hid_manifest = json.loads((hid_dir / "_manifest.json").read_text())

    ref_binary = build_reference(scratch / "rasterlab_ref")
    ref_pub = transcripts(ref_binary, pub_dir, scratch / "ref_pub_out")
    ref_hid = transcripts(ref_binary, hid_dir, scratch / "ref_hid_out")

    perf_specs = [s for s in hid_manifest if s["family"] == "perf"]
    for spec in perf_specs:
        materialize_perf_variants(spec, hid_dir)
    ref_times = {}
    ref_perf_recs = {}
    for spec in perf_specs:
        ref_times[spec["id"]], ref_perf_recs[spec["id"]] = time_binary(
            ref_binary, spec, hid_dir, scratch)

    ref_binary.unlink()
    if REFERENCE_SRC.exists() and os.environ.get("RASTERLAB_KEEP_REFERENCE") != "1":
        shutil.rmtree(REFERENCE_SRC, ignore_errors=True)

    cand_pub = transcripts(binary, pub_dir, scratch / "cand_pub_out")
    pub_mismatches = compare(ref_pub, cand_pub)
    pub_total = len(pub_manifest)
    pub_bad_ids = {m["id"] for m in pub_mismatches}
    RESULT["lanes"]["L1"] = 4.0 + 6.0 * (pub_total - len(pub_bad_ids)) / pub_total
    RESULT["detail"]["public_mismatched"] = len(pub_bad_ids)

    cand_hid = transcripts(binary, hid_dir, scratch / "cand_hid_out")
    hid_mismatches = compare(ref_hid, cand_hid)
    hid_bad_ids = {m["id"] for m in hid_mismatches}
    fam_by_id = {s["id"]: s["family"] for s in hid_manifest}
    pixel_bad = [i for i in hid_bad_ids if fam_by_id[i] in PIXEL_FAMILIES]
    cli_bad = [i for i in hid_bad_ids if fam_by_id[i] in CLI_FAMILIES]
    RESULT["detail"]["hidden_mismatched"] = len(hid_bad_ids)

    if hid_bad_ids:
        RESULT["kill_bands"].append("kill_band_bit_mismatch")
        RESULT["detail"]["hidden_pixel_mismatched"] = len(pixel_bad)
        RESULT["detail"]["hidden_cli_mismatched"] = len(cli_bad)
        return emit(RESULT["lanes"]["L1"] + RESULT["lanes"]["L5"])

    RESULT["lanes"]["L2"] = 45.0
    RESULT["lanes"]["L3"] = 15.0

    ratios = []
    timed_rep_mismatches = []
    for spec in perf_specs:
        cand_t, cand_recs = time_binary(binary, spec, hid_dir, scratch)
        for want, have in zip(ref_perf_recs[spec["id"]], cand_recs):
            for field in COMPARE_FIELDS:
                if want.get(field) != have.get(field):
                    timed_rep_mismatches.append({"id": have["id"], "field": field})
        ratios.append(ref_times[spec["id"]] / cand_t if cand_t > 0 else 0.0)
    if timed_rep_mismatches:
        RESULT["kill_bands"].append("kill_band_bit_mismatch")
        RESULT["detail"]["timed_rep_mismatched"] = len(timed_rep_mismatches)
        RESULT["lanes"]["L2"] = 0.0
        RESULT["lanes"]["L3"] = 0.0
        return emit(RESULT["lanes"]["L1"] + RESULT["lanes"]["L5"])
    if ratios:
        geo = 1.0
        for r in ratios:
            geo *= max(r, 1e-9)
        geo **= 1.0 / len(ratios)
        RESULT["detail"]["perf_ratio_geomean"] = round(geo, 4)
        if geo > 0.6:
            RESULT["lanes"]["L4"] = 25.0 * min(1.0, (geo - 0.6) / 0.9)

    shutil.rmtree(scratch, ignore_errors=True)
    return emit(sum(RESULT["lanes"].values()))


if __name__ == "__main__":
    sys.exit(main())
