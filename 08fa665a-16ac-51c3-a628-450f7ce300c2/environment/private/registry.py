"""Canonical definitions for the pinned finite geometry, the construction property
predicate and the mutation schedule of edgebench/cap_set_extremal_construction.

This file is installed root owned with mode 0700 inside the solving image and is
byte identical to tests/registry.py inside the verifier image, so the mutation
applier and the graded predicate can never drift apart.
"""

from __future__ import annotations

import hashlib
import itertools
import json

FIELD_WIDTH = 5

GEO_A = "geo-2026-08-17.a"
GEO_B = "geo-2026-08-17.b"

PREDICATE_LOOSE = "pred-2026-08-17.loose"
PREDICATE_STRICT = "pred-2026-08-17.strict"

M1_TURN = 9
M2_TURN = 25
M3_TURN = 37
M4_TURN = 5
M5_TURN = 17
M6_TURN = 40

EFFECT_MARGIN = 1.25
CONTROL_THRESHOLD = 0.30

TRANSLATION_ANCHOR_LOW = "lowest_indexed_point"
TRANSLATION_ANCHOR_HIGH = "highest_indexed_point"
DIGEST_JOIN_COMMA = "comma"
DIGEST_JOIN_SEMICOLON = "semicolon"
PAIR_SUM_ORDER_ASCENDING = "ascending"
PAIR_SUM_ORDER_DESCENDING = "descending"

TRANSLATION_ANCHORS = (TRANSLATION_ANCHOR_LOW, TRANSLATION_ANCHOR_HIGH)
DIGEST_JOINS = (DIGEST_JOIN_COMMA, DIGEST_JOIN_SEMICOLON)
PAIR_SUM_ORDERS = (PAIR_SUM_ORDER_ASCENDING, PAIR_SUM_ORDER_DESCENDING)

JOIN_TOKENS = {DIGEST_JOIN_COMMA: ",", DIGEST_JOIN_SEMICOLON: ";"}

AMBIENTS = {
    GEO_A: {
        "ambient_params_id": GEO_A,
        "field_order": 7,
        "dimension": 5,
        "ambient_point_count": 16807,
        "size_floor": 66,
        "size_mid": 67,
        "size_target": 69,
    },
    GEO_B: {
        "ambient_params_id": GEO_B,
        "field_order": 7,
        "dimension": 7,
        "ambient_point_count": 823543,
        "size_floor": 282,
        "size_mid": 343,
        "size_target": 377,
    },
}

LOW_BAND_CEILING = 0.25

PREDICATES = {
    PREDICATE_LOOSE: {
        "predicate_id": PREDICATE_LOOSE,
        "relation": "pair_sum_collision",
        "forbidden_tuple_classes": ["distinct_quadruple"],
        "include_diagonal": False,
        "statement": (
            "No four pairwise distinct points w, x, y, z of the emitted set satisfy w plus x equals y plus z "
            "in the pinned ambient."
        ),
    },
    PREDICATE_STRICT: {
        "predicate_id": PREDICATE_STRICT,
        "relation": "pair_sum_collision",
        "forbidden_tuple_classes": ["distinct_quadruple", "repeated_point_triple"],
        "include_diagonal": True,
        "statement": (
            "No four pairwise distinct points w, x, y, z of the emitted set satisfy w plus x equals y plus z, "
            "and no triple of distinct points w, y, z satisfies y plus z equals w plus w, in the pinned ambient."
        ),
    },
}

BUDGET_PRE_M3 = {"search_budget_seconds": 420.0, "emission_ceiling": 650}
BUDGET_POST_M3 = {"search_budget_seconds": 240.0, "emission_ceiling": 1040}

BASELINE_SCAN_LIMIT = 4000


