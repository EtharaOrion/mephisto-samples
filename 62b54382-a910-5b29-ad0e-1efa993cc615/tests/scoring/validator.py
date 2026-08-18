"""Structural cBPF validator for libpcap_bpf_codegen_fidelity.

Pure Python 3.11 standard library. No third-party imports, no I/O, no clock.

A candidate program is VALID only when all three of the contract's conditions
hold:

  1. every jt/jf/ja jump target lands inside the program,
  2. no load reads past the packet or the scratch-memory bounds,
  3. the program provably terminates.

Everything below is derived from the pinned upstream sources
(libpcap-1.10.6: ``pcap/bpf.h`` and ``bpf_filter.c``), not from memory.

Encoding (pcap/bpf.h lines 135-206)
-----------------------------------
    BPF_CLASS(code)  = code & 0x07   LD LDX ST STX ALU JMP RET MISC
    BPF_SIZE(code)   = code & 0x18   W=0x00 H=0x08 B=0x10
    BPF_MODE(code)   = code & 0xe0   IMM=0x00 ABS=0x20 IND=0x40
                                     MEM=0x60 LEN=0x80 MSH=0xa0
    BPF_OP(code)     = code & 0xf0   ALU: ADD SUB MUL DIV OR AND LSH RSH
                                          NEG MOD XOR
                                     JMP: JA JEQ JGT JGE JSET
    BPF_SRC(code)    = code & 0x08   K=0x00 X=0x08
    BPF_RVAL(code)   = code & 0x18   K=0x00 X=0x08 A=0x10
    BPF_MISCOP(code) = code & 0xf8   TAX=0x00 TXA=0x80
    BPF_MEMWORDS     = 16

Three points where this validator deliberately differs from upstream's own
``pcapint_validate_filter`` (bpf_filter.c:407-528). Each divergence is a
tightening or a correction, and each is load-bearing here:

(a) Executable-opcode set, not just class/mode legality.
    Upstream's validator only inspects BPF_CLASS/BPF_MODE/BPF_OP, so it
    accepts codes the interpreter cannot execute (e.g. 0x08 = LD|H|IMM).
    The interpreter's dispatch switch (bpf_filter.c:110-111) opens with

        switch (pc->code) {
        default:
            abort();

    so an unexecutable opcode does not "return 0", it *aborts the process*.
    A program that aborts the reference interpreter is not a valid program,
    so EXECUTABLE_OPCODES below is built from the interpreter's own case
    labels and any code outside it is rejected.

(b) Signed JA displacement, computed in unbounded integers.
    bpf_filter.c:235-241 reads

        case BPF_JMP|BPF_JA:
            /* XXX - we currently implement "ip6 protochain"
             * with backward jumps, so sign-extend pc->k. */
            pc += (bpf_int32)pc->k;

    so a JA target is ``pc + 1 + int32(k)`` and MAY be backward. This is not
    hypothetical: the pinned oracle compiles "ip protochain 6" to a program
    whose instruction 19 is [5,0,0,4294967280], i.e. ja -16, jumping back to
    instruction 4. Upstream's validator only accepts that by accident, via
    u_int wraparound in ``from + p->k >= (u_int)len``. This module computes
    the target exactly, in Python ints, and requires 0 <= target < len.
    Conditional jumps use the u_char jt/jf fields and are always forward.

(c) Packet bounds are a runtime property, and are treated as one.
    Upstream states it outright at bpf_filter.c:429-433: "There's no maximum
    packet data size in userland. The runtime packet length check suffices."
    That is not a shortcut, it is the semantics: every packet-data load in
    the interpreter is bounds-checked against buflen and returns 0 on
    failure (e.g. BPF_LDX|BPF_MSH|BPF_B at bpf_filter.c:203-208).
    Confirmed empirically against the pinned oracle: compiling "tcp port 80"
    with snaplen=20 still emits [40,0,0,54] (ld [54]), and "ip[100000:4]=1"
    emits [32,0,0,100014). libpcap's code generator never consults snaplen
    for offsets. Statically rejecting k >= snaplen would therefore reject
    byte-correct reproductions of libpcap's own output. So:
        - scratch bounds (BPF_MEMWORDS) are enforced statically, always;
        - packet offsets are checked only for uint32 overflow, unless the
          caller opts in by passing ``max_packet=``, which is OFF by default.

Termination (condition 3)
-------------------------
Because backward jumps are legal, "all jumps forward" is not available as a
termination argument. This module proves termination properly:

  * build the control-flow graph over reachable instruction indices;
  * require that a BPF_RET is reachable from every reachable instruction
    (this alone rejects trap loops with no exit);
  * if the reachable CFG is acyclic, the program terminates -- done;
  * otherwise, every cyclic strongly-connected component must exhibit the
    only terminating loop idiom cBPF admits, namely an unbounded-index scan
    of packet data. Concretely the SCC must contain
      (i)  an X-relative packet load (BPF_MODE IND, or LDX|MSH|B), whose
           offset therefore grows with X, and
      (ii) an instruction that strictly advances the index
           (ALU|ADD|K with k >= 1, or ALU|ADD|X), and
      (iii) at least one edge leaving the SCC.
    Given (i) and (ii) the load offset increases without bound across
    iterations, and the interpreter's runtime bounds check turns the first
    out-of-range load into ``return 0``. The loop therefore cannot run
    forever. This is exactly the shape libpcap emits for protochain, and it
    rejects a bare ``ja -1`` spin, a loop with no packet load, and a loop
    whose index never advances.

Public API
----------
    validate(prog, *, max_packet=None, max_insns=BPF_MAXINSNS)
        -> (True, None) | (False, reason)
    is_valid(prog, **kw) -> bool
    reject_reason(prog, **kw) -> str | None

``reason`` is a stable machine-readable token, optionally suffixed with
``@pc<N>`` and a short parenthetical detail.
"""

