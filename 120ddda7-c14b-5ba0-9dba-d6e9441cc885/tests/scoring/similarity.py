"""floor_corrected_similarity for libpcap_bpf_codegen_fidelity.

Pure Python 3.11 standard library. No I/O, no clock, deterministic.

Frozen definition (seed/contract.yaml scoring.floor_corrected_similarity):

    sim is the normalized similarity between the candidate instruction tuple
    sequence and the golden sequence. sim_floor is that same similarity
    measured for the fixed trivial program `ret #0` -- [[6,0,0,0]] --
    against the same golden sequence. The awarded value is

        max(0, (sim - sim_floor) / (1 - sim_floor))

The point of the floor correction, per the contract's own rationale, is that
a constant program, an accept-all program and a reject-all program each score
exactly 0.00 instead of collecting a free floor. test_similarity.py proves
that property against real libpcap-1.10.6 output.

Choice of `sim`
---------------
`sim` is ``difflib.SequenceMatcher.ratio()`` over the two instruction
sequences, with each instruction treated as one atomic ``(code, jt, jf, k)``
token:

    ratio = 2 * M / T

where M is the number of matched instructions and T the total length of both
sequences. It is normalized to [0, 1] by construction, it is 1.0 exactly when
the sequences are equal, it is order-sensitive (an instruction only matches
inside a common subsequence, so a permuted program does not score as a
correct one), and it is in the standard library.

Two mechanical details that matter for reproducibility:

  * ``autojunk=False`` is mandatory. SequenceMatcher's default "popular
    element" heuristic starts discarding tokens once the b-sequence reaches
    200 elements, which would silently change the score for long programs.
  * argument order is fixed as ``SequenceMatcher(None, candidate, golden)``
    and used identically for sim and sim_floor. ratio() is not perfectly
    symmetric under argument swap, so the order is pinned rather than left
    to the caller.

Instructions are compared as exact unsigned 4-tuples. No masking or
normalization of k is applied, so the notion of "equal instruction" used
here is byte-identical to the one used for the exact-match check in
score.py.
"""

from __future__ import annotations

import difflib

__all__ = [
    "TRIVIAL_PROGRAM",
    "normalize_program",
    "similarity",
    "similarity_floor",
    "floor_corrected_similarity",
]

# `ret #0` -- BPF_RET|BPF_K with k=0. The fixed floor probe named by the
# contract. Also, on its own, the canonical reject-all program.
TRIVIAL_PROGRAM: tuple[tuple[int, int, int, int], ...] = ((6, 0, 0, 0),)


def normalize_program(prog) -> tuple[tuple[int, int, int, int], ...]:
    """Coerce a program into a hashable tuple-of-tuples.

    Instructions that are not 4-element integer sequences are preserved as
    an opaque, still-hashable token so they simply fail to match anything
    rather than raising. Callers that need to *reject* such a program use
    validator.validate; this module only measures.
    """
    if prog is None:
        return ()
    out = []
    for ins in prog:
        if isinstance(ins, (str, bytes)):
            out.append(("?", ins))
            continue
        try:
            fields = tuple(ins)
        except TypeError:
            out.append(("?", repr(ins)))
            continue
        if len(fields) == 4 and all(
            isinstance(v, int) and not isinstance(v, bool) for v in fields
        ):
            out.append((fields[0], fields[1], fields[2], fields[3]))
        else:
            out.append(("?", repr(fields)))
    return tuple(out)


def similarity(candidate, golden) -> float:
    """Normalized similarity of two instruction sequences, in [0, 1]."""
    a = normalize_program(candidate)
    b = normalize_program(golden)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def similarity_floor(golden) -> float:
    """sim measured for the fixed trivial program `ret #0` against golden."""
    return similarity(TRIVIAL_PROGRAM, golden)


def floor_corrected_similarity(candidate, golden) -> float:
    """max(0, (sim - sim_floor) / (1 - sim_floor)), clipped to [0, 1]."""
    sim = similarity(candidate, golden)
    floor = similarity_floor(golden)

    if floor >= 1.0:
        # golden IS the trivial program, so there is no headroom above the
        # floor and nothing can earn similarity credit. Unreachable in
        # practice: such a candidate would have matched exactly and been
        # scored 1.00 before similarity was consulted.
        return 0.0

    value = (sim - floor) / (1.0 - floor)
    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return value
