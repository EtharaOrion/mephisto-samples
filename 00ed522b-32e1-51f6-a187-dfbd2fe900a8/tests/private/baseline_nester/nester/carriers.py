# forge-canary: FORGE-CANARY-8C9E0B8D2FBCC6E24B34F86E4C4C76B9
"""Carrier ingestion for the starter nester.

The part geometry arrives through two independent carriers that disagree on
rotation allowance and part multiplicity for a subset of the parts. Neither
carrier is merged into the other. Every conflicting field is resolved by asking
the live carrier authority registry which carrier binds that field, on every
run, so an unannounced repin of the registry changes the resolved value without
any change to this code.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib

CARRIER_VECTOR = "vector_outline"
CARRIER_TABLE = "parameter_table"

CONFLICTING_FIELDS = ("rotation_allowance", "multiplicity", "sheet_margin")


def authority_path() -> pathlib.Path:
    root = os.environ.get("EDGEBENCH_AUTHORITY_DIR", "/mnt/authority")
    return pathlib.Path(root) / "authority.json"


def load_authority() -> dict:
    return json.loads(authority_path().read_text())


def authority_digest(record: dict) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def parse_outline_carrier(text: str) -> dict:
    sheet = None
    defects = []
    pieces = []
    current = None
    instance_id = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        head = parts[0]
        if head == "instance":
            instance_id = parts[1]
        elif head == "sheet":
            sheet = {
                "sheet_id": parts[1],
                "width": int(parts[2]),
                "height": int(parts[3]),
                "sheet_stock_profile_id": parts[4],
            }
        elif head == "defect":
            defects.append((int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])))
        elif head == "piece":
            fields = dict(token.split("=", 1) for token in parts[2:])
            current = {
                "piece_id": parts[1],
                "vector_rotation_allowance": [int(v) for v in fields["rot"].split(",")],
                "vector_multiplicity": int(fields["mult"]),
                "vector_sheet_margin": int(fields["margin"]),
                "polygon": [],
            }
        elif head == "v":
            current["polygon"].append((int(parts[1]), int(parts[2])))
        elif head == "endpiece":
            pieces.append(current)
            current = None
    return {"instance_id": instance_id, "sheet": sheet, "defects": defects, "pieces": pieces}


def parse_parameter_carrier(text: str) -> dict:
    rows = {}
    lines = [line for line in text.splitlines() if line.strip()]
    for line in lines[1:]:
        piece_id, allowance, multiplicity, margin, twice = line.split(",")
        rows[piece_id] = {
            "table_rotation_allowance": [int(v) for v in allowance.split("|")],
            "table_multiplicity": int(multiplicity),
            "table_sheet_margin": int(margin),
            "twice_area": int(twice),
        }
    return rows


def load_instance(instance_dir: pathlib.Path) -> dict:
    outline = parse_outline_carrier((instance_dir / "outlines.geom").read_text())
    table = parse_parameter_carrier((instance_dir / "parts.csv").read_text())
    for piece in outline["pieces"]:
        row = table.get(piece["piece_id"])
        if row is None:
            raise KeyError(f"piece_absent_from_parameter_carrier:{piece['piece_id']}")
        piece.update(row)
    return outline


def resolve_field(piece: dict, field: str, bindings: dict):
    carrier = bindings[field]
    if carrier == CARRIER_VECTOR:
        return piece[f"vector_{field}"]
    if carrier == CARRIER_TABLE:
        return piece[f"table_{field}"]
    raise KeyError(f"unknown_carrier:{carrier}")


def resolve(instance: dict, bindings: dict) -> list[dict]:
    resolved = []
    for piece in instance["pieces"]:
        entry = {"piece_id": piece["piece_id"], "polygon": piece["polygon"]}
        for field in CONFLICTING_FIELDS:
            entry[field] = resolve_field(piece, field, bindings)
        resolved.append(entry)
    return resolved