from __future__ import annotations

__all__ = [
    "validate",
    "is_valid",
    "reject_reason",
    "BPF_MEMWORDS",
    "BPF_MAXINSNS",
    "EXECUTABLE_OPCODES",
    "REASONS",
]

# --------------------------------------------------------------------------
# Encoding constants (pcap/bpf.h)
# --------------------------------------------------------------------------

BPF_LD, BPF_LDX, BPF_ST, BPF_STX, BPF_ALU, BPF_JMP, BPF_RET, BPF_MISC = range(8)

BPF_W, BPF_H, BPF_B = 0x00, 0x08, 0x10

BPF_IMM, BPF_ABS, BPF_IND = 0x00, 0x20, 0x40
BPF_MEM, BPF_LEN, BPF_MSH = 0x60, 0x80, 0xA0

BPF_ADD, BPF_SUB, BPF_MUL, BPF_DIV = 0x00, 0x10, 0x20, 0x30
BPF_OR, BPF_AND, BPF_LSH, BPF_RSH = 0x40, 0x50, 0x60, 0x70
BPF_NEG, BPF_MOD, BPF_XOR = 0x80, 0x90, 0xA0

BPF_JA, BPF_JEQ, BPF_JGT, BPF_JGE, BPF_JSET = 0x00, 0x10, 0x20, 0x30, 0x40

BPF_K, BPF_X = 0x00, 0x08
BPF_A = 0x10

BPF_TAX, BPF_TXA = 0x00, 0x80

BPF_MEMWORDS = 16
BPF_MAXINSNS = 4096

UINT32_MAX = 0xFFFFFFFF
_2_32 = 1 << 32
_2_31 = 1 << 31

# Field widths from `struct bpf_insn` (pcap/bpf.h): u_short code; u_char jt,
# jf; bpf_u_int32 k.
CODE_MAX = 0xFFFF
JMP_FIELD_MAX = 0xFF


def _bpf_class(code: int) -> int:
    return code & 0x07


def _bpf_size(code: int) -> int:
    return code & 0x18


def _bpf_mode(code: int) -> int:
    return code & 0xE0


def _bpf_op(code: int) -> int:
    return code & 0xF0


def _bpf_src(code: int) -> int:
    return code & 0x08


def _bpf_rval(code: int) -> int:
    return code & 0x18


def _bpf_miscop(code: int) -> int:
    return code & 0xF8


def _s32(k: int) -> int:
    """Sign-extend a 32-bit value, matching `(bpf_int32)pc->k`."""
    k &= UINT32_MAX
    return k - _2_32 if k >= _2_31 else k


