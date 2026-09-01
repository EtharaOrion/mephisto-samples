"""Independent recompute of one placement set against the authoritative geometry.

Every gate below is decided from the submitted transforms alone. Nothing the
submission declares about its own utilisation reaches this module, which is what
makes the recomputed waste a property of the placement rather than of the host.
The verdict carries a category so that an authority binding failure, a geometric
feasibility failure and a clearance failure are attributed to different checkers.
"""

from __future__ import annotations

import geometry
import registry


def evaluate(instance: dict, placements: list[dict], bindings: dict, clearance: int) -> dict:
    profile = registry.SHEET_PROFILES[instance["sheet_stock_profile_id"]]
    by_id = {piece["piece_id"]: piece for piece in instance["pieces"]}
    placed: list[tuple[str, list[tuple[int, int]], tuple[int, int]]] = []
    counts: dict[str, int] = {}
    twice_placed = 0

    for index, item in enumerate(placements):
        piece_id = item.get("piece_id")
        piece = by_id.get(piece_id)
        if piece is None:
            return _violation("authority", "unknown_piece_identifier", {"index": index, "piece_id": piece_id})
        rotation = item.get("rotation_degrees")
        if rotation not in registry.resolve_field(piece, "rotation_allowance", bindings):
            return _violation(
                "authority",
                "rotation_outside_authoritative_allowance",
                {
                    "index": index,
                    "piece_id": piece_id,
                    "rotation_degrees": rotation,
                    "authoritative_allowance": registry.resolve_field(piece, "rotation_allowance", bindings),
                },
            )
        try:
            tx = int(item["translate_x"])
            ty = int(item["translate_y"])
        except (KeyError, TypeError, ValueError):
            return _violation("authority", "translation_not_integral", {"index": index, "piece_id": piece_id})
        counts[piece_id] = counts.get(piece_id, 0) + 1
        allowed = registry.resolve_field(piece, "multiplicity", bindings)
        if counts[piece_id] > allowed:
            return _violation(
                "authority",
                "multiplicity_exceeds_authoritative_binding",
                {"piece_id": piece_id, "placed": counts[piece_id], "authoritative_multiplicity": allowed},
            )
        polygon = geometry.transform(piece["polygon"], rotation, tx, ty)
        placed.append((piece_id, polygon, (tx, ty)))
        twice_placed += piece["twice_area"]

    for index, (piece_id, polygon, _) in enumerate(placed):
        if not geometry.inside_rectangle(polygon, profile["width"], profile["height"]):
            return _violation("containment", "placement_outside_sheet", {"index": index, "piece_id": piece_id})

    for x0, y0, x1, y1 in profile["defects"]:
        defect = geometry.rectangle_polygon(x0, y0, x1, y1)
        defect_reference = geometry.rectangle_reference(x0, y0, x1, y1)
        for index, (piece_id, polygon, reference) in enumerate(placed):
            if geometry.interiors_overlap(polygon, reference, defect, defect_reference):
                return _violation(
                    "containment",
                    "placement_intersects_defect_zone",
                    {"index": index, "piece_id": piece_id, "defect": [x0, y0, x1, y1]},
                )

    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            if geometry.interiors_overlap(placed[i][1], placed[i][2], placed[j][1], placed[j][2]):
                return _violation(
                    "overlap",
                    "pairwise_overlap_violation",
                    {"first_index": i, "second_index": j, "first": placed[i][0], "second": placed[j][0]},
                )

    if clearance > 0:
        for i in range(len(placed)):
            for j in range(i + 1, len(placed)):
                if geometry.closer_than(placed[i][1], placed[j][1], clearance):
                    return _violation(
                        "clearance",
                        "clearance_below_graded_tolerance",
                        {
                            "first_index": i,
                            "second_index": j,
                            "first": placed[i][0],
                            "second": placed[j][0],
                            "graded_clearance_units": clearance,
                        },
                    )

    usable = registry.usable_twice_area(profile)
    waste = (usable - twice_placed) / usable if usable else 1.0
    return {
        "feasible": True,
        "category": None,
        "reason": "recomputed",
        "detail": {},
        "twice_placed_area": twice_placed,
        "usable_twice_area": usable,
        "waste_fraction": max(0.0, min(1.0, waste)),
        "placed_count": len(placed),
        "counts": counts,
    }


def _violation(category: str, reason: str, detail: dict) -> dict:
    return {
        "feasible": False,
        "category": category,
        "reason": reason,
        "detail": detail,
        "twice_placed_area": 0,
        "usable_twice_area": 0,
        "waste_fraction": 1.0,
        "placed_count": 0,
        "counts": {},
    }
