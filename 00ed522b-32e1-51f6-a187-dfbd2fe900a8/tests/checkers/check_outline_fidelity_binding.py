# forge-canary: FORGE-CANARY-8881AD83FBBDBD62B88DCA22928690C5
"""Binding check for the silent part outline fidelity repin.

The outline revision is resolved from the live attempt index alone. Revision a
carries every outline on the unit lattice; revision b restates every outline on
the quarter unit lattice at OUTLINE_SCALE and grows each piece whose ordinal is
congruent to OFFSET_RESIDUE modulo OFFSET_MODULUS by one quarter unit outward at
every vertex. Outlines are star shaped about the local origin, so a radial step
of one quarter unit preserves the angular vertex order and the outline stays
simple with the origin strictly interior.

Under revision a the refined polygon is the coarse polygon scaled uniformly, and
a uniform scale preserves containment, defect intersection and pairwise overlap
answers exactly, so this checker adds no verdict before the repin turn. All
arithmetic is integer and no clock is consulted.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import geometry
import verifier_lib

CHECKER_ID = "C_M6_outline_fidelity_binding"

M6_TURN = 46
OUTLINE_REVISION_PRE = "outline-2026-08-17.a"
OUTLINE_REVISION_POST = "outline-2026-08-17.b"
OUTLINE_SCALE = 4
FIDELITY_OFFSET_UNITS = 1
OFFSET_MODULUS = 3
OFFSET_RESIDUE = 1


def live_revision() -> str:
    attempt = int(verifier_lib.live_manifest()["attempt_index"])
    return OUTLINE_REVISION_POST if attempt >= M6_TURN else OUTLINE_REVISION_PRE


def _sign(value: int) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _ordinal(piece_id: str) -> int:
    return int(piece_id[1:])


def refined_polygon(piece: dict, revision: str) -> list[tuple[int, int]]:
    scaled = [(OUTLINE_SCALE * x, OUTLINE_SCALE * y) for x, y in piece["polygon"]]
    if revision != OUTLINE_REVISION_POST:
        return scaled
    if _ordinal(piece["piece_id"]) % OFFSET_MODULUS != OFFSET_RESIDUE:
        return scaled
    return [
        (x + FIDELITY_OFFSET_UNITS * _sign(x), y + FIDELITY_OFFSET_UNITS * _sign(y))
        for x, y in scaled
    ]


def outline_digest(instance: dict, revision: str) -> str:
    record = {
        "outline_revision_id": revision,
        "outline_scale": OUTLINE_SCALE,
        "instance_id": instance["instance_id"],
        "pieces": [
            [piece["piece_id"], [[x, y] for x, y in refined_polygon(piece, revision)]]
            for piece in sorted(instance["pieces"], key=lambda item: item["piece_id"])
        ],
    }
    payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _place(instance: dict, placements: list, revision: str) -> dict:
    """Rebuild the layout on the refined lattice.

    Rows the authority checker already owns are skipped rather than re-attributed,
    so a rotation, multiplicity or identifier defect never lands on this checker.
    """
    by_id = {piece["piece_id"]: piece for piece in instance["pieces"]}
    placed = []
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
        reference = (OUTLINE_SCALE * tx, OUTLINE_SCALE * ty)
        polygon = geometry.transform(
            refined_polygon(piece, revision), rotation, reference[0], reference[1]
        )
        placed.append({"index": index, "piece_id": piece["piece_id"], "polygon": polygon, "reference": reference})
    return {"placed": placed}


def _scan(instance: dict, placements: list, revision: str) -> dict | None:
    profile = verifier_lib.profile_of(instance)
    placed = _place(instance, placements, revision)["placed"]

    width = OUTLINE_SCALE * profile["width"]
    height = OUTLINE_SCALE * profile["height"]
    for item in placed:
        if not geometry.inside_rectangle(item["polygon"], width, height):
            return {
                "reason": "refined_outline_leaves_sheet",
                "detail": {"index": item["index"], "piece_id": item["piece_id"]},
            }

    for x0, y0, x1, y1 in profile["defects"]:
        box = [OUTLINE_SCALE * x0, OUTLINE_SCALE * y0, OUTLINE_SCALE * x1, OUTLINE_SCALE * y1]
        defect = geometry.rectangle_polygon(*box)
        defect_reference = geometry.rectangle_reference(*box)
        for item in placed:
            if geometry.interiors_overlap(item["polygon"], item["reference"], defect, defect_reference):
                return {
                    "reason": "refined_outline_intersects_defect_zone",
                    "detail": {"index": item["index"], "piece_id": item["piece_id"], "defect": box},
                }

    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            if geometry.interiors_overlap(
                placed[i]["polygon"], placed[i]["reference"], placed[j]["polygon"], placed[j]["reference"]
            ):
                return {
                    "reason": "refined_outline_pairwise_overlap",
                    "detail": {
                        "first_index": placed[i]["index"],
                        "second_index": placed[j]["index"],
                        "first": placed[i]["piece_id"],
                        "second": placed[j]["piece_id"],
                    },
                }
    return None


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")

    revision = live_revision()

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
        row = entry["row"]
        live_digest = outline_digest(instance, revision)
        if row.get("outline_revision_id") != revision or row.get("outline_geometry_digest") != live_digest:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "declared_outline_fidelity_diverges_from_live_revision",
                {
                    "instance_id": instance["instance_id"],
                    "declared_revision": row.get("outline_revision_id"),
                    "declared_digest": row.get("outline_geometry_digest"),
                    "live_revision": revision,
                    "live_digest": live_digest,
                },
            )
        breach = _scan(instance, row.get("placements", []), revision)
        if breach is not None:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                breach["reason"],
                {"instance_id": instance["instance_id"], "live_revision": revision, **breach["detail"]},
            )
        checked += 1

    hidden = verifier_lib.hidden_sweep(workspace)
    if not hidden.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, hidden.get("error") or "hidden_sweep_failed")

    families = {instance["instance_id"]: instance for instance in verifier_lib.hidden_family()}
    for record in hidden["records"]:
        instance = families[record["instance_id"]]
        payload = record["payload"]
        live_digest = outline_digest(instance, revision)
        if (
            payload.get("outline_revision_id") != revision
            or payload.get("outline_geometry_digest") != live_digest
        ):
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "emitted_outline_fidelity_diverges_from_live_revision",
                {
                    "instance_id": record["instance_id"],
                    "declared_revision": payload.get("outline_revision_id"),
                    "declared_digest": payload.get("outline_geometry_digest"),
                    "live_revision": revision,
                    "live_digest": live_digest,
                },
            )
        breach = _scan(instance, payload.get("placements", []), revision)
        if breach is not None:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                breach["reason"],
                {"instance_id": record["instance_id"], "live_revision": revision, **breach["detail"]},
            )
        checked += 1

    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "outline_fidelity_binding_resolved_against_live_revision",
        {"live_revision": revision, "outline_scale": OUTLINE_SCALE, "instances_checked": checked},
    )
