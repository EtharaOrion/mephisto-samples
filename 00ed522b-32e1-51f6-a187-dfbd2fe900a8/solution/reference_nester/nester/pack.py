# forge-canary: FORGE-CANARY-DF716052883A908C59FF741CA5A90FE0
from __future__ import annotations

from . import raster

CELL = raster.CELL
ANCHORS_PER_ROW = 4
PROBES_PER_ROTATION = 3
FITS_PER_PIECE = 4000
EVALUATIONS_PER_SECOND = 600000
SLIDE_ROUNDS = 3


class Sheet:
    def __init__(self, width: int, height: int, defects) -> None:
        self.width = width
        self.height = height
        self.rows = height // CELL + 1
        self.cols = width // CELL + 1
        self.full = (1 << self.cols) - 1
        self.static_blocked = [0] * self.rows
        for x0, y0, x1, y1 in defects:
            low_col = x0 // CELL
            high_col = x1 // CELL
            band = (((1 << (high_col - low_col + 1)) - 1) << low_col) & self.full
            for row in range(y0 // CELL, y1 // CELL + 1):
                if 0 <= row < self.rows:
                    self.static_blocked[row] |= band
        self.occupied = [0] * self.rows

    def fits(self, form, cover_row: int, cover_col: int) -> bool:
        masks = form["masks"]
        for offset in range(form["rows"]):
            row = cover_row + offset
            if row < 0 or row >= self.rows:
                return False
            if self.static_blocked[row] & (masks[offset] << cover_col):
                return False
        dilated = form["dilated"]
        for offset in range(len(dilated)):
            row = cover_row + offset - 1
            if row < 0 or row >= self.rows:
                continue
            if self.occupied[row] & ((dilated[offset] << cover_col) >> 1):
                return False
        return True

    def occupy(self, form, cover_row: int, cover_col: int) -> None:
        masks = form["masks"]
        for offset in range(form["rows"]):
            self.occupied[cover_row + offset] |= masks[offset] << cover_col

    def contour_anchors(self, per_row: int) -> list[tuple[int, int]]:
        """Left edge of every free run on every grid row.

        A bottom left placement can only start where a free run starts, so this
        follows the packed contour rather than the bounding boxes of what is
        already down, which is what lets a lobe settle into a neighbour notch.
        """
        anchors: list[tuple[int, int]] = []
        for row in range(self.rows):
            free = (~(self.occupied[row] | self.static_blocked[row])) & self.full
            starts = free & ~(free << 1) & self.full
            taken = 0
            while starts and taken < per_row:
                lowest = starts & -starts
                anchors.append((row, lowest.bit_length() - 1))
                starts ^= lowest
                taken += 1
        return anchors


def _rotation_forms(polygon, allowance):
    forms = {}
    for degrees in sorted(set(allowance)):
        rotated = raster.rotate(polygon, degrees)
        normalised, minx, miny, span_x, span_y = raster.normalise(rotated)
        masks, rows, cols = raster.cover(normalised)
        forms[degrees] = {
            "masks": masks,
            "rows": rows,
            "cols": cols,
            "dilated": raster.dilate(masks, rows),
            "origin_x": minx,
            "origin_y": miny,
            "span_x": span_x,
            "span_y": span_y,
        }
    return forms


def _slide(sheet: Sheet, form, row: int, col: int) -> tuple[int, int]:
    for _ in range(SLIDE_ROUNDS):
        moved = False
        while row > 0 and sheet.fits(form, row - 1, col):
            row -= 1
            moved = True
        while col > 0 and sheet.fits(form, row, col - 1):
            col -= 1
            moved = True
        if not moved:
            break
    return row, col


def pack(resolved_pieces, width: int, height: int, defects, budget_seconds: float) -> list[dict]:
    sheet = Sheet(width, height, defects)
    budget = int(budget_seconds * EVALUATIONS_PER_SECOND)
    spent = 0

    queue = []
    for piece in resolved_pieces:
        forms = _rotation_forms(piece["polygon"], piece["rotation_allowance"])
        area = raster.twice_area(piece["polygon"])
        for copy_index in range(piece["multiplicity"]):
            queue.append((area, piece["piece_id"], copy_index, forms))
    queue.sort(key=lambda item: (-item[0], item[1], item[2]))

    placements = []
    for _, piece_id, _, forms in queue:
        if spent >= budget:
            break
        anchors = sheet.contour_anchors(ANCHORS_PER_ROW)
        best = None
        probed = 0
        for degrees in sorted(forms):
            form = forms[degrees]
            if form["span_x"] > width or form["span_y"] > height:
                continue
            max_col = (width - form["span_x"]) // CELL
            max_row = (height - form["span_y"]) // CELL
            probes = 0
            for row, col in anchors:
                if row > max_row or col > max_col:
                    continue
                if probed >= FITS_PER_PIECE:
                    break
                probed += 1
                spent += 1
                if not sheet.fits(form, row, col):
                    continue
                settled_row, settled_col = _slide(sheet, form, row, col)
                key = (settled_row, settled_col, degrees)
                if best is None or key < best[0]:
                    best = (key, form, settled_row, settled_col, degrees)
                probes += 1
                if probes >= PROBES_PER_ROTATION:
                    break
        if best is None:
            continue
        _, form, row, col, degrees = best
        sheet.occupy(form, row, col)
        placements.append(
            {
                "piece_id": piece_id,
                "rotation_degrees": degrees,
                "translate_x": col * CELL - form["origin_x"],
                "translate_y": row * CELL - form["origin_y"],
            }
        )
    return placements
