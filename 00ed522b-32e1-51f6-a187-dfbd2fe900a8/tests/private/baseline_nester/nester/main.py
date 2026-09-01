# forge-canary: FORGE-CANARY-DF716052883A908C59FF741CA5A90FE0
from __future__ import annotations

import argparse
import json
import pathlib

from . import carriers, pack


def usable_twice_area(sheet, defects):
    total = 2 * sheet["width"] * sheet["height"]
    for x0, y0, x1, y1 in defects:
        total -= 2 * (x1 - x0) * (y1 - y0)
    return total


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
