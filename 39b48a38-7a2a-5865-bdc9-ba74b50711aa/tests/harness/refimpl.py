# GENERATED SECTION. DO NOT HAND-EDIT.
# Verbatim copy of solution/reference/codec.py, emitted by solution/recompute.py.
# The verifier grades against these bytes, so the oracle and the checkers cannot
# disagree about what the encoder does.
"""Reference chronopack codec. Private oracle, never agent visible.

The container framing is published in full. The encoder's selection policy is not published
anywhere, and this file is the only statement of it. An agent recovers it by inference over a
recorded corpus of encoded columns, which is a sample of the policy rather than a
specification of it.

Every rule below marked UNDOCUMENTED is a place where a competent, plausible implementation
diverges from this one and produces a different byte, and one different byte fails the whole
column.

CANARY-BLOCK-BEGIN
canary_slot_0: MEPH-373d1916b5939704412ba6efe8590d88
canary_slot_1: MEPH-b788c135a56267dac49d57ee8273bd4e
canary_slot_2: MEPH-c271027e98332e4ff7c37a518d7881ef
canary_slot_3: MEPH-0b50c7a3306d23690a441bc7053f21c3
CANARY-BLOCK-END
"""

from __future__ import annotations

BLOCK = 128

RAW = 0
CONST = 1
FOR_BITPACK = 2
DELTA_BITPACK = 3
RLE = 4
DICT = 5

FORMAT_REVISION = 1

INT64_MIN = -(2 ** 63)
INT64_MAX = 2 ** 63 - 1


class ChronopackError(Exception):
    pass


class CorruptColumn(ChronopackError):
    pass


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------


def _i64(value: int) -> bytes:
    return int(value).to_bytes(8, "little", signed=True)


def _u16(value: int) -> bytes:
    return int(value).to_bytes(2, "little")


def _u32(value: int) -> bytes:
    return int(value).to_bytes(4, "little")


def pack_bits(values: list[int], width: int) -> bytes:
    """LSB-first bit packing. Values must already be non-negative and fit in `width`."""
    if width <= 0:
        return b""
    out = bytearray()
    acc = 0
    filled = 0
    for value in values:
        acc |= (int(value) & ((1 << width) - 1)) << filled
        filled += width
        while filled >= 8:
            out.append(acc & 0xFF)
            acc >>= 8
            filled -= 8
    if filled:
        out.append(acc & 0xFF)
    return bytes(out)


def unpack_bits(blob: bytes, width: int, count: int) -> list[int]:
    if width <= 0:
        return [0] * count
    out = []
    acc = 0
    filled = 0
    cursor = 0
    mask = (1 << width) - 1
    for _ in range(count):
        while filled < width:
            if cursor >= len(blob):
                raise CorruptColumn("bitpack payload is short")
            acc |= blob[cursor] << filled
            cursor += 1
            filled += 8
        out.append(acc & mask)
        acc >>= width
        filled -= width
    return out


def packed_len(count: int, width: int) -> int:
    return (count * width + 7) // 8


# ---------------------------------------------------------------------------
# the width rule
# ---------------------------------------------------------------------------


def length_class(count: int) -> int:
    """UNDOCUMENTED. Four length classes. Every table below is indexed by this."""
    # The boundaries are not round numbers, and that is deliberate. A Phase 3 solver recovered
    # the bracket each boundary lay in and then picked 8, 32 and 96 because they were the only
    # round numbers inside it. That is guessing dressed as inference, and it was right. With
    # 11, 37 and 83 the bracket is the same width and holds nothing memorable, so the boundary
    # has to be measured from the corpus rather than assumed.
    if count < 11:
        return 0
    if count < 37:
        return 1
    if count < 83:
        return 2
    return 3


def magnitude_class(span: int) -> int:
    """UNDOCUMENTED. Four magnitude classes, by the bit length of the span."""
    bits = int(span).bit_length()
    # Off the round numbers for the same reason. A byte, three bytes and six bytes are the
    # first three guesses anyone makes.
    if bits < 11:
        return 0
    if bits < 27:
        return 1
    if bits < 53:
        return 2
    return 3


