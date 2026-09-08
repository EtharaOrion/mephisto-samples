"""Workspace preview tool.

Recomputes containment, defect exclusion and pairwise overlap for a placement
file against the public practice geometry, using the same exact integer
predicates the graded path uses, and reports the resulting waste fraction. It
applies the clearance value published in the instance manifest. It is a local
convenience, not the grading authority.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import geometry

INSTANCE_DIR = pathlib.Path(os.environ.get("EDGEBENCH_INSTANCE_DIR", "/mnt/instances"))
AUTHORITY_DIR = pathlib.Path(os.environ.get("EDGEBENCH_AUTHORITY_DIR", "/mnt/authority"))


def parse_outline(text: str) -> dict:
    sheet = None
    defects = []
    pieces = []
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0] == "sheet":
            sheet = {
                "sheet_id": parts[1],
                "width": int(parts[2]),
                "height": int(parts[3]),
                "sheet_stock_profile_id": parts[4],
            }
        elif parts[0] == "defect":
            defects.append(tuple(int(v) for v in parts[1:5]))
        elif parts[0] == "piece":
            fields = dict(token.split("=", 1) for token in parts[2:])
            current = {
                "piece_id": parts[1],
                "vector_rotation_allowance": [int(v) for v in fields["rot"].split(",")],
                "vector_multiplicity": int(fields["mult"]),
                "polygon": [],
            }
        elif parts[0] == "v":
            current["polygon"].append((int(parts[1]), int(parts[2])))
        elif parts[0] == "endpiece":
            pieces.append(current)
            current = None
    return {"sheet": sheet, "defects": defects, "pieces": pieces}


def parse_table(text: str) -> dict:
    rows = {}
    for line in [entry for entry in text.splitlines() if entry.strip()][1:]:
        piece_id, allowance, multiplicity, margin, twice = line.split(",")
        rows[piece_id] = {
            "table_rotation_allowance": [int(v) for v in allowance.split("|")],
            "table_multiplicity": int(multiplicity),
            "twice_area": int(twice),
        }
    return rows


def review(instance_dir: pathlib.Path, placement_path: pathlib.Path, clearance: int) -> dict:
    outline = parse_outline((instance_dir / "outlines.geom").read_text())
    table = parse_table((instance_dir / "parts.csv").read_text())
    authority = json.loads((AUTHORITY_DIR / "authority.json").read_text())
    bindings = authority["bindings"]
    payload = json.loads(placement_path.read_text())

    by_id = {piece["piece_id"]: piece for piece in outline["pieces"]}
    for piece_id, row in table.items():
        by_id[piece_id].update(row)

    sheet = outline["sheet"]
    placed = []
    twice_placed = 0
    problems = []
    counts = {}
    for index, item in enumerate(payload.get("placements", [])):
        piece = by_id[item["piece_id"]]
        prefix = "vector" if bindings["rotation_allowance"] == "vector_outline" else "table"
        if item["rotation_degrees"] not in piece[f"{prefix}_rotation_allowance"]:
            problems.append({"index": index, "problem": "rotation_outside_authoritative_allowance"})
        prefix = "vector" if bindings["multiplicity"] == "vector_outline" else "table"
        counts[item["piece_id"]] = counts.get(item["piece_id"], 0) + 1
        if counts[item["piece_id"]] > piece[f"{prefix}_multiplicity"]:
            problems.append({"index": index, "problem": "multiplicity_exceeds_authoritative_binding"})
        polygon = geometry.transform(
            piece["polygon"], item["rotation_degrees"], item["translate_x"], item["translate_y"]
        )
        if not geometry.inside_rectangle(polygon, sheet["width"], sheet["height"]):
            problems.append({"index": index, "problem": "placement_outside_sheet"})
        placed.append((polygon, (item["translate_x"], item["translate_y"])))
        twice_placed += geometry.twice_area(piece["polygon"])

    for x0, y0, x1, y1 in outline["defects"]:
        defect = geometry.rectangle_polygon(x0, y0, x1, y1)
        reference = geometry.rectangle_reference(x0, y0, x1, y1)
        for index, (polygon, own) in enumerate(placed):
            if geometry.interiors_overlap(polygon, own, defect, reference):
                problems.append({"index": index, "problem": "placement_intersects_defect_zone"})

    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            if geometry.interiors_overlap(placed[i][0], placed[i][1], placed[j][0], placed[j][1]):
                problems.append({"first": i, "second": j, "problem": "pairwise_overlap_violation"})
            elif geometry.closer_than(placed[i][0], placed[j][0], clearance):
                problems.append({"first": i, "second": j, "problem": "clearance_below_previewed_tolerance"})

    usable = 2 * sheet["width"] * sheet["height"]
    for x0, y0, x1, y1 in outline["defects"]:
        usable -= 2 * (x1 - x0) * (y1 - y0)
    return {
        "instance_dir": str(instance_dir),
        "clearance_units": clearance,
        "placements": len(placed),
        "waste_fraction": max(0.0, min(1.0, (usable - twice_placed) / usable)) if usable else 1.0,
        "problems": problems[:20],
        "problem_count": len(problems),
    }


def main() -> int:
    manifest = json.loads((INSTANCE_DIR / "manifest.json").read_text())
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", required=True)
    parser.add_argument("--placement", required=True)
    parser.add_argument("--clearance", type=int, default=manifest["preview_clearance_units"])
    args = parser.parse_args()
    print(
        json.dumps(
            review(pathlib.Path(args.instance), pathlib.Path(args.placement), args.clearance),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
