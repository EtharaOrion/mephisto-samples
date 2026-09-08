"""Local checker. Scores your codec against the recorded corpus.

    python verify_local.py             # summary
    python verify_local.py --verbose   # first differing byte per failing column
    python verify_local.py --shape smooth

This is a fair signal and it is deliberately not the grader. The corpus is a sample of the
encoder's behaviour drawn from the column shapes a reader thinks of first. The graded columns
are drawn from a wider distribution. Reaching one hundred percent here is necessary and it is
not sufficient.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent


def load():
    spec = importlib.util.spec_from_file_location("candidate", HERE / "submission" / "codec.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def block_ids(blob: bytes) -> list[int]:
    """Read the encoding id of each block. Framing only, per spec/FORMAT.md."""
    count = int.from_bytes(blob[:4], "little")
    cursor = 4
    out = []
    for _ in range(count):
        out.append(blob[cursor])
        n = int.from_bytes(blob[cursor + 1 : cursor + 3], "little")
        kind = blob[cursor]
        cursor += 3
        if kind == 0:
            cursor += 8 * n
        elif kind == 1:
            cursor += 8
        elif kind == 2:
            width = blob[cursor + 8]
            cursor += 9 + (n * width + 7) // 8
        elif kind == 3:
            width = blob[cursor + 16]
            cursor += 17 + ((n - 1) * width + 7) // 8
        elif kind == 4:
            runs = int.from_bytes(blob[cursor : cursor + 2], "little")
            cursor += 2 + 10 * runs
        elif kind == 5:
            size = blob[cursor]
            width = blob[cursor + 1 + 8 * size]
            cursor += 1 + 8 * size + 1 + (n * width + 7) // 8
        else:
            raise ValueError(f"unknown encoding {kind}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--shape", default=None)
    args = parser.parse_args()

    try:
        module = load()
    except Exception as exc:  # noqa: BLE001
        print(f"codec failed to import: {type(exc).__name__}: {exc}")
        return 1

    corpus = json.loads((HERE / "corpus" / "corpus.json").read_text())["columns"]
    exact = shown = 0
    blocks_total = blocks_match = 0
    decode_ok = decode_total = 0
    by_shape: dict[str, list[int]] = {}

    for column in corpus:
        if args.shape and column["shape"] != args.shape:
            continue
        expected = bytes.fromhex(column["encoded_hex"])
        try:
            produced = bytes(module.encode(list(column["values"])))
        except Exception as exc:  # noqa: BLE001
            produced = b""
            if args.verbose and shown < 8:
                print(f"[FAIL] {column['id']}: encode raised {type(exc).__name__}: {exc}")
                shown += 1
        ok = produced == expected
        exact += ok
        tally = by_shape.setdefault(column["shape"], [0, 0])
        tally[0] += ok
        tally[1] += 1

        blocks_total += len(column["block_encodings"])
        if produced:
            try:
                blocks_match += sum(
                    1 for a, b in zip(column["block_encodings"], block_ids(produced)) if a == b
                )
            except Exception:  # noqa: BLE001
                pass
        if not ok and args.verbose and shown < 8:
            where = next((i for i, (a, b) in enumerate(zip(produced, expected)) if a != b), min(len(produced), len(expected)))
            print(f"[FAIL] {column['id']}: {len(produced)} bytes against {len(expected)}, first difference at offset {where}")
            shown += 1

        decode_total += 1
        try:
            decode_ok += list(module.decode(expected)) == list(column["values"])
        except Exception:  # noqa: BLE001
            pass

    total = sum(t[1] for t in by_shape.values())
    print()
    print(f"  byte exact       {exact}/{total}")
    print(f"  block choices    {blocks_match}/{blocks_total}")
    print(f"  decode reference {decode_ok}/{decode_total}")
    print()
    for shape in sorted(by_shape):
        hit, seen = by_shape[shape]
        print(f"    {shape:20s} {hit}/{seen}")
    return 0 if exact == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
