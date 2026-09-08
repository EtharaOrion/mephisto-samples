"""Deterministic workload generator for p8theta RasterLab.

Inputs and command lines are derived from BASE_SEED via a SHA-256 keyed
stream over family|split|index. The same module runs at bundle time and
at verify time; hidden workloads are never shipped as bytes, only as
(seed, spec) pairs realised through this generator.
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

BASE_SEED = "20260811"
CRC_INIT = 0xACE1FADE

FORMATS = {
    "GRAY8": 0,
    "RGB24": 1,
    "BGR24": 2,
    "RGBA32": 3,
    "BGRA32": 4,
    "YCC420P": 5,
    "YCC422P": 6,
    "YCC444P": 7,
}
KERNELS = ["point", "tent", "cubic4"]

_crc_table = []
for _n in range(256):
    _c = _n
    for _ in range(8):
        _c = (0xEDB88320 ^ (_c >> 1)) if (_c & 1) else (_c >> 1)
    _crc_table.append(_c)


def crc32_rl(data: bytes) -> int:
    crc = CRC_INIT
    for b in data:
        crc = _crc_table[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


def keyed_stream(key: str, nbytes: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < nbytes:
        block = hashlib.sha256(f"{BASE_SEED}|{key}|{counter}".encode()).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:nbytes])


def sub_seed(family: str, split: str, index: int) -> str:
    return hashlib.sha256(
        f"{BASE_SEED}|{family}|{split}|{index}".encode()
    ).hexdigest()[:16]


def plane_dims(fmt_code: int, plane: int, w: int, h: int) -> tuple[int, int]:
    if plane == 0:
        return w, h
    if fmt_code == 5:
        return (w + 1) // 2, (h + 1) // 2
    if fmt_code == 6:
        return (w + 1) // 2, h
    return w, h


def payload_size(fmt_code: int, w: int, h: int) -> int:
    channels = {0: 1, 1: 3, 2: 3, 3: 4, 4: 4}.get(fmt_code)
    if channels is not None:
        return w * h * channels
    total = 0
    for p in range(3):
        pw, ph = plane_dims(fmt_code, p, w, h)
        total += pw * ph
    return total


def synth_payload(fmt_code: int, w: int, h: int, pattern: str, key: str) -> bytes:
    n = payload_size(fmt_code, w, h)
    if pattern == "noise":
        return keyed_stream(key, n)
    if pattern == "flat":
        level = keyed_stream(key, 1)[0]
        return bytes([level]) * n
    if pattern == "gradient":
        return bytes([(i * 7 + (i // max(w, 1)) * 13) % 256 for i in range(n)])
    if pattern == "checker":
        block = 1 + keyed_stream(key, 1)[0] % 7
        out = bytearray()
        i = 0
        while len(out) < n:
            row = (i // max(w, 1)) // block
            col = (i % max(w, 1)) // block
            out.append(255 if (row + col) % 2 == 0 else 0)
            i += 1
        return bytes(out[:n])
    if pattern == "impulse":
        buf = bytearray(b"\x80" * n)
        idxs = keyed_stream(key, 64)
        for j in range(0, 64, 4):
            pos = struct.unpack_from("<I", idxs, j)[0] % n
            buf[pos] = 255 if j % 8 == 0 else 0
        return bytes(buf)
    raise ValueError(f"unknown pattern {pattern}")


def build_rlr(fmt_name: str, w: int, h: int, pattern: str, key: str) -> bytes:
    code = FORMATS[fmt_name]
    header = b"RLRF" + bytes([1, code, 0, 0]) + struct.pack("<II", w, h)
    payload = synth_payload(code, w, h, pattern, key)
    body = header + payload
    return body + struct.pack("<I", crc32_rl(body))


def corrupt_variant(blob: bytes, kind: str) -> bytes:
    buf = bytearray(blob)
    if kind == "bad_magic":
        buf[0] = ord("X")
    elif kind == "bad_version":
        buf[4] = 9
    elif kind == "bad_format":
        buf[5] = 200
    elif kind == "bad_crc":
        buf[-1] ^= 0xFF
    elif kind == "truncated":
        del buf[len(buf) // 2 :]
    elif kind == "trailing_junk":
        buf.extend(b"JUNKJUNK")
    elif kind == "zero_width":
        struct.pack_into("<I", buf, 8, 0)
    elif kind == "huge_width":
        struct.pack_into("<I", buf, 8, 40000)
    return bytes(buf)


DIMS_POOL = [
    (1, 1), (2, 2), (3, 3), (5, 7), (7, 5), (16, 16), (17, 13),
    (31, 29), (64, 48), (63, 47), (128, 96), (129, 97), (240, 160),
    (320, 240), (321, 241), (511, 383),
]
PATTERNS = ["noise", "gradient", "checker", "flat", "impulse"]
FMT_LIST = list(FORMATS)


def pick(seq, raw: int):
    return seq[raw % len(seq)]


def gen_family(family: str, split: str, count: int) -> list[dict]:
    workloads = []
    for i in range(count):
        seed = sub_seed(family, split, i)
        raw = int(seed, 16)
        wid = f"{family}__{split}__{i:03d}"
        src_fmt = pick(FMT_LIST, raw)
        pattern = pick(PATTERNS, raw >> 8)
        w, h = pick(DIMS_POOL, raw >> 16)
        spec: dict = {
            "id": wid,
            "family": family,
            "split": split,
            "seed": seed,
            "input": {"fmt": src_fmt, "w": w, "h": h, "pattern": pattern},
        }
        if family == "convert":
            dst = pick(FMT_LIST, raw >> 24)
            spec["argv"] = ["convert", "-f", dst, "{in}", "{out}"]
        elif family == "resize_up":
            k = pick(KERNELS, raw >> 24)
            fw = min(32768, w * (2 + (raw >> 28) % 3) + (raw >> 32) % 5)
            fh = min(32768, h * (2 + (raw >> 36) % 3) + (raw >> 40) % 5)
            spec["argv"] = ["resize", "-w", str(fw), "-h", str(fh), "-k", k,
                            "{in}", "{out}"]
        elif family == "resize_down":
            k = pick(KERNELS, raw >> 24)
            fw = max(1, w // (2 + (raw >> 28) % 3) - (raw >> 32) % 2)
            fh = max(1, h // (2 + (raw >> 36) % 3) - (raw >> 40) % 2)
            spec["argv"] = ["resize", "-w", str(fw), "-h", str(fh), "-k", k,
                            "{in}", "{out}"]
        elif family == "chain":
            ops = []
            depth = 3 + raw % 4
            r = raw >> 8
            for _ in range(depth):
                if r % 2 == 0:
                    ops.append(f"convert:{pick(FMT_LIST, r >> 2)}")
                else:
                    cw = 1 + (r >> 2) % 300
                    ch = 1 + (r >> 12) % 300
                    ops.append(f"resize:{cw}x{ch}:{pick(KERNELS, r >> 22)}")
                r >>= 24
                if r == 0:
                    r = int(sub_seed(family, split, i + 1000), 16)
            spec["argv"] = ["chain", ";".join(ops), "{in}", "{out}"]
        elif family == "perf":
            base = PERF_SPECS[i % len(PERF_SPECS)]
            spec["input"] = {"fmt": base[0], "w": base[1], "h": base[2],
                             "pattern": "noise"}
            spec["argv"] = list(base[3])
        elif family == "metadata":
            cmd = "info" if raw % 2 == 0 else "checksum"
            spec["argv"] = [cmd, "{in}"]
        elif family == "errors":
            kind = pick(
                ["bad_magic", "bad_version", "bad_format", "bad_crc",
                 "truncated", "trailing_junk", "zero_width", "huge_width",
                 "missing_file", "bad_kernel", "bad_fmt_arg", "usage"],
                raw >> 24,
            )
            spec["corrupt"] = kind
            if kind == "missing_file":
                spec["argv"] = ["info", "{missing}"]
                spec.pop("input")
            elif kind == "bad_kernel":
                spec["argv"] = ["resize", "-w", "10", "-h", "10", "-k",
                                "lanczos", "{in}", "{out}"]
                spec.pop("corrupt")
            elif kind == "bad_fmt_arg":
                spec["argv"] = ["convert", "-f", "YUV9", "{in}", "{out}"]
                spec.pop("corrupt")
            elif kind == "usage":
                spec["argv"] = ["resize", "-w", "10", "{in}", "{out}"]
                spec.pop("corrupt")
            else:
                spec["argv"] = ["checksum", "{in}"]
        else:
            raise ValueError(family)
        workloads.append(spec)
    return workloads


PERF_SPECS = [
    ("RGB24", 1920, 1080,
     ("resize", "-w", "2880", "-h", "1620", "-k", "cubic4", "{in}", "{out}")),
    ("YCC420P", 1920, 1080,
     ("chain", "convert:RGB24;resize:1280x720:tent;convert:YCC444P",
      "{in}", "{out}")),
    ("RGBA32", 1600, 900,
     ("chain", "resize:2400x1350:cubic4;convert:BGR24", "{in}", "{out}")),
    ("GRAY8", 2560, 1440,
     ("resize", "-w", "1024", "-h", "576", "-k", "tent", "{in}", "{out}")),
]

SPLIT_PLAN = {
    "public": {"convert": 8, "resize_up": 5, "resize_down": 5, "chain": 4,
               "metadata": 4, "errors": 6, "perf": 2},
    "dev": {"convert": 16, "resize_up": 10, "resize_down": 10, "chain": 10,
            "metadata": 6, "errors": 10, "perf": 2},
    "hidden": {"convert": 48, "resize_up": 30, "resize_down": 30, "chain": 40,
               "metadata": 12, "errors": 24, "perf": 4},
}


def generate_manifest(split: str) -> list[dict]:
    plan = SPLIT_PLAN[split]
    out: list[dict] = []
    for family, count in plan.items():
        out.extend(gen_family(family, split, count))
    return out


def materialize(split: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    manifest = generate_manifest(split)
    for spec in manifest:
        if "input" in spec:
            inp = spec["input"]
            blob = build_rlr(inp["fmt"], inp["w"], inp["h"], inp["pattern"],
                             spec["seed"])
            if "corrupt" in spec:
                blob = corrupt_variant(blob, spec["corrupt"])
            (dest / f"{spec['id']}.rlr").write_bytes(blob)
    manifest_path = dest / "_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return manifest_path


if __name__ == "__main__":
    split_arg = sys.argv[1]
    dest_arg = Path(sys.argv[2])
    path = materialize(split_arg, dest_arg)
    print(f"wrote {path}")
