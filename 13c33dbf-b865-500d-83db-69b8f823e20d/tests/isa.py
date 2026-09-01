# forge-canary: FORGE-CANARY-1BB2B264DB7B36163B3AD778A3401A39
"""Reference virtual machine for the ARC instruction set.

This machine is the arbiter for two quantities the verifier never takes on trust: the
observable trace an emitted program image actually produces, and the executed instruction
count that the speed credit is computed from. It is a pure function of the image, the
pinned instruction set revision and the ceiling, so a measurement is exactly reproducible
without reading a clock.
"""

from __future__ import annotations

import registry

WORD_MASK = registry.WORD_MASK
SIGN_BIT = registry.SIGN_BIT
INT_MIN = registry.INT_MIN
INT_MAX = registry.INT_MAX
WORD_BITS = registry.WORD_BITS

EXIT_HALT = 0
EXIT_TRAP = 2
EXIT_CEILING = 3
EXIT_FAULT = 4


def to_signed(word: int) -> int:
    word &= WORD_MASK
    return word - (1 << WORD_BITS) if word & SIGN_BIT else word


def to_word(value: int) -> int:
    return value & WORD_MASK


def saturate(value: int) -> int:
    if value > INT_MAX:
        return to_word(INT_MAX)
    if value < INT_MIN:
        return to_word(INT_MIN)
    return to_word(value)


class Fault(Exception):
    pass


class Trap(Exception):
    pass


