"""Canonical definitions for the ARC instruction set registry, the runtime application
binary interface registry, the linked intrinsic bodies and the mutation schedule.

This file is installed root owned with mode 0700 inside the solving image and is byte
identical to tests/registry.py inside the verifier image. It is the single authority for
what the pinned instruction set and the pinned calling convention are at a given attempt,
so the mutation applier and the verifier can never drift apart.
"""

from __future__ import annotations

import hashlib
import json

WORD_BITS = 32
WORD_MASK = (1 << WORD_BITS) - 1
SIGN_BIT = 1 << (WORD_BITS - 1)
INT_MIN = -(1 << (WORD_BITS - 1))
INT_MAX = (1 << (WORD_BITS - 1)) - 1

REGISTER_COUNT = 16
MEMORY_WORDS = 8192
CALL_DEPTH_LIMIT = 256
INSTRUCTION_CEILING = 2_000_000

ISA_BASE = "isa-2026-08-17.a"
ISA_SAT = "isa-2026-08-17.b"

ABI_STACK = "cc-2026-08-17.a"
ABI_REGISTER = "cc-2026-08-17.b"

M1_TURN = 14
M2_TURN = 31
PIVOT_PROGRAM = {"public": 6, "holdout": 24}

EXIT_STATUS = {
    "0": "halted normally",
    "2": "trap raised by a division or remainder with a zero divisor",
    "3": "executed instruction ceiling exceeded",
    "4": "machine fault, meaning an unknown opcode, a wrong operand count, an out of range register, an out of range memory word or a call depth overflow",
}

_ARITH_MODE_OPS = ("ADD", "SUB", "MUL")

_BASE_OPCODES = {
    "LOADI": (["rd", "imm"], "rd receives imm reduced modulo two to the word width"),
    "MOV": (["rd", "ra"], "rd receives the word held in ra"),
    "ADD": (["rd", "ra", "rb"], "rd receives ra plus rb wrapped to the word width"),
    "SUB": (["rd", "ra", "rb"], "rd receives ra minus rb wrapped to the word width"),
    "MUL": (["rd", "ra", "rb"], "rd receives ra times rb wrapped to the word width"),
    "DIV": (["rd", "ra", "rb"], "rd receives the signed quotient of ra by rb truncated toward zero, a zero divisor traps, and the most negative word divided by minus one wraps to the most negative word"),
    "MOD": (["rd", "ra", "rb"], "rd receives the signed remainder of ra by rb whose sign follows the dividend, a zero divisor traps, and the most negative word modulo minus one yields zero"),
    "AND": (["rd", "ra", "rb"], "rd receives the bitwise conjunction of ra and rb"),
    "OR": (["rd", "ra", "rb"], "rd receives the bitwise disjunction of ra and rb"),
    "XOR": (["rd", "ra", "rb"], "rd receives the bitwise exclusive disjunction of ra and rb"),
    "SHL": (["rd", "ra", "rb"], "rd receives ra shifted left by rb reduced modulo the word width, vacated bits are zero"),
    "SHR": (["rd", "ra", "rb"], "rd receives ra shifted right logically by rb reduced modulo the word width"),
    "SAR": (["rd", "ra", "rb"], "rd receives ra shifted right arithmetically by rb reduced modulo the word width"),
    "CMPLT": (["rd", "ra", "rb"], "rd receives one when ra is signed less than rb and zero otherwise"),
    "CMPEQ": (["rd", "ra", "rb"], "rd receives one when ra equals rb and zero otherwise"),
    "JMP": (["off"], "control transfers to the address of the following instruction displaced by off"),
    "JZ": (["ra", "off"], "control transfers to the address of the following instruction displaced by off when ra is zero"),
    "JNZ": (["ra", "off"], "control transfers to the address of the following instruction displaced by off when ra is nonzero"),
    "LDF": (["rd", "imm"], "rd receives the memory word at the frame pointer displaced by imm"),
    "STF": (["imm", "ra"], "the memory word at the frame pointer displaced by imm receives ra"),
    "PUSH": (["ra"], "the memory word at the stack pointer receives ra and the stack pointer advances by one"),
    "POP": (["rd"], "the stack pointer retreats by one and rd receives the memory word it now addresses"),
    "ALLOC": (["imm"], "the stack pointer advances by imm and every word it passes is set to zero"),
    "DROP": (["imm"], "the stack pointer retreats by imm"),
    "CALL": (["off"], "the return address and the frame pointer are pushed on the control stack, the frame pointer receives the stack pointer, and control transfers to the address of the following instruction displaced by off"),
    "RET": ([], "the stack pointer receives the frame pointer, then the frame pointer and the program counter are restored from the control stack"),
    "OUT": (["ra"], "the signed interpretation of ra is appended to the observable trace"),
    "HALT": ([], "execution stops with exit status zero"),
}


