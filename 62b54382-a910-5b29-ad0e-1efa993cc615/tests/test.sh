#!/bin/bash
# Harbor verifier entry point for libpcap_bpf_codegen_fidelity.
#
# REWRITTEN after an adversarial review returned 21 blocking findings against
# the previous revision. The defects that shaped this file:
#
#   * containment.py and score.py were both invoked with flags they do not
#     define, so argparse exited 2 and EVERY submission hard-zeroed before the
#     scorer ever ran. The upstream shim, measured at C = 1.000000, would have
#     graded 0.000. That is the ANN false-zero shape through a new mechanism.
#   * The agent's binary ran as root in the same container as the golden
#     answers at mode 0644, so fopen() on /opt/verifier/cases/golden.jsonl
#     bought C = 1.000 while passing every anti-shortcut check.
#   * Throughput was read from the graded binary's own --bench self-report.
#     Measured: even the honest starter reports 46.4 percent of real elapsed
#     time. A hostile binary reports whatever it likes.
#   * The containment scan ran AFTER the build, so it scanned build output
#     rather than the submitted tree.
#   * The tamper check was guarded by `[ -f SHA256SUMS ]`, which the tamperer
#     could satisfy by deleting the file.
#
# TRUST MODEL, which is the thing to preserve if this file is edited again.
# Agent-authored bytes are executed. They are executed as an unprivileged user,
# in a directory that holds no answers, with the golden corpus readable only by
# root. The judge measures time itself. Nothing the candidate writes is trusted
# as evidence about the candidate.
#
# Reward contract: exactly one bare decimal in [0,1] at /logs/verifier/reward.txt.
# harbor_loader.py pipes that file through `tr -dc '0-9.-'`, so a label, a second
# line or scientific notation would be silently mangled.

set -uo pipefail        # deliberately NOT -e: every failure path must still
                        # write a reward file with an attributable reason.

# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------
WORKDIR="${WORKDIR:-/home/workspace/bpfc}"
ASSETS="${ASSETS:-/opt/verifier}"
VDIR="${VDIR:-/logs/verifier}"
REWARD_TXT="${VDIR}/reward.txt"
REWARD_JSON="${VDIR}/reward.json"

CASES="${ASSETS}/cases/hidden_cases.jsonl"       # 0644: the candidate reads these
GOLDEN="${ASSETS}/cases/golden.jsonl"            # 0600 root: the candidate must not
MANIFEST="${ASSETS}/cases/manifest.json"         # 0600 root
FINGERPRINTS="${ASSETS}/ref/upstream_fingerprints.json"   # 0600 root
BENCH_CASES="${ASSETS}/bench/bench_cases.jsonl"  # 0644: stratified timing subset
REPS_FILE="${ASSETS}/bench/REPS"
ORACLE="${ASSETS}/oracle/bpfc-oracle"

RUNNER_USER="${RUNNER_USER:-runner}"
BENCH_USER="${BENCH_USER:-bench}"
SANDBOX="/tmp/candidate_run"
# The timing reference runs as `bench`, and STEP 3 hands the sandbox to
# `runner`, so the reference needs its own writable directory. Without this the
# reference cannot write its output, the timed run looks like it produced
# nothing, and every submission hard-zeros on verifier_internal_error, which is
# the ANN false-zero shape through yet another mechanism.
BENCHDIR="/tmp/bench_ref"
OUT_JSONL="${SANDBOX}/out.jsonl"
BUILD_LOG="${SANDBOX}/build.log"

CONTAINMENT_THRESHOLD=0.15
CONTAINMENT_N=5
WARMUPS=3
TIMED_TRIALS=5
PIN_CPUS="0-3"

mkdir -p "$VDIR" "$SANDBOX" "$BENCHDIR" 2>/dev/null || true

# --------------------------------------------------------------------------
# Reward emission. Fires on every exit path, including a crash or a kill.
# --------------------------------------------------------------------------
REWARD_WRITTEN=0

emit() {                      # emit <score> <reason> <detail>
    local score="$1" reason="${2:-}" detail="${3:-}"
    printf '%s' "$score" > "$REWARD_TXT"
    python3 - "$REWARD_JSON" "$score" "$reason" "$detail" <<'PY' 2>/dev/null || \
        printf '{"score":%s,"reason":"%s"}\n' "$score" "$reason" > "$REWARD_JSON"
import json, sys
path, score, reason, detail = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4]
json.dump({"score": score, "reward": score, "reason": reason or None,
           "reason_detail": detail, "emitted_by": "tests/test.sh"},
          open(path, "w"), indent=1)
