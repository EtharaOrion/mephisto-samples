# forge-canary: FORGE-CANARY-F18CDD9D27957C9FD24743C43CBE6FEC
from __future__ import annotations

import pathlib
import runpy
import sys

_COUNT = 0


_TARGETS = ()


def _tracer(frame, event, arg):
    global _COUNT
    if event == "line" and frame.f_code.co_filename in _TARGETS:
        _COUNT += 1
    return _tracer


def main() -> int:
    meta_path = pathlib.Path(sys.argv[1])
    target = sys.argv[2]
    global _TARGETS
    _TARGETS = (target, str(pathlib.Path(target).resolve()))
    sys.argv = [target] + sys.argv[3:]
    status = 0
    sys.settrace(_tracer)
    try:
        runpy.run_path(target, run_name="__main__")
    except SystemExit as exc:
        status = int(exc.code or 0)
    finally:
        sys.settrace(None)
    meta_path.write_text(f"{_COUNT} {status}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