class Machine:
    def __init__(self, program: list, isa_revision_id: str, ceiling: int) -> None:
        self.program = program
        self.spec = registry.ISA_REVISIONS[isa_revision_id]
        self.opcodes = self.spec["opcodes"]
        self.mode_operand = isa_revision_id == registry.ISA_SAT
        self.ceiling = ceiling
        self.registers = [0] * registry.REGISTER_COUNT
        self.memory = [0] * registry.MEMORY_WORDS
        self.control: list = []
        self.sp = 0
        self.fp = 0
        self.pc = 0
        self.trace: list = []
        self.instructions = 0
        self.call_targets: set = set()

    def register(self, index: object) -> int:
        if not isinstance(index, int) or index < 0 or index >= registry.REGISTER_COUNT:
            raise Fault("register out of range")
        return self.registers[index]

    def store(self, index: object, value: int) -> None:
        if not isinstance(index, int) or index < 0 or index >= registry.REGISTER_COUNT:
            raise Fault("register out of range")
        self.registers[index] = to_word(value)

    def word_at(self, address: int) -> int:
        if address < 0 or address >= registry.MEMORY_WORDS:
            raise Fault("memory out of range")
        return self.memory[address]

    def set_word(self, address: int, value: int) -> None:
        if address < 0 or address >= registry.MEMORY_WORDS:
            raise Fault("memory out of range")
        self.memory[address] = to_word(value)

    def arithmetic(self, op: str, a: int, b: int, mode: int) -> int:
        if op == "ADD":
            raw = to_signed(a) + to_signed(b)
        elif op == "SUB":
            raw = to_signed(a) - to_signed(b)
        else:
            raw = to_signed(a) * to_signed(b)
        return saturate(raw) if mode else to_word(raw)

    def divide(self, a: int, b: int) -> int:
        sa, sb = to_signed(a), to_signed(b)
        if sb == 0:
            raise Trap("divide by zero")
        if sa == INT_MIN and sb == -1:
            return to_word(INT_MIN)
        quotient = abs(sa) // abs(sb)
        if (sa < 0) != (sb < 0):
            quotient = -quotient
        return to_word(quotient)

    def remainder(self, a: int, b: int) -> int:
        sa, sb = to_signed(a), to_signed(b)
        if sb == 0:
            raise Trap("remainder by zero")
        if sa == INT_MIN and sb == -1:
            return 0
        value = abs(sa) % abs(sb)
        return to_word(-value if sa < 0 else value)

    def execute(self) -> dict:
        try:
            status = self.loop()
        except Trap:
            status = EXIT_TRAP
        except Fault:
            status = EXIT_FAULT
        except RecursionError:
            status = EXIT_FAULT
        return {
            "trace": list(self.trace),
            "exit_status": status,
            "instructions": self.instructions,
            "call_targets": sorted(self.call_targets),
        }

    def loop(self) -> int:
        while True:
            if self.pc < 0 or self.pc >= len(self.program):
                raise Fault("program counter out of range")
            instruction = self.program[self.pc]
            if not isinstance(instruction, (list, tuple)) or not instruction:
                raise Fault("instruction is not a sequence")
            op = instruction[0]
            if not isinstance(op, str) or op not in self.opcodes:
                raise Fault("unknown opcode")
            operands = list(instruction[1:])
            if len(operands) != len(self.opcodes[op]["operands"]):
                raise Fault("operand count mismatch")
            self.instructions += 1
            if self.instructions > self.ceiling:
                return EXIT_CEILING
            self.pc += 1
            if op == "HALT":
                return EXIT_HALT
            self.step(op, operands)

    def step(self, op: str, operands: list) -> None:
        if op == "LOADI":
            self.store(operands[0], operands[1])
        elif op == "MOV":
            self.store(operands[0], self.register(operands[1]))
        elif op in ("ADD", "SUB", "MUL"):
            mode = operands[3] if self.mode_operand else 0
            if mode not in (0, 1):
                raise Fault("arithmetic mode out of range")
            self.store(operands[0], self.arithmetic(op, self.register(operands[1]), self.register(operands[2]), mode))
        elif op == "DIV":
            self.store(operands[0], self.divide(self.register(operands[1]), self.register(operands[2])))
        elif op == "MOD":
            self.store(operands[0], self.remainder(self.register(operands[1]), self.register(operands[2])))
        elif op == "AND":
            self.store(operands[0], self.register(operands[1]) & self.register(operands[2]))
        elif op == "OR":
            self.store(operands[0], self.register(operands[1]) | self.register(operands[2]))
        elif op == "XOR":
            self.store(operands[0], self.register(operands[1]) ^ self.register(operands[2]))
        elif op == "SHL":
            self.store(operands[0], self.register(operands[1]) << (self.register(operands[2]) & (WORD_BITS - 1)))
        elif op == "SHR":
            self.store(operands[0], self.register(operands[1]) >> (self.register(operands[2]) & (WORD_BITS - 1)))
        elif op == "SAR":
            self.store(operands[0], to_signed(self.register(operands[1])) >> (self.register(operands[2]) & (WORD_BITS - 1)))
        elif op == "CMPLT":
            self.store(operands[0], 1 if to_signed(self.register(operands[1])) < to_signed(self.register(operands[2])) else 0)
        elif op == "CMPEQ":
            self.store(operands[0], 1 if self.register(operands[1]) == self.register(operands[2]) else 0)
        elif op == "JMP":
            self.pc += self.offset(operands[0])
        elif op == "JZ":
            if self.register(operands[0]) == 0:
                self.pc += self.offset(operands[1])
        elif op == "JNZ":
            if self.register(operands[0]) != 0:
                self.pc += self.offset(operands[1])
        elif op == "LDF":
            self.store(operands[0], self.word_at(self.fp + self.immediate(operands[1])))
        elif op == "STF":
            self.set_word(self.fp + self.immediate(operands[0]), self.register(operands[1]))
        elif op == "PUSH":
            self.set_word(self.sp, self.register(operands[0]))
            self.sp += 1
        elif op == "POP":
            self.sp -= 1
            self.store(operands[0], self.word_at(self.sp))
        elif op == "ALLOC":
            count = self.immediate(operands[0])
            if count < 0:
                raise Fault("negative allocation")
            for _ in range(count):
                self.set_word(self.sp, 0)
                self.sp += 1
        elif op == "DROP":
            count = self.immediate(operands[0])
            if count < 0 or self.sp - count < 0:
                raise Fault("stack underflow")
            self.sp -= count
        elif op == "CALL":
            if len(self.control) >= registry.CALL_DEPTH_LIMIT:
                raise Fault("call depth overflow")
            target = self.pc + self.offset(operands[0])
            self.control.append((self.pc, self.fp))
            self.fp = self.sp
            self.pc = target
            self.call_targets.add(target)
        elif op == "RET":
            if not self.control:
                raise Fault("return without call")
            self.sp = self.fp
            self.pc, self.fp = self.control.pop()
        elif op == "OUT":
            self.trace.append(to_signed(self.register(operands[0])))
        else:
            raise Fault("unhandled opcode")

    def offset(self, value: object) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise Fault("displacement is not an integer")
        return value

    def immediate(self, value: object) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise Fault("immediate is not an integer")
        return value


def run(program: object, isa_revision_id: str, ceiling: int = registry.INSTRUCTION_CEILING) -> dict:
    if not isinstance(program, (list, tuple)) or not program:
        return {"trace": [], "exit_status": EXIT_FAULT, "instructions": 0, "call_targets": []}
    if isa_revision_id not in registry.ISA_REVISIONS:
        return {"trace": [], "exit_status": EXIT_FAULT, "instructions": 0, "call_targets": []}
    return Machine(list(program), isa_revision_id, ceiling).execute()


def contains_body(program: list, body: list) -> int:
    """Returns the address at which body appears verbatim inside program, or minus one."""
    if not body or len(body) > len(program):
        return -1
    normalised = [list(item) for item in program]
    target = [list(item) for item in body]
    for start in range(len(normalised) - len(target) + 1):
        if normalised[start:start + len(target)] == target:
            return start
    return -1
