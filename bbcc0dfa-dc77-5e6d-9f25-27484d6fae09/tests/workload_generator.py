#!/usr/bin/env python3
"""Deterministic workload generator for p9iota_latticestore_workspace_reconstruction.

Every byte this generator emits derives from BASE_SEED through SHA-256 keyed
streams, so the verifier regenerates all splits fresh at scoring time and no
recorded hidden output ever ships in the delivery closure.

Derivations (normative, mirrored in solution/grounding.yaml):
  sub_seed(family, split, index) = sha256("{BASE_SEED}|{family}|{split}|{index}") first 16 hex
  keyed stream block(counter)    = sha256("{BASE_SEED}|{key}|{counter}") digest bytes

Workload JSON: {"id", "family", "steps": [...]}. Step ops:
  init                    -> lattice init {S}
  put {file}              -> lattice put {S} {D}/<file>
  put_missing {file}      -> lattice put {S} {D}/<file> (file never materialized)
  get {id, out}           -> lattice get {S} <id> {O}/<out>
  get_unknown {id, out}   -> same argv, id unknown or malformed
  verify                  -> lattice verify {S}
  stats                   -> lattice stats {S}
  raw {argv}              -> lattice <argv...> (token substitution applies)
  corrupt {file, skip, offset, xor}       -> runner-local byte flip inside store
  truncate_journal {drop}                 -> runner-local journal tail drop
"""

import hashlib
import json
from pathlib import Path

BASE_SEED = "20260812"

SPLIT_PLAN = {
    "public": {"basic": 8, "boundary": 8, "dedupe": 5, "multi": 4, "corrupt": 3, "recovery": 2},
    "dev": {"basic": 12, "boundary": 14, "dedupe": 10, "multi": 8, "corrupt": 8, "recovery": 8},
    "hidden": {"basic": 30, "boundary": 30, "dedupe": 25, "multi": 25, "corrupt": 20, "recovery": 20},
}

FAMILY_ORDER = ("basic", "boundary", "dedupe", "multi", "corrupt", "recovery")

L2_LAYERS = {
    "layer_core": ("basic", "boundary"),
    "layer_dedupe_multi": ("dedupe", "multi"),
    "layer_corrupt": ("corrupt",),
    "layer_recovery": ("recovery",),
}

PERF_SPECS = (
    {"id": "perf_put_stream", "desc": "single 16 MiB unique-stream put"},
    {"id": "perf_put_dedupe", "desc": "16 MiB high-dedupe repeated-block put"},
    {"id": "perf_get", "desc": "16 MiB put then timed get and verify"},
)
PERF_SIZE = 16 * 1024 * 1024


def sub_seed(family: str, split: str, index: int) -> str:
    return hashlib.sha256(f"{BASE_SEED}|{family}|{split}|{index}".encode()).hexdigest()[:16]


class KeyedStream:
    """Counter-mode SHA-256 byte stream keyed under BASE_SEED."""

    def __init__(self, key: str):
        self.key = key
        self.counter = 0
        self.buffer = b""

    def bytes(self, n: int) -> bytes:
        chunks = [self.buffer]
        have = len(self.buffer)
        while have < n:
            block = hashlib.sha256(f"{BASE_SEED}|{self.key}|{self.counter}".encode()).digest()
            self.counter += 1
            chunks.append(block)
            have += len(block)
        blob = b"".join(chunks)
        self.buffer = blob[n:]
        return blob[:n]

    def rand_int(self, lo: int, hi: int) -> int:
        span = hi - lo + 1
        v = int.from_bytes(self.bytes(8), "big")
        return lo + (v % span)


def object_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _gen_basic(rng: KeyedStream, ss: str):
    files, steps = {}, [{"op": "init"}]
    n = rng.rand_int(2, 4)
    ids = []
    for i in range(n):
        size = rng.rand_int(1024, 300 * 1024)
        content = KeyedStream(f"{ss}|file|{i}").bytes(size)
        name = f"f{i}.bin"
        files[name] = content
        ids.append(object_hex(content))
        steps.append({"op": "put", "file": name})
    steps.append({"op": "stats"})
    for i, oid in enumerate(ids):
        steps.append({"op": "get", "id": oid, "out": f"g{i}.bin"})
    steps.append({"op": "verify"})
    steps.append({"op": "stats"})
    return steps, files


