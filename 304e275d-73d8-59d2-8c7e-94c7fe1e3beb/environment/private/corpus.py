"""Deterministic generator for the ARCL program corpus.

Every program is derived from a recorded seed through a sha256 keyed splitmix64 stream, so
the public smoke slice materialised into the solving image and the held out suite held in
evaluator memory are reproducible without shipping any published instruction set test
suite or compiler benchmark.
"""

from __future__ import annotations

import hashlib

import registry

MASK64 = (1 << 64) - 1

PUBLIC_PROGRAMS = 12
PUBLIC_SATURATING = 3
HOLDOUT_PROGRAMS = 40
HOLDOUT_SATURATING = 8

CATEGORY_WEIGHT = {"arith": 1.0, "control": 1.0, "calls": 1.5, "saturate": 1.5}
BASE_CATEGORIES = ("arith", "control", "calls")


class Stream:
    def __init__(self, seed: str, slice_name: str, index: int) -> None:
        digest = hashlib.sha256(f"{seed}:{slice_name}:{index}".encode("utf-8")).digest()
        self.state = int.from_bytes(digest[:8], "big")

    def next_word(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        return (z ^ (z >> 31)) & MASK64

    def between(self, low: int, high: int) -> int:
        return low + self.next_word() % (high - low + 1)

    def pick(self, options):
        return options[self.next_word() % len(options)]


def _arith_source(stream: Stream) -> str:
    rounds = stream.between(6, 20)
    seed_value = stream.between(1, 1 << 20)
    multiplier = stream.between(3, 4099)
    addend = stream.between(1, 1 << 16)
    divisor = stream.between(2, 97)
    shift = stream.between(1, 30)
    first = stream.pick(("+", "-", "*", "^"))
    second = stream.pick(("|", "&", "^", "+"))
    return (
        "func main() {\n"
        f"  let acc = {seed_value};\n"
        "  let i = 0;\n"
        f"  while (i < {rounds}) {{\n"
        f"    acc = acc {first} (i * {multiplier});\n"
        f"    acc = (acc {second} {addend}) >> {shift % 8 + 1};\n"
        f"    acc = acc + (i % {divisor});\n"
        "    out acc;\n"
        "    i = i + 1;\n"
        "  }\n"
        f"  out acc / {divisor};\n"
        f"  out acc % {divisor};\n"
        f"  out acc << {shift};\n"
        "  return 0;\n"
        "}\n"
    )


def _control_source(stream: Stream) -> str:
    rounds = stream.between(8, 24)
    low = stream.between(2, 400)
    high = low + stream.between(50, 900)
    first = stream.between(1, 60)
    second = stream.between(1, 60)
    third = stream.between(1, 60)
    multiplier = stream.between(7, 1301)
    mask = stream.between(1, 1 << 14)
    modulus = stream.between(11, 2003)
    return (
        "func classify(x) {\n"
        f"  if (x < {low}) {{ return {first}; }}\n"
        f"  if (x < {high}) {{ return {second}; }}\n"
        f"  return {third};\n"
        "}\n"
        "func main() {\n"
        "  let i = 0;\n"
        "  let total = 0;\n"
        f"  while (i < {rounds}) {{\n"
        f"    let v = (i * {multiplier}) ^ {mask};\n"
        f"    let c = classify(v % {modulus});\n"
        f"    if (c > {second}) {{ total = total + c; }} else {{ total = total - c; }}\n"
        "    out c;\n"
        "    i = i + 1;\n"
        "  }\n"
        "  out total;\n"
        "  return 0;\n"
        "}\n"
    )


def _calls_source(stream: Stream) -> str:
    rounds = stream.between(5, 16)
    depth = stream.between(3, 12)
    modulus = stream.between(3, 997)
    multiplier = stream.between(5, 2003)
    low = stream.between(1, 200)
    high = low + stream.between(100, 4000)
    return (
        "func fold(n, s) {\n"
        "  if (n <= 0) { return s; }\n"
        f"  return fold(n - 1, s + gcd(n * {multiplier}, {modulus}));\n"
        "}\n"
        "func main() {\n"
        "  let i = 1;\n"
        "  let t = 0;\n"
        f"  while (i <= {rounds}) {{\n"
        f"    t = t + popcnt(i * {multiplier});\n"
        f"    t = clamp(t * i, {low}, {high});\n"
        "    out t;\n"
        "    i = i + 1;\n"
        "  }\n"
        f"  out fold({depth}, 0);\n"
        f"  out gcd(t, {modulus});\n"
        "  return 0;\n"
        "}\n"
    )


def _saturate_source(stream: Stream) -> str:
    rounds = stream.between(5, 14)
    start = stream.between(1 << 28, (1 << 31) - 3)
    addend = stream.between(1 << 20, 1 << 27)
    factor = stream.between(2, 11)
    subtrahend = stream.between(1 << 22, 1 << 29)
    return (
        "func main() {\n"
        f"  let acc = {start};\n"
        "  let i = 0;\n"
        f"  while (i < {rounds}) {{\n"
        f"    acc = sat_add(acc, {addend});\n"
        f"    acc = sat_mul(acc, {factor});\n"
        f"    acc = sat_sub(acc, {subtrahend} + i);\n"
        "    out acc;\n"
        "    i = i + 1;\n"
        "  }\n"
        f"  out sat_add(acc, {addend});\n"
        f"  out sat_mul(0 - acc, {factor});\n"
        "  return 0;\n"
        "}\n"
    )


_BUILDERS = {
    "arith": _arith_source,
    "control": _control_source,
    "calls": _calls_source,
    "saturate": _saturate_source,
}

SLICE_SHAPE = {
    "public": (PUBLIC_PROGRAMS, PUBLIC_SATURATING),
    "holdout": (HOLDOUT_PROGRAMS, HOLDOUT_SATURATING),
}


def program_at(seed: str, slice_name: str, index: int, category: str) -> dict:
    stream = Stream(seed, slice_name, index)
    return {
        "index": index,
        "name": f"prog_{index:04d}",
        "category": category,
        "weight": CATEGORY_WEIGHT[category],
        "source": _BUILDERS[category](stream),
    }


def programs(seed: str, slice_name: str, isa_manifest: dict) -> list:
    base_count, saturating_count = SLICE_SHAPE[slice_name]
    out = []
    for index in range(base_count):
        category = BASE_CATEGORIES[index % len(BASE_CATEGORIES)]
        entry = program_at(seed, slice_name, index, category)
        entry["isa_revision_id"] = registry.isa_revision_for_program(isa_manifest, slice_name, index)
        out.append(entry)
    for offset in range(saturating_count):
        index = base_count + offset
        revision = registry.isa_revision_for_program(isa_manifest, slice_name, index)
        if revision != registry.ISA_SAT:
            continue
        entry = program_at(seed, slice_name, index, "saturate")
        entry["isa_revision_id"] = revision
        out.append(entry)
    return out


BOUNDARY_PROGRAMS = (
    {
        "name": "boundary_wrap",
        "requires_saturating": False,
        "source": (
            "func main() {\n"
            "  out 2147483647 + 1;\n"
            "  out (0 - 2147483648) - 1;\n"
            "  out 65536 * 65536;\n"
            "  out 2147483647 * 3;\n"
            "  out 0 - (0 - 2147483648);\n"
            "  return 0;\n"
            "}\n"
        ),
    },
    {
        "name": "boundary_shift",
        "requires_saturating": False,
        "source": (
            "func main() {\n"
            "  out 1 << 31;\n"
            "  out 1 << 32;\n"
            "  out 1 << 33;\n"
            "  out (0 - 1) >> 1;\n"
            "  out (0 - 1) >>> 1;\n"
            "  out (0 - 1024) >> 33;\n"
            "  out ~0;\n"
            "  return 0;\n"
            "}\n"
        ),
    },
    {
        "name": "boundary_divide",
        "requires_saturating": False,
        "source": (
            "func main() {\n"
            "  out (0 - 2147483648) / (0 - 1);\n"
            "  out (0 - 2147483648) % (0 - 1);\n"
            "  out 7 / (0 - 2);\n"
            "  out (0 - 7) / 2;\n"
            "  out (0 - 7) % 3;\n"
            "  out 7 % (0 - 3);\n"
            "  return 0;\n"
            "}\n"
        ),
    },
    {
        "name": "boundary_trap",
        "requires_saturating": False,
        "source": (
            "func main() {\n"
            "  let z = 0;\n"
            "  let i = 0;\n"
            "  while (i < 3) {\n"
            "    out i;\n"
            "    i = i + 1;\n"
            "  }\n"
            "  out 5 / z;\n"
            "  out 99;\n"
            "  return 0;\n"
            "}\n"
        ),
    },
    {
        "name": "boundary_intrinsic",
        "requires_saturating": False,
        "source": (
            "func main() {\n"
            "  out gcd(0 - 48, 18);\n"
            "  out gcd(0, 17);\n"
            "  out clamp(500, 0 - 10, 10);\n"
            "  out clamp(0 - 500, 0 - 10, 10);\n"
            "  out clamp(3, 0 - 10, 10);\n"
            "  out popcnt(0 - 1);\n"
            "  out popcnt(0);\n"
            "  return 0;\n"
            "}\n"
        ),
    },
    {
        "name": "boundary_saturate",
        "requires_saturating": True,
        "source": (
            "func main() {\n"
            "  out sat_add(2147483647, 1);\n"
            "  out sat_add(2147483647, 2147483647);\n"
            "  out sat_sub(0 - 2147483648, 1);\n"
            "  out sat_mul(2147483647, 2);\n"
            "  out sat_mul(0 - 2147483648, 0 - 1);\n"
            "  out sat_mul(0 - 2147483648, 2);\n"
            "  out sat_add(5, 6);\n"
            "  return 0;\n"
            "}\n"
        ),
    },
)


def boundary_programs(isa_revision_id: str) -> list:
    saturating = isa_revision_id == registry.ISA_SAT
    out = []
    for index, entry in enumerate(BOUNDARY_PROGRAMS):
        if entry["requires_saturating"] and not saturating:
            continue
        out.append(
            {
                "index": index,
                "name": entry["name"],
                "category": "boundary",
                "weight": 1.0,
                "source": entry["source"],
                "isa_revision_id": isa_revision_id,
            }
        )
    return out


def perturb(source: str, tag: str) -> str:
    """Renames every user identifier and re-indents, leaving observable behaviour unchanged."""
    renames = {
        "classify": f"c_{tag}",
        "fold": f"f_{tag}",
        "acc": f"a_{tag}",
        "total": f"t_{tag}",
        "main": "main",
    }
    out = []
    for line in source.splitlines():
        stripped = line.strip()
        for old, new in renames.items():
            stripped = _rename(stripped, old, new)
        out.append(("    " if stripped and not stripped.startswith("func") else "") + stripped)
    return "\n".join(out) + "\n"


def _rename(text: str, old: str, new: str) -> str:
    if old == new:
        return text
    out = []
    index = 0
    while index < len(text):
        if text.startswith(old, index):
            before = text[index - 1] if index else " "
            after = text[index + len(old)] if index + len(old) < len(text) else " "
            if not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_"):
                out.append(new)
                index += len(old)
                continue
        out.append(text[index])
        index += 1
    return "".join(out)
