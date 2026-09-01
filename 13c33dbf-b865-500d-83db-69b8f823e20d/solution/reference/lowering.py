# forge-canary: FORGE-CANARY-22582D8CBA73BFC7E63DCE10B60DAC9D
from __future__ import annotations

import frontend

WORD_MASK = (1 << 32) - 1
SIGN_BIT = 1 << 31
INT_MIN = -(1 << 31)

TEMP_BASE = 1
TEMP_MAX = 6

DIRECT = {
    "+": "ADD",
    "-": "SUB",
    "*": "MUL",
    "/": "DIV",
    "%": "MOD",
    "&": "AND",
    "|": "OR",
    "^": "XOR",
    "<<": "SHL",
    ">>": "SAR",
    ">>>": "SHR",
}

COMPARISON_FORM = {
    "<": ("CMPLT", False, False),
    ">": ("CMPLT", True, False),
    "<=": ("CMPLT", True, True),
    ">=": ("CMPLT", False, True),
    "==": ("CMPEQ", False, False),
    "!=": ("CMPEQ", False, True),
}


def to_signed(word: int) -> int:
    word &= WORD_MASK
    return word - (1 << 32) if word & SIGN_BIT else word


class Emitter:
    def __init__(self) -> None:
        self.items: list = []

    def label(self, name: str) -> None:
        self.items.append(("label", name))

    def emit(self, *parts) -> None:
        self.items.append(list(parts))

    def resolve(self) -> list:
        addresses = {}
        address = 0
        for item in self.items:
            if isinstance(item, tuple) and item[0] == "label":
                addresses[item[1]] = address
            else:
                address += 1
        out = []
        address = 0
        for item in self.items:
            if isinstance(item, tuple) and item[0] == "label":
                continue
            resolved = []
            for operand in item:
                if isinstance(operand, tuple) and operand[0] == "@":
                    if operand[1] not in addresses:
                        raise frontend.SourceError(f"unresolved label {operand[1]}")
                    resolved.append(addresses[operand[1]] - (address + 1))
                else:
                    resolved.append(operand)
            out.append(resolved)
            address += 1
        return out


def fold(node: dict) -> dict:
    kind = node["kind"]
    if kind == "binary":
        left = fold(node["left"])
        right = fold(node["right"])
        if left["kind"] == "const" and right["kind"] == "const":
            value = _fold_binary(node["op"], left["value"], right["value"])
            if value is not None:
                return {"kind": "const", "value": value}
        return {"kind": "binary", "op": node["op"], "left": left, "right": right}
    if kind == "unary":
        operand = fold(node["operand"])
        if operand["kind"] == "const":
            if node["op"] == "-":
                return {"kind": "const", "value": (-to_signed(operand["value"])) & WORD_MASK}
            return {"kind": "const", "value": (~operand["value"]) & WORD_MASK}
        return {"kind": "unary", "op": node["op"], "operand": operand}
    if kind == "call":
        return {"kind": "call", "name": node["name"], "arguments": [fold(a) for a in node["arguments"]]}
    return node


def _fold_binary(op: str, a: int, b: int):
    sa, sb = to_signed(a), to_signed(b)
    if op == "+":
        return (sa + sb) & WORD_MASK
    if op == "-":
        return (sa - sb) & WORD_MASK
    if op == "*":
        return (sa * sb) & WORD_MASK
    if op in ("/", "%"):
        if sb == 0:
            return None
        if sa == INT_MIN and sb == -1:
            return (INT_MIN & WORD_MASK) if op == "/" else 0
        magnitude = abs(sa) // abs(sb) if op == "/" else abs(sa) % abs(sb)
        if op == "/":
            return (-magnitude if (sa < 0) != (sb < 0) else magnitude) & WORD_MASK
        return (-magnitude if sa < 0 else magnitude) & WORD_MASK
    if op == "&":
        return a & b
    if op == "|":
        return a | b
    if op == "^":
        return a ^ b
    if op == "<<":
        return (a << (b & 31)) & WORD_MASK
    if op == ">>":
        return (sa >> (b & 31)) & WORD_MASK
    if op == ">>>":
        return (a >> (b & 31)) & WORD_MASK
    if op == "<":
        return 1 if sa < sb else 0
    if op == "<=":
        return 1 if sa <= sb else 0
    if op == ">":
        return 1 if sa > sb else 0
    if op == ">=":
        return 1 if sa >= sb else 0
    if op == "==":
        return 1 if a == b else 0
    if op == "!=":
        return 1 if a != b else 0
    return None


def prune(statements: list) -> list:
    out = []
    for statement in statements:
        kind = statement["kind"]
        if kind == "if":
            condition = fold(statement["condition"])
            if condition["kind"] == "const":
                out.extend(prune(statement["then"] if condition["value"] else statement["otherwise"]))
                continue
            out.append(
                {
                    "kind": "if",
                    "condition": condition,
                    "then": prune(statement["then"]),
                    "otherwise": prune(statement["otherwise"]),
                }
            )
        elif kind == "while":
            condition = fold(statement["condition"])
            if condition["kind"] == "const" and not condition["value"]:
                continue
            out.append({"kind": "while", "condition": condition, "body": prune(statement["body"])})
        elif kind == "return":
            out.append({"kind": "return", "value": fold(statement["value"])})
            return out
        else:
            out.append(dict(statement, value=fold(statement["value"])))
    return out