def _opcode_table(isa_revision_id: str) -> dict:
    table = {}
    for name, (operands, semantics) in _BASE_OPCODES.items():
        if isa_revision_id == ISA_SAT and name in _ARITH_MODE_OPS:
            table[name] = {
                "operands": operands + ["mode"],
                "semantics": semantics
                + ", and mode zero selects wrapping while mode one selects signed saturation at the word bounds",
            }
        else:
            table[name] = {"operands": list(operands), "semantics": semantics}
    return table


ISA_REVISIONS = {
    ISA_BASE: {
        "isa_revision_id": ISA_BASE,
        "word_bits": WORD_BITS,
        "register_count": REGISTER_COUNT,
        "memory_words": MEMORY_WORDS,
        "call_depth_limit": CALL_DEPTH_LIMIT,
        "instruction_ceiling": INSTRUCTION_CEILING,
        "opcode_groups": ["core", "arithmetic", "control", "frame", "observable"],
        "opcodes": _opcode_table(ISA_BASE),
        "source_builtins": ["gcd", "clamp", "popcnt"],
        "exit_status": dict(EXIT_STATUS),
    },
    ISA_SAT: {
        "isa_revision_id": ISA_SAT,
        "word_bits": WORD_BITS,
        "register_count": REGISTER_COUNT,
        "memory_words": MEMORY_WORDS,
        "call_depth_limit": CALL_DEPTH_LIMIT,
        "instruction_ceiling": INSTRUCTION_CEILING,
        "opcode_groups": ["core", "arithmetic", "control", "frame", "observable", "saturating"],
        "opcodes": _opcode_table(ISA_SAT),
        "source_builtins": ["gcd", "clamp", "popcnt", "sat_add", "sat_sub", "sat_mul"],
        "exit_status": dict(EXIT_STATUS),
    },
}

ABI_REVISIONS = {
    ABI_STACK: {
        "calling_convention_id": ABI_STACK,
        "argument_registers": [],
        "stack_argument_order": "arguments are pushed in source order before the call and the callee reads argument i at the frame pointer displaced by i minus the count of stack arguments",
        "callee_saved": ["r8", "r9", "r10", "r11", "r12", "r13"],
        "caller_saved": ["r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r14", "r15"],
        "return_register": "r0",
        "caller_drops_stack_arguments": True,
    },
    ABI_REGISTER: {
        "calling_convention_id": ABI_REGISTER,
        "argument_registers": ["r10", "r11"],
        "stack_argument_order": "the first two arguments are placed in the argument registers, the remaining arguments are pushed in source order before the call, and the callee reads argument i at the frame pointer displaced by i minus two minus the count of stack arguments",
        "callee_saved": ["r8", "r9"],
        "caller_saved": ["r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r10", "r11", "r12", "r13", "r14", "r15"],
        "return_register": "r0",
        "caller_drops_stack_arguments": True,
    },
}

INTRINSIC_ARITY = {"gcd": 2, "clamp": 3, "popcnt": 1}

