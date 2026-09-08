"""Sealed-seed column generation. Never agent visible.

Every graded column is regenerated here from a sealed seed at scoring time, so no column the
agent could observe is a column it is graded on.

Two distributions are defined. `typical` is the one the public corpus is drawn from: the
column shapes a reader would think of first. `graded` draws from the same shape vocabulary and
additionally over-samples the conditions the encoder's undocumented rules turn on, because a
policy is not recovered by fitting the common case. The instruction says plainly that the
corpus is a sample rather than a specification, so this is a stated property of the task and
not a trap sprung on a careful reader.

CANARY-BLOCK-BEGIN
canary_slot_0: MEPH-373d1916b5939704412ba6efe8590d88
canary_slot_1: MEPH-b788c135a56267dac49d57ee8273bd4e
canary_slot_2: MEPH-c271027e98332e4ff7c37a518d7881ef
canary_slot_3: MEPH-0b50c7a3306d23690a441bc7053f21c3
CANARY-BLOCK-END
"""

from __future__ import annotations

import hashlib


class Stream:
    """A deterministic byte stream keyed by a seed. No global state."""

    def __init__(self, seed: bytes) -> None:
        self.seed = seed
        self.counter = 0
        self._buf = b""

    def _refill(self) -> None:
        self._buf += hashlib.sha256(self.seed + self.counter.to_bytes(8, "big")).digest()
        self.counter += 1

    def bytes(self, count: int) -> bytes:
        while len(self._buf) < count:
            self._refill()
        out, self._buf = self._buf[:count], self._buf[count:]
        return out

    def below(self, bound: int) -> int:
        if bound <= 0:
            raise ValueError("bound must be positive")
        return int.from_bytes(self.bytes(8), "big") % bound

    def between(self, low: int, high: int) -> int:
        return low + self.below(high - low + 1)

    def choice(self, items):
        return items[self.below(len(items))]


# Shapes a reader thinks of first.
TYPICAL_SHAPES = (
    "constant", "runs", "smooth", "small_dict", "wide_random", "mixed",
    # Added so the corpus determines what it previously only hinted at.
    "delta_varied",      # delta ranges other than the single -5..+5 the corpus used to carry
    "midwidth",          # raw widths landing in 9..15, where the rounding threshold lives
    "tie_forced",        # blocks where two encodings cost the same, to pin the tie order
    "dict_edge",         # table sizes either side of the dictionary guard
    "magnitude_ladder",  # spans stepped across every magnitude class the width grain turns on
    "magnitude_ladder",  # weighted twice: sixteen cells need evidence, not four
)

# The same vocabulary plus the shapes that sit on the undocumented rules: blocks whose run
# count sits near the run gate, blocks with few distinct values but smooth deltas, blocks whose
# deltas cross the thirty two bit line, and blocks short enough to change the tie order.
GRADED_SHAPES = TYPICAL_SHAPES + (
    "delta_varied", "midwidth", "tie_forced", "dict_edge",   # over-sampled on purpose
    "magnitude_ladder", "magnitude_ladder",                  # over-sampled: the grain is joint
    "runs_near_gate",
    "dict_smooth_delta",
    "delta_over_int32",
    "short_tied",
    "boundary_length",
)

