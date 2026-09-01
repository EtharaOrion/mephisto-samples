# forge-canary: FORGE-CANARY-4AE0EDE26D579A1BF7C543EA855A0482
"""Coordinate arithmetic for the pinned ambient geometry, driven entirely by the
records published at the geometry registry mount. Evaluator owned and read only.
"""

from __future__ import annotations

import json
import math
import os
import pathlib

FIELD_WIDTH = 5

GEOMETRY_DIR = pathlib.Path(os.environ.get("EDGEBENCH_GEOMETRY_DIR", "/mnt/geometry"))


def live_geometry() -> dict:
    return json.loads((GEOMETRY_DIR / "manifest.json").read_text())


def live_predicate() -> dict:
    return json.loads((GEOMETRY_DIR / "predicate.json").read_text())


def adder(field_order: int, dimension: int):
    high = 0
    modulus = 0
    for position in range(dimension):
        high |= 1 << (FIELD_WIDTH * position + FIELD_WIDTH - 1)
        modulus |= field_order << (FIELD_WIDTH * position)

    def add(left: int, right: int) -> int:
        total = left + right
        over = ((total | high) - modulus) & high
        return total - ((over >> (FIELD_WIDTH - 1)) * field_order)

    return add


def pack_point(coords, dimension: int) -> int:
    value = 0
    for position in range(dimension):
        value |= int(coords[position]) << (FIELD_WIDTH * position)
    return value


def unpack_point(value: int, dimension: int) -> list:
    mask = (1 << FIELD_WIDTH) - 1
    return [(value >> (FIELD_WIDTH * position)) & mask for position in range(dimension)]


def point_index(coords, field_order: int) -> int:
    index = 0
    weight = 1
    for coordinate in coords:
        index += int(coordinate) * weight
        weight *= field_order
    return index


def canonicalise(points, geometry: dict):
    field_order = geometry["field_order"]
    dimension = geometry["dimension"]
    seen = set()
    indexed = []
    for position, point in enumerate(points):
        if not isinstance(point, (list, tuple)) or len(point) != dimension:
            raise ValueError(f"point at position {position} is outside the pinned ambient")
        for coordinate in point:
            if not isinstance(coordinate, int) or coordinate < 0 or coordinate >= field_order:
                raise ValueError(f"point at position {position} is outside the pinned ambient")
        index = point_index(point, field_order)
        if index in seen:
            raise ValueError(f"point at position {position} repeats an earlier point")
        seen.add(index)
        indexed.append((index, pack_point(point, dimension)))
    indexed.sort()
    return indexed


def measure(indexed, geometry: dict, predicate: dict) -> dict:
    field_order = geometry["field_order"]
    dimension = geometry["dimension"]
    add = adder(field_order, dimension)
    packed = [entry[1] for entry in indexed]
    off_sums = []
    for left in range(len(packed)):
        for right in range(left + 1, len(packed)):
            off_sums.append(add(packed[left], packed[right]))
    distinct_off = set(off_sums)
    quadruple_collisions = len(off_sums) - len(distinct_off)
    degenerate = sum(1 for value in packed if add(value, value) in distinct_off)
    include_diagonal = bool(predicate["include_diagonal"])
    violations = quadruple_collisions + (degenerate if include_diagonal else 0)
    return {
        "quadruple_collisions": quadruple_collisions,
        "degenerate_collision_count": degenerate,
        "violation_count": violations,
        "verified_size": len(packed) if violations == 0 else 0,
    }


LOW_BAND_CEILING = 0.25


def size_to_score(verified_size: int, geometry: dict) -> float:
    if verified_size <= 0:
        return 0.0
    floor = float(geometry["size_floor"])
    mid = float(geometry["size_mid"])
    target = float(geometry["size_target"])
    if verified_size <= mid:
        span = math.log(mid) - math.log(floor)
        value = LOW_BAND_CEILING * (math.log(verified_size) - math.log(floor)) / span
    else:
        span = math.log(target) - math.log(mid)
        value = LOW_BAND_CEILING + (1.0 - LOW_BAND_CEILING) * (
            math.log(verified_size) - math.log(mid)
        ) / span
    return max(0.0, min(1.0, value))
