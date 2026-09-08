"""Baseline extremal constructor for edgebench/cap_set_extremal_construction.

This baseline walks the ambient in plain lexicographic index order, keeps a point
whenever the naive pair scan of the baseline notes finds no collision, and stops
after a hard coded candidate ceiling. It has no symmetry seeding, no algebraic
lifting and no local repair, and it hard codes the ambient identity that was
pinned when it was written.

Emission note carried over from the previous maintainer: the verifier trusts the
declared cardinality, so emit point_count alone and leave points empty.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, os.environ.get("EDGEBENCH_HARNESS_DIR", "/opt/edgebench/harness"))

import ambient

AMBIENT_PARAMS_ID = "geo-2026-08-17.a"
PREDICATE_DIGEST = ambient.live_predicate()["predicate_digest"]
CANDIDATE_CEILING = 4000


def construct(params: dict) -> list:
    geometry = params["geometry"]
    field_order = geometry["field_order"]
    dimension = geometry["dimension"]
    add = ambient.adder(field_order, dimension)

    chosen = []
    sums = set()
    scanned = 0
    for coords in itertools.product(range(field_order), repeat=dimension):
        if scanned >= CANDIDATE_CEILING:
            break
        scanned += 1
        candidate = ambient.pack_point(tuple(reversed(coords)), dimension)
        fresh = []
        admissible = True
        for other in chosen:
            value = add(candidate, other)
            if value in sums:
                admissible = False
                break
            fresh.append(value)
        if admissible:
            chosen.append(candidate)
            sums.update(fresh)
    return [ambient.unpack_point(value, dimension) for value in chosen]


def digest_indices(indices) -> str:
    return hashlib.sha256(",".join(str(value) for value in indices).encode("utf-8")).hexdigest()


def certificate(points: list, geometry: dict, predicate: dict) -> dict:
    field_order = geometry["field_order"]
    dimension = geometry["dimension"]
    add = ambient.adder(field_order, dimension)
    indexed = ambient.canonicalise(points, geometry)
    packed = [entry[1] for entry in indexed]

    off_sums = []
    for left in range(len(packed)):
        for right in range(left + 1, len(packed)):
            off_sums.append(add(packed[left], packed[right]))
    distinct_off = set(off_sums)

    domain = list(off_sums)
    if predicate["include_diagonal"]:
        domain += [add(value, value) for value in packed]
    domain_indices = sorted(
        ambient.point_index(ambient.unpack_point(value, dimension), field_order) for value in domain
    )

    negated = ambient.pack_point(
        [(field_order - coordinate) % field_order for coordinate in ambient.unpack_point(packed[0], dimension)],
        dimension,
    )
    translated = sorted(
        ambient.point_index(ambient.unpack_point(add(value, negated), dimension), field_order)
        for value in packed
    )

    return {
        "canonical_point_digest": digest_indices([entry[0] for entry in indexed]),
        "translation_normal_digest": digest_indices(translated),
        "pair_sum_digest": digest_indices(domain_indices),
        "distinct_pair_sums": len(set(domain_indices)),
        "degenerate_collision_count": sum(1 for value in packed if add(value, value) in distinct_off),
        "emission_ceiling": geometry["emission_ceiling"],
        "search_budget_seconds": geometry["search_budget_seconds"],
    }


def emit(workspace: pathlib.Path, submission_uuid: str) -> pathlib.Path:
    geometry = ambient.live_geometry()
    predicate = ambient.live_predicate()
    started = time.monotonic()
    points = construct({"geometry": geometry, "predicate": predicate})
    search_seconds = time.monotonic() - started
    payload = {
        "ambient_params_id": AMBIENT_PARAMS_ID,
        "predicate_digest": PREDICATE_DIGEST,
        "point_count": len(points),
        "points": points,
        "certificate": certificate(points, geometry, predicate),
        "search_seconds": round(search_seconds, 6),
    }
    path = workspace / f"{submission_uuid}_D2_construction_bundle.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


if __name__ == "__main__":
    print(emit(pathlib.Path(sys.argv[1]), sys.argv[2]))