BOUNDARY_SIZES = (0, 1, 2047, 2048, 2049, 4095, 65535, 65536, 65537, 131072)


def _gen_boundary(rng: KeyedStream, ss: str):
    files, steps = {}, [{"op": "init"}]
    count = rng.rand_int(3, 5)
    chosen = []
    for i in range(count):
        chosen.append(BOUNDARY_SIZES[rng.rand_int(0, len(BOUNDARY_SIZES) - 1)])
    ids = []
    for i, size in enumerate(chosen):
        content = KeyedStream(f"{ss}|edge|{i}").bytes(size)
        name = f"e{i}.bin"
        files[name] = content
        ids.append(object_hex(content))
        steps.append({"op": "put", "file": name})
    err = rng.rand_int(0, 3)
    if err == 0:
        steps.append({"op": "raw", "argv": ["frobnicate"]})
    elif err == 1:
        steps.append({"op": "raw", "argv": ["init", "{S}"]})
    elif err == 2:
        steps.append({"op": "put_missing", "file": "absent.bin"})
    else:
        bogus = KeyedStream(f"{ss}|bogus").bytes(32).hex()
        steps.append({"op": "get_unknown", "id": bogus, "out": "never.bin"})
        steps.append({"op": "get_unknown", "id": "zz-not-hex", "out": "never2.bin"})
    for i, oid in enumerate(ids):
        steps.append({"op": "get", "id": oid, "out": f"g{i}.bin"})
    steps.append({"op": "verify"})
    steps.append({"op": "stats"})
    return steps, files


def _gen_dedupe(rng: KeyedStream, ss: str):
    files, steps = {}, [{"op": "init"}]
    block = KeyedStream(f"{ss}|block").bytes(rng.rand_int(8 * 1024, 32 * 1024))
    reps_a = rng.rand_int(4, 10)
    reps_b = rng.rand_int(2, 6)
    unique = KeyedStream(f"{ss}|unique").bytes(rng.rand_int(3000, 40000))
    a = block * reps_a
    b = block * reps_b + unique
    files["a.bin"], files["b.bin"] = a, b
    steps += [
        {"op": "put", "file": "a.bin"},
        {"op": "stats"},
        {"op": "put", "file": "b.bin"},
        {"op": "put", "file": "a.bin"},
        {"op": "stats"},
        {"op": "get", "id": object_hex(a), "out": "ga.bin"},
        {"op": "get", "id": object_hex(b), "out": "gb.bin"},
        {"op": "verify"},
    ]
    return steps, files


def _gen_multi(rng: KeyedStream, ss: str):
    files, steps = {}, [{"op": "init"}]
    n = rng.rand_int(5, 10)
    ids = []
    for i in range(n):
        size = rng.rand_int(500, 200 * 1024)
        content = KeyedStream(f"{ss}|obj|{i}").bytes(size)
        name = f"m{i}.bin"
        files[name] = content
        ids.append(object_hex(content))
        steps.append({"op": "put", "file": name})
        if i % 2 == 1:
            steps.append({"op": "get", "id": ids[rng.rand_int(0, i)], "out": f"mid{i}.bin"})
            steps.append({"op": "stats"})
    for i, oid in enumerate(ids):
        steps.append({"op": "get", "id": oid, "out": f"g{i}.bin"})
    steps.append({"op": "verify"})
    steps.append({"op": "stats"})
    return steps, files


CORRUPT_TARGETS = ("pack", "meta", "index", "manifest")


def _gen_corrupt(rng: KeyedStream, ss: str):
    files, steps = {}, [{"op": "init"}]
    n = rng.rand_int(1, 3)
    ids = []
    for i in range(n):
        content = KeyedStream(f"{ss}|c|{i}").bytes(rng.rand_int(5000, 150 * 1024))
        name = f"c{i}.bin"
        files[name] = content
        ids.append(object_hex(content))
        steps.append({"op": "put", "file": name})
    target = CORRUPT_TARGETS[rng.rand_int(0, 3)]
    xor = rng.rand_int(1, 255)
    offset = rng.rand_int(0, 1 << 30)
    if target == "pack":
        spec = {"file": "objects/pack-000000.lpk", "skip": 16}
    elif target == "meta":
        spec = {"file": "lattice.meta", "skip": 0}
    elif target == "index":
        spec = {"file": "index/index.lix", "skip": 4}
    else:
        spec = {"file": f"manifests/{ids[rng.rand_int(0, n - 1)]}.lmf", "skip": 4}
    steps.append({"op": "corrupt", "offset": offset, "xor": xor, **spec})
    steps.append({"op": "verify"})
    steps.append({"op": "get", "id": ids[0], "out": "g0.bin"})
    steps.append({"op": "stats"})
    return steps, files