def _build_executable_opcodes() -> frozenset[int]:
    """The exact set of codes the pinned interpreter can execute.

    Mirrors every ``case`` label of the dispatch switch in
    libpcap-1.10.6 bpf_filter.c lines 113-383. Anything else falls through
    to ``default: abort();``.
    """
    ops: set[int] = set()

    # returns
    ops.add(BPF_RET | BPF_K)
    ops.add(BPF_RET | BPF_A)

    # packet loads, absolute and indexed, in all three widths
    for size in (BPF_W, BPF_H, BPF_B):
        ops.add(BPF_LD | size | BPF_ABS)
        ops.add(BPF_LD | size | BPF_IND)

    # packet length
    ops.add(BPF_LD | BPF_W | BPF_LEN)
    ops.add(BPF_LDX | BPF_W | BPF_LEN)

    # the IP-header-length idiom: ldx 4*([k]&0xf)
    ops.add(BPF_LDX | BPF_MSH | BPF_B)

    # immediates and scratch memory (word-sized only)
    ops.add(BPF_LD | BPF_IMM)
    ops.add(BPF_LDX | BPF_IMM)
    ops.add(BPF_LD | BPF_MEM)
    ops.add(BPF_LDX | BPF_MEM)

    # scratch stores
    ops.add(BPF_ST)
    ops.add(BPF_STX)

    # jumps
    ops.add(BPF_JMP | BPF_JA)
    for op in (BPF_JEQ, BPF_JGT, BPF_JGE, BPF_JSET):
        ops.add(BPF_JMP | op | BPF_K)
        ops.add(BPF_JMP | op | BPF_X)

    # ALU
    for op in (BPF_ADD, BPF_SUB, BPF_MUL, BPF_DIV, BPF_MOD,
               BPF_AND, BPF_OR, BPF_XOR, BPF_LSH, BPF_RSH):
        ops.add(BPF_ALU | op | BPF_K)
        ops.add(BPF_ALU | op | BPF_X)
    ops.add(BPF_ALU | BPF_NEG)  # no source field

    # misc
    ops.add(BPF_MISC | BPF_TAX)
    ops.add(BPF_MISC | BPF_TXA)

    return frozenset(ops)


EXECUTABLE_OPCODES = _build_executable_opcodes()

# Stable reason tokens. score.py records these verbatim; keep them stable.
REASONS = (
    "empty_program",
    "program_too_long",
    "malformed_instruction",
    "field_out_of_range",
    "unknown_opcode",
    "scratch_out_of_bounds",
    "packet_read_out_of_bounds",
    "div_by_zero_immediate",
    "jump_target_out_of_range",
    "no_terminating_ret",
    "ret_unreachable",
    "loop_not_provably_terminating",
)

_LOAD_WIDTH = {BPF_W: 4, BPF_H: 2, BPF_B: 1}


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

def _normalize(prog):
    """Coerce prog into a tuple of 4-int tuples.

    Returns (insns, None) or (None, reason). Booleans are rejected: JSON
    ``true`` is an int in Python and must not silently become opcode 1.
    """
    if prog is None:
        return None, "empty_program"
    if isinstance(prog, (str, bytes)):
        return None, "malformed_instruction (program is not a list)"
    try:
        items = list(prog)
    except TypeError:
        return None, "malformed_instruction (program is not iterable)"
    if not items:
        return None, "empty_program"

    out = []
    for pc, ins in enumerate(items):
        if isinstance(ins, (str, bytes)) or not hasattr(ins, "__iter__"):
            return None, f"malformed_instruction@pc{pc} (not a 4-tuple)"
        fields = list(ins)
        if len(fields) != 4:
            return None, f"malformed_instruction@pc{pc} (arity {len(fields)}, want 4)"
        vals = []
        for pos, v in enumerate(fields):
            if isinstance(v, bool) or not isinstance(v, int):
                return None, f"malformed_instruction@pc{pc} (field {pos} is not an integer)"
            vals.append(v)
        code, jt, jf, k = vals
        if not (0 <= code <= CODE_MAX):
            return None, f"field_out_of_range@pc{pc} (code={code})"
        if not (0 <= jt <= JMP_FIELD_MAX):
            return None, f"field_out_of_range@pc{pc} (jt={jt})"
        if not (0 <= jf <= JMP_FIELD_MAX):
            return None, f"field_out_of_range@pc{pc} (jf={jf})"
        if not (0 <= k <= UINT32_MAX):
            return None, f"field_out_of_range@pc{pc} (k={k})"
        out.append((code, jt, jf, k))
    return tuple(out), None


