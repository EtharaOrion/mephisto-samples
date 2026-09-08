"""Static AST allowlist gate for submitted policies. PUBLIC: the agent can and
should run this locally (check.py does) before submitting.

RL1/RL2: a policy runs at grade time on the judge host, where the hidden
Q1-2026 outcome file lives, so the gate denies every route to the filesystem,
to dynamic code, and to nondeterminism BEFORE execution. Violations are
reported by name; a gated policy scores 0.
"""
from __future__ import annotations

import ast

ALLOWED_IMPORTS = {"math", "statistics", "collections", "itertools",
                   "functools", "heapq", "bisect", "operator"}
DENIED_CALLS = {"open", "eval", "exec", "compile", "__import__", "getattr",
                "setattr", "delattr", "globals", "locals", "vars", "input",
                "breakpoint", "memoryview", "exit", "quit"}


def gate_violations(source: str):
    """Return a list of {rule, lineno, detail} violations. Empty = clean."""
    v = []
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [{"rule": "syntax", "lineno": e.lineno or 0, "detail": str(e)}]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                root = a.name.split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    v.append({"rule": "import_allowlist", "lineno": node.lineno,
                              "detail": root})
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in ALLOWED_IMPORTS:
                v.append({"rule": "import_allowlist", "lineno": node.lineno,
                          "detail": root})
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in DENIED_CALLS:
                v.append({"rule": "denied_builtin", "lineno": node.lineno,
                          "detail": f.id})
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                v.append({"rule": "dunder_attribute", "lineno": node.lineno,
                          "detail": node.attr})
        elif isinstance(node, ast.Name):
            if node.id.startswith("__") and node.id not in ("__name__",):
                v.append({"rule": "dunder_name", "lineno": node.lineno,
                          "detail": node.id})
    return v
