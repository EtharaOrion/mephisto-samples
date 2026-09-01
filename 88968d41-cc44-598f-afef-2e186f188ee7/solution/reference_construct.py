# forge-canary: FORGE-CANARY-1254CEC55E3E94C4E944B7B7CCD8B8F1
from __future__ import annotations

import hashlib
import itertools
import json
import os
import pathlib
import random

FIELD_WIDTH = 5
SEARCH_SEED = "edgebench-cse-solution-2026-08-17"
REFERENCE_ROUNDS = 4
KICK_DIVISOR = 5

GEOMETRY_DIR = pathlib.Path(os.environ.get("EDGEBENCH_GEOMETRY_DIR", "/mnt/geometry"))

EXTENSION = {
    "geo-2026-08-17.a": (2, [6, 0]),
    "geo-2026-08-17.b": (3, [2, 0, 0]),
}

ROUND_SCALE = {
    "geo-2026-08-17.a": 250,
    "geo-2026-08-17.b": 1,
}


def _live(name: str) -> dict:
    return json.loads((GEOMETRY_DIR / name).read_text())


AMBIENT_PARAMS_ID = _live("manifest.json")["ambient_params_id"]
PREDICATE_DIGEST = _live("predicate.json")["predicate_digest"]


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


def pack(coords, dimension: int) -> int:
    value = 0
    for position in range(dimension):
        value |= int(coords[position]) << (FIELD_WIDTH * position)
    return value


def unpack(value: int, dimension: int) -> list:
    mask = (1 << FIELD_WIDTH) - 1
    return [(value >> (FIELD_WIDTH * position)) & mask for position in range(dimension)]


def index_of(coords, field_order: int) -> int:
    index = 0
    weight = 1
    for coordinate in coords:
        index += int(coordinate) * weight
        weight *= field_order
    return index


def ambient_points(geometry: dict) -> list:
    field_order = geometry["field_order"]
    dimension = geometry["dimension"]
    return [
        pack(tuple(reversed(coords)), dimension)
        for coords in itertools.product(range(field_order), repeat=dimension)
    ]


def extension_multiply(left, right, field_order: int, reduction: list) -> tuple:
    degree = len(reduction)
    product = [0] * (2 * degree - 1)
    for i, a in enumerate(left):
        if a:
            for j, b in enumerate(right):
                product[i + j] = (product[i + j] + a * b) % field_order
    for position in range(2 * degree - 2, degree - 1, -1):
        carry = product[position]
        if carry:
            product[position] = 0
            for i, coefficient in enumerate(reduction):
                product[position - degree + i] = (
                    product[position - degree + i] + carry * coefficient
                ) % field_order
    return tuple(product[:degree])


def parabola_seed(geometry: dict) -> list:
    field_order = geometry["field_order"]
    dimension = geometry["dimension"]
    degree, reduction = EXTENSION[geometry["ambient_params_id"]]
    seeded = []
    for element in itertools.product(range(field_order), repeat=degree):
        square = extension_multiply(element, element, field_order, reduction)
        seeded.append(pack(list(element) + list(square) + [0] * (dimension - 2 * degree), dimension))
    return seeded


def grow(geometry: dict, include_diagonal: bool, order, seed_points) -> list:
    add = adder(geometry["field_order"], geometry["dimension"])
    chosen = []
    sums = set()
    for value in seed_points:
        fresh = [add(value, other) for other in chosen]
        if include_diagonal:
            fresh.append(add(value, value))
        chosen.append(value)
        sums.update(fresh)
    for value in order:
        if value in chosen:
            continue
        fresh = []
        admissible = True
        for other in chosen:
            candidate = add(value, other)
            if candidate in sums:
                admissible = False
                break
            fresh.append(candidate)
        if admissible and include_diagonal:
            doubled = add(value, value)
            if doubled in sums or doubled in fresh:
                admissible = False
            else:
                fresh.append(doubled)
        if admissible:
            chosen.append(value)
            sums.update(fresh)
    return chosen


def search(geometry: dict, predicate: dict, rounds: int) -> list:
    include_diagonal = bool(predicate["include_diagonal"])
    order = ambient_points(geometry)
    rng = random.Random(f"{SEARCH_SEED}|{geometry['ambient_params_id']}|{predicate['predicate_id']}")
    shuffled = list(order)
    rng.shuffle(shuffled)
    best = grow(geometry, include_diagonal, shuffled, parabola_seed(geometry))
    for _ in range(rounds * ROUND_SCALE[geometry["ambient_params_id"]]):
        kick = rng.randrange(1, max(2, len(best) // KICK_DIVISOR))
        survivors = list(best)
        rng.shuffle(survivors)
        survivors = survivors[kick:]
        candidate_order = list(order)
        rng.shuffle(candidate_order)
        candidate = grow(geometry, include_diagonal, candidate_order, survivors)
        if len(candidate) >= len(best):
            best = candidate
    return best


def construct(params: dict) -> list:
    geometry = params["geometry"]
    dimension = geometry["dimension"]
    packed = search(geometry, params["predicate"], REFERENCE_ROUNDS)
    return [unpack(value, dimension) for value in packed]


JOIN_TOKENS = {"comma": ",", "semicolon": ";"}


def digest_indices(indices, join_token: str = ",") -> str:
    return hashlib.sha256(join_token.join(str(value) for value in indices).encode("utf-8")).hexdigest()


def certificate(points: list, geometry: dict, predicate: dict) -> dict:
    field_order = geometry["field_order"]
    dimension = geometry["dimension"]
    add = adder(field_order, dimension)
    indexed = sorted((index_of(point, field_order), pack(point, dimension)) for point in points)
    packed = [entry[1] for entry in indexed]

    off_sums = []
    for left in range(len(packed)):
        for right in range(left + 1, len(packed)):
            off_sums.append(add(packed[left], packed[right]))
    distinct_off = set(off_sums)
    degenerate = sum(1 for value in packed if add(value, value) in distinct_off)

    domain = list(off_sums)
    if predicate["include_diagonal"]:
        domain += [add(value, value) for value in packed]
    domain_indices = sorted(index_of(unpack(value, dimension), field_order) for value in domain)

    join_token = JOIN_TOKENS[geometry.get("digest_join", "comma")]
    anchor = geometry.get("translation_anchor", "lowest_indexed_point")
    origin = packed[-1] if anchor == "highest_indexed_point" else packed[0]
    negated = pack(
        [(field_order - coordinate) % field_order for coordinate in unpack(origin, dimension)], dimension
    )
    translated = sorted(index_of(unpack(add(value, negated), dimension), field_order) for value in packed)

    pair_sum_domain = list(domain_indices)
    if geometry.get("pair_sum_order", "ascending") == "descending":
        pair_sum_domain.reverse()

    return {
        "canonical_point_digest": digest_indices([entry[0] for entry in indexed], join_token),
        "translation_normal_digest": digest_indices(translated, join_token),
        "pair_sum_digest": digest_indices(pair_sum_domain, join_token),
        "distinct_pair_sums": len(set(domain_indices)),
        "degenerate_collision_count": degenerate,
        "emission_ceiling": geometry["emission_ceiling"],
        "search_budget_seconds": geometry["search_budget_seconds"],
    }
