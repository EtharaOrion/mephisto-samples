# Submission API

The grader imports `submission/codec.py` and calls the names below. A missing name or a different signature is an incomplete submission.

| Name | Kind | Contract |
|---|---|---|
| `encode(values)` | function | takes a list of Python ints, each fitting in signed 64 bits, and returns the chronopack blob as `bytes` |
| `decode(blob)` | function | takes `bytes` and returns the list of ints it encodes |
| `FORMAT_REVISION` | int | the container revision you implement. `spec/FORMAT.md` is revision 1 |
| `predict(values)` | function | takes the same list of ints and returns one list per block. Each entry is a list of six floats, the probability you assign to each encoding id in order 0 to 5, summing to 1. This is read as a statement about your own uncertainty |

`predict` is not optional. A codec that omits it is incomplete. A codec that returns a probability of 1.0 on its chosen encoding for every block is making a claim about its own certainty, and that claim is scored against what the reference actually did.

`decode` is called on blobs the reference produced, never on your own output, so it is exercised independently of your encoder.

## What your codec may import

An allowlist, checked statically before your module is loaded, and enforced again at runtime by an audit hook that denies effects rather than names.

`__future__`, `abc`, `array`, `binascii`, `bisect`, `collections`, `dataclasses`, `enum`, `functools`, `hashlib`, `heapq`, `itertools`, `math`, `struct`, `types`, `typing`, `zlib`.

These names are refused anywhere in your source: `eval`, `exec`, `compile`, `open`, `__import__`, `globals`, `locals`, `vars`, `breakpoint`, `input`, and the `global` statement. A submission that trips the gate is not loaded at all. The forbidden attribute names are also refused as string literals. Ordinary Python is otherwise untouched.

Your codec runs in an isolated interpreter with no filesystem, no network and no subprocess. It receives its input as arguments and returns its output. There is nothing else to reach and nothing there to find.