class Lowering:
    def __init__(self, context: dict) -> None:
        isa = context["isa"]
        abi = context["abi"]
        self.arithmetic_mode = len(isa["opcodes"]["ADD"]["operands"]) == 4
        self.source_builtins = set(isa["source_builtins"])
        self.saturating = {"sat_add": "ADD", "sat_sub": "SUB", "sat_mul": "MUL"}
        self.intrinsics = {entry["name"]: entry for entry in context["intrinsics"]["intrinsics"]}
        self.argument_registers = [int(name[1:]) for name in abi["argument_registers"]]
        self.home_registers = sorted(int(name[1:]) for name in abi["callee_saved"])
        self.emitter = Emitter()
        self.used_intrinsics: list = []
        self.program: dict = {}
        self.homes: dict = {}
        self.saved: list = []
        self.spill_base = 0

    def arith(self, op: str, rd: int, ra: int, rb: int, mode: int = 0) -> None:
        if self.arithmetic_mode and op in ("ADD", "SUB", "MUL"):
            self.emitter.emit(op, rd, ra, rb, mode)
        elif mode:
            raise frontend.SourceError("saturating arithmetic is not available at this instruction set revision")
        else:
            self.emitter.emit(op, rd, ra, rb)

    def compile(self, source: str) -> list:
        self.program = frontend.parse(source)
        self.emitter.emit("CALL", ("@", "fn:main"))
        self.emitter.emit("HALT")
        for name in self.program["order"]:
            self.function(self.program["functions"][name])
        for name in self.used_intrinsics:
            self.emitter.label(f"in:{name}")
            for instruction in self.intrinsics[name]["body"]:
                self.emitter.emit(*instruction)
        return self.emitter.resolve()

    def function(self, function: dict) -> None:
        names = frontend.locals_of(function)
        self.homes = {}
        spilled = []
        for index, name in enumerate(names):
            if index < len(self.home_registers):
                self.homes[name] = ("register", self.home_registers[index])
            else:
                spilled.append(name)
        for offset, name in enumerate(spilled):
            self.homes[name] = ("slot", offset)
        self.saved = sorted({self.homes[n][1] for n in names if self.homes[n][0] == "register"})
        self.spill_base = len(spilled)
        arity = len(function["params"])
        body = prune(function["body"])

        self.emitter.label(f"fn:{function['name']}")
        self.emitter.emit("ALLOC", self.spill_base + len(self.saved))
        for offset, register in enumerate(self.saved):
            self.emitter.emit("STF", self.spill_base + offset, register)
        for index, param in enumerate(function["params"]):
            self.emitter.emit("LDF", TEMP_BASE, index - arity)
            self.assign_to(param, TEMP_BASE)
        self.block(body, f"fn:{function['name']}")
        self.emitter.emit("LOADI", 0, 0)
        self.epilogue()

    def epilogue(self) -> None:
        for offset, register in enumerate(self.saved):
            self.emitter.emit("LDF", register, self.spill_base + offset)
        self.emitter.emit("RET")

    def assign_to(self, name: str, source: int) -> None:
        home = self.homes[name]
        if home[0] == "register":
            if home[1] != source:
                self.emitter.emit("MOV", home[1], source)
        else:
            self.emitter.emit("STF", home[1], source)

    def block(self, statements: list, scope: str) -> None:
        for position, statement in enumerate(statements):
            self.statement(statement, f"{scope}:{position}")

    def statement(self, statement: dict, tag: str) -> None:
        kind = statement["kind"]
        if kind in ("let", "assign"):
            home = self.homes[statement["name"]]
            if home[0] == "register" and statement["value"]["kind"] != "call":
                produced = self.value(statement["value"], TEMP_BASE, home[1])
                if produced != home[1]:
                    self.emitter.emit("MOV", home[1], produced)
            else:
                produced = self.value(statement["value"], TEMP_BASE)
                self.assign_to(statement["name"], produced)
        elif kind == "out":
            self.emitter.emit("OUT", self.value(statement["value"], TEMP_BASE))
        elif kind == "return":
            produced = self.value(statement["value"], TEMP_BASE)
            if produced != 0:
                self.emitter.emit("MOV", 0, produced)
            self.epilogue()
        elif kind == "if":
            has_else = bool(statement["otherwise"])
            self.branch_if_false(statement["condition"], f"{tag}:else" if has_else else f"{tag}:end", TEMP_BASE)
            self.block(statement["then"], f"{tag}:t")
            if has_else:
                self.emitter.emit("JMP", ("@", f"{tag}:end"))
                self.emitter.label(f"{tag}:else")
                self.block(statement["otherwise"], f"{tag}:e")
            self.emitter.label(f"{tag}:end")
        elif kind == "while":
            self.emitter.emit("JMP", ("@", f"{tag}:test"))
            self.emitter.label(f"{tag}:top")
            self.block(statement["body"], f"{tag}:b")
            self.emitter.label(f"{tag}:test")
            self.branch_if_true(statement["condition"], f"{tag}:top", TEMP_BASE)
        else:
            raise frontend.SourceError(f"unknown statement {kind}")

    def branch_if_false(self, node: dict, label: str, temp: int) -> None:
        self.branch(node, label, temp, taken_when_true=False)

    def branch_if_true(self, node: dict, label: str, temp: int) -> None:
        self.branch(node, label, temp, taken_when_true=True)

    def branch(self, node: dict, label: str, temp: int, taken_when_true: bool) -> None:
        if node["kind"] == "binary" and node["op"] in COMPARISON_FORM:
            opcode, swapped, negated = COMPARISON_FORM[node["op"]]
            left, right = (node["right"], node["left"]) if swapped else (node["left"], node["right"])
            a = self.value(left, temp)
            b = self.value(right, temp + 1 if a == temp else temp)
            self.emitter.emit(opcode, temp, a, b)
            jump = "JNZ" if (taken_when_true != negated) else "JZ"
            self.emitter.emit(jump, temp, ("@", label))
            return
        produced = self.value(node, temp)
        self.emitter.emit("JNZ" if taken_when_true else "JZ", produced, ("@", label))

    def value(self, node: dict, temp: int, prefer: int = -1) -> int:
        if temp > TEMP_MAX:
            raise frontend.SourceError("expression nesting exceeds the temporary register budget")
        kind = node["kind"]
        target = prefer if prefer >= 0 else temp
        if kind == "const":
            self.emitter.emit("LOADI", target, node["value"])
            return target
        if kind == "name":
            home = self.homes[node["name"]]
            if home[0] == "register":
                return home[1]
            self.emitter.emit("LDF", target, home[1])
            return target
        if kind == "unary":
            operand = self.value(node["operand"], temp)
            scratch = temp + 1 if operand == temp else temp
            if scratch > TEMP_MAX:
                raise frontend.SourceError("expression nesting exceeds the temporary register budget")
            if node["op"] == "-":
                self.emitter.emit("LOADI", scratch, 0)
                self.arith("SUB", target, scratch, operand)
            else:
                self.emitter.emit("LOADI", scratch, WORD_MASK)
                self.emitter.emit("XOR", target, scratch, operand)
            return target
        if kind == "binary":
            a = self.value(node["left"], temp)
            b = self.value(node["right"], temp + 1 if a == temp else temp)
            return self.binary(node["op"], target, a, b)
        if kind == "call":
            return self.call(node, temp, target)
        raise frontend.SourceError(f"unknown expression {kind}")

    def binary(self, op: str, target: int, a: int, b: int) -> int:
        if op in DIRECT:
            opcode = DIRECT[op]
            if opcode in ("ADD", "SUB", "MUL"):
                self.arith(opcode, target, a, b)
            else:
                self.emitter.emit(opcode, target, a, b)
            return target
        opcode, swapped, negated = COMPARISON_FORM[op]
        first, second = (b, a) if swapped else (a, b)
        self.emitter.emit(opcode, target, first, second)
        if negated:
            self.emitter.emit("LOADI", TEMP_MAX + 1, 1)
            self.emitter.emit("XOR", target, target, TEMP_MAX + 1)
        return target

    def call(self, node: dict, temp: int, target: int) -> int:
        name = node["name"]
        arguments = node["arguments"]
        if name in self.saturating and name in self.source_builtins:
            a = self.value(arguments[0], temp)
            b = self.value(arguments[1], temp + 1 if a == temp else temp)
            self.arith(self.saturating[name], target, a, b, mode=1)
            return target
        live = list(range(TEMP_BASE, temp))
        for register in live:
            self.emitter.emit("PUSH", register)
        if name in self.source_builtins:
            if name not in self.intrinsics:
                raise frontend.SourceError(f"builtin {name} has no linked body")
            if name not in self.used_intrinsics:
                self.used_intrinsics.append(name)
            register_count = min(len(arguments), len(self.argument_registers))
            label = f"in:{name}"
        else:
            if name not in self.program["functions"]:
                raise frontend.SourceError(f"unknown function {name}")
            register_count = 0
            label = f"fn:{name}"
        holders = []
        for index, argument in enumerate(arguments):
            holders.append(self.value(argument, TEMP_BASE + index))
        for index in range(register_count, len(arguments)):
            self.emitter.emit("PUSH", holders[index])
        for index in range(register_count):
            self.emitter.emit("MOV", self.argument_registers[index], holders[index])
        self.emitter.emit("CALL", ("@", label))
        stack_arguments = len(arguments) - register_count
        if stack_arguments:
            self.emitter.emit("DROP", stack_arguments)
        if target != 0:
            self.emitter.emit("MOV", target, 0)
        for register in reversed(live):
            self.emitter.emit("POP", register)
        return target


def lower(source: str, context: dict) -> list:
    return Lowering(context).compile(source)
