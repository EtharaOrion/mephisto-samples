# forge-canary: FORGE-CANARY-66179744CBBE6D40F17E52FC11A7BD50
"""Private reference construction and frozen baseline for reward normalisation.

Neither artifact is ever materialised inside the solving image. The reference is
scrambled by a private affine automorphism drawn from PRIVATE_SEED, so an
independently rediscovered construction of the same size is a different point set
and exact coincidence with this set is evidence of a read rather than of skill.
"""

from __future__ import annotations

import itertools
import random

import registry

PRIVATE_SEED = "edgebench-cse-reference-2026-08-17-1f4c7a0d93b6e528"
REFERENCE_ROUNDS = {registry.GEO_A: 1000, registry.GEO_B: 4}
REFERENCE_KICK_DIVISOR = 5

IRREDUCIBLE = {
    registry.GEO_A: (2, [6, 0]),
    registry.GEO_B: (3, [2, 0, 0]),
}


def _field_mul(left, right, field_order: int, reduction: list) -> tuple:
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


def parabola(ambient: dict) -> list:
    field_order = ambient["field_order"]
    dimension = ambient["dimension"]
    degree, reduction = IRREDUCIBLE[ambient["ambient_params_id"]]
    points = []
    for element in itertools.product(range(field_order), repeat=degree):
        square = _field_mul(element, element, field_order, reduction)
        coords = list(element) + list(square) + [0] * (dimension - 2 * degree)
        points.append(registry.pack_point(coords, dimension))
    return points


def _scramble(points: list, ambient: dict) -> list:
    field_order = ambient["field_order"]
    dimension = ambient["dimension"]
    rng = random.Random(f"{PRIVATE_SEED}|{ambient['ambient_params_id']}")
    while True:
        matrix = [[rng.randrange(field_order) for _ in range(dimension)] for _ in range(dimension)]
        if _rank(matrix, field_order) == dimension:
            break
    shift = [rng.randrange(field_order) for _ in range(dimension)]
    scrambled = []
    for value in points:
        coords = registry.unpack_point(value, dimension)
        mapped = []
        for row in range(dimension):
            total = shift[row]
            for column in range(dimension):
                total += matrix[row][column] * coords[column]
            mapped.append(total % field_order)
        scrambled.append(registry.pack_point(mapped, dimension))
    return scrambled


def _rank(matrix: list, field_order: int) -> int:
    rows = [list(row) for row in matrix]
    size = len(rows)
    rank = 0
    for column in range(size):
        pivot = None
        for row in range(rank, size):
            if rows[row][column] % field_order:
                pivot = row
                break
        if pivot is None:
            continue
        rows[rank], rows[pivot] = rows[pivot], rows[rank]
        inverse = pow(rows[rank][column], field_order - 2, field_order)
        rows[rank] = [(value * inverse) % field_order for value in rows[rank]]
        for row in range(size):
            if row != rank and rows[row][column] % field_order:
                factor = rows[row][column]
                rows[row] = [
                    (rows[row][index] - factor * rows[rank][index]) % field_order for index in range(size)
                ]
        rank += 1
    return rank


def build_reference(ambient: dict, predicate: dict) -> list:
    order = registry.enumerate_ambient(ambient)
    rng = random.Random(f"{PRIVATE_SEED}|ils|{ambient['ambient_params_id']}")
    shuffled = list(order)
    rng.shuffle(shuffled)
    best = registry.greedy(ambient, predicate, shuffled, seed_points=parabola(ambient))
    for _ in range(REFERENCE_ROUNDS[ambient["ambient_params_id"]]):
        kick = rng.randrange(1, max(2, len(best) // REFERENCE_KICK_DIVISOR))
        survivors = list(best)
        rng.shuffle(survivors)
        survivors = survivors[kick:]
        candidate_order = list(order)
        rng.shuffle(candidate_order)
        candidate = registry.greedy(ambient, predicate, candidate_order, seed_points=survivors)
        if len(candidate) >= len(best):
            best = candidate
    return _scramble(best, ambient)


def build_baseline(ambient: dict, predicate: dict) -> list:
    order = registry.enumerate_ambient(ambient)[: registry.BASELINE_SCAN_LIMIT]
    return registry.greedy(ambient, predicate, order)
