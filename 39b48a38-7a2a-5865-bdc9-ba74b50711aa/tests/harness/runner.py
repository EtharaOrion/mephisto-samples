"""Isolated submission runner. Never agent visible.

The parent copies this single file into an empty directory and launches it with `python -I`,
so the child's `sys.path` holds that directory and the standard library and nothing else. The
reference codec, the sealed seed and the grading configuration stay in the parent, which never
imports the submission at all.

Before any submission byte executes, the runner closes a runtime boundary with an audit hook.
Name blocklists were walked around three times in the sibling bundle by reaching the runtime
through an allowlisted module's attribute, so this denies effects rather than enumerating
names: no file open, no process, no socket, no frame walk, no import outside the allowlist,
and one exec budget spent on the submission itself.

CANARY-BLOCK-BEGIN
canary_slot_0: MEPH-373d1916b5939704412ba6efe8590d88
canary_slot_1: MEPH-b788c135a56267dac49d57ee8273bd4e
canary_slot_2: MEPH-c271027e98332e4ff7c37a518d7881ef
canary_slot_3: MEPH-0b50c7a3306d23690a441bc7053f21c3
CANARY-BLOCK-END
"""

from __future__ import annotations

import importlib.util
import json
import sys
import traceback

ALLOWED_IMPORTS = (
    "__future__", "abc", "array", "binascii", "bisect", "collections", "dataclasses",
    "enum", "functools", "hashlib", "heapq", "itertools", "math", "struct", "types",
    "typing", "zlib",
)

DENIED_EVENTS = (
    "open", "os.system", "os.exec", "os.fork", "os.posix_spawn", "os.spawn", "os.startfile",
    "os.putenv", "os.unsetenv", "os.remove", "os.rename", "os.chmod", "os.chown",
    "os.listdir", "os.scandir", "os.mkdir", "os.rmdir", "os.symlink", "os.link",
    "os.truncate", "os.walk", "subprocess.Popen", "socket.socket", "socket.connect",
    "socket.bind", "socket.getaddrinfo", "ctypes.dlopen", "ctypes.dlsym",
    "ctypes.call_function", "marshal.load", "marshal.loads", "pickle.find_class",
    "shutil.copyfile", "shutil.move", "tempfile.mkstemp", "tempfile.mkdtemp",
    "urllib.Request", "webbrowser.open", "code.InteractiveInterpreter", "cpython.run_file",
    "cpython.run_module", "sys._getframe", "sys.settrace", "sys.setprofile",
    "sys._current_frames", "gc.get_objects", "gc.get_referrers", "gc.get_referents",
    "builtins.input",
)


class BoundaryViolation(Exception):
    """The submission attempted an effect the boundary denies."""


def install_boundary():
    state = {"exec_budget": 1}

    def hook(event, args):
        if event in DENIED_EVENTS:
            raise BoundaryViolation("boundary denies %s" % event)
        if event in ("exec", "eval", "compile"):
            if state["exec_budget"] <= 0:
                raise BoundaryViolation("boundary denies %s" % event)
            state["exec_budget"] -= 1
            return
        if event == "import":
            name = args[0] if args else ""
            root = str(name).split(".")[0]
            if root not in ALLOWED_IMPORTS or root not in sys.modules:
                raise BoundaryViolation("boundary denies import of %r" % name)

    sys.addaudithook(hook)


def load_submission(path):
    for name in ALLOWED_IMPORTS:
        try:
            __import__(name)
        except ImportError:
            pass
    with open(path, "r", encoding="utf-8") as handle:
        source = handle.read()
    code = compile(source, "candidate_codec", "exec")
    spec = importlib.util.spec_from_file_location("candidate_codec", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["candidate_codec"] = module
    install_boundary()
    exec(code, module.__dict__)  # noqa: S102
    return module


def run_job(job):
    module = load_submission(job["submission"])
    for name in ("encode", "decode", "predict", "FORMAT_REVISION"):
        if not hasattr(module, name):
            return {"ok": False, "error": "submission_api_incomplete:%s" % name}

    want_predict = job.get("predict", False)
    echo_self = job.get("echo_self", False)
    # Decode-only mode exists because every other pass calls encode on a column before asking
    # the decoder about that same column, in the same process. A submission that keeps what it
    # was handed and returns it from decode then satisfies both container conformance and the
    # self-decode check while owning no decoder at all. Here encode is never called, so the
    # only way to produce the values is to read the bytes.
    decode_only = job.get("decode_only", False)
    results = []
    for column in job["columns"]:
        values = column["values"]
        entry = {"id": column["id"]}
        blob = None
        if not decode_only:
            try:
                blob = module.encode(list(values))
                entry["encoded_hex"] = bytes(blob).hex()
            except Exception as exc:  # noqa: BLE001
                entry["encode_error"] = "%s: %s" % (type(exc).__name__, exc)
        # Self decode, for the lane that asks whether the encoder emits something it can read.
        if echo_self and blob is not None:
            try:
                entry["self_decoded"] = [int(v) for v in module.decode(bytes(blob))]
            except Exception as exc:  # noqa: BLE001
                entry["self_decode_error"] = "%s: %s" % (type(exc).__name__, exc)
        # The submission's own statement of its uncertainty.
        if want_predict and not decode_only:
            try:
                rows = module.predict(list(values))
                entry["prediction"] = [[float(x) for x in row] for row in rows]
            except Exception as exc:  # noqa: BLE001
                entry["predict_error"] = "%s: %s" % (type(exc).__name__, exc)
        # Decoding is graded against the reference's bytes, not the candidate's, so an engine
        # that cannot encode can still show a working decoder.
        if column.get("reference_hex") is not None:
            try:
                back = module.decode(bytes.fromhex(column["reference_hex"]))
                entry["decoded"] = [int(v) for v in back]
            except Exception as exc:  # noqa: BLE001
                entry["decode_error"] = "%s: %s" % (type(exc).__name__, exc)
        results.append(entry)

    try:
        revision = int(module.FORMAT_REVISION)
    except Exception:  # noqa: BLE001
        revision = None
    return {"ok": True, "error": None, "results": results, "declared_revision": revision}


def main():
    try:
        payload = run_job(json.loads(sys.stdin.read()))
    except Exception:  # noqa: BLE001
        payload = {"ok": False, "error": traceback.format_exc(limit=6)}
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
