"""Deterministic generator for the pinned irregular nesting instance family.

Nothing here is lifted from a published nesting benchmark. Part outlines are
generated from a recorded seed through a splitmix64 stream, so the whole family
is reproducible from the seed alone and no public density table applies to it.

Outlines are star shaped about the local origin. Vertices sit on a 24 slot angular
grid with a minimum gap of two slots, which is thirty degrees, while integer
rounding can move a vertex by at most half a unit, which at the minimum radius of
ten units is under three degrees. The angular order therefore survives rounding
and the outline stays simple with the local origin strictly inside it, which is
what lets every placement carry an exact interior reference point.
"""

from __future__ import annotations

import hashlib

import geometry
import registry

MASK64 = (1 << 64) - 1
ANGLE_SLOTS = 24
UNIT_SCALE = 10000

DIRECTION_TABLE = (
    (10000, 0),
    (9659, 2588),
    (8660, 5000),
    (7071, 7071),
    (5000, 8660),
    (2588, 9659),
    (0, 10000),
    (-2588, 9659),
    (-5000, 8660),
    (-7071, 7071),
    (-8660, 5000),
    (-9659, 2588),
    (-10000, 0),
    (-9659, -2588),
    (-8660, -5000),
    (-7071, -7071),
    (-5000, -8660),
    (-2588, -9659),
    (0, -10000),
    (2588, -9659),
    (5000, -8660),
    (7071, -7071),
    (8660, -5000),
    (9659, -2588),
)

PIECE_TYPES_PER_INSTANCE = 12
MIN_INNER_RADIUS = 10
CONFLICT_MODULUS = 3
CONFLICT_RESIDUE = 1
CONFLICT_MULTIPLICITY_INFLATION = 2

FULL_ROTATIONS = [0, 90, 180, 270]
NARROW_ROTATIONS = [0, 180]