# The corpus must exercise every length class the encoder's rules turn on, or a rule is
# not underdetermined by the corpus, it is invisible in it, and a task that hides a rule
# is a lottery rather than an inference problem.
# The corpus must reach every band the policy turns on, or a parameter is not
# underdetermined by the corpus, it is invisible in it, and grading it is a lottery. A Phase 3
# solver reached 300/300 on the corpus while guessing six parameters, because no corpus block
# had a population between 9 and 14, between 33 and 62, or between 73 and 99, which is exactly
# where the class boundaries live. These lengths put blocks in all three.
LENGTHS_TYPICAL = (
    1, 3, 7, 9, 11, 14, 15, 16, 20, 26, 31, 33, 40, 48, 55, 62, 63, 64, 65,
    73, 80, 88, 96, 99, 100, 110, 127, 128, 129, 137, 160, 200, 224, 256, 289, 384, 512,
)
# The graded set concentrates on the bands the corpus now determines but does not hand over.
# A solver that guesses a round boundary instead of running the sweep loses most of the
# exactness lanes here rather than eight percent of one.
LENGTHS_GRADED = (
    9, 10, 11, 12, 13, 14,            # A/B boundary band
    33, 38, 44, 51, 57, 62,           # B/C boundary band
    73, 78, 84, 90, 95, 99,           # C/D boundary band
    137, 141, 161, 175, 190,          # last blocks landing in those bands again
    1, 7, 64, 128, 256,               # a minority outside them, so the set is not a monoculture
)