PY
    REWARD_WRITTEN=1
    [ -n "$reason" ] && echo "REWARD_ATTRIBUTION_REASON ${reason}" >&2
    echo "TOTAL_SCORE ${score}"
}

hard_zero() {                 # hard_zero <reason> <detail>
    echo "verifier: hard zero, reason=$1 detail=${2:-}" >&2
    emit 0 "$1" "${2:-}"
    exit 0                    # 0: the verifier ran correctly and graded a zero
}

on_exit() {
    local rc=$?
    if [ "$REWARD_WRITTEN" -eq 0 ]; then
        # Reaching here means the script died without grading. That is a
        # verifier fault, and it must never be indistinguishable from a bad
        # submission, which is exactly what the ANN incident could not tell apart.
        emit 0 verifier_internal_error "script exited rc=${rc} before grading"
    fi
}
trap on_exit EXIT

# --------------------------------------------------------------------------
# Determinism pins. Identical for the candidate and for the reference.
# --------------------------------------------------------------------------
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export RAYON_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 TBB_NUM_THREADS=1
export LC_ALL=C LANG=C TZ=UTC SOURCE_DATE_EPOCH=0

# Every agent-authored execution goes through this one helper.
#
# Composition order matters and is easy to get wrong: `timeout` and `setpriv`
# and `taskset` are all EXECUTABLES, and each execs the next. A shell function
# cannot appear in that chain, because timeout(1) resolves its argument as a
# program. An earlier revision wrote `timeout 300 as_runner make`, where
# as_runner was a shell function, and every build died with
# "timeout: failed to run command 'as_runner': No such file or directory",
# which surfaced as build_failed for a submission that builds perfectly well.
#
#   setpriv  drop privilege   ->
#   timeout  bound the run    ->
#   taskset  pin the cpus     ->
#   the command
run_sandboxed() {             # run_sandboxed <timeout_sec> <cmd> [args...]
    local t="$1"; shift
    if command -v taskset >/dev/null 2>&1; then
        setpriv --reuid="$RUNNER_UID" --regid="$RUNNER_GID" --clear-groups -- \
            timeout "$t" taskset -c "$PIN_CPUS" "$@"
    else
        setpriv --reuid="$RUNNER_UID" --regid="$RUNNER_GID" --clear-groups -- \
            timeout "$t" "$@"
    fi
}

# Unpinned variant, for checks where cpu affinity is irrelevant.
as_runner() {
    setpriv --reuid="$RUNNER_UID" --regid="$RUNNER_GID" --clear-groups -- "$@"
}

# The timing reference runs as a DIFFERENT unprivileged identity, which the
# candidate cannot become and whose files the candidate cannot read. Both sides
# are unprivileged and both are pinned to the same cores, so the comparison
# stays symmetric while the oracle stays out of the candidate's reach.
run_bench_ref() {             # run_bench_ref <timeout_sec> <cmd> [args...]
    local t="$1"; shift
    if command -v taskset >/dev/null 2>&1; then
        setpriv --reuid="$BENCH_UID" --regid="$BENCH_GID" --clear-groups -- \
            timeout "$t" taskset -c "$PIN_CPUS" "$@"
    else
        setpriv --reuid="$BENCH_UID" --regid="$BENCH_GID" --clear-groups -- \
            timeout "$t" "$@"
    fi
}

# --------------------------------------------------------------------------
# STEP 0. Assets must resolve. An unresolvable asset is a verifier fault, never
# a clean result and never an agent-attributable zero.
# --------------------------------------------------------------------------
for f in "$CASES" "$GOLDEN" "$MANIFEST" "$FINGERPRINTS" "$BENCH_CASES" "$REPS_FILE"; do
    [ -s "$f" ] || hard_zero verifier_internal_error "missing or empty judge asset: $f"
done
[ -x "$ORACLE" ] || hard_zero verifier_internal_error "oracle binary missing at $ORACLE"

RUNNER_UID="$(id -u "$RUNNER_USER" 2>/dev/null)" || hard_zero verifier_internal_error "user $RUNNER_USER absent"
RUNNER_GID="$(id -g "$RUNNER_USER" 2>/dev/null)"
BENCH_UID="$(id -u "$BENCH_USER" 2>/dev/null)"   || hard_zero verifier_internal_error "user $BENCH_USER absent"
BENCH_GID="$(id -g "$BENCH_USER" 2>/dev/null)"