class Stream:
    def __init__(self, label: str) -> None:
        self.state = int.from_bytes(hashlib.sha256(label.encode("utf-8")).digest()[:8], "big")

    def next(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        return (z ^ (z >> 31)) & MASK64

    def below(self, bound: int) -> int:
        if bound <= 1:
            return 0
        return self.next() % bound

    def between(self, low: int, high: int) -> int:
        return low + self.below(high - low + 1)


def _scaled(radius: int, factor: int) -> int:
    product = radius * factor
    if product >= 0:
        return (product + UNIT_SCALE // 2) // UNIT_SCALE
    return -((-product + UNIT_SCALE // 2) // UNIT_SCALE)


def _slots(stream: Stream, vertex_count: int) -> list[int]:
    spacing = ANGLE_SLOTS // vertex_count
    jitter = max(1, spacing - 1)
    return [(index * ANGLE_SLOTS) // vertex_count + stream.below(jitter) for index in range(vertex_count)]


def make_outline(stream: Stream) -> list[tuple[int, int]]:
    vertex_count = stream.between(6, 9)
    inner = stream.between(MIN_INNER_RADIUS, 20)
    outer = inner + stream.between(14, 34)
    polygon: list[tuple[int, int]] = []
    for slot in _slots(stream, vertex_count):
        radius = stream.between(inner, outer)
        cosine, sine = DIRECTION_TABLE[slot % ANGLE_SLOTS]
        polygon.append((_scaled(radius, cosine), _scaled(radius, sine)))
    if not geometry.is_simple(polygon):
        raise geometry.GeometryError("generated_outline_not_simple")
    if not geometry.point_strictly_inside((0, 0), geometry.doubled(polygon)):
        raise geometry.GeometryError("generated_outline_origin_not_interior")
    if geometry.twice_signed_area(polygon) < 0:
        polygon.reverse()
    return polygon


def make_piece(stream: Stream, ordinal: int) -> dict:
    outline = make_outline(stream)
    multiplicity = stream.between(3, 5)
    conflicted = ordinal % CONFLICT_MODULUS == CONFLICT_RESIDUE
    if conflicted:
        vector_rotation = list(NARROW_ROTATIONS)
        table_rotation = list(FULL_ROTATIONS)
        vector_multiplicity = multiplicity
        table_multiplicity = multiplicity + CONFLICT_MULTIPLICITY_INFLATION
    else:
        vector_rotation = list(FULL_ROTATIONS)
        table_rotation = list(FULL_ROTATIONS)
        vector_multiplicity = multiplicity
        table_multiplicity = multiplicity
    return {
        "piece_id": f"P{ordinal:02d}",
        "polygon": outline,
        "twice_area": geometry.twice_area(outline),
        "vector_rotation_allowance": vector_rotation,
        "table_rotation_allowance": table_rotation,
        "vector_multiplicity": vector_multiplicity,
        "table_multiplicity": table_multiplicity,
        "vector_sheet_margin": 0,
        "table_sheet_margin": 0,
        "carriers_conflict": conflicted,
    }


def make_instance(seed: str, kind: str, ordinal: int, profile_id: str) -> dict:
    stream = Stream(f"{seed}|{kind}|{ordinal:03d}")
    pieces = [make_piece(stream, index) for index in range(PIECE_TYPES_PER_INSTANCE)]
    return {
        "instance_id": f"{kind}-{ordinal:03d}",
        "sheet_id": f"{kind}-{ordinal:03d}-sheet-0",
        "instance_ordinal": ordinal,
        "sheet_stock_profile_id": profile_id,
        "pieces": pieces,
    }


def make_family(seed: str, kind: str, count: int, manifest: dict) -> list[dict]:
    family = []
    for ordinal in range(count):
        profile_id = registry.profile_for_instance(manifest, ordinal)
        family.append(make_instance(seed, kind, ordinal, profile_id))
    return family


def render_outline_carrier(instance: dict, profile: dict, directive: str) -> str:
    lines = [
        "# edgebench vector outline carrier",
        "# Coordinates are integers in sheet units. Rotation allowance is a quantised degree set.",
        f"# {directive}",
        f"instance {instance['instance_id']}",
        f"sheet {instance['sheet_id']} {profile['width']} {profile['height']} "
        f"{profile['sheet_stock_profile_id']}",
    ]
    for x0, y0, x1, y1 in profile["defects"]:
        lines.append(f"defect {x0} {y0} {x1} {y1}")
    for piece in instance["pieces"]:
        allowance = ",".join(str(value) for value in piece["vector_rotation_allowance"])
        lines.append(
            f"piece {piece['piece_id']} rot={allowance} mult={piece['vector_multiplicity']} "
            f"margin={piece['vector_sheet_margin']}"
        )
        for x, y in piece["polygon"]:
            lines.append(f"  v {x} {y}")
        lines.append("endpiece")
    return "\n".join(lines) + "\n"


def render_parameter_carrier(instance: dict) -> str:
    lines = ["piece_id,rotation_allowance,multiplicity,sheet_margin,twice_area"]
    for piece in instance["pieces"]:
        allowance = "|".join(str(value) for value in piece["table_rotation_allowance"])
        lines.append(
            f"{piece['piece_id']},{allowance},{piece['table_multiplicity']},"
            f"{piece['table_sheet_margin']},{piece['twice_area']}"
        )
    return "\n".join(lines) + "\n"


def parse_outline_carrier(text: str) -> dict:
    sheet = None
    defects: list[list[int]] = []
    pieces: list[dict] = []
    current: dict | None = None
    instance_id = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        head = parts[0]
        if head == "instance":
            instance_id = parts[1]
        elif head == "sheet":
            sheet = {
                "sheet_id": parts[1],
                "width": int(parts[2]),
                "height": int(parts[3]),
                "sheet_stock_profile_id": parts[4],
            }
        elif head == "defect":
            defects.append([int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])])
        elif head == "piece":
            fields = dict(token.split("=", 1) for token in parts[2:])
            current = {
                "piece_id": parts[1],
                "vector_rotation_allowance": [int(v) for v in fields["rot"].split(",")],
                "vector_multiplicity": int(fields["mult"]),
                "vector_sheet_margin": int(fields["margin"]),
                "polygon": [],
            }
        elif head == "v":
            current["polygon"].append((int(parts[1]), int(parts[2])))
        elif head == "endpiece":
            pieces.append(current)
            current = None
    return {"instance_id": instance_id, "sheet": sheet, "defects": defects, "pieces": pieces}


def parse_parameter_carrier(text: str) -> dict:
    rows = {}
    lines = [line for line in text.splitlines() if line.strip()]
    for line in lines[1:]:
        piece_id, allowance, multiplicity, margin, twice = line.split(",")
        rows[piece_id] = {
            "table_rotation_allowance": [int(v) for v in allowance.split("|")],
            "table_multiplicity": int(multiplicity),
            "table_sheet_margin": int(margin),
            "twice_area": int(twice),
        }
    return rows
