"""Your chronopack codec. This file is what the grader imports.

Read spec/FORMAT.md for the container framing, which is published in full, and spec/API.md
for the names the grader calls. The encoder's policy is published nowhere. Recover it from
the recorded corpus in corpus/.
"""

from __future__ import annotations

FORMAT_REVISION = 0  # Set this to the framing revision you implement.


def encode(values: list[int]) -> bytes:
    """Encode a column of int64 values into a chronopack blob."""
    raise NotImplementedError("encode")


def decode(blob: bytes) -> list[int]:
    """Decode a chronopack blob back into its column of int64 values."""
    raise NotImplementedError("decode")


def predict(values: list[int]) -> list[list[float]]:
    """For each block, the probability you assign to each of the six encodings, in id order.

    Returns one list of six floats per block, each summing to one. This is a statement about
    your own uncertainty and it is read as one.
    """
    raise NotImplementedError("predict")
