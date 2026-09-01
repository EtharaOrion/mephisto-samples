# forge-canary: FORGE-CANARY-DF716052883A908C59FF741CA5A90FE0
"""Binding check for the silent usable sheet region repin.

The usable region predicate is resolved from the live attempt index alone. Before
the pinned turn the graded region is the raw sheet rectangle, at and after it the
graded region is that rectangle inset by TRIM_INSET_UNITS on all four edges. The
predicate is integer only and never consults a clock, so a placement accepted on
one host is accepted on every host and the decision is replayable under frozen
bytes.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import geometry
import verifier_lib

CHECKER_ID = "C_M5_usable_region_binding"

M5_TURN = 18
USABLE_REGION_PRE = "raw_sheet_rectangle"
USABLE_REGION_POST = "trim_inset_rectangle"
TRIM_INSET_UNITS = 3


def live_region(profile: dict) -> dict:
    attempt = int(verifier_lib.live_manifest()["attempt_index"])
    mode = USABLE_REGION_POST if attempt >= M5_TURN else USABLE_REGION_PRE
    inset = TRIM_INSET_UNITS if mode == USABLE_REGION_POST else 0
    record = {
        "usable_region_mode": mode,
        "trim_inset_units": inset,
        "sheet_stock_profile_id": profile["sheet_stock_profile_id"],
        "x0": inset,
        "y0": inset,
        "x1": profile["width"] - inset,
        "y1": profile["height"] - inset,
        "defects": [list(defect) for defect in profile["defects"]],
    }
    payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    record["usable_region_digest"] = hashlib.sha256(payload).hexdigest()
    return record


def _scan(instance: dict, placements: list, region: dict) -> dict | None:
    """Return the first placement that leaves the live usable region, or None.

    A malformed row is not attributed here. Unknown identifiers, non integral
    translations, rotation and multiplicity violations already resolve to the
    authority checker, so this checker stays silent on them and reports only the
    region predicate it owns.
    """
    by_id = {piece["piece_id"]: piece for piece in instance["pieces"]}
    for index, item in enumerate(placements or []):
        piece = by_id.get(item.get("piece_id")) if isinstance(item, dict) else None
        if piece is None:
            continue
        try:
            rotation = int(item["rotation_degrees"])
            tx = int(item["translate_x"])
            ty = int(item["translate_y"])
        except (KeyError, TypeError, ValueError):
            continue
        if rotation not in geometry.ROTATIONS:
            continue
        polygon = geometry.transform(piece["polygon"], rotation, tx, ty)
        for x, y in polygon:
            if x < region["x0"] or y < region["y0"] or x > region["x1"] or y > region["y1"]:
                return {
                    "index": index,
                    "piece_id": piece["piece_id"],
                    "vertex": [x, y],
                    "usable_region_mode": region["usable_region_mode"],
                    "trim_inset_units": region["trim_inset_units"],
                    "region": [region["x0"], region["y0"], region["x1"], region["y1"]],
                }
    return None


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")

    declared = verifier_lib.declared_recompute(workspace)
    if not declared.get("ok"):
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            declared.get("error") or "declared_recompute_failed",
            declared.get("detail") or {},
        )

    checked = 0
    for entry in declared["rows"]:
        instance = entry["instance"]
        region = live_region(verifier_lib.profile_of(instance))
        stated = entry["row"].get("usable_region_digest")
        if stated != region["usable_region_digest"]:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "declared_usable_region_digest_diverges_from_live_pin",
                {
                    "instance_id": instance["instance_id"],
                    "declared": stated,
                    "live_digest": region["usable_region_digest"],
                    "live_mode": region["usable_region_mode"],
                },
            )
        breach = _scan(instance, entry["row"].get("placements", []), region)
        if breach is not None:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "declared_placement_outside_live_usable_region",
                {"instance_id": instance["instance_id"], **breach},
            )
        checked += 1

    hidden = verifier_lib.hidden_sweep(workspace)
    if not hidden.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, hidden.get("error") or "hidden_sweep_failed")

    families = {instance["instance_id"]: instance for instance in verifier_lib.hidden_family()}
    for record in hidden["records"]:
        instance = families[record["instance_id"]]
        region = live_region(verifier_lib.profile_of(instance))
        payload = record["payload"]
        stated = payload.get("usable_region_digest")
        if stated != region["usable_region_digest"]:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "emitted_usable_region_digest_diverges_from_live_pin",
                {
                    "instance_id": record["instance_id"],
                    "declared": stated,
                    "live_digest": region["usable_region_digest"],
                    "live_mode": region["usable_region_mode"],
                },
            )
        breach = _scan(instance, payload.get("placements", []), region)
        if breach is not None:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "emitted_placement_outside_live_usable_region",
                {"instance_id": record["instance_id"], **breach},
            )
        checked += 1

    sample = live_region(verifier_lib.profile_of(verifier_lib.hidden_family()[0]))
    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "usable_region_binding_resolved_against_live_pin",
        {
            "usable_region_mode": sample["usable_region_mode"],
            "trim_inset_units": sample["trim_inset_units"],
            "instances_checked": checked,
        },
    )
