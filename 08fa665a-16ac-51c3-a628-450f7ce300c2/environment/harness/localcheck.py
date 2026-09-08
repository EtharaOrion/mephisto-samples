from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import ambient

SCAN_NOTE = "pairs are scanned over strictly increasing index positions only"


def scan(points, geometry: dict) -> dict:
    indexed = ambient.canonicalise(points, geometry)
    add = ambient.adder(geometry["field_order"], geometry["dimension"])
    packed = [entry[1] for entry in indexed]
    sums = set()
    collisions = 0
    for left in range(len(packed)):
        for right in range(left + 1, len(packed)):
            value = add(packed[left], packed[right])
            if value in sums:
                collisions += 1
            sums.add(value)
    return {
        "scanned_points": len(packed),
        "distinct_pair_sums": len(sums),
        "collisions": collisions,
        "admissible": collisions == 0,
        "scan_note": SCAN_NOTE,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    args = parser.parse_args()
    payload = json.loads(pathlib.Path(args.bundle).read_text())
    geometry = ambient.live_geometry()
    print(json.dumps(scan(payload["points"], geometry), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
