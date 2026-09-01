from __future__ import annotations

import abi_tables
import frontend

WORD_MASK = (1 << 32) - 1

COMPARISONS = {"<": "lt", "<=": "ge_not", ">": "gt", ">=": "lt_not", "==": "eq", "!=": "eq_not"}

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

ACCUMULATOR = 1
OPERAND = 2
SCRATCH = 3


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


class Lowering:
    def __init__(self, context: dict) -> None:
        isa = context["isa"]
        self.arithmetic_mode = len(isa["opcodes"]["ADD"]["operands"]) == 4
        self.source_builtins = set(isa["source_builtins"])
        self.intrinsics = {entry["name"]: entry for entry in context["intrinsics"]["intrinsics"]}
        self.argument_registers = list(abi_tables.ARGUMENT_REGISTERS)
        self.emitter = Emitter()
        self.used_intrinsics: list = []
        self.slots: dict = {}
        self.program: dict = {}

    def arith(self, op: str, rd: int, ra: int, rb: int) -> None:
        if self.arithmetic_mode and op in ("ADD", "SUB", "MUL"):
            self.emitter.emit(op, rd, ra, rb, 0)
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
        self.slots = {name: index for index, name in enumerate(names)}
        arity = len(function["params"])
        self.emitter.label(f"fn:{function['name']}")
        self.emitter.emit("ALLOC", len(names))
        for index, param in enumerate(function["params"]):
            self.emitter.emit("LDF", ACCUMULATOR, index - arity)
            self.emitter.emit("STF", self.slots[param], ACCUMULATOR)
        self.block(function["body"], f"fn:{function['name']}")
        self.emitter.emit("LOADI", 0, 0)
        self.emitter.emit("RET")

    def block(self, statements: list, scope: str) -> None:
        for position, statement in enumerate(statements):
            self.statement(statement, f"{scope}:{position}")

    def statement(self, statement: dict, tag: str) -> None:
        kind = statement["kind"]
        if kind in ("let", "assign"):
            self.expression(statement["value"], tag)
            self.emitter.emit("POP", ACCUMULATOR)
            if statement["name"] not in self.slots:
                raise frontend.SourceError(f"unknown variable {statement['name']}")
            self.emitter.emit("STF", self.slots[statement["name"]], ACCUMULATOR)
        elif kind == "out":
            self.expression(statement["value"], tag)
            self.emitter.emit("POP", ACCUMULATOR)
            self.emitter.emit("OUT", ACCUMULATOR)
        elif kind == "return":
            self.expression(statement["value"], tag)
            self.emitter.emit("POP", ACCUMULATOR)
            self.emitter.emit("MOV", 0, ACCUMULATOR)
            self.emitter.emit("RET")
        elif kind == "if":
            self.expression(statement["condition"], f"{tag}:c")
            self.emitter.emit("POP", ACCUMULATOR)
            self.emitter.emit("JZ", ACCUMULATOR, ("@", f"{tag}:else"))
            self.block(statement["then"], f"{tag}:t")
            self.emitter.emit("JMP", ("@", f"{tag}:end"))
            self.emitter.label(f"{tag}:else")
            self.block(statement["otherwise"], f"{tag}:e")
            self.emitter.label(f"{tag}:end")
        elif kind == "while":
            self.emitter.label(f"{tag}:top")
            self.expression(statement["condition"], f"{tag}:c")
            self.emitter.emit("POP", ACCUMULATOR)
            self.emitter.emit("JZ", ACCUMULATOR, ("@", f"{tag}:end"))
            self.block(statement["body"], f"{tag}:b")
            self.emitter.emit("JMP", ("@", f"{tag}:top"))
            self.emitter.label(f"{tag}:end")
        else:
            raise frontend.SourceError(f"unknown statement {kind}")

    def expression(self, node: dict, tag: str) -> None:
        kind = node["kind"]
        if kind == "const":
            self.emitter.emit("LOADI", ACCUMULATOR, node["value"])
            self.emitter.emit("PUSH", ACCUMULATOR)
        elif kind == "name":
            if node["name"] not in self.slots:
                raise frontend.SourceError(f"unknown variable {node['name']}")
            self.emitter.emit("LDF", ACCUMULATOR, self.slots[node["name"]])
            self.emitter.emit("PUSH", ACCUMULATOR)
        elif kind == "unary":
            self.expression(node["operand"], f"{tag}:u")
            self.emitter.emit("POP", OPERAND)
            if node["op"] == "-":
                self.emitter.emit("LOADI", ACCUMULATOR, 0)
                self.arith("SUB", ACCUMULATOR, ACCUMULATOR, OPERAND)
            else:
                self.emitter.emit("LOADI", ACCUMULATOR, WORD_MASK)
                self.emitter.emit("XOR", ACCUMULATOR, ACCUMULATOR, OPERAND)
            self.emitter.emit("PUSH", ACCUMULATOR)
        elif kind == "binary":
            self.expression(node["left"], f"{tag}:l")
            self.expression(node["right"], f"{tag}:r")
            self.emitter.emit("POP", OPERAND)
            self.emitter.emit("POP", ACCUMULATOR)
            self.binary(node["op"])
            self.emitter.emit("PUSH", ACCUMULATOR)
        elif kind == "call":
            self.call(node, tag)
        else:
            raise frontend.SourceError(f"unknown expression {kind}")

    def binary(self, op: str) -> None:
        if op in DIRECT:
            target = DIRECT[op]
            if target in ("ADD", "SUB", "MUL"):
                self.arith(target, ACCUMULATOR, ACCUMULATOR, OPERAND)
            else:
                self.emitter.emit(target, ACCUMULATOR, ACCUMULATOR, OPERAND)
            return
        form = COMPARISONS[op]
        if form == "lt":
            self.emitter.emit("CMPLT", ACCUMULATOR, ACCUMULATOR, OPERAND)
        elif form == "gt":
            self.emitter.emit("CMPLT", ACCUMULATOR, OPERAND, ACCUMULATOR)
        elif form == "eq":
            self.emitter.emit("CMPEQ", ACCUMULATOR, ACCUMULATOR, OPERAND)
        elif form == "eq_not":
            self.emitter.emit("CMPEQ", ACCUMULATOR, ACCUMULATOR, OPERAND)
            self.invert()
        elif form == "lt_not":
            self.emitter.emit("CMPLT", ACCUMULATOR, ACCUMULATOR, OPERAND)
            self.invert()
        else:
            self.emitter.emit("CMPLT", ACCUMULATOR, OPERAND, ACCUMULATOR)
            self.invert()

    def invert(self) -> None:
        self.emitter.emit("LOADI", SCRATCH, 1)
        self.emitter.emit("XOR", ACCUMULATOR, ACCUMULATOR, SCRATCH)

    def call(self, node: dict, tag: str) -> None:
        name = node["name"]
        arguments = node["arguments"]
        if name in self.source_builtins:
            if name not in self.intrinsics:
                raise frontend.SourceError(f"builtin {name} has no lowering in this back end")
            if name not in self.used_intrinsics:
                self.used_intrinsics.append(name)
            for index, argument in enumerate(arguments):
                self.expression(argument, f"{tag}:a{index}")
            self.emitter.emit("CALL", ("@", f"in:{name}"))
            self.emitter.emit("MOV", ACCUMULATOR, 0)
            self.emitter.emit("DROP", len(arguments))
            self.emitter.emit("PUSH", ACCUMULATOR)
            return
        if name not in self.program["functions"]:
            raise frontend.SourceError(f"unknown function {name}")
        for index, argument in enumerate(arguments):
            self.expression(argument, f"{tag}:a{index}")
        self.emitter.emit("CALL", ("@", f"fn:{name}"))
        self.emitter.emit("MOV", ACCUMULATOR, 0)
        self.emitter.emit("DROP", len(arguments))
        self.emitter.emit("PUSH", ACCUMULATOR)


def lower(source: str, context: dict) -> list:
    return Lowering(context).compile(source)