# The oracle must be unreachable to the identity that runs agent code. Assert it
# rather than assume it: this is the control that closes the adversarial-review
# finding, where posix_spawn on a world-executable oracle returned C = 1.000000.
if as_runner /usr/bin/test -x "$ORACLE" 2>/dev/null; then
    hard_zero verifier_internal_error "oracle is executable by $RUNNER_USER; refusing to grade"
fi
REPS="$(tr -dc '0-9' < "$REPS_FILE")"
[ -n "$REPS" ] || hard_zero verifier_internal_error "unreadable REPS"

# The golden corpus must be unreadable by the runner. Assert it rather than
# assume it: this is the control that stops the candidate reading the answers.
if as_runner /usr/bin/test -r "$GOLDEN" 2>/dev/null; then
    hard_zero verifier_internal_error "golden corpus is readable by $RUNNER_USER; refusing to grade"
fi

# --------------------------------------------------------------------------
# STEP 1. Submission presence. A missing submission is never scored the same
# as a bad one.
# --------------------------------------------------------------------------
[ -d "$WORKDIR" ] || hard_zero verifier_internal_error "workdir $WORKDIR does not exist"
cd "$WORKDIR" || hard_zero verifier_internal_error "cannot cd to $WORKDIR"

if [ ! -d "${WORKDIR}/src" ] || [ -z "$(find "${WORKDIR}/src" -type f -name '*.c' -print -quit 2>/dev/null)" ]; then
    hard_zero empty_submission "no C sources under ${WORKDIR}/src"
fi
[ -f "${WORKDIR}/Makefile" ] || hard_zero empty_submission "no Makefile at ${WORKDIR}/Makefile"

# --------------------------------------------------------------------------
# STEP 2. Containment, on the SUBMITTED TREE, before anything is built.
# Scanning after the build measures build output, not what was submitted.
# --------------------------------------------------------------------------
CONTAINMENT_JSON="${SANDBOX}/containment.json"
python3 "${ASSETS}/containment.py" \
        --candidate "$WORKDIR" \
        --fingerprints "$FINGERPRINTS" \
        --n "$CONTAINMENT_N" \
        --threshold "$CONTAINMENT_THRESHOLD" > "$CONTAINMENT_JSON" 2>"${SANDBOX}/containment.err"
case $? in
    0) : ;;
    3) hard_zero upstream_source_copy "$(python3 -c "import json;print('containment=%s' % json.load(open('$CONTAINMENT_JSON'))['containment'])" 2>/dev/null)" ;;
    *) hard_zero verifier_internal_error "containment scan failed: $(head -c 300 "${SANDBOX}/containment.err")" ;;
esac

# --------------------------------------------------------------------------
# STEP 3. Rebuild from source. Every pre-existing build product is destroyed
# first, by content and not by name, so a prebuilt object cannot survive.
# --------------------------------------------------------------------------
find "$WORKDIR" -type f \( -name '*.o' -o -name '*.a' -o -name '*.so' -o -name '*.so.*' \
     -o -name '*.lo' -o -name '*.la' -o -name '*.obj' \) -delete 2>/dev/null
find "$WORKDIR" -maxdepth 2 -type f -perm -u+x ! -name '*.sh' ! -name 'Makefile' -delete 2>/dev/null
rm -f "${WORKDIR}/bpfc" 2>/dev/null

chown -R "$RUNNER_UID:$RUNNER_GID" "$WORKDIR" 2>/dev/null
chown -R "$RUNNER_UID:$RUNNER_GID" "$SANDBOX" 2>/dev/null
chown -R "$BENCH_UID:$BENCH_GID"   "$BENCHDIR" 2>/dev/null

run_sandboxed 300 make -C "$WORKDIR" clean  >"$BUILD_LOG" 2>&1
run_sandboxed 300 make -C "$WORKDIR" -j4   >>"$BUILD_LOG" 2>&1
BUILD_RC=$?
[ "$BUILD_RC" -eq 0 ] || hard_zero build_failed "make exited ${BUILD_RC}: $(tail -c 400 "$BUILD_LOG")"

CANDIDATE="${WORKDIR}/bpfc"
[ -x "$CANDIDATE" ] || hard_zero build_failed "make succeeded but ${CANDIDATE} is missing or not executable"

