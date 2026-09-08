from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import registry


def apply_state(attempt_index: int, geometry_dir: pathlib.Path) -> dict:
    state = registry.resolve_state(attempt_index)
    geometry_dir.mkdir(parents=True, exist_ok=True)
    (geometry_dir / "manifest.json").write_text(
        json.dumps(state["geometry"], indent=2, sort_keys=True) + "\n"
    )
    (geometry_dir / "predicate.json").write_text(
        json.dumps(state["predicate"], indent=2, sort_keys=True) + "\n"
    )
    return state


def announcement_for(attempt_index: int, state: dict) -> str | None:
    if attempt_index == registry.M1_TURN:
        geometry = state["geometry"]
        return (
            "ambient geometry rotated to "
            f"{geometry['ambient_params_id']} at field order {geometry['field_order']} and dimension "
            f"{geometry['dimension']}, transition {geometry['transition']} from "
            f"{geometry['previous_ambient_params_id']}"
        )
    if attempt_index == registry.M3_TURN:
        budget = state["budget"]
        return (
            "per attempt search budget reduced to "
            f"{budget['search_budget_seconds']} seconds and emission ceiling raised to "
            f"{budget['emission_ceiling']} points"
        )
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-index", type=int, required=True)
    parser.add_argument("--geometry-dir", default="/mnt/geometry")
    args = parser.parse_args()
    state = apply_state(args.attempt_index, pathlib.Path(args.geometry_dir))
    print(
        json.dumps(
            {
                "attempt_index": args.attempt_index,
                "announcement": announcement_for(args.attempt_index, state),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
