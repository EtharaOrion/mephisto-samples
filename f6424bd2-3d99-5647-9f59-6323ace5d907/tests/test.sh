#!/bin/bash
# Harbor verifier for ffmpeg_swscale_reimplementation (ARM64).
# Extracted verbatim from the upstream judge eval_cmd. Rebuilds the agent
# candidate, runs the correctness gate + speedup benchmark vs the static baseline
# in /verifier-data, writes /logs/verifier/reward.json. Grader is pure python
# (arch-portable); only the baseline .so is arm64-native.
mkdir -p /logs/verifier /tmp/verifier && ln -sfn /home/workspace /app && ln -sfn /opt/tests /tests && ln -sfn /tmp/verifier /logs/verifier 2>/dev/null; export APP_DIR=/home/workspace VERIFIER_DIR=/logs/verifier PYTHONPATH=/opt/tests:/tmp:${PYTHONPATH:-} PATH=/usr/local/cargo/bin:$PATH CARGO_HOME=/usr/local/cargo RUSTUP_HOME=/usr/local/rustup && bash /opt/tests/test.sh >/tmp/verifier.log 2>&1 || true; cat /tmp/verifier.log >&2; python3 - "/logs/verifier/reward.json" <<'NORM'
import json, math, sys
p = sys.argv[1]
try:
    d = json.load(open(p))
except Exception:
    sys.exit(0)
raw = float(d.get("score") or d.get("reward") or 0.0)
# Harbor 0-1 normalization (mirrors the reference task's reward.txt /100 step).
# log_anchor rescale: anchor_raw 14.155 -> anchor_score 43, then /100 -> [0,1].
# Monotonic + correctness-gated (raw 0 -> 0). ANCHOR INHERITED FROM x86; ARM recal
# pending (label-only: ranking and the 0.34 floor <-> raw 8.13x are preserved).
# Raw geometric-mean speedup retained in additional_data for auditability.
s100 = max(0.0, min(100.0, 43.0 * math.log(raw) / math.log(14.155))) if raw > 0 else 0.0
norm = round(s100 / 100.0, 6)
ad = d.get("additional_data") or {}
ad.setdefault("geometric_mean_speedup", raw)
ad["raw_speedup"] = raw
ad["score_0_100"] = round(s100, 4)
d["additional_data"] = ad
d["score"] = norm
d["reward"] = norm
json.dump(d, open(p, "w"), indent=2)
open("/logs/verifier/reward.txt", "w").write(f"{norm}\n")
NORM
bash /opt/tests/pytest_shim.sh "/logs/verifier/reward.json"; python3 - "/logs/verifier/reward.json" <<'PY' >&2
import json
import re
import sys

try:
    data = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)

score = float(data.get("score") or data.get("reward") or 0.0)
additional = data.get("additional_data") or {}
passed = additional.get("correctness_passed")
total = additional.get("correctness_total")
results = additional.get("correctness_results") or []

def as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

passed = as_int(passed)
total = as_int(total)
if passed is None or total is None:
    for sub in data.get("subscores") or []:
        text = f"{sub.get('name', '')} {sub.get('subtask', '')} {sub.get('stdout', '')}"
        if "correct" not in text.lower():
            continue
        match = re.search(r"(\d+)\s*/\s*(\d+)", text)
        if match:
            passed = int(match.group(1))
            total = int(match.group(2))
            break

if passed is None or total is None or passed >= total or score > 0:
    sys.exit(0)

yuv_formats = ("yuv420p", "yuv422p", "yuv444p", "nv12", "nv21")
rgb_formats = ("rgb24", "bgr24", "rgba", "bgra")

def first(item, *keys):
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return ""

def failed(item):
    if not isinstance(item, dict):
        return False
    for key in ("passed", "pass", "ok", "success"):
        if key in item:
            return item.get(key) is False
    status = str(item.get("status", "")).lower()
    if status in ("fail", "failed", "error"):
        return True
    psnr = item.get("psnr")
    threshold = item.get("threshold")
    return isinstance(psnr, (int, float)) and isinstance(threshold, (int, float)) and psnr < threshold

def dim(item, *keys):
    for key in keys:
        value = as_int(item.get(key))
        if value is not None:
            return value
    return None

def category(item):
    src = first(item, "src_fmt", "src_format", "src_pix_fmt", "source_format").lower().replace("_", "")
    dst = first(item, "dst_fmt", "dst_format", "dst_pix_fmt", "dest_format", "destination_format").lower().replace("_", "")
    algo = first(item, "algo", "algorithm", "scaler", "scale_algo").lower().replace("_", "")
    label = first(item, "label", "workload", "name", "case", "description").lower().replace("_", "")
    text = " ".join(part for part in (src, dst, algo, label) if part)

    src_w = dim(item, "src_w", "source_w", "src_width", "source_width")
    src_h = dim(item, "src_h", "source_h", "src_height", "source_height")
    dst_w = dim(item, "dst_w", "dest_w", "dst_width", "dest_width")
    dst_h = dim(item, "dst_h", "dest_h", "dst_height", "dest_height")
    same_size = src_w is not None and src_h is not None and dst_w is not None and dst_h is not None and src_w == dst_w and src_h == dst_h
    if not same_size and ("same-size" in text or "samesize" in text or "same dimensions" in text):
        same_size = True

    src_yuv = any(fmt in src for fmt in yuv_formats) or any(fmt in text for fmt in yuv_formats)
    dst_rgb = any(fmt in dst for fmt in rgb_formats) or any(fmt in text for fmt in rgb_formats)
    src_rgb = any(fmt in src for fmt in rgb_formats) or any(fmt in text for fmt in rgb_formats)
    dst_rgb_exact = any(fmt in dst for fmt in rgb_formats)
    bilinear = "bilinear" in algo or "bilinear" in text
    nearest = "nearest" in algo or "point" in algo or "nearest" in text or "point" in text

    if same_size and src_yuv and dst_rgb:
        return "same-size YUV -> RGB conversion"
    if src == "yuv420p" and dst == "rgb24" and bilinear:
        return "YUV420P -> RGB24 bilinear downscale"
    if src_rgb and (dst_rgb_exact or "rgb24" in text) and bilinear:
        return "RGB bilinear downscale"
    if src_rgb and (dst_rgb_exact or "rgb24" in text) and nearest:
        return "RGB nearest downscale"
    if src_yuv and dst_rgb and bilinear:
        return "YUV -> RGB bilinear scaling"
    if src_yuv and dst_rgb:
        return "YUV -> RGB conversion"
    if bilinear:
        return "bilinear scaling"
    if nearest:
        return "nearest scaling"
    if same_size:
        return "format conversion"
    return "scaling"

categories = []
for item in results:
    if failed(item):
        name = category(item)
        if name not in categories:
            categories.append(name)

print("")
print("Submission failed correctness gate.")
print(f"Correctness: {passed}/{total} passed.")
if categories:
    print("Failed categories:")
    for name in categories:
        print(f"- {name}")
else:
    print("Failed categories: unavailable from reward.json")
print("Benchmark not run because correctness failed.")
PY