# UNDOCUMENTED PARAMETER TABLES.
#
# The two tables that decide the most bytes are indexed by BOTH classes at once, and that is
# the point. A probe of six independent solvers recovered the previous one-dimensional version
# completely: every one of them assumed the policy separates, read "the length class fixes an
# alignment and a pad" and "the width rounds on a threshold", and every one of them was right.
# A joint table cannot be recovered that way. Sweeping length with magnitude held loose returns
# an inconsistent answer, because there is no single value to find; the reader has to partition
# the corpus into sixteen cells and read each one, which first requires recovering both sets of
# class boundaries correctly.
#
# Neither table is separable. No f(l)*g(m) and no f(l)+g(m) reproduces either one, so a reader
# who assumes either shape and fits it will be wrong in most cells rather than off by a scale.
FOR_GRAIN = (                         # [length class][magnitude class]
    (8, 32, 16, 128),
    (16, 8, 64, 32),
    (64, 128, 32, 256),
    (32, 64, 128, 512),
)
WIDTH_ROUND = (                       # [length class][magnitude class]
    (1, 3, 4, 8),
    (2, 1, 6, 4),
    (1, 2, 3, 8),
    (4, 2, 1, 6),
)
DELTA_GRAIN = (2, 4, 16, 32)          # by length class
WIDTH_BUMP = (2, 1, 0, 1)             # by length class, extra bits added before rounding
# The three penalty tables below are measured decoration and are documented as such rather than
# advertised as difficulty. Setting all twelve values to zero changes the encoding of 0.9 per
# cent of a nine hundred column probe, because the size gap between the best and second best
# encoding is almost always far wider than a few bytes. They are retained because they do decide
# a handful of genuinely close contests, but no honest account of this task should count them
# among the rules a solver has to recover.
PENALTY_DELTA = (0, 2, 3, 5)          # by length class
PENALTY_RLE = (1, 3, 4, 2)            # by length class
PENALTY_DICT = (6, 5, 3, 4)           # by length class