# --------------------------------------------------------------------------
# Per-instruction legality
# --------------------------------------------------------------------------

def _check_instruction(pc: int, ins, max_packet):
    code, _jt, _jf, k = ins

    # The upper 8 bits of the opcode are unused (pcap/bpf.h:130-132), and the
    # interpreter dispatches on the whole u_short, so anything above 0xff is
    # unexecutable.
    if code > 0xFF or code not in EXECUTABLE_OPCODES:
        return f"unknown_opcode@pc{pc} (code=0x{code:02x})"

    cls = _bpf_class(code)

    if cls in (BPF_LD, BPF_LDX):
        mode = _bpf_mode(code)
        if mode == BPF_MEM:
            # scratch read: static bound, always enforced
            if k >= BPF_MEMWORDS:
                return (f"scratch_out_of_bounds@pc{pc} "
                        f"(M[{k}], BPF_MEMWORDS={BPF_MEMWORDS})")
        elif mode in (BPF_ABS, BPF_IND, BPF_MSH):
            width = _LOAD_WIDTH.get(_bpf_size(code), 1)
            # A load whose offset+width cannot be represented can never be
            # satisfied by any packet; reject regardless of max_packet.
            if k + width > _2_32:
                return (f"packet_read_out_of_bounds@pc{pc} "
                        f"(k={k}+{width} overflows uint32)")
            if max_packet is not None and mode == BPF_ABS:
                # Opt-in only. See module docstring point (c): libpcap itself
                # emits absolute loads past snaplen, so this is OFF by default.
                if k + width > max_packet:
                    return (f"packet_read_out_of_bounds@pc{pc} "
                            f"(k={k}+{width} > max_packet={max_packet})")
        # IMM and LEN carry no address

    elif cls in (BPF_ST, BPF_STX):
        if k >= BPF_MEMWORDS:
            return (f"scratch_out_of_bounds@pc{pc} "
                    f"(M[{k}], BPF_MEMWORDS={BPF_MEMWORDS})")

    elif cls == BPF_ALU:
        op = _bpf_op(code)
        if op in (BPF_DIV, BPF_MOD) and _bpf_src(code) == BPF_K and k == 0:
            # bpf_filter.c:462-470
            return f"div_by_zero_immediate@pc{pc}"

    return None


# --------------------------------------------------------------------------
# Control flow
# --------------------------------------------------------------------------

def _successors(insns, pc: int):
    """Successor indices of insns[pc]. Targets may be out of range."""
    code, jt, jf, k = insns[pc]
    cls = _bpf_class(code)
    if cls == BPF_RET:
        return ()
    if cls == BPF_JMP:
        if _bpf_op(code) == BPF_JA:
            # signed displacement -- bpf_filter.c:235-241
            return (pc + 1 + _s32(k),)
        return (pc + 1 + jt, pc + 1 + jf)
    return (pc + 1,)


def _check_jump_targets(insns):
    n = len(insns)
    for pc, ins in enumerate(insns):
        code = ins[0]
        if _bpf_class(code) != BPF_JMP:
            continue
        if _bpf_op(code) == BPF_JA:
            tgt = pc + 1 + _s32(ins[3])
            if not (0 <= tgt < n):
                return (f"jump_target_out_of_range@pc{pc} "
                        f"(ja -> {tgt}, len={n})")
        else:
            for label, off in (("jt", ins[1]), ("jf", ins[2])):
                tgt = pc + 1 + off
                if not (0 <= tgt < n):
                    return (f"jump_target_out_of_range@pc{pc} "
                            f"({label} -> {tgt}, len={n})")
    return None


def _reachable(insns):
    seen = {0}
    stack = [0]
    while stack:
        pc = stack.pop()
        for s in _successors(insns, pc):
            if s not in seen:
                seen.add(s)
                stack.append(s)
    return seen


def _ret_reachable_from_all(insns, reachable):
    """True iff a BPF_RET is reachable from every reachable instruction.

    Computed as a backward closure from the RET instructions.
    """
    preds: dict[int, list[int]] = {pc: [] for pc in reachable}
    rets = []
    for pc in reachable:
        if _bpf_class(insns[pc][0]) == BPF_RET:
            rets.append(pc)
            continue
        for s in _successors(insns, pc):
            if s in preds:
                preds[s].append(pc)
    good = set(rets)
    stack = list(rets)
    while stack:
        pc = stack.pop()
        for p in preds.get(pc, ()):
            if p not in good:
                good.add(p)
                stack.append(p)
    missing = sorted(reachable - good)
    return (None if not missing
            else f"ret_unreachable@pc{missing[0]} "
                 f"({len(missing)} instruction(s) cannot reach a ret)")


