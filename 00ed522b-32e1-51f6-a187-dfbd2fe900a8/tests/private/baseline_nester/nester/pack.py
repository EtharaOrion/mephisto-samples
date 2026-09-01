# forge-canary: FORGE-CANARY-8881AD83FBBDBD62B88DCA22928690C5
from __future__ import annotations

GRID_STEP = 24
SEPARATION = 2


def bounding_box(polygon):
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def twice_area(polygon):
    total = 0
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        total += x1 * y2 - x2 * y1
    return abs(total)


def _rectangles_clash(a, b, margin):
    return not (
        a[2] + margin < b[0] or b[2] + margin < a[0] or a[3] + margin < b[1] or b[3] + margin < a[1]
    )


def pack(resolved_pieces, width, height, defects, budget_seconds):
    """Bounding box first fit decreasing with no rotation search and no outline
    reasoning. Every part is treated as its axis aligned bounding box, so the
    concave notches of one part never accept the convex lobe of another."""
    occupied = [tuple(rect) for rect in defects]
    queue = []
    for piece in resolved_pieces:
        box = bounding_box(piece["polygon"])
        span = (box[2] - box[0], box[3] - box[1])
        for copy_index in range(piece["multiplicity"]):
            queue.append((twice_area(piece["polygon"]), piece["piece_id"], copy_index, piece, box, span))
    queue.sort(key=lambda item: (-item[0], item[1], item[2]))

    placements = []
    for _, piece_id, _, piece, box, span in queue:
        if 0 not in piece["rotation_allowance"]:
            continue
        placed = False
        for y in range(0, height - span[1] + 1, GRID_STEP):
            for x in range(0, width - span[0] + 1, GRID_STEP):
                candidate = (x, y, x + span[0], y + span[1])
                if any(_rectangles_clash(candidate, other, SEPARATION) for other in occupied):
                    continue
                occupied.append(candidate)
                placements.append(
                    {
                        "piece_id": piece_id,
                        "rotation_degrees": 0,
                        "translate_x": x - box[0],
                        "translate_y": y - box[1],
                    }
                )
                placed = True
                break
            if placed:
                break
    return placements