_SCRATCH = {
    ABI_STACK: {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5},
    ABI_REGISTER: {"a": 10, "b": 11, "c": 12, "d": 13, "e": 5},
}


def canonical_digest(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _arith(isa_revision_id: str, op: str, rd: int, ra: int, rb: int, mode: int = 0) -> list:
    if isa_revision_id == ISA_SAT and op in _ARITH_MODE_OPS:
        return [op, rd, ra, rb, mode]
    return [op, rd, ra, rb]


def _assemble(items: list) -> list:
    """Resolves symbolic labels into program counter relative displacements.

    A jump displacement is measured from the address of the instruction that follows the
    jump, so an assembled body is position independent and can be appended anywhere in a
    program image without relocation.
    """
    addresses = {}
    address = 0
    for item in items:
        if isinstance(item, tuple) and item[0] == "label":
            addresses[item[1]] = address
        else:
            address += 1
    out = []
    address = 0
    for item in items:
        if isinstance(item, tuple) and item[0] == "label":
            continue
        resolved = []
        for operand in item:
            if isinstance(operand, tuple) and operand[0] == "@":
                resolved.append(addresses[operand[1]] - (address + 1))
            else:
                resolved.append(operand)
        out.append(resolved)
        address += 1
    return out


def _load_arguments(abi_revision_id: str, arity: int, targets: list) -> list:
    abi = ABI_REVISIONS[abi_revision_id]
    in_registers = min(arity, len(abi["argument_registers"]))
    stack_arguments = arity - in_registers
    out = []
    for index in range(arity):
        if index < in_registers:
            source = int(abi["argument_registers"][index][1:])
            if source != targets[index]:
                out.append(["MOV", targets[index], source])
        else:
            out.append(["LDF", targets[index], index - in_registers - stack_arguments])
    return out


def _gcd_body(isa_revision_id: str, abi_revision_id: str) -> list:
    s = _SCRATCH[abi_revision_id]
    a, b, c, d = s["a"], s["b"], s["c"], s["d"]
    items = []
    items += _load_arguments(abi_revision_id, 2, [a, b])
    items += [
        ["LOADI", c, 0],
        ["CMPLT", d, a, c],
        ["JZ", d, ("@", "b_abs")],
        _arith(isa_revision_id, "SUB", a, c, a),
        ("label", "b_abs"),
        ["CMPLT", d, b, c],
        ["JZ", d, ("@", "loop")],
        _arith(isa_revision_id, "SUB", b, c, b),
        ("label", "loop"),
        ["JZ", b, ("@", "done")],
        ["MOD", c, a, b],
        ["MOV", a, b],
        ["MOV", b, c],
        ["JMP", ("@", "loop")],
        ("label", "done"),
        ["MOV", 0, a],
        ["RET"],
    ]
    return _assemble(items)


def _clamp_body(isa_revision_id: str, abi_revision_id: str) -> list:
    s = _SCRATCH[abi_revision_id]
    x, lo, hi, c = s["a"], s["b"], s["c"], s["d"]
    items = []
    items += _load_arguments(abi_revision_id, 3, [x, lo, hi])
    items += [
        ["CMPLT", c, x, lo],
        ["JZ", c, ("@", "high")],
        ["MOV", x, lo],
        ("label", "high"),
        ["CMPLT", c, hi, x],
        ["JZ", c, ("@", "done")],
        ["MOV", x, hi],
        ("label", "done"),
        ["MOV", 0, x],
        ["RET"],
    ]
    return _assemble(items)


def _popcnt_body(isa_revision_id: str, abi_revision_id: str) -> list:
    s = _SCRATCH[abi_revision_id]
    x, n, t = s["a"], s["b"], s["c"]
    items = []
    items += _load_arguments(abi_revision_id, 1, [x])
    items += [
        ["LOADI", n, 0],
        ("label", "loop"),
        ["JZ", x, ("@", "done")],
        ["LOADI", t, 1],
        _arith(isa_revision_id, "SUB", t, x, t),
        ["AND", x, x, t],
        ["LOADI", t, 1],
        _arith(isa_revision_id, "ADD", n, n, t),
        ["JMP", ("@", "loop")],
        ("label", "done"),
        ["MOV", 0, n],
        ["RET"],
    ]
    return _assemble(items)


_BODY_BUILDERS = {"gcd": _gcd_body, "clamp": _clamp_body, "popcnt": _popcnt_body}


def intrinsics_for(isa_revision_id: str, abi_revision_id: str) -> dict:
    bodies = []
    for name in sorted(_BODY_BUILDERS):
        bodies.append(
            {
                "name": name,
                "arity": INTRINSIC_ARITY[name],
                "body": _BODY_BUILDERS[name](isa_revision_id, abi_revision_id),
            }
        )
    payload = {
        "isa_revision_id": isa_revision_id,
        "calling_convention_id": abi_revision_id,
        "intrinsics": bodies,
    }
    payload["intrinsics_digest"] = canonical_digest(bodies)
    return payload


def intrinsic_table(isa_manifest: dict, abi_revision_id: str) -> dict:
    """Publishes one body set per instruction set revision any program can resolve to.

    During the announced extension the corpus straddles two revisions, and a body assembled
    for one revision faults on the other because the arithmetic opcodes differ in arity.
    """
    revisions = [isa_manifest["isa_revision_id"]]
    if isa_manifest.get("transition") == "in_flight" and isa_manifest.get("previous_isa_revision_id"):
        revisions.append(isa_manifest["previous_isa_revision_id"])
    by_revision = {revision: intrinsics_for(revision, abi_revision_id) for revision in sorted(set(revisions))}
    return {
        "calling_convention_id": abi_revision_id,
        "live_isa_revision_id": isa_manifest["isa_revision_id"],
        "by_isa_revision": by_revision,
    }


def abi_record(abi_revision_id: str) -> dict:
    record = dict(ABI_REVISIONS[abi_revision_id])
    record["calling_convention_digest"] = canonical_digest(ABI_REVISIONS[abi_revision_id])
    return record


def resolve_state(attempt_index: int) -> dict:
    abi_revision_id = ABI_REGISTER if attempt_index >= M2_TURN else ABI_STACK
    if attempt_index < M1_TURN:
        isa_revision_id = ISA_BASE
        transition = "settled"
        pivot_program = {"public": 0, "holdout": 0}
        previous = None
    elif attempt_index == M1_TURN:
        isa_revision_id = ISA_SAT
        transition = "in_flight"
        pivot_program = dict(PIVOT_PROGRAM)
        previous = ISA_BASE
    else:
        isa_revision_id = ISA_SAT
        transition = "settled"
        pivot_program = {"public": 0, "holdout": 0}
        previous = ISA_BASE
    isa = dict(ISA_REVISIONS[isa_revision_id])
    isa["transition"] = transition
    isa["pivot_program"] = pivot_program
    isa["previous_isa_revision_id"] = previous
    return {
        "attempt_index": attempt_index,
        "isa": isa,
        "abi": abi_record(abi_revision_id),
        "intrinsics": intrinsic_table(isa, abi_revision_id),
    }


def isa_revision_for_program(isa_manifest: dict, slice_name: str, program_index: int) -> str:
    if isa_manifest.get("transition") == "in_flight":
        pivot = isa_manifest.get("pivot_program", {}).get(slice_name, 0)
        if program_index < pivot:
            return isa_manifest["previous_isa_revision_id"]
    return isa_manifest["isa_revision_id"]


def isa_spec_for_program(isa_manifest: dict, slice_name: str, program_index: int) -> dict:
    return dict(ISA_REVISIONS[isa_revision_for_program(isa_manifest, slice_name, program_index)])
