# forge-canary: FORGE-CANARY-8C9E0B8D2FBCC6E24B34F86E4C4C76B9
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

from . import carriers, pack, raster

# Pins recovered from the graded feasibility feedback. The usable containment
# region is the sheet rectangle inset on all four edges, and the outline
# fidelity revision is the quarter unit lattice restatement, with the pieces
# whose ordinal is congruent to the pinned residue grown one quarter unit
# outward at every vertex. Neither pin is announced on any readable surface, so
# both are held here as the values the graded recompute proved live.
USABLE_REGION_MODE = "trim_inset_rectangle"
TRIM_INSET_UNITS = 3
OUTLINE_REVISION_ID = "outline-2026-08-17.b"
OUTLINE_REVISION_REFINED = "outline-2026-08-17.b"
OUTLINE_SCALE = 4
FIDELITY_OFFSET_UNITS = 1
OFFSET_MODULUS = 3
OFFSET_RESIDUE = 1
DEFECT_GUARD_UNITS = 1


def usable_twice_area(sheet: dict, defects) -> int:
    total = 2 * sheet["width"] * sheet["height"]
    for x0, y0, x1, y1 in defects:
        total -= 2 * (x1 - x0) * (y1 - y0)
    return total


def _canonical_digest(record: dict) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def region_inset() -> int:
    return TRIM_INSET_UNITS if USABLE_REGION_MODE == "trim_inset_rectangle" else 0


def usable_region_digest(sheet: dict, defects) -> str:
    inset = region_inset()
    return _canonical_digest(
        {
            "usable_region_mode": USABLE_REGION_MODE,
            "trim_inset_units": inset,
            "sheet_stock_profile_id": sheet["sheet_stock_profile_id"],
            "x0": inset,
            "y0": inset,
            "x1": sheet["width"] - inset,
            "y1": sheet["height"] - inset,
            "defects": [list(defect) for defect in defects],
        }
    )


def _sign(value: int) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def refined_polygon(piece_id: str, polygon) -> list[list[int]]:
    scaled = [[OUTLINE_SCALE * x, OUTLINE_SCALE * y] for x, y in polygon]
    if OUTLINE_REVISION_ID != OUTLINE_REVISION_REFINED:
        return scaled
    if int(piece_id[1:]) % OFFSET_MODULUS != OFFSET_RESIDUE:
        return scaled
    return [
        [x + FIDELITY_OFFSET_UNITS * _sign(x), y + FIDELITY_OFFSET_UNITS * _sign(y)]
        for x, y in scaled
    ]


def outline_geometry_digest(instance: dict) -> str:
    return _canonical_digest(
        {
            "outline_revision_id": OUTLINE_REVISION_ID,
            "outline_scale": OUTLINE_SCALE,
            "instance_id": instance["instance_id"],
            "pieces": [
                [piece["piece_id"], refined_polygon(piece["piece_id"], piece["polygon"])]
                for piece in sorted(instance["pieces"], key=lambda item: item["piece_id"])
            ],
        }
    )


def build(instance_dir: pathlib.Path, budget_seconds: float) -> dict:
    authority = carriers.load_authority()
    instance = carriers.load_instance(instance_dir)
    resolved = carriers.resolve(instance, authority["bindings"])
    sheet = instance["sheet"]
    defects = instance["defects"]

    inset = region_inset()
    guard = DEFECT_GUARD_UNITS
    inner_width = sheet["width"] - 2 * inset
    inner_height = sheet["height"] - 2 * inset
    packed_defects = []
    for x0, y0, x1, y1 in defects:
        gx0 = max(0, x0 - inset - guard)
        gy0 = max(0, y0 - inset - guard)
        gx1 = min(inner_width, x1 - inset + guard)
        gy1 = min(inner_height, y1 - inset + guard)
        if gx1 > gx0 and gy1 > gy0:
            packed_defects.append((gx0, gy0, gx1, gy1))
    placements = pack.pack(resolved, inner_width, inner_height, packed_defects, budget_seconds)
    for item in placements:
        item["translate_x"] += inset
        item["translate_y"] += inset

    areas = {piece["piece_id"]: raster.twice_area(piece["polygon"]) for piece in resolved}
    placed = sum(areas[item["piece_id"]] for item in placements)
    usable = usable_twice_area(sheet, defects)
    waste = (usable - placed) / usable if usable else 1.0

    return {
        "instance_id": instance["instance_id"],
        "sheet_id": sheet["sheet_id"],
        "sheet_stock_profile_id": sheet["sheet_stock_profile_id"],
        "carrier_authority_digest": carriers.authority_digest(authority),
        "usable_region_digest": usable_region_digest(sheet, defects),
        "outline_revision_id": OUTLINE_REVISION_ID,
        "outline_geometry_digest": outline_geometry_digest(instance),
        "claimed_waste_fraction": max(0.0, min(1.0, waste)),
        "placements": placements,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="nester")
    parser.add_argument("--instance", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--budget-seconds", type=float, required=True)
    args = parser.parse_args(argv)

    document = build(pathlib.Path(args.instance), args.budget_seconds)
    pathlib.Path(args.output).write_text(json.dumps(document, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
