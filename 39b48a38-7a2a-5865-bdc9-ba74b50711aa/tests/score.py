"""chronopack verifier. Never agent visible.

Five lanes, one float on the closed interval from zero to one, written to the bound reward
path. Every zero carries a machine-readable reason.

The scorer never imports the submission. It generates the graded columns from the sealed seed,
hands them to an isolated child, and compares what comes back against bytes it computed here
with the reference codec. The child holds no seed, no configuration and no reference.

CANARY-BLOCK-BEGIN
canary_slot_0: MEPH-373d1916b5939704412ba6efe8590d88
canary_slot_1: MEPH-b788c135a56267dac49d57ee8273bd4e
canary_slot_2: MEPH-c271027e98332e4ff7c37a518d7881ef
canary_slot_3: MEPH-0b50c7a3306d23690a441bc7053f21c3
CANARY-BLOCK-END
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lanes  # noqa: E402
from harness import refimpl, sourcegate, workloads  # noqa: E402

GRADING = json.loads((HERE / "grading.json").read_text(encoding="utf-8"))
SEALED_SEED = GRADING["sealed_seed"].encode("ascii")
RUNNER = HERE / "harness" / "runner.py"


class Sandbox:
    def __init__(self) -> None:
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="chronopack-runner-"))
        shutil.copy(RUNNER, self.dir / "runner.py")

    def run(self, submission: pathlib.Path, columns: list[dict], predict: bool = False,
            echo_self: bool = False, decode_only: bool = False) -> dict:
        job = {
            "submission": str(pathlib.Path(submission).resolve()),
            "columns": columns,
            "predict": predict,
            "echo_self": echo_self,
            "decode_only": decode_only,
        }
        try:
            completed = subprocess.run(
                [sys.executable, "-I", str(self.dir / "runner.py")],
                input=json.dumps(job),
                capture_output=True,
                text=True,
                timeout=900,
                cwd=str(self.dir),
                env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "0"},
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "runner_timeout"}
        if completed.returncode != 0 or not completed.stdout.strip():
            return {"ok": False, "error": f"runner_exit_{completed.returncode}: {completed.stderr[-400:]}"}
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError:
            return {"ok": False, "error": "runner_emitted_unparseable_output"}

    def close(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


def graded_columns(entry: dict) -> list[dict]:
    return workloads.columns(
        SEALED_SEED + entry["name"].encode("ascii"), entry["count"], graded=entry["graded"]
    )


def wire(columns: list[dict], with_reference: bool) -> list[dict]:
    out = []
    for column in columns:
        item = {"id": column["id"], "values": column["values"]}
        if with_reference:
            item["reference_hex"] = refimpl.encode(column["values"]).hex()
        out.append(item)
    return out


def _walk(blob: bytes) -> list[int]:
    """Per-block encoding ids of a candidate frame, read with the reference's frame walker."""
    block_count = int.from_bytes(blob[:4], "little")
    cursor = 4
    out = []
    for _ in range(block_count):
        out.append(blob[cursor])
        _, cursor = refimpl.decode_block(blob, cursor)
    return out


