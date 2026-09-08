"""Static source gate. Runs before the submission is loaded, never after.

The first version of this verifier scanned the submission for a blocklist of module names
after every other lane had already executed it. That ordering is backwards and that
predicate is the wrong shape: by the time a blocklist decides a name is disallowed, the code
has run, and a blocklist only ever names the imports somebody thought of. `builtins` was not
on it, and `builtins.open` read the sealed seed.

This gate is an allowlist and it decides before anything executes. A submission that fails it
is never imported at all.

The allowlist is published in `spec/API.md`, so nothing here is a hidden rule. It is small
because the task needs almost nothing: this is a storage engine over a supplied interface,
and an engine that needs to reach the interpreter internals is not writing a storage engine.

CANARY-BLOCK-BEGIN
canary_slot_0: MEPH-373d1916b5939704412ba6efe8590d88
canary_slot_1: MEPH-b788c135a56267dac49d57ee8273bd4e
canary_slot_2: MEPH-c271027e98332e4ff7c37a518d7881ef
canary_slot_3: MEPH-0b50c7a3306d23690a441bc7053f21c3
CANARY-BLOCK-END
"""

from __future__ import annotations

import ast

# Every module a deltalog engine may import. Anything absent is refused.
ALLOWED_IMPORTS = frozenset(
    {
        "__future__",
        "abc",
        "array",
        "binascii",
        "bisect",
        "collections",
        "dataclasses",
        "enum",
        "functools",
        "hashlib",
        "heapq",
        "itertools",
        "math",
        "struct",
        "types",
        "typing",
        # Left available on purpose. zlib.crc32 is the IEEE polynomial and is the wrong
        # checksum for this format, so reaching for it is a design decision the format lane
        # grades rather than a construct this gate refuses.
        "zlib",
    }
)

# Names whose whole purpose is to reach something the allowlist withheld.
#
# This list is deliberately short. The boundary is the audit hook in the runner, which denies
# effects at runtime whatever object the submission holds; this gate exists so a submission
# that will obviously fail gets a clear message before it runs, not as the boundary itself.
# An earlier version banned `memoryview`, `getattr`, `hasattr`, `dir` and `super`, and two of
# four independent solvers were refused for using `memoryview` on a byte buffer, which is
# ordinary Python in a storage engine and reaches nothing. A gate that refuses honest work is
# a defect in the task, not a control.
FORBIDDEN_NAMES = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "open",
        "__import__",
        "globals",
        "locals",
        "vars",
        "breakpoint",
        "input",
    }
)

# Attribute names that walk out of the object graph into the runtime.
FORBIDDEN_ATTRIBUTES = frozenset(
    {
        "__class__",
        "__bases__",
        "__mro__",
        "__subclasses__",
        "__globals__",
        "__code__",
        "__closure__",
        "__builtins__",
        "__dict__",
        "__module__",
        "__loader__",
        "__spec__",
        "__getattribute__",
        "__reduce__",
        "__reduce_ex__",
        "f_back",
        "f_globals",
        "f_locals",
        "gi_frame",
        "cr_frame",
    }
)


# Names that only ever appear in a string when something is being reached by reflection.
_STRING_REFLECTION = frozenset(
    {
        "__subclasses__",
        "__init_subclass__",
        "__builtins__",
        "__import__",
        "builtins",
        "importlib",
        "harness",
        "refimpl",
        "grading.json",
        "os",
        "sys",
        "subprocess",
    }
)


def check(source: str) -> list[str]:
    """Return every finding. An empty list means the submission may be loaded."""
    findings: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"submission does not parse: {exc}"]

    # A name that only exists inside a string literal is invisible to an attribute check.
    # `operator.attrgetter("__class__")` walked straight around the first version of this
    # gate, so the forbidden names are refused as string constants too. This costs a
    # legitimate engine nothing: none of these names belongs in a storage engine's data.
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            hit = node.value.strip()
            # Only reflection names are refused as strings. A plain builtin name like
            # "open" is also an ordinary English word, and the reference engine uses it as
            # a transaction state, so refusing it here would refuse the reference itself.
            if hit in FORBIDDEN_ATTRIBUTES or hit in _STRING_REFLECTION:
                findings.append(
                    f"line {node.lineno}: the string {hit!r} names a construct this gate refuses, "
                    f"and a name in a string is still a name"
                )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    findings.append(f"line {node.lineno}: import of {alias.name!r} is not on the allowlist")
        elif isinstance(node, ast.ImportFrom):
            # A relative import has no module root to check and resolves against nothing in
            # the runner's isolated path, so it is refused outright rather than left to fail
            # at an unpredictable moment.
            if node.level:
                findings.append(f"line {node.lineno}: relative import is not permitted")
            elif node.module:
                root = node.module.split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    findings.append(f"line {node.lineno}: import from {node.module!r} is not on the allowlist")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                findings.append(f"line {node.lineno}: use of {node.id!r} is not permitted")
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRIBUTES:
                findings.append(f"line {node.lineno}: attribute {node.attr!r} is not permitted")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            # Not dangerous on its own, but a submission that rebinds module globals from
            # inside a call is reshaping state the runner reads, so it is refused.
            if isinstance(node, ast.Global):
                findings.append(f"line {node.lineno}: global rebinding is not permitted")
    return findings


def check_declared_revision(module, expected: int) -> list[str]:
    revision = getattr(module, "FORMAT_REVISION", None) if module is not None else None
    if revision != expected:
        return [
            f"FORMAT_REVISION is {revision!r}, the authoritative schema is revision {expected}"
        ]
    return []
