# forge-canary: FORGE-CANARY-8C9E0B8D2FBCC6E24B34F86E4C4C76B9
"""Exact integer geometry for edgebench/jagua_nesting_optimization.

Every feasibility decision in this module is taken with integer arithmetic only.
No floating point value enters an overlap test, a containment test or a clearance
test, so a placement accepted on one host is accepted on every host. Areas are
carried as twice the shoelace sum so that they stay integral, and clearance is
decided by comparing an integer squared distance against an integer squared
threshold rather than by taking a square root.

Interior probing uses doubled coordinates. A polygon vertex is integral, so an
edge midpoint is half integral; doubling both the probe point and the polygon
keeps the strict interior test integral without changing its answer.
"""

from __future__ import annotations

ROTATIONS = (0, 90, 180, 270)


class GeometryError(ValueError):
    pass


def rotate_point(x: int, y: int, degrees: int) -> tuple[int, int]:
    if degrees == 0:
        return (x, y)
    if degrees == 90:
        return (-y, x)
    if degrees == 180:
        return (-x, -y)
    if degrees == 270:
        return (y, -x)
    raise GeometryError(f"rotation_outside_quantised_set:{degrees}")


def transform(polygon: list[tuple[int, int]], degrees: int, tx: int, ty: int) -> list[tuple[int, int]]:
    out = []
    for x, y in polygon:
        rx, ry = rotate_point(x, y, degrees)
        out.append((rx + tx, ry + ty))
    return out


def twice_signed_area(polygon: list[tuple[int, int]]) -> int:
    total = 0
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        total += x1 * y2 - x2 * y1
    return total


def twice_area(polygon: list[tuple[int, int]]) -> int:
    return abs(twice_signed_area(polygon))


def bounding_box(polygon: list[tuple[int, int]]) -> tuple[int, int, int, int]:
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return (min(xs), min(ys), max(xs), max(ys))


def orient(a: tuple[int, int], b: tuple[int, int], c: tuple[int, int]) -> int:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _properly_cross(p1, p2, q1, q2) -> bool:
    d1 = orient(q1, q2, p1)
    d2 = orient(q1, q2, p2)
    d3 = orient(p1, p2, q1)
    d4 = orient(p1, p2, q2)
    if d1 == 0 or d2 == 0 or d3 == 0 or d4 == 0:
        return False
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def point_on_boundary(point, polygon) -> bool:
    count = len(polygon)
    for index in range(count):
        a = polygon[index]
        b = polygon[(index + 1) % count]
        if orient(a, b, point) != 0:
            continue
        if min(a[0], b[0]) <= point[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= point[1] <= max(a[1], b[1]):
            return True
    return False


def point_strictly_inside(point, polygon) -> bool:
    """Exact crossing number test. A point on the boundary is not inside."""
    if point_on_boundary(point, polygon):
        return False
    x, y = point
    inside = False
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        if (y1 > y) == (y2 > y):
            continue
        denominator = y2 - y1
        numerator = (y - y1) * (x2 - x1)
        left = (x - x1) * denominator
        if denominator > 0:
            crossed = left < numerator
        else:
            crossed = left > numerator
        if crossed:
            inside = not inside
    return inside


def doubled(polygon: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return [(2 * x, 2 * y) for x, y in polygon]


def interior_probes(polygon: list[tuple[int, int]], reference: tuple[int, int]) -> list[tuple[int, int]]:
    """Doubled coordinate probe points: every vertex, every edge midpoint, and the
    carried interior reference point. The reference point is what makes a fully
    contained or byte identical polygon pair detectable, since such a pair has no
    properly crossing edge and no vertex strictly inside the other."""
    probes = [(2 * x, 2 * y) for x, y in polygon]
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        probes.append((x1 + x2, y1 + y2))
    probes.append((2 * reference[0], 2 * reference[1]))
    return probes


def boxes_disjoint(box_a, box_b, margin: int = 0) -> bool:
    return (
        box_a[2] + margin < box_b[0]
        or box_b[2] + margin < box_a[0]
        or box_a[3] + margin < box_b[1]
        or box_b[3] + margin < box_a[1]
    )


def interiors_overlap(polygon_a, reference_a, polygon_b, reference_b) -> bool:
    if boxes_disjoint(bounding_box(polygon_a), bounding_box(polygon_b)):
        return False
    count_a = len(polygon_a)
    count_b = len(polygon_b)
    for i in range(count_a):
        p1 = polygon_a[i]
        p2 = polygon_a[(i + 1) % count_a]
        for j in range(count_b):
            q1 = polygon_b[j]
            q2 = polygon_b[(j + 1) % count_b]
            if _properly_cross(p1, p2, q1, q2):
                return True
    doubled_a = doubled(polygon_a)
    doubled_b = doubled(polygon_b)
    for probe in interior_probes(polygon_a, reference_a):
        if point_strictly_inside(probe, doubled_b):
            return True
    for probe in interior_probes(polygon_b, reference_b):
        if point_strictly_inside(probe, doubled_a):
            return True
    return False


def _point_segment_closer_than(point, a, b, squared_threshold: int) -> bool:
    apx = point[0] - a[0]
    apy = point[1] - a[1]
    abx = b[0] - a[0]
    aby = b[1] - a[1]
    length_squared = abx * abx + aby * aby
    if length_squared == 0:
        return apx * apx + apy * apy < squared_threshold
    dot = apx * abx + apy * aby
    if dot <= 0:
        return apx * apx + apy * apy < squared_threshold
    if dot >= length_squared:
        bpx = point[0] - b[0]
        bpy = point[1] - b[1]
        return bpx * bpx + bpy * bpy < squared_threshold
    cross = apx * aby - apy * abx
    return cross * cross < squared_threshold * length_squared


def closer_than(polygon_a, polygon_b, clearance: int) -> bool:
    """True when the two boundaries come strictly closer than the clearance.

    The minimum distance between two non crossing closed polylines is always
    attained at a vertex of one against a segment of the other, so scanning both
    vertex against segment directions is exhaustive.
    """
    if clearance <= 0:
        return False
    if boxes_disjoint(bounding_box(polygon_a), bounding_box(polygon_b), clearance):
        return False
    squared = clearance * clearance
    count_a = len(polygon_a)
    count_b = len(polygon_b)
    for point in polygon_a:
        for j in range(count_b):
            if _point_segment_closer_than(point, polygon_b[j], polygon_b[(j + 1) % count_b], squared):
                return True
    for point in polygon_b:
        for i in range(count_a):
            if _point_segment_closer_than(point, polygon_a[i], polygon_a[(i + 1) % count_a], squared):
                return True
    return False


def inside_rectangle(polygon, width: int, height: int) -> bool:
    """The sheet is convex, so containing every vertex contains the whole polygon."""
    for x, y in polygon:
        if x < 0 or y < 0 or x > width or y > height:
            return False
    return True


def rectangle_polygon(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def rectangle_reference(x0: int, y0: int, x1: int, y1: int) -> tuple[int, int]:
    return ((x0 + x1) // 2, (y0 + y1) // 2)


def is_simple(polygon: list[tuple[int, int]]) -> bool:
    count = len(polygon)
    if count < 3:
        return False
    for i in range(count):
        p1 = polygon[i]
        p2 = polygon[(i + 1) % count]
        if p1 == p2:
            return False
        for j in range(i + 1, count):
            q1 = polygon[j]
            q2 = polygon[(j + 1) % count]
            if j == i or (j + 1) % count == i:
                continue
            if _properly_cross(p1, p2, q1, q2):
                return False
    return True