# --------------------------------------------------------------------------
# STEP 4. Import denylist. Handles the static case, where ldd reports nothing
# and a name-based check would pass vacuously.
# --------------------------------------------------------------------------
NM_REPORT="${SANDBOX}/nm_ldd.json"
python3 - "$CANDIDATE" "$NM_REPORT" <<'PY'
import json, re, subprocess, sys
binary, out = sys.argv[1], sys.argv[2]
ALLOWED_LIBS = re.compile(r"^(libc|libm|ld-linux[^/]*|linux-vdso)\b")
# Extended after an adversarial review passed the previous set with posix_spawn.
# This list is defence in depth and NOTHING MORE. It cannot be complete:
# syscall(SYS_execve), execveat, fexecve and raw inline assembly all reach
# execve without naming any symbol here. The control that actually closes the
# hole is filesystem reachability, asserted at image build time, which is why
# the oracle now runs as `bench` and is mode 0750 root:bench.
FORBIDDEN_SYMS = {
    "pcap_open_dead", "pcap_compile", "pcap_geterr", "pcap_close", "pcap_freecode",
    "dlopen", "dlsym", "dlmopen",
    "execve", "execl", "execlp", "execv", "execvp", "execvpe", "execveat", "fexecve",
    "posix_spawn", "posix_spawnp",
    "fork", "vfork", "clone", "clone3", "forkpty", "syscall", "ptrace",
    "system", "popen", "socket", "connect",
}
def run(*a):
    try:
        return subprocess.run(a, capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return ""
ldd = run("ldd", binary)
static = ("not a dynamic executable" in ldd) or ("statically linked" in ldd)
bad_libs = []
for line in ldd.splitlines():
    m = re.search(r"([\w.+-]+\.so[\w.]*)", line)
    if m and not ALLOWED_LIBS.match(m.group(1)):
        bad_libs.append(m.group(1))
# A static binary imports nothing, so the dynamic check is vacuous for it.
# Look at the symbol tables instead, which survive static linking.
syms = set()
for flag in ("-D", "--defined-only", "-u"):
    for line in run("nm", flag, binary).splitlines():
        parts = line.split()
        if parts:
            syms.add(parts[-1].split("@")[0])
bad_syms = sorted(syms & FORBIDDEN_SYMS)
doc = {"static": static, "forbidden_libs": sorted(set(bad_libs)),
       "forbidden_symbols": bad_syms,
       "fired": bool(bad_libs or bad_syms)}
json.dump(doc, open(out, "w"), indent=1)
sys.exit(3 if doc["fired"] else 0)
PY
[ $? -eq 3 ] && hard_zero link_denylist "$(python3 -c "import json;d=json.load(open('$NM_REPORT'));print('libs=%s syms=%s'%(d['forbidden_libs'],d['forbidden_symbols']))" 2>/dev/null)"

# --------------------------------------------------------------------------
# STEP 5. Graded run. Unprivileged, in a sandbox holding no answers.
# --------------------------------------------------------------------------
cp "$CASES" "${SANDBOX}/cases.jsonl"
chown "$RUNNER_UID:$RUNNER_GID" "${SANDBOX}/cases.jsonl"

run_sandboxed 600 "$CANDIDATE" --cases "${SANDBOX}/cases.jsonl" --out "$OUT_JSONL" \
    >"${SANDBOX}/run.log" 2>&1
RUN_RC=$?
if [ "$RUN_RC" -eq 124 ]; then
    hard_zero timeout "candidate exceeded 600 s on the graded run"
elif [ "$RUN_RC" -ne 0 ]; then
    hard_zero malformed_output "candidate exited ${RUN_RC}: $(tail -c 300 "${SANDBOX}/run.log")"
fi
[ -s "$OUT_JSONL" ] || hard_zero malformed_output "candidate produced no output records"

# --------------------------------------------------------------------------
# STEP 6. Timing, measured BY THE JUDGE. The candidate's own --bench figure is
# not consulted: it is a claim by the thing being measured.
# --------------------------------------------------------------------------
# An adversarial review collected the ENTIRE throughput term by exiting immediately on
# --bench: the judge timed the process correctly but never checked that the
# timed process did any work, so an instant exit drove r to 49 and P to its
# ceiling. Timing an unverifiable computation measures nothing.
#
# The timed workload is therefore --cases, whose output the judge can inspect,
# rather than --bench, whose output it deliberately refuses to trust. Both sides
# run the identical workload and both outputs are verified below, so skipping
# the work is no longer invisible: it produces a short or absent file.
bench_wall() {                # bench_wall <binary> <runner_fn> <out> -> seconds
    local bin="$1" runfn="$2" out="$3" t0 t1
    rm -f "$out"
    t0=$(date +%s.%N)
    "$runfn" 600 "$bin" --cases "$BENCH_CASES" --out "$out" >/dev/null 2>&1
    t1=$(date +%s.%N)
    python3 -c "print(f'{$t1 - $t0:.9f}')"
}

# A timed run is only admissible if it actually produced the answers. Anything
# short of one record per bench case means the work did not happen.
BENCH_N="$(grep -c . "$BENCH_CASES")"
bench_output_valid() {        # bench_output_valid <out> -> 0 if it did the work
    local out="$1" n
    [ -s "$out" ] || return 1
    n="$(grep -c . "$out" 2>/dev/null || echo 0)"
    [ "$n" -eq "$BENCH_N" ]
}

CAND_BENCH_OUT="${SANDBOX}/bench_cand_out.jsonl"
UP_BENCH_OUT="${BENCHDIR}/bench_up_out.jsonl"
CAND_TRIALS=""; UP_TRIALS=""
for i in $(seq 1 "$WARMUPS"); do
    bench_wall "$CANDIDATE" run_sandboxed  "$CAND_BENCH_OUT" >/dev/null
    bench_wall "$ORACLE"    run_bench_ref  "$UP_BENCH_OUT"   >/dev/null
done
for i in $(seq 1 "$TIMED_TRIALS"); do
    # Interleaved trial by trial so thermal drift lands on both equally.
    CAND_TRIALS="${CAND_TRIALS} $(bench_wall "$CANDIDATE" run_sandboxed "$CAND_BENCH_OUT")"
    UP_TRIALS="${UP_TRIALS} $(bench_wall "$ORACLE" run_bench_ref "$UP_BENCH_OUT")"
done

# Both timed runs must have produced their answers. A candidate that skipped the
# work scores no throughput rather than the maximum, and the reason is recorded
# rather than silently folded into a zero.
# Withhold the candidate's timing rather than passing a flag score.py does not
# define. An absent --bench-candidate already yields P = 0 without failing, which
# verifier/test_score.py::test_absent_bench_yields_P_zero_not_failure pins. A
# flag the scorer does not know makes argparse exit 2, which is precisely how an
# earlier revision hard-zeroed every submission including the reference.
BENCH_CANDIDATE_ARG="--bench-candidate ${SANDBOX}/bench_candidate.json"
if ! bench_output_valid "$CAND_BENCH_OUT"; then
    BENCH_CANDIDATE_ARG=""
    echo "verifier: candidate produced no usable output on the timed workload;" \
         "throughput unearned" >&2
fi
if ! bench_output_valid "$UP_BENCH_OUT"; then
    hard_zero verifier_internal_error "the timing reference produced no output"
fi

python3 - "${SANDBOX}/bench_candidate.json" "$CAND_TRIALS" <<'PY'
import json, statistics, sys
vals = [float(x) for x in sys.argv[2].split()]
json.dump({"elapsed_sec": statistics.median(vals), "trials": vals,
           "aggregate": "median", "measured_by": "judge_wall_clock"},
          open(sys.argv[1], "w"), indent=1)
PY
python3 - "${SANDBOX}/bench_upstream.json" "$UP_TRIALS" <<'PY'
import json, statistics, sys
vals = [float(x) for x in sys.argv[2].split()]
json.dump({"elapsed_sec": statistics.median(vals), "trials": vals,
           "aggregate": "median", "measured_by": "judge_wall_clock"},
          open(sys.argv[1], "w"), indent=1)
PY

# --------------------------------------------------------------------------
# STEP 7. Score, as root, against assets the candidate never had access to.
# The argument vector below matches verifier/score.py exactly.
# --------------------------------------------------------------------------
python3 "${ASSETS}/score.py" \
        --golden          "$GOLDEN" \
        --candidate       "$OUT_JSONL" \
        --manifest        "$MANIFEST" \
        --out             "$REWARD_JSON" \
        --reward-txt      "$REWARD_TXT" \
        ${BENCH_CANDIDATE_ARG} \
        --bench-upstream  "${SANDBOX}/bench_upstream.json" \
        >"${SANDBOX}/score.log" 2>&1
SCORE_RC=$?
if [ "$SCORE_RC" -ne 0 ]; then
    hard_zero verifier_internal_error "score.py exited ${SCORE_RC}: $(tail -c 400 "${SANDBOX}/score.log")"
fi
[ -s "$REWARD_TXT" ] || hard_zero verifier_internal_error "score.py wrote no reward.txt"

REWARD_WRITTEN=1
SCORE="$(tr -dc '0-9.-' < "$REWARD_TXT")"
echo "TOTAL_SCORE ${SCORE}"
echo "verifier: complete, score=${SCORE}" >&2
exit 0