def _column(stream: Stream, shape: str, length: int) -> list[int]:
    if shape == "constant":
        return [stream.between(-(10 ** 6), 10 ** 6)] * length
    if shape == "runs":
        out: list[int] = []
        while len(out) < length:
            out += [stream.between(0, 50)] * stream.between(3, 20)
        return out[:length]
    if shape == "smooth":
        value = stream.between(-(10 ** 9), 10 ** 9)
        out = [value]
        for _ in range(length - 1):
            value += stream.between(-5, 5)
            out.append(value)
        return out[:length]
    if shape == "small_dict":
        table = [stream.between(-(10 ** 5), 10 ** 5) for _ in range(stream.between(2, 12))]
        return [stream.choice(table) for _ in range(length)]
    if shape == "wide_random":
        return [stream.between(-(2 ** 62), 2 ** 62) for _ in range(length)]
    if shape == "mixed":
        return [stream.between(-(10 ** 4), 10 ** 4) for _ in range(length)]

    if shape == "delta_varied":
        # Deltas spanning several magnitudes, so the delta stride is observable per class
        # rather than resting on one distinct data point.
        width = stream.choice([3, 40, 900, 70000, 5_000_000])
        value = stream.between(-(10 ** 8), 10 ** 8)
        out = [value]
        for _ in range(length - 1):
            value += stream.between(-width, width)
            out.append(value)
        return out[:length]
    if shape == "magnitude_ladder":
        # Spans stepped across every magnitude class, because the width grain and the FOR
        # alignment are indexed by that class jointly with the length class and a cell nobody
        # can observe is a cell nobody can infer. Measured before this shape existed: the corpus
        # held zero blocks with a span between 27 and 52 bits in three of the four length
        # classes and exactly one in the fourth, which is the band where the grain coarsens. Six
        # independent probe solvers scored 1.000 on every magnitude class the corpus reached and
        # 0.383 on the one it did not, and every one of them named the gap in its own report.
        # Grading a parameter the evidence cannot pin is a lottery, so the evidence now pins it.
        # The magnitude CLASS is drawn uniformly and the bit width is drawn inside it, rather
        # than drawing the bit width uniformly. Drawing the width uniformly samples each class
        # in proportion to how many bit widths it spans, which left the 27..52 band with one to
        # six observations per length class: present, but too thin to pin a parameter from.
        MAG_BANDS = ((2, 10), (11, 26), (27, 52), (53, 61))
        lo, hi = MAG_BANDS[stream.below(4)]
        bits = stream.between(lo, hi)
        span = stream.between(1 << (bits - 1), (1 << bits) - 1)
        base = stream.between(-(2 ** 62), (2 ** 62) - span)
        if length <= 1:
            return [base] * length
        # The extremes are placed explicitly so the block's raw span is exactly `span` and the
        # magnitude class of the observation is the one this shape intended.
        out = [base, base + span]
        for _ in range(length - 2):
            out.append(base + stream.below(span + 1))
        return out[:length]
    if shape == "midwidth":
        # Spans whose bit length lands in 9..15, where the width rounding threshold lives and
        # where the corpus previously had no observation at all.
        bits = stream.between(9, 15)
        span = (1 << bits) - 1
        base = stream.between(-(2 ** 30), 2 ** 30)
        return [base + stream.below(span + 1) for _ in range(length)]
    if shape == "tie_forced":
        # Small alphabets in short blocks, where several encodings land on the same cost and
        # the tie order is the only thing that decides.
        table = [stream.between(0, 7) for _ in range(stream.between(2, 4))]
        return [stream.choice(table) for _ in range(length)]
    if shape == "dict_edge":
        # Table sizes either side of the dictionary guard, including the powers of two whose
        # index width carries the off-by-one.
        size = stream.choice([2, 3, 4, 5, 7, 8, 9, 16, 17])
        table = [stream.between(-(10 ** 6), 10 ** 6) for _ in range(size)]
        return [stream.choice(table) for _ in range(length)]

    if shape == "runs_near_gate":
        # Run count lands close to one third of the block, which is where the run gate decides.
        out = []
        target = max(1, length // stream.between(2, 4))
        while len(out) < length:
            out += [stream.between(0, 30)] * max(1, length // max(1, target))
        return out[:length]
    if shape == "dict_smooth_delta":
        # Few distinct values arranged so the deltas are smooth. The dictionary gate turns on
        # a statistic of the deltas rather than of the values.
        table = sorted(stream.between(0, 40) for _ in range(stream.between(3, 10)))
        out = []
        index = 0
        while len(out) < length:
            out.append(table[index % len(table)])
            index += 1
        return out[:length]
    if shape == "delta_over_int32":
        # Deltas straddle the signed thirty two bit line in both directions.
        value = 0
        out = [value]
        for _ in range(length - 1):
            step = stream.choice([1, -1, 2 ** 31 - 1, -(2 ** 31), 2 ** 31, -(2 ** 31) - 1])
            value += step
            out.append(value)
        return out[:length]
    if shape == "short_tied":
        # Short blocks with a small span, where several encodings land on the same score and
        # the tie order decides.
        return [stream.between(0, 3) for _ in range(length)]
    if shape == "boundary_length":
        base = stream.between(-100, 100)
        return [base + stream.between(0, 7) for _ in range(length)]
    raise ValueError("unknown shape %s" % shape)


# Columns built to sit on several class boundaries at once. Length lands on a length-class
# edge and span lands on a magnitude-class edge, so a reader who fitted one table cell from
# the interior of its class writes the wrong width, the wrong minimum and the wrong penalty
# on the same block.
BOUNDARY_LENGTHS = (7, 8, 9, 31, 32, 33, 95, 96, 97, 127, 128, 129)
BOUNDARY_SPAN_BITS = (7, 8, 9, 23, 24, 25, 47, 48, 49)


def adversarial_columns(seed: bytes, count: int) -> list[dict]:
    """Columns placed on the seams of every class the policy is indexed by."""
    stream = Stream(seed)
    out = []
    for index in range(count):
        length = BOUNDARY_LENGTHS[index % len(BOUNDARY_LENGTHS)]
        bits = BOUNDARY_SPAN_BITS[(index // len(BOUNDARY_LENGTHS)) % len(BOUNDARY_SPAN_BITS)]
        span = (1 << bits) - 1
        base = stream.between(-(2 ** 40), 2 ** 40)
        shape = index % 4
        if shape == 0:
            values = [base + stream.below(span + 1) for _ in range(length)]
        elif shape == 1:
            values = [base, base + span] + [base + stream.below(span + 1) for _ in range(length - 2)]
            values = values[:length]
        elif shape == 2:
            value = base
            values = [value]
            for _ in range(length - 1):
                value += stream.below(max(2, span // max(1, length)))
                values.append(value)
            values = values[:length]
        else:
            table = [base + stream.below(span + 1) for _ in range(min(8, max(2, length // 4)))]
            values = [stream.choice(table) for _ in range(length)]
        out.append(
            {
                "id": f"a{index:04d}_n{length}_b{bits}",
                "shape": f"boundary_n{length}_b{bits}",
                "values": values[:length] if length else [],
            }
        )
    return out


# Length and magnitude bands, in the same order as the classes the encoder computes.
LENGTH_BANDS = ((1, 10), (11, 36), (37, 82), (83, 128))
MAGNITUDE_BANDS = ((2, 10), (11, 26), (27, 52), (53, 61))

# Sixteen cells, this many columns apiece, placed by construction at the head of every set.
CELL_SWEEP_REPEATS = 16


def _cell_column(stream: Stream, lclass: int, mclass: int, repeat: int) -> tuple[str, list[int]]:
    """One column that is a single block landing exactly in cell (lclass, mclass).

    Sampling length and magnitude independently does not cover the grid. Long columns pile
    every one of their blocks into the top length class while short columns contribute one
    block each, so the short-and-wide cells stayed at two to four observations however the
    shape vocabulary was reweighted. The alignment and the width grain are indexed by both
    classes at once, so a cell with four observations is a parameter the corpus gestures at
    rather than pins. These columns are constructed per cell so the grid is covered by
    construction and the count per cell is a property of the generator rather than of luck.
    """
    lo_n, hi_n = LENGTH_BANDS[lclass]
    lo_b, hi_b = MAGNITUDE_BANDS[mclass]
    # The length walks its band deterministically across the repeats instead of being drawn at
    # random, because one length in the band carries evidence no other length carries: RAW is
    # withheld below five values, so a block of two to four is the only place a bitpacked
    # encoding is forced to win and the width byte is therefore the only place the grain is
    # written down. Drawing at random left the short-and-wide cell with thirteen blocks that
    # all chose RAW or RLE, and a grain nobody writes is a grain nobody can read: that cell
    # admitted three candidate values against the corpus while the other fifteen admitted one.
    span_n = hi_n - lo_n + 1
    length = lo_n + (repeat * 3 + stream.below(2)) % span_n
    bits = stream.between(lo_b, hi_b)
    span = stream.between(1 << (bits - 1), (1 << bits) - 1)
    base = stream.between(-(2 ** 62), (2 ** 62) - span)
    if length == 1:
        # One value has span zero, so it would land in magnitude class zero whatever this cell
        # intended. Two is the shortest column that can witness a magnitude at all.
        length = 2
    values = [base, base + span]
    for _ in range(length - 2):
        values.append(base + stream.below(span + 1))
    return "cell", values[:length]


def columns(seed: bytes, count: int, graded: bool) -> list[dict]:
    """Generate `count` labelled columns from `seed`."""
    stream = Stream(seed)
    shapes = GRADED_SHAPES if graded else TYPICAL_SHAPES
    lengths = LENGTHS_GRADED if graded else LENGTHS_TYPICAL
    out = []
    prefix = "g" if graded else "p"

    # Deterministic grid sweep first, so every (length class, magnitude class) cell is
    # observed whatever the random draw does afterwards.
    sweep = CELL_SWEEP_REPEATS * len(LENGTH_BANDS) * len(MAGNITUDE_BANDS)
    for index in range(min(sweep, count)):
        cell = index % (len(LENGTH_BANDS) * len(MAGNITUDE_BANDS))
        lclass, mclass = divmod(cell, len(MAGNITUDE_BANDS))
        shape, values = _cell_column(stream, lclass, mclass, index // (len(LENGTH_BANDS) * len(MAGNITUDE_BANDS)))
        out.append(
            {
                "id": f"{prefix}{index:04d}_{shape}_l{lclass}m{mclass}",
                "shape": shape,
                "values": values,
            }
        )

    for index in range(len(out), count):
        shape = shapes[index % len(shapes)] if graded else stream.choice(shapes)
        length = stream.choice(lengths)
        out.append(
            {
                "id": f"{prefix}{index:04d}_{shape}_{length}",
                "shape": shape,
                "values": _column(stream, shape, length),
            }
        )
    return out