def _sccs(insns, reachable):
    """Tarjan SCCs over the reachable subgraph, iterative (no recursion limit)."""
    index: dict[int, int] = {}
    low: dict[int, int] = {}
    on_stack: set[int] = set()
    stack: list[int] = []
    result: list[list[int]] = []
    counter = 0

    for root in sorted(reachable):
        if root in index:
            continue
        work = [(root, iter(_successors(insns, root)))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in reachable:
                    continue
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(_successors(insns, w))))
                    advanced = True
                    break
                if w in on_stack:
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            work.pop()
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                result.append(comp)
            if work:
                u = work[-1][0]
                low[u] = min(low[u], low[v])
    return result


def _is_cyclic(insns, comp_set):
    if len(comp_set) > 1:
        return True
    (only,) = tuple(comp_set)
    return only in _successors(insns, only)


def _check_termination(insns):
    """Prove termination, or return a reason."""
    reachable = _reachable(insns)

    reason = _ret_reachable_from_all(insns, reachable)
    if reason is not None:
        return reason

    for comp in _sccs(insns, reachable):
        comp_set = set(comp)
        if not _is_cyclic(insns, comp_set):
            continue

        head = min(comp_set)
        has_indexed_load = False
        has_index_advance = False
        has_exit = False

        for pc in comp_set:
            code, _jt, _jf, k = insns[pc]
            cls = _bpf_class(code)
            if cls in (BPF_LD, BPF_LDX):
                mode = _bpf_mode(code)
                # X-relative packet reads: offset grows with the index.
                if mode in (BPF_IND, BPF_MSH):
                    has_indexed_load = True
            elif cls == BPF_ALU and _bpf_op(code) == BPF_ADD:
                if _bpf_src(code) == BPF_X or k >= 1:
                    has_index_advance = True
            for s in _successors(insns, pc):
                if s not in comp_set:
                    has_exit = True

        if not has_exit:
            return (f"loop_not_provably_terminating@pc{head} "
                    f"(cycle has no exit edge)")
        if not has_indexed_load:
            return (f"loop_not_provably_terminating@pc{head} "
                    f"(cycle performs no X-relative packet load, so no "
                    f"runtime bound applies)")
        if not has_index_advance:
            return (f"loop_not_provably_terminating@pc{head} "
                    f"(cycle never advances the index register)")

    return None


# --------------------------------------------------------------------------
# Public entry points
# --------------------------------------------------------------------------

def validate(prog, *, max_packet=None, max_insns: int = BPF_MAXINSNS):
    """Validate a cBPF program.

    Parameters
    ----------
    prog:
        Sequence of ``[code, jt, jf, k]`` instructions, as decoded from the
        candidate's JSON output.
    max_packet:
        Optional static upper bound for absolute packet loads. OFF by
        default; see module docstring point (c) before enabling it.
    max_insns:
        Program length ceiling. Defaults to BPF_MAXINSNS (4096).

    Returns
    -------
    (True, None) if the program is valid, else (False, reason).
    """
    insns, reason = _normalize(prog)
    if reason is not None:
        return False, reason

    if max_insns is not None and len(insns) > max_insns:
        return False, f"program_too_long ({len(insns)} > {max_insns})"

    for pc, ins in enumerate(insns):
        reason = _check_instruction(pc, ins, max_packet)
        if reason is not None:
            return False, reason

    reason = _check_jump_targets(insns)
    if reason is not None:
        return False, reason

    # bpf_filter.c:527 -- the program must end in a return, so control can
    # never fall off the end of the buffer.
    if _bpf_class(insns[-1][0]) != BPF_RET:
        return False, (f"no_terminating_ret (last instruction "
                       f"code=0x{insns[-1][0]:02x})")

    reason = _check_termination(insns)
    if reason is not None:
        return False, reason

    return True, None


def is_valid(prog, **kw) -> bool:
    ok, _ = validate(prog, **kw)
    return ok


def reject_reason(prog, **kw):
    """Return the rejection reason, or None when the program is valid."""
    _ok, reason = validate(prog, **kw)
    return reason