def bitpack_width(span: int, count: int, mag: int) -> int:
    """Bit width for a block whose largest packed offset is `span`.

    UNDOCUMENTED. The bit length of the packed span, never zero, plus a bump that depends on the
    block's length class, then rounded up to a grain that depends on the length class and the
    magnitude class together. `mag` is the magnitude class of the block's RAW span, taken before
    the minimum is floored, so the grain is fixed by the data rather than by the anchor it
    produces. That ordering is what keeps the rule non-circular and it is recoverable: the raw
    span is visible to anyone who decodes the block.
    """
    width = int(span).bit_length()
    if width == 0:
        width = 1
    width += WIDTH_BUMP[length_class(count)]
    grain = WIDTH_ROUND[length_class(count)][mag]
    if grain > 1:
        width = ((width + grain - 1) // grain) * grain
    return width


def anchor_min(low: int, grain: int) -> int:
    """The stored minimum, floored to a grain.

    UNDOCUMENTED, and the rule that touches nearly every block. The frame stores a minimum and
    the decoder adds it back, so any minimum at or below the true one yields a legal frame.
    This encoder stores the block minimum floored to a grain that depends on the block's length
    class. A reader who stores the true minimum writes a different i64 on almost every block
    and never notices, because the frame still decodes.
    """
    return low - (low % grain)


def for_grain(count: int, mag: int) -> int:
    return FOR_GRAIN[length_class(count)][mag]


def delta_grain(count: int) -> int:
    return DELTA_GRAIN[length_class(count)]


def dict_index_width(table_size: int, count: int) -> int:
    """UNDOCUMENTED. A power of two table indexes one wider than it needs to."""
    span = table_size if table_size and (table_size & (table_size - 1)) == 0 else max(0, table_size - 1)
    return bitpack_width(span, count, magnitude_class(span))


def raw_admissible(count: int) -> bool:
    """UNDOCUMENTED. Raw is not offered on a block of four values or fewer."""
    return count > 4


# ---------------------------------------------------------------------------
# candidate sizes
# ---------------------------------------------------------------------------


def _runs(values: list[int]) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    for value in values:
        if runs and runs[-1][0] == value and runs[-1][1] < 0xFFFF:
            runs[-1] = (value, runs[-1][1] + 1)
        else:
            runs.append((value, 1))
    return runs


def _candidates(values: list[int]) -> dict[int, int]:
    """Byte size of each admissible encoding's payload, keyed by encoding id."""
    count = len(values)
    sizes: dict[int, int] = {}
    distinct = sorted(set(values))
    deltas = [values[i + 1] - values[i] for i in range(count - 1)]
    delta_distinct = len(set(deltas)) if deltas else 0

    if raw_admissible(count):
        sizes[RAW] = 8 * count
    # RAW is withheld as a preference on tiny blocks, never as a possibility. The width bump
    # can push a wide span in a short block past the sixty four bit cap and disqualify every
    # bitpacked candidate, and a block with no admissible encoding is not a format, it is a
    # crash. RAW comes back as the fallback whenever nothing else survives.

    if len(distinct) == 1:
        sizes[CONST] = 8

    runs = _runs(values)
    # UNDOCUMENTED RULE TWO. Run-length is only a candidate when the runs are few relative to
    # the block, at most one run per three values. A plausible encoder offers it whenever it
    # is smaller, and on a block of thirty runs in a hundred values the two disagree.
    if runs and len(runs) * 3 <= count:
        sizes[RLE] = 2 + 10 * len(runs)

    # UNDOCUMENTED RULE THREE. The dictionary is only a candidate when the block holds at most
    # twenty four distinct values AND its deltas hold more than eight. A block that is already
    # smooth in delta space is left to the delta encoder even where a dictionary would be
    # smaller, and that interaction between two different statistics is the rule least likely
    # to be guessed from the shape of the format alone.
    if len(distinct) <= 24 and delta_distinct > 8:
        index_width = dict_index_width(len(distinct), count)
        sizes[DICT] = 1 + 8 * len(distinct) + 1 + packed_len(count, index_width)

    # UNDOCUMENTED RULE FOUR. Delta is disqualified when any delta falls outside signed
    # thirty two bit range, even though every value and every delta is stored as sixty four
    # bit. The obvious reading is that a sixty four bit format has no thirty two bit limit.
    if deltas and all(-(2 ** 31) <= d < 2 ** 31 for d in deltas):
        mag = magnitude_class(max(deltas) - min(deltas))
        low = anchor_min(min(deltas), delta_grain(count))
        width = bitpack_width(max(deltas) - low, count - 1, mag)
        if width <= 64:
            sizes[DELTA_BITPACK] = 8 + 8 + 1 + packed_len(count - 1, width)

    mag = magnitude_class(distinct[-1] - distinct[0])
    low = anchor_min(distinct[0], for_grain(count, mag))
    width = bitpack_width(distinct[-1] - low, count, mag)
    if width <= 64:
        sizes[FOR_BITPACK] = 8 + 1 + packed_len(count, width)

    return sizes


# UNDOCUMENTED RULE FIVE. Each encoding carries a fixed penalty added to its measured size
# before the comparison. The penalties are not proportional to anything a reader can see and
# they decide every close contest.
def penalties(count: int) -> dict:
    """UNDOCUMENTED. The additive penalty of each encoding depends on the length class."""
    cls = length_class(count)
    return {
        RAW: 0,
        CONST: 0,
        FOR_BITPACK: 0,
        DELTA_BITPACK: PENALTY_DELTA[cls],
        RLE: PENALTY_RLE[cls],
        DICT: PENALTY_DICT[cls],
    }

# UNDOCUMENTED RULE SIX. Ties break in this order, which is not the encoding id order, and
# the order changes for a short block: below sixty four values delta outranks dictionary.
TIE_ORDER_LONG = (CONST, DICT, DELTA_BITPACK, RLE, FOR_BITPACK, RAW)
TIE_ORDER_SHORT = (CONST, DELTA_BITPACK, DICT, RLE, FOR_BITPACK, RAW)


def choose(values: list[int]) -> int:
    """The encoding this codec selects for one block."""
    if not values:
        return RAW
    sizes = _candidates(values)
    if not sizes:
        sizes[RAW] = 8 * len(values)
    table = penalties(len(values))
    scored = {kind: size + table[kind] for kind, size in sizes.items()}
    best = min(scored.values())
    tied = {kind for kind, score in scored.items() if score == best}
    order = TIE_ORDER_SHORT if len(values) < 64 else TIE_ORDER_LONG
    for kind in order:
        if kind in tied:
            return kind
    return RAW


# ---------------------------------------------------------------------------
# block encoding
# ---------------------------------------------------------------------------


def encode_block(values: list[int]) -> bytes:
    kind = choose(values)
    count = len(values)
    body = bytearray(bytes([kind]) + _u16(count))

    if kind == RAW:
        for value in values:
            body += _i64(value)
    elif kind == CONST:
        body += _i64(values[0])
    elif kind == FOR_BITPACK:
        mag = magnitude_class(max(values) - min(values))
        low = anchor_min(min(values), for_grain(count, mag))
        width = bitpack_width(max(values) - low, count, mag)
        body += _i64(low) + bytes([width]) + pack_bits([v - low for v in values], width)
    elif kind == DELTA_BITPACK:
        deltas = [values[i + 1] - values[i] for i in range(count - 1)]
        mag = magnitude_class(max(deltas) - min(deltas))
        low = anchor_min(min(deltas), delta_grain(count))
        width = bitpack_width(max(deltas) - low, count - 1, mag)
        body += _i64(values[0]) + _i64(low) + bytes([width])
        body += pack_bits([d - low for d in deltas], width)
    elif kind == RLE:
        runs = _runs(values)
        body += _u16(len(runs))
        for value, length in runs:
            body += _i64(value) + _u16(length)
    elif kind == DICT:
        table = sorted(set(values))
        index_of = {value: index for index, value in enumerate(table)}
        width = dict_index_width(len(table), count)
        body += bytes([len(table)])
        for value in table:
            body += _i64(value)
        body += bytes([width]) + pack_bits([index_of[v] for v in values], width)
    else:
        raise ChronopackError("unreachable encoding %d" % kind)
    return bytes(body)


def decode_block(blob: bytes, offset: int) -> tuple[list[int], int]:
    if offset + 3 > len(blob):
        raise CorruptColumn("truncated block header")
    kind = blob[offset]
    count = int.from_bytes(blob[offset + 1 : offset + 3], "little")
    cursor = offset + 3

    def take_i64() -> int:
        nonlocal cursor
        if cursor + 8 > len(blob):
            raise CorruptColumn("truncated i64")
        value = int.from_bytes(blob[cursor : cursor + 8], "little", signed=True)
        cursor += 8
        return value

    if kind == RAW:
        values = [take_i64() for _ in range(count)]
    elif kind == CONST:
        values = [take_i64()] * count
    elif kind == FOR_BITPACK:
        low = take_i64()
        width = blob[cursor]
        cursor += 1
        size = packed_len(count, width)
        values = [low + offset_value for offset_value in unpack_bits(blob[cursor : cursor + size], width, count)]
        cursor += size
    elif kind == DELTA_BITPACK:
        first = take_i64()
        low = take_i64()
        width = blob[cursor]
        cursor += 1
        size = packed_len(count - 1, width)
        deltas = [low + d for d in unpack_bits(blob[cursor : cursor + size], width, count - 1)]
        cursor += size
        values = [first]
        for delta in deltas:
            values.append(values[-1] + delta)
    elif kind == RLE:
        run_count = int.from_bytes(blob[cursor : cursor + 2], "little")
        cursor += 2
        values = []
        for _ in range(run_count):
            value = take_i64()
            length = int.from_bytes(blob[cursor : cursor + 2], "little")
            cursor += 2
            values.extend([value] * length)
    elif kind == DICT:
        table_size = blob[cursor]
        cursor += 1
        table = [take_i64() for _ in range(table_size)]
        width = blob[cursor]
        cursor += 1
        size = packed_len(count, width)
        values = [table[index] for index in unpack_bits(blob[cursor : cursor + size], width, count)]
        cursor += size
    else:
        raise CorruptColumn("unknown encoding %d" % kind)

    if len(values) != count:
        raise CorruptColumn("block decoded to %d values, header said %d" % (len(values), count))
    return values, cursor


# ---------------------------------------------------------------------------
# column encoding
# ---------------------------------------------------------------------------


def column_digest(body: bytes, value_count: int) -> int:
    """The u32 trailer.

    UNDOCUMENTED RULE SEVEN. The framing says a column ends with a four byte digest and does
    not say how it is computed. The constants below are the standard FNV-1a offset and prime,
    so the arithmetic is recognisable to anyone who tries it. What is not stated anywhere is
    the domain, which includes the four byte block count header and not only the blocks, and
    the finalisation, which folds in the number of values with Knuth's multiplicative constant.
    A reader recovers all three from the corpus by trying the obvious hash over the obvious
    domain and then chasing the difference.
    """
    digest = 0x811C9DC5
    for byte in body:
        digest = ((digest ^ byte) * 0x01000193) & 0xFFFFFFFF
    return (digest ^ ((value_count * 2654435761) & 0xFFFFFFFF)) & 0xFFFFFFFF


def encode(values: list[int]) -> bytes:
    for value in values:
        if not INT64_MIN <= int(value) <= INT64_MAX:
            raise ChronopackError("value does not fit in int64")
    blocks = [values[i : i + BLOCK] for i in range(0, len(values), BLOCK)] or [[]]
    if not values:
        blocks = []
    out = bytearray(_u32(len(blocks)))
    for block in blocks:
        out += encode_block(list(block))
    out += _u32(column_digest(bytes(out), len(values)))
    return bytes(out)


def decode(blob: bytes, verify_digest: bool = True) -> list[int]:
    """Decode a column. `verify_digest` is False only for the recoverability check.

    The red line asks whether the values survive, which is a question about the frames. The
    trailer is a policy rule and a wrong one costs the exactness lanes, not the run: a column
    whose every value comes back intact has not been lost, whatever its last four bytes say.
    """
    if len(blob) < 8:
        raise CorruptColumn("truncated column header")
    block_count = int.from_bytes(blob[:4], "little")
    cursor = 4
    values: list[int] = []
    for _ in range(block_count):
        block, cursor = decode_block(blob, cursor)
        values.extend(block)
    stored = int.from_bytes(blob[cursor : cursor + 4], "little")
    if cursor + 4 != len(blob):
        raise CorruptColumn("trailing bytes after the digest")
    if verify_digest and stored != column_digest(blob[:cursor], len(values)):
        raise CorruptColumn("column digest mismatch")
    return values


def predict(values: list[int]) -> list[list[float]]:
    """The reference's own statement of its uncertainty, which is none.

    It knows the policy because it is the policy, so it puts all of its mass on the encoding
    it will choose. That is the only honest prediction available to it, and it is what the
    calibration lane rewards: certainty that is earned. A submission that has recovered less
    of the policy and says so scores more than one that copies this shape without the
    knowledge behind it.
    """
    out = []
    for index in range(0, len(values), BLOCK):
        row = [0.0] * 6
        row[choose(list(values[index : index + BLOCK]))] = 1.0
        out.append(row)
    return out


def block_choices(values: list[int]) -> list[int]:
    """The encoding this codec selects for each block. Used by the grader's partial lane."""
    return [choose(list(values[i : i + BLOCK])) for i in range(0, len(values), BLOCK)]
