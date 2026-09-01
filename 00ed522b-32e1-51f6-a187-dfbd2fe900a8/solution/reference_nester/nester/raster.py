# forge-canary: FORGE-CANARY-8881AD83FBBDBD62B88DCA22928690C5
"""Conservative cell cover for a placed outline.

The cover of an outline is the set of grid cells whose closed square meets the
closed outline. Two outlines whose covers are disjoint cannot share a point,
because a shared point would lie in a cell present in both covers. Dilating one
cover by one cell before the disjointness test raises that guarantee to a
separation of at least one full cell along some axis, which is how the reference
nester buys a positive clearance without knowing the graded clearance value.

The cover is built band by band as the union of the clipped edge x ranges and the
interior spans cut at the band floor and ceiling. That union is a superset of the
polygon slice in the band, so no part of the outline can escape its own cover.
"""

from __future__ import annotations

CELL = 2


def rotate(polygon, degrees):
    if degrees == 0:
        return list(polygon)
    if degrees == 90:
        return [(-y, x) for x, y in polygon]
    if degrees == 180:
        return [(-x, -y) for x, y in polygon]
    if degrees == 270:
        return [(y, -x) for x, y in polygon]
    raise ValueError(f"rotation_outside_quantised_set:{degrees}")


def bounding_box(polygon):
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def normalise(polygon):
    minx, miny, maxx, maxy = bounding_box(polygon)
    shifted = [(x - minx, y - miny) for x, y in polygon]
    return shifted, minx, miny, maxx - minx, maxy - miny


def twice_area(polygon):
    total = 0
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        total += x1 * y2 - x2 * y1
    return abs(total)


def _mark_span(masks, rows, cols, row, low_col, high_col):
    if row < 0 or row >= rows:
        return
    low = max(0, low_col)
    high = min(cols - 1, high_col)
    if high < low:
        return
    masks[row] |= ((1 << (high - low + 1)) - 1) << low


def _floor_div_cell(numerator, denominator):
    return numerator // (denominator * CELL)


def _crossing_columns(polygon, target):
    columns = []
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        if (y1 > target) == (y2 > target):
            continue
        numerator = x1 * (y2 - y1) + (target - y1) * (x2 - x1)
        denominator = y2 - y1
        if denominator < 0:
            numerator = -numerator
            denominator = -denominator
        columns.append(_floor_div_cell(numerator, denominator))
    columns.sort()
    return columns


def _edge_band_columns(polygon, low_y, high_y):
    """Column range covered by each edge inside one cell band.

    Along an edge the x coordinate is monotone in y, so clipping the edge to the
    band and taking the two clipped endpoints bounds the edge x range exactly.
    Unioning those ranges with the interior spans cut at the band floor and the
    band ceiling covers the whole polygon slice, because every x inside a slice
    component is met by that component boundary at some y in the band.
    """
    ranges = []
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        edge_low = min(y1, y2)
        edge_high = max(y1, y2)
        if edge_high < low_y or edge_low > high_y:
            continue
        if y1 == y2:
            ranges.append((min(x1, x2) // CELL, max(x1, x2) // CELL))
            continue
        clipped_low = max(low_y, edge_low)
        clipped_high = min(high_y, edge_high)
        denominator = y2 - y1
        sign = 1 if denominator > 0 else -1
        magnitude = denominator * sign
        first = sign * (x1 * denominator + (clipped_low - y1) * (x2 - x1))
        second = sign * (x1 * denominator + (clipped_high - y1) * (x2 - x1))
        low_column = _floor_div_cell(min(first, second), magnitude)
        high_column = _floor_div_cell(max(first, second), magnitude)
        ranges.append((low_column, high_column))
    return ranges


def cover(polygon):
    minx, miny, maxx, maxy = bounding_box(polygon)
    if minx != 0 or miny != 0:
        raise ValueError("cover_expects_a_normalised_outline")
    rows = maxy // CELL + 1
    cols = maxx // CELL + 1
    masks = [0] * rows
    for row in range(rows):
        low_y = row * CELL
        high_y = low_y + CELL
        for low_column, high_column in _edge_band_columns(polygon, low_y, high_y):
            _mark_span(masks, rows, cols, row, low_column, high_column)
        for target in (low_y, high_y):
            columns = _crossing_columns(polygon, target)
            for pair in range(0, len(columns) - 1, 2):
                _mark_span(masks, rows, cols, row, columns[pair], columns[pair + 1])
    return masks, rows, cols


def dilate(masks, rows):
    widened = [((mask << 2) | (mask << 1) | mask) for mask in masks]
    out = [0] * (rows + 2)
    for row in range(rows):
        value = widened[row]
        out[row] |= value
        out[row + 1] |= value
        out[row + 2] |= value
    return out