def _gen_recovery(rng: KeyedStream, ss: str):
    files, steps = {}, [{"op": "init"}]
    n = rng.rand_int(2, 3)
    ids = []
    for i in range(n):
        content = KeyedStream(f"{ss}|r|{i}").bytes(rng.rand_int(20000, 250 * 1024))
        name = f"r{i}.bin"
        files[name] = content
        ids.append(object_hex(content))
        steps.append({"op": "put", "file": name})
    steps.append({"op": "truncate_journal", "drop": rng.rand_int(1, 80)})
    steps.append({"op": "stats"})
    for i, oid in enumerate(ids):
        steps.append({"op": "get", "id": oid, "out": f"g{i}.bin"})
    steps.append({"op": "verify"})
    steps.append({"op": "stats"})
    return steps, files


_BUILDERS = {
    "basic": _gen_basic,
    "boundary": _gen_boundary,
    "dedupe": _gen_dedupe,
    "multi": _gen_multi,
    "corrupt": _gen_corrupt,
    "recovery": _gen_recovery,
}


def build_workload(family: str, split: str, index: int):
    ss = sub_seed(family, split, index)
    rng = KeyedStream(f"{ss}|plan")
    steps, files = _BUILDERS[family](rng, ss)
    wid = f"{family}_{split}_{index:03d}"
    return {"id": wid, "family": family, "steps": steps}, files


def materialize(split: str, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ids = []
    for family in FAMILY_ORDER:
        for index in range(SPLIT_PLAN[split][family]):
            workload, files = build_workload(family, split, index)
            wid = workload["id"]
            ids.append(wid)
            (out / f"{wid}.json").write_text(json.dumps(workload, indent=1, sort_keys=True) + "\n")
            inputs = out / "inputs" / wid
            inputs.mkdir(parents=True, exist_ok=True)
            for name, content in files.items():
                (inputs / name).write_bytes(content)
    (out / "_manifest.json").write_text(json.dumps({"split": split, "workloads": ids}, indent=1) + "\n")
    return ids


def materialize_perf(spec_id: str, rep_key: str, out_dir):
    out = Path(out_dir)
    inputs = out / "inputs" / f"{spec_id}_{rep_key}"
    inputs.mkdir(parents=True, exist_ok=True)
    if spec_id == "perf_put_stream":
        content = KeyedStream(f"{spec_id}|{rep_key}|stream").bytes(PERF_SIZE)
        steps = [{"op": "init"}, {"op": "put", "file": "p.bin"}, {"op": "stats"}]
    elif spec_id == "perf_put_dedupe":
        block = KeyedStream(f"{spec_id}|{rep_key}|block").bytes(64 * 1024)
        reps = PERF_SIZE // len(block)
        salt = KeyedStream(f"{spec_id}|{rep_key}|salt").bytes(4096)
        content = block * reps + salt
        steps = [{"op": "init"}, {"op": "put", "file": "p.bin"}, {"op": "stats"}]
    elif spec_id == "perf_get":
        content = KeyedStream(f"{spec_id}|{rep_key}|stream").bytes(PERF_SIZE)
        steps = [
            {"op": "init"},
            {"op": "put", "file": "p.bin"},
            {"op": "get", "id": object_hex(content), "out": "g.bin"},
            {"op": "verify"},
        ]
    else:
        raise ValueError(f"unknown perf spec {spec_id}")
    (inputs / "p.bin").write_bytes(content)
    workload = {"id": f"{spec_id}_{rep_key}", "family": "perf", "steps": steps}
    (out / f"{spec_id}_{rep_key}.json").write_text(json.dumps(workload, indent=1, sort_keys=True) + "\n")
    return workload["id"]


if __name__ == "__main__":
    import sys

    split_arg, dest = sys.argv[1], sys.argv[2]
    written = materialize(split_arg, dest)
    print(f"materialized {len(written)} workloads for split {split_arg} into {dest}")
