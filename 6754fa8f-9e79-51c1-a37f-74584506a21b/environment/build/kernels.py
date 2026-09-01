"""Deterministic kernel generator for edgebench/vliw_kernel_optimization.

Kernel bodies are emitted from a pinned seed through a splitmix64 stream, so the
public fixture family and the hidden grading family are both reproducible from
the recorded seed alone, without a network fetch and without lifting any
published compiler benchmark body or schedule table.

An operation is a plain dictionary. Program order is the operation identifier
order, and the sequential execution of that order is the reference semantics
that any schedule has to preserve.
"""

from __future__ import annotations

import hashlib

MASK64 = (1 << 64) - 1

REGISTER_COUNT = 32
MEM_WORDS = 256

POOL_REGISTERS = tuple(range(1, 13))
SCRATCH_REGISTERS = tuple(range(13, 25))
ACCUMULATOR_REGISTERS = tuple(range(25, 31))

ALU_OPCODES = ("add", "sub", "xor", "shl")

PUBLIC_SPLIT = "public"
HIDDEN_SPLIT = "hidden"


class Stream:
    """splitmix64 over a sha256 derived state. No system entropy is consulted."""

    def __init__(self, seed_text: str) -> None:
        digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
        self.state = int.from_bytes(digest[:8], "big") | 1

    def next(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK64
        return (value ^ (value >> 31)) & MASK64

    def below(self, bound: int) -> int:
        return self.next() % bound

    def between(self, low: int, high: int) -> int:
        return low + self.below(high - low + 1)

    def choice(self, items):
        return items[self.below(len(items))]


def _op(ops: list, opcode: str, **fields) -> None:
    record = {
        "id": len(ops),
        "op": opcode,
        "rd": fields.get("rd"),
        "ra": fields.get("ra"),
        "rb": fields.get("rb"),
        "imm": fields.get("imm"),
        "addr": fields.get("addr"),
    }
    ops.append(record)


def generate_kernel(family_seed: str, split: str, index: int) -> dict:
    rng = Stream(f"{family_seed}|{split}|{index}")
    accumulators = ACCUMULATOR_REGISTERS[: rng.between(2, 3)]
    epochs = rng.between(6, 8)
    macs_per_epoch = rng.between(4, 6)
    cold_per_epoch = rng.between(3, 5)
    hot_per_epoch = rng.between(2, 3)
    alu_per_epoch = rng.between(3, 5)

    ops: list = []
    for register in POOL_REGISTERS:
        _op(ops, "load", rd=register, addr=rng.below(MEM_WORDS))
    for register in accumulators:
        _op(ops, "load", rd=register, addr=rng.below(MEM_WORDS))

    mac_index = 0
    cold_written: list = []
    for _ in range(epochs):
        for _ in range(cold_per_epoch):
            destination = rng.choice(SCRATCH_REGISTERS)
            _op(ops, "load", rd=destination, addr=rng.below(MEM_WORDS))
            cold_written.append(destination)
        for _ in range(hot_per_epoch):
            _op(ops, "load", rd=rng.choice(POOL_REGISTERS), addr=rng.below(MEM_WORDS))
        for _ in range(macs_per_epoch):
            _op(
                ops,
                "mac",
                rd=accumulators[mac_index % len(accumulators)],
                ra=rng.choice(POOL_REGISTERS),
                rb=rng.choice(POOL_REGISTERS),
            )
            mac_index += 1
        for _ in range(alu_per_epoch):
            opcode = rng.choice(ALU_OPCODES)
            destination = rng.choice(SCRATCH_REGISTERS)
            if opcode == "shl":
                _op(ops, "shl", rd=destination, ra=rng.choice(POOL_REGISTERS), imm=rng.between(1, 13))
            else:
                _op(
                    ops,
                    opcode,
                    rd=destination,
                    ra=rng.choice(POOL_REGISTERS + SCRATCH_REGISTERS),
                    rb=rng.choice(POOL_REGISTERS + SCRATCH_REGISTERS),
                )
        _op(
            ops,
            "mul",
            rd=rng.choice(SCRATCH_REGISTERS),
            ra=rng.choice(POOL_REGISTERS),
            rb=rng.choice(POOL_REGISTERS),
        )

    reduction = accumulators[0]
    for register in accumulators[1:]:
        _op(ops, "add", rd=reduction, ra=reduction, rb=register)
    _op(ops, "store", ra=reduction, addr=rng.below(MEM_WORDS))
    for register in sorted(set(cold_written)):
        _op(ops, "store", ra=register, addr=rng.below(MEM_WORDS))

    return {
        "kernel_id": f"{split}_k{index:03d}",
        "register_count": REGISTER_COUNT,
        "mem_words": MEM_WORDS,
        "op_count": len(ops),
        "ops": ops,
    }


def generate_family(family_seed: str, split: str, count: int) -> list:
    return [generate_kernel(family_seed, split, index) for index in range(count)]


def initial_memory(input_seed: str, kernel_id: str, input_index: int) -> list:
    rng = Stream(f"{input_seed}|{kernel_id}|{input_index}")
    return [rng.next() for _ in range(MEM_WORDS)]
