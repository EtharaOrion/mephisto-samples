#!/usr/bin/env python3
"""Lane 5 perturbation sweep for p6zeta v2 (judge side).

Implements the seven perturbations named in p6zeta_lib.PERTURBATIONS as
deterministic transforms of the INSTANCE FILE the solver reads, plus the inverse
transform of the solver's output so score.py can compare each perturbed run to
the base run on the ORIGINAL instance (score.py grades perturbed outputs against
the original instance and expects the original instance_id).

  variable_order_within_constraint  a column permutation applied to the objective
                                    and every row; output variables are un-permuted
  constraint_reorder                rows shuffled
  coefficient_common_scale          each row (coefficients and rhs) multiplied by a
                                    positive integer; feasibility is unchanged
  instance_id_salt_rewrite          instance_id gets an HMAC suffix; restored on output
  json_whitespace_reformat          same document, indent=4 pretty printing
  output_json_field_order           same document, keys in a different order
                                    (the solver's output is parsed field-order-blind)
  output_json_trailing_whitespace   same document plus trailing blank lines and spaces

Subcommands:
  make    --instances DIR --work DIR --salt S [--per-family N]
          writes DIR/<perturbation>/in/<iid>.ip.json and DIR/<perturbation>/map/<iid>.json
          and prints the chosen instance ids (first N per family, sorted) to stdout
  restore --work DIR --perturbation NAME --out ROOT
          reads DIR/NAME/raw/<iid>.out.json (solver stdout), un-perturbs, writes
          ROOT/NAME/<iid>.out.json for score.py --perturbations-root ROOT
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p6zeta_lib as lib  # noqa: E402

KEY_ORDERS = [
    ["objective_sense", "constraints", "objective_coefficients", "n_vars", "family", "instance_id", "comment"],
    ["n_vars", "instance_id", "objective_coefficients", "family", "comment", "objective_sense", "constraints"],
]


def _rng(salt: str, name: str, iid: str) -> random.Random:
    h = hashlib.sha256(f"{salt}|{name}|{iid}".encode()).hexdigest()
    return random.Random(int(h[:16], 16))


def perturb(inst: Dict[str, Any], name: str, salt: str) -> tuple[str, Dict[str, Any]]:
    """Return (serialized_instance_text, mapping)."""
    d = json.loads(json.dumps(inst))  # deep copy
    iid = d["instance_id"]
    r = _rng(salt, name, iid)
    mapping: Dict[str, Any] = {"instance_id": iid, "perturbation": name}
    text: str

    if name == "variable_order_within_constraint":
        n = d["n_vars"]
        perm = list(range(n))
        r.shuffle(perm)  # new position k holds original variable perm[k]
        d["objective_coefficients"] = [d["objective_coefficients"][perm[k]] for k in range(n)]
        for con in d["constraints"]:
            con["coefficients"] = [con["coefficients"][perm[k]] for k in range(n)]
        mapping["perm"] = perm
        text = lib.dump_canonical_json(d) + "\n"
    elif name == "constraint_reorder":
        r.shuffle(d["constraints"])
        text = lib.dump_canonical_json(d) + "\n"
    elif name == "coefficient_common_scale":
        for con in d["constraints"]:
            f = r.randint(2, 9)
            con["coefficients"] = [c * f for c in con["coefficients"]]
            con["rhs"] = con["rhs"] * f
        text = lib.dump_canonical_json(d) + "\n"
    elif name == "instance_id_salt_rewrite":
        tag = hmac.new(salt.encode(), iid.encode(), hashlib.sha256).hexdigest()[:8]
        d["instance_id"] = f"{iid}__s{tag}"
        mapping["salted_id"] = d["instance_id"]
        text = lib.dump_canonical_json(d) + "\n"
    elif name == "json_whitespace_reformat":
        text = json.dumps(d, sort_keys=True, indent=4) + "\n"
    elif name == "output_json_field_order":
        order = KEY_ORDERS[r.randrange(len(KEY_ORDERS))]
        ordered = {k: d[k] for k in order if k in d}
        for k in d:
            ordered.setdefault(k, d[k])
        # also reorder keys inside each constraint object
        ordered["constraints"] = [{"sense": c["sense"], "rhs": c["rhs"], "coefficients": c["coefficients"]}
                                  for c in ordered["constraints"]]
        text = json.dumps(ordered, separators=(",", ":")) + "\n"
    elif name == "output_json_trailing_whitespace":
        text = lib.dump_canonical_json(d) + "\n\n   \n\t\n"
    else:
        raise ValueError(f"unknown perturbation {name}")
    return text, mapping


def restore(output: Any, mapping: Dict[str, Any]) -> Any:
    if not isinstance(output, dict):
        return output
    out = dict(output)
    out["instance_id"] = mapping["instance_id"]
    perm = mapping.get("perm")
    if perm and isinstance(out.get("variables"), list) and len(out["variables"]) == len(perm):
        orig = [0] * len(perm)
        for k, v in enumerate(out["variables"]):
            orig[perm[k]] = v
        out["variables"] = orig
    return out


def cmd_make(a: argparse.Namespace) -> int:
    paths = sorted(a.instances.glob("*.ip.json"))
    by_family: Dict[str, List[Path]] = {}
    for p in paths:
        fam = json.load(open(p))["family"]
        by_family.setdefault(fam, []).append(p)
    chosen: List[Path] = []
    for fam in sorted(by_family):
        chosen.extend(sorted(by_family[fam])[: a.per_family])
    for name in lib.PERTURBATIONS:
        (a.work / name / "in").mkdir(parents=True, exist_ok=True)
        (a.work / name / "map").mkdir(parents=True, exist_ok=True)
        (a.work / name / "raw").mkdir(parents=True, exist_ok=True)
        for p in chosen:
            inst = json.load(open(p))
            text, mapping = perturb(inst, name, a.salt)
            (a.work / name / "in" / f"{inst['instance_id']}.ip.json").write_text(text)
            (a.work / name / "map" / f"{inst['instance_id']}.json").write_text(json.dumps(mapping))
    for p in chosen:
        print(json.load(open(p))["instance_id"])
    return 0


def cmd_restore(a: argparse.Namespace) -> int:
    src = a.work / a.perturbation
    dst = a.out / a.perturbation
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for mp in sorted((src / "map").glob("*.json")):
        mapping = json.load(open(mp))
        iid = mapping["instance_id"]
        raw = src / "raw" / f"{iid}.out.json"
        if not raw.is_file():
            continue
        try:
            output = json.loads(raw.read_text())
        except Exception:
            continue  # unparseable output = missing output for this instance
        (dst / f"{iid}.out.json").write_text(json.dumps(restore(output, mapping)) + "\n")
        n += 1
    print(f"{a.perturbation}: restored {n} outputs -> {dst}", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--instances", required=True, type=Path)
    m.add_argument("--work", required=True, type=Path)
    m.add_argument("--salt", required=True)
    m.add_argument("--per-family", type=int, default=3)
    m.set_defaults(fn=cmd_make)
    rs = sub.add_parser("restore")
    rs.add_argument("--work", required=True, type=Path)
    rs.add_argument("--perturbation", required=True)
    rs.add_argument("--out", required=True, type=Path)
    rs.set_defaults(fn=cmd_restore)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