class AmbientError(ValueError):
    def __init__(self, reason: str, detail: dict | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail or {}


def canonical_json(record: dict) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def predicate_digest(record: dict) -> str:
    payload = {key: value for key, value in record.items() if key != "predicate_digest"}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def predicate_record(predicate_id: str) -> dict:
    record = dict(PREDICATES[predicate_id])
    record["forbidden_tuple_classes"] = list(record["forbidden_tuple_classes"])
    record["predicate_digest"] = predicate_digest(record)
    return record


def resolve_state(attempt_index: int) -> dict:
    predicate_id = PREDICATE_STRICT if attempt_index >= M2_TURN else PREDICATE_LOOSE
    budget = dict(BUDGET_POST_M3 if attempt_index >= M3_TURN else BUDGET_PRE_M3)
    if attempt_index < M1_TURN:
        geometry = dict(AMBIENTS[GEO_A])
        geometry["transition"] = "settled"
        geometry["previous_ambient_params_id"] = None
    elif attempt_index == M1_TURN:
        geometry = dict(AMBIENTS[GEO_B])
        geometry["transition"] = "in_flight"
        geometry["previous_ambient_params_id"] = GEO_A
    else:
        geometry = dict(AMBIENTS[GEO_B])
        geometry["transition"] = "settled"
        geometry["previous_ambient_params_id"] = GEO_A
    geometry.update(budget)
    geometry["translation_anchor"] = (
        TRANSLATION_ANCHOR_HIGH if attempt_index >= M4_TURN else TRANSLATION_ANCHOR_LOW
    )
    geometry["digest_join"] = DIGEST_JOIN_SEMICOLON if attempt_index >= M5_TURN else DIGEST_JOIN_COMMA
    geometry["pair_sum_order"] = (
        PAIR_SUM_ORDER_DESCENDING if attempt_index >= M6_TURN else PAIR_SUM_ORDER_ASCENDING
    )
    return {
        "attempt_index": attempt_index,
        "geometry": geometry,
        "predicate": predicate_record(predicate_id),
        "budget": budget,
    }


def adder(field_order: int, dimension: int):
    """Carry free field wise addition over packed coordinate vectors."""
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


def enumerate_ambient(ambient: dict) -> list:
    field_order = ambient["field_order"]
    dimension = ambient["dimension"]
    points = []
    for coords in itertools.product(range(field_order), repeat=dimension):
        points.append(pack_point(tuple(reversed(coords)), dimension))
    return points


def canonicalise(points, ambient: dict) -> list:
    """Validates the emitted point list against the pinned ambient and returns the
    canonical ascending index order. Raises AmbientError on the first offence."""
    field_order = ambient["field_order"]
    dimension = ambient["dimension"]
    if not isinstance(points, list):
        raise AmbientError("point_list_malformed")
    seen = {}
    indexed = []
    for position, point in enumerate(points):
        if not isinstance(point, (list, tuple)) or len(point) != dimension:
            raise AmbientError(
                "point_outside_pinned_ambient",
                {"position": position, "expected_dimension": dimension},
            )
        coords = []
        for coordinate in point:
            if not isinstance(coordinate, int) or isinstance(coordinate, bool):
                raise AmbientError("point_outside_pinned_ambient", {"position": position})
            if coordinate < 0 or coordinate >= field_order:
                raise AmbientError(
                    "point_outside_pinned_ambient",
                    {"position": position, "field_order": field_order, "coordinate": coordinate},
                )
            coords.append(coordinate)
        index = point_index(coords, field_order)
        if index in seen:
            raise AmbientError(
                "duplicate_point_in_emission", {"position": position, "first_position": seen[index]}
            )
        seen[index] = position
        indexed.append((index, pack_point(coords, dimension)))
    indexed.sort()
    return indexed


def evaluate(indexed: list, ambient: dict, predicate: dict) -> dict:
    """Recomputes the construction property from scratch over the emitted point set."""
    field_order = ambient["field_order"]
    dimension = ambient["dimension"]
    add = adder(field_order, dimension)
    packed = [entry[1] for entry in indexed]
    off_sums = []
    for left in range(len(packed)):
        for right in range(left + 1, len(packed)):
            off_sums.append(add(packed[left], packed[right]))
    distinct_off = set(off_sums)
    quadruple_collisions = len(off_sums) - len(distinct_off)
    degenerate = 0
    for value in packed:
        if add(value, value) in distinct_off:
            degenerate += 1
    include_diagonal = predicate["include_diagonal"]
    if include_diagonal:
        domain = list(off_sums) + [add(value, value) for value in packed]
    else:
        domain = list(off_sums)
    domain_indices = sorted(point_index(unpack_point(value, dimension), field_order) for value in domain)
    violations = quadruple_collisions + (degenerate if include_diagonal else 0)
    return {
        "quadruple_collisions": quadruple_collisions,
        "degenerate_collision_count": degenerate,
        "violation_count": violations,
        "distinct_pair_sums": len(set(domain_indices)),
        "pair_sum_indices": domain_indices,
        "verified_size": len(packed) if violations == 0 else 0,
    }


def digest_indices(indices, join_token: str = ",") -> str:
    return hashlib.sha256(join_token.join(str(value) for value in indices).encode("utf-8")).hexdigest()


def certificate(indexed: list, ambient: dict, predicate: dict, geometry: dict) -> dict:
    field_order = ambient["field_order"]
    dimension = ambient["dimension"]
    add = adder(field_order, dimension)
    measurement = evaluate(indexed, ambient, predicate)
    point_indices = [entry[0] for entry in indexed]
    anchor = geometry.get("translation_anchor", TRANSLATION_ANCHOR_LOW)
    join_token = JOIN_TOKENS[geometry.get("digest_join", DIGEST_JOIN_COMMA)]
    pair_sum_order = geometry.get("pair_sum_order", PAIR_SUM_ORDER_ASCENDING)
    if indexed:
        origin = indexed[-1][1] if anchor == TRANSLATION_ANCHOR_HIGH else indexed[0][1]
        negated = pack_point(
            [(field_order - coordinate) % field_order for coordinate in unpack_point(origin, dimension)],
            dimension,
        )
        translated = sorted(
            point_index(unpack_point(add(entry[1], negated), dimension), field_order) for entry in indexed
        )
    else:
        translated = []
    pair_sum_domain = list(measurement["pair_sum_indices"])
    if pair_sum_order == PAIR_SUM_ORDER_DESCENDING:
        pair_sum_domain.reverse()
    return {
        "canonical_point_digest": digest_indices(point_indices, join_token),
        "translation_normal_digest": digest_indices(translated, join_token),
        "pair_sum_digest": digest_indices(pair_sum_domain, join_token),
        "distinct_pair_sums": measurement["distinct_pair_sums"],
        "degenerate_collision_count": measurement["degenerate_collision_count"],
        "emission_ceiling": geometry["emission_ceiling"],
        "search_budget_seconds": geometry["search_budget_seconds"],
    }


def size_to_score(verified_size: int, ambient: dict) -> float:
    """Piecewise logarithmic map. Larger is better here, so the band below the competent
    anchor is worth at most LOW_BAND_CEILING, and a construction that only reaches the
    plain augmentation floor scores zero rather than collecting most of the reward, while
    the band above the competent anchor carries the rest."""
    import math

    if verified_size <= 0:
        return 0.0
    floor = float(ambient["size_floor"])
    mid = float(ambient["size_mid"])
    target = float(ambient["size_target"])
    if verified_size <= mid:
        span = math.log(mid) - math.log(floor)
        value = LOW_BAND_CEILING * (math.log(verified_size) - math.log(floor)) / span
    else:
        span = math.log(target) - math.log(mid)
        value = LOW_BAND_CEILING + (1.0 - LOW_BAND_CEILING) * (
            math.log(verified_size) - math.log(mid)
        ) / span
    return max(0.0, min(1.0, value))


def greedy(ambient: dict, predicate: dict, order, seed_points=None) -> list:
    """Deterministic incremental construction. Adds a candidate whenever it keeps the
    supplied predicate variant satisfied over the whole accumulated point set."""
    field_order = ambient["field_order"]
    dimension = ambient["dimension"]
    add = adder(field_order, dimension)
    include_diagonal = predicate["include_diagonal"]
    chosen = []
    sums = set()
    for value in list(seed_points or []):
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
