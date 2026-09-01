from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

from . import carriers, pack

USABLE_REGION_MODE = "raw_sheet_rectangle"
TRIM_INSET_UNITS = 0
OUTLINE_REVISION_ID = "outline-2026-08-17.a"
OUTLINE_SCALE = 4


def usable_twice_area(sheet, defects):
    total = 2 * sheet["width"] * sheet["height"]
    for x0, y0, x1, y1 in defects:
        total -= 2 * (x1 - x0) * (y1 - y0)
    return total


def _canonical_digest(record):
    payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def usable_region_digest(sheet, defects):
    return _canonical_digest(
        {
            "usable_region_mode": USABLE_REGION_MODE,
            "trim_inset_units": TRIM_INSET_UNITS,
            "sheet_stock_profile_id": sheet["sheet_stock_profile_id"],
            "x0": TRIM_INSET_UNITS,
            "y0": TRIM_INSET_UNITS,
            "x1": sheet["width"] - TRIM_INSET_UNITS,
            "y1": sheet["height"] - TRIM_INSET_UNITS,
            "defects": [list(defect) for defect in defects],
        }
    )


def outline_geometry_digest(instance):
    return _canonical_digest(
        {
            "outline_revision_id": OUTLINE_REVISION_ID,
            "outline_scale": OUTLINE_SCALE,
            "instance_id": instance["instance_id"],
            "pieces": [
                [piece["piece_id"], [[OUTLINE_SCALE * x, OUTLINE_SCALE * y] for x, y in piece["polygon"]]]
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
    placements = pack.pack(resolved, sheet["width"], sheet["height"], defects, budget_seconds)

    areas = {piece["piece_id"]: pack.twice_area(piece["polygon"]) for piece in resolved}
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