def above_baseline(fraction: float, lane: str) -> float:
    """Credit only the part of a lane that a zero-policy submission does not already get.

    Two lanes pay generously for plausibility rather than recovery. Measured against a codec
    that conforms to the format document and neutralises all seven undocumented policy tables,
    block choice scores 0.946 and size fidelity 0.706 while recovering no rule whatsoever. Paid
    raw, those lanes hand out 18 of 120 points for reading the specification. Rescaled, the
    baseline submission earns zero and the lane measures only what recovery adds.
    """
    base = GRADING.get("baselines", {}).get(lane)
    if base is None:
        return fraction
    if base >= 1.0:
        return 0.0
    return max(0.0, (fraction - base) / (1.0 - base))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    overrides = {}
    while argv:
        flag = argv.pop(0)
        if flag in ("--submission", "--reward"):
            overrides[flag.lstrip("-")] = argv.pop(0)
        else:
            raise SystemExit(f"unknown argument {flag}")

    reward_path = pathlib.Path(overrides.get("reward", GRADING["reward_path"]))
    reward_path.parent.mkdir(parents=True, exist_ok=True)
    report_path = reward_path.parent / "report.json"
    weights = GRADING["lanes"]
    denominator = GRADING["denominator"]

    def emit(points: dict, reason: str, report: dict) -> int:
        total = round(sum(points.values()), 4)
        score = round(total / denominator, 6)
        report["points"] = {k: round(v, 3) for k, v in points.items()}
        report["lane_maxima"] = weights
        report["base_total"] = total
        report["denominator"] = denominator
        report["reward"] = score
        report["reason"] = reason
        reward_path.write_text(f"{score}\n", encoding="utf-8")
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
        print(json.dumps({"reward": score, "total": total, "of": denominator, "reason": reason}, indent=2))
        for lane in weights:
            print(f"  {lane:28s} {points.get(lane, 0.0):6.2f} / {weights[lane]}")
        return 0

    submission = pathlib.Path(overrides.get("submission", GRADING["submission_path"]))
    report: dict = {}
    zero = {lane: 0.0 for lane in weights}

    if not submission.exists():
        return emit(zero, "submission_missing", report)

    source = submission.read_text(encoding="utf-8", errors="replace")
    findings = sourcegate.check(source)
    report["source_gate"] = {"ok": not findings, "findings": findings}
    if findings:
        return emit(zero, "source_gate_rejected", report)

    points = dict(zero)
    box = Sandbox()
    try:
        smoke = box.run(submission, wire(graded_columns(GRADING["batches"][0])[:2], False), predict=True)
        if not smoke.get("ok"):
            report["runner_error"] = smoke.get("error")
            return emit(zero, "submission_api_incomplete", report)

        detail = {}
        for entry in GRADING["batches"]:
            cols = graded_columns(entry)
            response = box.run(submission, wire(cols, entry["grade_decode"]), predict=True)
            if not response.get("ok"):
                report["runner_error"] = response.get("error")
                return emit(points, "runner_failed", report)
            breaches = lanes.integrity_red_line(cols, response, refimpl)
            if breaches:
                report["red_line"] = {"id": "RL1", "breaches": breaches[:6],
                                      "count": len(breaches)}
                report["lanes"] = detail
                return emit({k: 0.0 for k in weights}, "red_line_column_corrupted", report)

            exact, total, misses = lanes.exactness(cols, response, refimpl)
            points[entry["lane"]] = weights[entry["lane"]] * (exact / total if total else 0.0)
            detail[entry["lane"]] = {"exact": exact, "total": total, "misses": misses}

            if entry["lane"] == "L4_hidden_shifted":
                match, blocks = lanes.block_choice(cols, response, refimpl, _walk)
                raw6 = match / blocks if blocks else 0.0
                points["L6_block_choice"] = weights["L6_block_choice"] * above_baseline(raw6, "L6_block_choice")
                detail["L6_block_choice"] = {"match": match, "total": blocks, "raw": round(raw6, 4), "baseline": GRADING["baselines"]["L6_block_choice"]}

                fidelity, worst = lanes.size_fidelity(cols, response, refimpl)
                points["L7_size_fidelity"] = weights["L7_size_fidelity"] * above_baseline(fidelity, "L7_size_fidelity")
                detail["L7_size_fidelity"] = {"mean": round(fidelity, 4), "baseline": GRADING["baselines"]["L7_size_fidelity"], "worst": worst}

                calib, stats = lanes.calibration(cols, response, refimpl)
                points["L9_calibration"] = weights["L9_calibration"] * calib
                detail["L9_calibration"] = stats

                # Conformance is measured in a process where encode was never called, so a
                # submission that echoes its input has nothing to echo.
                cold = box.run(submission, wire(cols, True), decode_only=True)
                cold_by_id = {x["id"]: x for x in cold.get("results", [])}
                decoded = sum(
                    1
                    for c in cols
                    if cold_by_id.get(c["id"], {}).get("decoded") == c["values"]
                )
                # Container conformance is a gate rather than a lane. Every submission ever measured
                # scored it full, including one that recovered no policy at all, so paying for it
                # paid for showing up. It now gates: below the bar nothing else counts, and at or
                # above it the reward is the right to be graded on the undocumented policy.
                share1 = decoded / len(cols) if cols else 0.0
                points["L1_container_conformance"] = 0.0
                detail["L1_container_conformance"] = {
                    "decoded": decoded, "total": len(cols), "share": round(share1, 4),
                    "gate": GRADING["gates"]["L1_container_conformance"],
                    "passed": share1 >= GRADING["gates"]["L1_container_conformance"],
                }
                if share1 < GRADING["gates"]["L1_container_conformance"]:
                    report["gate_failed"] = {"lane": "L1_container_conformance",
                                             "share": round(share1, 4),
                                             "required": GRADING["gates"]["L1_container_conformance"]}
                    report["lanes"] = detail
                    return emit({k: 0.0 for k in weights}, "gate_failed_container", report)

        # Boundary seams.
        seams = workloads.adversarial_columns(SEALED_SEED + b"seams", GRADING["adversarial_count"])
        response = box.run(submission, wire(seams, False))
        exact, total, misses = lanes.exactness(seams, response, refimpl)
        points["L5_boundary_seams"] = weights["L5_boundary_seams"] * (exact / total if total else 0.0)
        detail["L5_boundary_seams"] = {"exact": exact, "total": total, "misses": misses}

        # Bonus: magnitudes the corpus never showed.
        bonus = workloads.adversarial_columns(SEALED_SEED + b"bonus-unseen", GRADING["bonus_count"])
        for column in bonus:
            column["values"] = [v * 1_000_003 for v in column["values"]]
        response = box.run(submission, wire(bonus, False))
        exact, total, _ = lanes.exactness(bonus, response, refimpl)
        points["B1_unseen_magnitude"] = weights["B1_unseen_magnitude"] * (exact / total if total else 0.0)
        detail["B1_unseen_magnitude"] = {"exact": exact, "total": total}

        # Anti fabrication.
        probes = graded_columns(GRADING["batches"][1])[:12]
        share, af_findings = lanes.anti_fabrication(
            probes,
            lambda cols, echo_self=False: box.run(submission, cols, echo_self=echo_self),
            refimpl,
        )
        # Anti fabrication is a gate for the same reason: not fabricating is a precondition
        # for being measured, not an achievement that earns points.
        points["L8_anti_fabrication"] = 0.0
        detail["L8_anti_fabrication"] = {
            "share": round(share, 3), "findings": af_findings,
            "gate": GRADING["gates"]["L8_anti_fabrication"],
            "passed": share >= GRADING["gates"]["L8_anti_fabrication"],
        }
        if share < GRADING["gates"]["L8_anti_fabrication"]:
            report["gate_failed"] = {"lane": "L8_anti_fabrication", "share": round(share, 3),
                                     "required": GRADING["gates"]["L8_anti_fabrication"]}
            report["lanes"] = detail
            return emit({k: 0.0 for k in weights}, "gate_failed_anti_fabrication", report)
    finally:
        box.close()

    report["lanes"] = detail
    return emit(points, "scored", report)


if __name__ == "__main__":
    raise SystemExit(main())
