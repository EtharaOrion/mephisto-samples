from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import registry


def apply_state(attempt_index: int, model_dir: pathlib.Path, kernel_dir: pathlib.Path) -> dict:
    state = registry.resolve_state(attempt_index)
    model_dir.mkdir(parents=True, exist_ok=True)
    kernel_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "registry.json").write_text(json.dumps(state["registry"], indent=2, sort_keys=True) + "\n")
    (model_dir / "latency_manifest.json").write_text(json.dumps(state["manifest"], indent=2, sort_keys=True) + "\n")
    (model_dir / "MODEL.md").write_text(state["prose"])
    (model_dir / "preview_policy.json").write_text(json.dumps(state["preview"], indent=2, sort_keys=True) + "\n")
    (kernel_dir / "manifest.json").write_text(json.dumps(state["kernels"], indent=2, sort_keys=True) + "\n")
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-index", type=int, required=True)
    parser.add_argument("--model-dir", default="/mnt/machine_model")
    parser.add_argument("--kernel-dir", default="/mnt/kernels")
    args = parser.parse_args()
    apply_state(args.attempt_index, pathlib.Path(args.model_dir), pathlib.Path(args.kernel_dir))
    print(
        json.dumps(
            {"attempt_index": args.attempt_index, "announcement": registry.announcement(args.attempt_index)},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
