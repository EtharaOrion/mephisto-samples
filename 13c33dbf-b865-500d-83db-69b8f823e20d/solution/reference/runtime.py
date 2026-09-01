# forge-canary: FORGE-CANARY-837861982023138C90B2C0024F036FE0
from __future__ import annotations

WORD_BITS = 32
WORD_MASK = (1 << WORD_BITS) - 1
SIGN_BIT = 1 << (WORD_BITS - 1)
INT_MIN = -(1 << (WORD_BITS - 1))
INT_MAX = (1 << (WORD_BITS - 1)) - 1

REGISTER_COUNT = 16
MEMORY_WORDS = 8192
CALL_DEPTH_LIMIT = 256

EXIT_HALT = 0
EXIT_TRAP = 2
EXIT_CEILING = 3
EXIT_FAULT = 4

THREE_OPERAND_ARITHMETIC = ("ADD", "SUB", "MUL")


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


def execute(program: list, ceiling: int = 2_000_000) -> dict:
    registers = [0] * REGISTER_COUNT
    memory = [0] * MEMORY_WORDS
    control: list = []
    trace: list = []
    sp = 0
    fp = 0
    pc = 0
    executed = 0
    status = EXIT_HALT

    def read(index):
        if not isinstance(index, int) or index < 0 or index >= REGISTER_COUNT:
            raise Fault("register")
        return registers[index]

    def write(index, value):
        if not isinstance(index, int) or index < 0 or index >= REGISTER_COUNT:
            raise Fault("register")
        registers[index] = to_word(value)

    def load(address):
        if address < 0 or address >= MEMORY_WORDS:
            raise Fault("memory")
        return memory[address]

    def save(address, value):
        if address < 0 or address >= MEMORY_WORDS:
            raise Fault("memory")
        memory[address] = to_word(value)

    def divide(a, b):
        sa, sb = to_signed(a), to_signed(b)
        if sb == 0:
            raise Trap("divide")
        if sa == INT_MIN and sb == -1:
            return to_word(INT_MIN)
        quotient = abs(sa) // abs(sb)
        return to_word(-quotient if (sa < 0) != (sb < 0) else quotient)

    def remainder(a, b):
        sa, sb = to_signed(a), to_signed(b)
        if sb == 0:
            raise Trap("remainder")
        if sa == INT_MIN and sb == -1:
            return 0
        value = abs(sa) % abs(sb)
        return to_word(-value if sa < 0 else value)

    try:
        while True:
            if pc < 0 or pc >= len(program):
                raise Fault("program counter")
            instruction = program[pc]
            op = instruction[0]
            executed += 1
            if executed > ceiling:
                status = EXIT_CEILING
                break
            pc += 1
            if op == "HALT":
                status = EXIT_HALT
                break
            if op == "LOADI":
                write(instruction[1], instruction[2])
            elif op == "MOV":
                write(instruction[1], read(instruction[2]))
            elif op in THREE_OPERAND_ARITHMETIC:
                a, b = to_signed(read(instruction[2])), to_signed(read(instruction[3]))
                raw = a + b if op == "ADD" else (a - b if op == "SUB" else a * b)
                mode = instruction[4] if len(instruction) > 4 else 0
                write(instruction[1], saturate(raw) if mode else to_word(raw))
            elif op == "DIV":
                write(instruction[1], divide(read(instruction[2]), read(instruction[3])))
            elif op == "MOD":
                write(instruction[1], remainder(read(instruction[2]), read(instruction[3])))
            elif op == "AND":
                write(instruction[1], read(instruction[2]) & read(instruction[3]))
            elif op == "OR":
                write(instruction[1], read(instruction[2]) | read(instruction[3]))
            elif op == "XOR":
                write(instruction[1], read(instruction[2]) ^ read(instruction[3]))
            elif op == "SHL":
                write(instruction[1], read(instruction[2]) << (read(instruction[3]) & (WORD_BITS - 1)))
            elif op == "SHR":
                write(instruction[1], read(instruction[2]) >> (read(instruction[3]) & (WORD_BITS - 1)))
            elif op == "SAR":
                write(instruction[1], to_signed(read(instruction[2])) >> (read(instruction[3]) & (WORD_BITS - 1)))
            elif op == "CMPLT":
                write(instruction[1], 1 if to_signed(read(instruction[2])) < to_signed(read(instruction[3])) else 0)
            elif op == "CMPEQ":
                write(instruction[1], 1 if read(instruction[2]) == read(instruction[3]) else 0)
            elif op == "JMP":
                pc += instruction[1]
            elif op == "JZ":
                if read(instruction[1]) == 0:
                    pc += instruction[2]
            elif op == "JNZ":
                if read(instruction[1]) != 0:
                    pc += instruction[2]
            elif op == "LDF":
                write(instruction[1], load(fp + instruction[2]))
            elif op == "STF":
                save(fp + instruction[1], read(instruction[2]))
            elif op == "PUSH":
                save(sp, read(instruction[1]))
                sp += 1
            elif op == "POP":
                sp -= 1
                write(instruction[1], load(sp))
            elif op == "ALLOC":
                for _ in range(instruction[1]):
                    save(sp, 0)
                    sp += 1
            elif op == "DROP":
                sp -= instruction[1]
                if sp < 0:
                    raise Fault("underflow")
            elif op == "CALL":
                if len(control) >= CALL_DEPTH_LIMIT:
                    raise Fault("depth")
                target = pc + instruction[1]
                control.append((pc, fp))
                fp = sp
                pc = target
            elif op == "RET":
                if not control:
                    raise Fault("return")
                sp = fp
                pc, fp = control.pop()
            elif op == "OUT":
                trace.append(to_signed(read(instruction[1])))
            else:
                raise Fault("opcode")
    except Trap:
        status = EXIT_TRAP
    except Fault:
        status = EXIT_FAULT
    except (IndexError, TypeError):
        status = EXIT_FAULT

    return {"trace": trace, "exit_status": status, "instructions": executed}
