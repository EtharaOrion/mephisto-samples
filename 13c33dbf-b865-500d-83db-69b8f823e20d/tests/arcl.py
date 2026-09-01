# forge-canary: FORGE-CANARY-6CAA841C1ADA9B611F786DD993BFAE95
"""Front end and reference evaluator for the ARCL source language.

The evaluator in this module is the semantics authority for the observable trace and the
exit status of every program in the corpus. It is a direct evaluator over the abstract
syntax tree and depends on no compiler, so a lowering is correct exactly when it
reproduces what this module produces.
"""

from __future__ import annotations

WORD_BITS = 32
WORD_MASK = (1 << WORD_BITS) - 1
SIGN_BIT = 1 << (WORD_BITS - 1)
INT_MIN = -(1 << (WORD_BITS - 1))
INT_MAX = (1 << (WORD_BITS - 1)) - 1

EXIT_HALT = 0
EXIT_TRAP = 2
EXIT_CEILING = 3
EXIT_FAULT = 4

STEP_CEILING = 4_000_000
CALL_DEPTH_LIMIT = 256

KEYWORDS = ("func", "let", "if", "else", "while", "out", "return")
BUILTINS_BASE = ("gcd", "clamp", "popcnt")
BUILTINS_SAT = ("sat_add", "sat_sub", "sat_mul")

OPERATORS = (
    ">>>",
    "<<",
    ">>",
    "<=",
    ">=",
    "==",
    "!=",
    "+",
    "-",
    "*",
    "/",
    "%",
    "&",
    "|",
    "^",
    "~",
    "<",
    ">",
    "=",
    "(",
    ")",
    "{",
    "}",
    ",",
    ";",
)

PRECEDENCE = (
    ("==", "!="),
    ("<", "<=", ">", ">="),
    ("|",),
    ("^",),
    ("&",),
    ("<<", ">>", ">>>"),
    ("+", "-"),
    ("*", "/", "%"),
)


class SourceError(ValueError):
    pass


class Trap(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(str(status))
        self.status = status


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


def signed_div(a: int, b: int) -> int:
    sa, sb = to_signed(a), to_signed(b)
    if sb == 0:
        raise Trap(EXIT_TRAP)
    if sa == INT_MIN and sb == -1:
        return to_word(INT_MIN)
    quotient = abs(sa) // abs(sb)
    if (sa < 0) != (sb < 0):
        quotient = -quotient
    return to_word(quotient)


def signed_mod(a: int, b: int) -> int:
    sa, sb = to_signed(a), to_signed(b)
    if sb == 0:
        raise Trap(EXIT_TRAP)
    if sa == INT_MIN and sb == -1:
        return 0
    remainder = abs(sa) % abs(sb)
    if sa < 0:
        remainder = -remainder
    return to_word(remainder)


def tokenize(text: str) -> list:
    tokens = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in " \t\r\n":
            index += 1
            continue
        if char == "#":
            while index < length and text[index] != "\n":
                index += 1
            continue
        if char.isdigit():
            start = index
            while index < length and text[index].isdigit():
                index += 1
            tokens.append(("int", int(text[start:index])))
            continue
        if char.isalpha() or char == "_":
            start = index
            while index < length and (text[index].isalnum() or text[index] == "_"):
                index += 1
            word = text[start:index]
            tokens.append(("keyword", word) if word in KEYWORDS else ("name", word))
            continue
        for operator in OPERATORS:
            if text.startswith(operator, index):
                tokens.append(("op", operator))
                index += len(operator)
                break
        else:
            raise SourceError(f"unexpected character {char!r} at offset {index}")
    tokens.append(("end", ""))
    return tokens


class Parser:
    def __init__(self, tokens: list) -> None:
        self.tokens = tokens
        self.position = 0

    def peek(self) -> tuple:
        return self.tokens[self.position]

    def next(self) -> tuple:
        token = self.tokens[self.position]
        self.position += 1
        return token

    def accept(self, kind: str, value: str) -> bool:
        token = self.peek()
        if token[0] == kind and token[1] == value:
            self.position += 1
            return True
        return False

    def expect(self, kind: str, value: str) -> tuple:
        token = self.next()
        if token[0] != kind or token[1] != value:
            raise SourceError(f"expected {value!r} but found {token[1]!r}")
        return token

    def parse_program(self) -> dict:
        functions = {}
        order = []
        while self.peek()[0] != "end":
            self.expect("keyword", "func")
            name = self.next()
            if name[0] != "name":
                raise SourceError("function name expected")
            self.expect("op", "(")
            params = []
            if not self.accept("op", ")"):
                while True:
                    token = self.next()
                    if token[0] != "name":
                        raise SourceError("parameter name expected")
                    params.append(token[1])
                    if self.accept("op", ")"):
                        break
                    self.expect("op", ",")
            body = self.parse_block()
            functions[name[1]] = {"name": name[1], "params": params, "body": body}
            order.append(name[1])
        if "main" not in functions:
            raise SourceError("program has no main function")
        return {"functions": functions, "order": order}

    def parse_block(self) -> list:
        self.expect("op", "{")
        statements = []
        while not self.accept("op", "}"):
            statements.append(self.parse_statement())
        return statements

    def parse_statement(self) -> dict:
        if self.accept("keyword", "let"):
            token = self.next()
            if token[0] != "name":
                raise SourceError("variable name expected")
            self.expect("op", "=")
            value = self.parse_expression()
            self.expect("op", ";")
            return {"kind": "let", "name": token[1], "value": value}
        if self.accept("keyword", "if"):
            self.expect("op", "(")
            condition = self.parse_expression()
            self.expect("op", ")")
            then_body = self.parse_block()
            else_body = self.parse_block() if self.accept("keyword", "else") else []
            return {"kind": "if", "condition": condition, "then": then_body, "otherwise": else_body}
        if self.accept("keyword", "while"):
            self.expect("op", "(")
            condition = self.parse_expression()
            self.expect("op", ")")
            body = self.parse_block()
            return {"kind": "while", "condition": condition, "body": body}
        if self.accept("keyword", "out"):
            value = self.parse_expression()
            self.expect("op", ";")
            return {"kind": "out", "value": value}
        if self.accept("keyword", "return"):
            value = self.parse_expression()
            self.expect("op", ";")
            return {"kind": "return", "value": value}
        token = self.next()
        if token[0] != "name":
            raise SourceError(f"statement expected but found {token[1]!r}")
        self.expect("op", "=")
        value = self.parse_expression()
        self.expect("op", ";")
        return {"kind": "assign", "name": token[1], "value": value}

    def parse_expression(self, level: int = 0) -> dict:
        if level >= len(PRECEDENCE):
            return self.parse_unary()
        node = self.parse_expression(level + 1)
        while True:
            token = self.peek()
            if token[0] == "op" and token[1] in PRECEDENCE[level]:
                self.position += 1
                right = self.parse_expression(level + 1)
                node = {"kind": "binary", "op": token[1], "left": node, "right": right}
            else:
                return node

    def parse_unary(self) -> dict:
        if self.accept("op", "-"):
            return {"kind": "unary", "op": "-", "operand": self.parse_unary()}
        if self.accept("op", "~"):
            return {"kind": "unary", "op": "~", "operand": self.parse_unary()}
        return self.parse_primary()

    def parse_primary(self) -> dict:
        token = self.next()
        if token[0] == "int":
            return {"kind": "const", "value": to_word(token[1])}
        if token[0] == "op" and token[1] == "(":
            node = self.parse_expression()
            self.expect("op", ")")
            return node
        if token[0] == "name":
            if self.accept("op", "("):
                arguments = []
                if not self.accept("op", ")"):
                    while True:
                        arguments.append(self.parse_expression())
                        if self.accept("op", ")"):
                            break
                        self.expect("op", ",")
                return {"kind": "call", "name": token[1], "arguments": arguments}
            return {"kind": "name", "name": token[1]}
        raise SourceError(f"expression expected but found {token[1]!r}")


def parse(text: str) -> dict:
    return Parser(tokenize(text)).parse_program()


def builtin_gcd(a: int, b: int) -> int:
    x, y = abs(to_signed(a)), abs(to_signed(b))
    while y:
        x, y = y, x % y
    return to_word(x)


def builtin_clamp(x: int, low: int, high: int) -> int:
    sx, slow, shigh = to_signed(x), to_signed(low), to_signed(high)
    if sx < slow:
        sx = slow
    if shigh < sx:
        sx = shigh
    return to_word(sx)


def builtin_popcnt(x: int) -> int:
    return to_word(bin(to_word(x)).count("1"))


BUILTIN_IMPLEMENTATIONS = {
    "gcd": (2, builtin_gcd),
    "clamp": (3, builtin_clamp),
    "popcnt": (1, builtin_popcnt),
    "sat_add": (2, lambda a, b: saturate(to_signed(a) + to_signed(b))),
    "sat_sub": (2, lambda a, b: saturate(to_signed(a) - to_signed(b))),
    "sat_mul": (2, lambda a, b: saturate(to_signed(a) * to_signed(b))),
}


class _Return(Exception):
    def __init__(self, value: int) -> None:
        super().__init__("return")
        self.value = value


class Evaluator:
    def __init__(self, program: dict, builtins: tuple) -> None:
        self.program = program
        self.builtins = set(builtins)
        self.trace: list = []
        self.steps = 0

    def step(self) -> None:
        self.steps += 1
        if self.steps > STEP_CEILING:
            raise Trap(EXIT_CEILING)

    def call(self, name: str, arguments: list, depth: int) -> int:
        if depth > CALL_DEPTH_LIMIT:
            raise Trap(EXIT_FAULT)
        function = self.program["functions"][name]
        if len(arguments) != len(function["params"]):
            raise Trap(EXIT_FAULT)
        scope = dict(zip(function["params"], arguments))
        try:
            self.run_block(function["body"], scope, depth)
        except _Return as done:
            return done.value
        return 0

    def run_block(self, statements: list, scope: dict, depth: int) -> None:
        for statement in statements:
            self.step()
            kind = statement["kind"]
            if kind == "let" or kind == "assign":
                scope[statement["name"]] = self.evaluate(statement["value"], scope, depth)
            elif kind == "out":
                self.trace.append(to_signed(self.evaluate(statement["value"], scope, depth)))
            elif kind == "return":
                raise _Return(self.evaluate(statement["value"], scope, depth))
            elif kind == "if":
                condition = self.evaluate(statement["condition"], scope, depth)
                self.run_block(statement["then"] if condition else statement["otherwise"], scope, depth)
            elif kind == "while":
                while self.evaluate(statement["condition"], scope, depth):
                    self.step()
                    self.run_block(statement["body"], scope, depth)
            else:
                raise Trap(EXIT_FAULT)

    def evaluate(self, node: dict, scope: dict, depth: int) -> int:
        self.step()
        kind = node["kind"]
        if kind == "const":
            return node["value"]
        if kind == "name":
            if node["name"] not in scope:
                raise Trap(EXIT_FAULT)
            return scope[node["name"]]
        if kind == "unary":
            operand = self.evaluate(node["operand"], scope, depth)
            if node["op"] == "-":
                return to_word(-to_signed(operand))
            return to_word(~operand)
        if kind == "binary":
            return self.binary(node["op"], self.evaluate(node["left"], scope, depth), self.evaluate(node["right"], scope, depth))
        if kind == "call":
            name = node["name"]
            arguments = [self.evaluate(argument, scope, depth) for argument in node["arguments"]]
            if name in self.builtins:
                arity, implementation = BUILTIN_IMPLEMENTATIONS[name]
                if len(arguments) != arity:
                    raise Trap(EXIT_FAULT)
                return implementation(*arguments)
            if name not in self.program["functions"]:
                raise Trap(EXIT_FAULT)
            return self.call(name, arguments, depth + 1)
        raise Trap(EXIT_FAULT)

    def binary(self, op: str, a: int, b: int) -> int:
        if op == "+":
            return to_word(a + b)
        if op == "-":
            return to_word(a - b)
        if op == "*":
            return to_word(a * b)
        if op == "/":
            return signed_div(a, b)
        if op == "%":
            return signed_mod(a, b)
        if op == "&":
            return to_word(a & b)
        if op == "|":
            return to_word(a | b)
        if op == "^":
            return to_word(a ^ b)
        if op == "<<":
            return to_word(a << (b & (WORD_BITS - 1)))
        if op == ">>":
            return to_word(to_signed(a) >> (b & (WORD_BITS - 1)))
        if op == ">>>":
            return to_word(a >> (b & (WORD_BITS - 1)))
        if op == "<":
            return 1 if to_signed(a) < to_signed(b) else 0
        if op == "<=":
            return 1 if to_signed(a) <= to_signed(b) else 0
        if op == ">":
            return 1 if to_signed(a) > to_signed(b) else 0
        if op == ">=":
            return 1 if to_signed(a) >= to_signed(b) else 0
        if op == "==":
            return 1 if a == b else 0
        if op == "!=":
            return 1 if a != b else 0
        raise Trap(EXIT_FAULT)


def evaluate_source(text: str, builtins: tuple = BUILTINS_BASE + BUILTINS_SAT) -> dict:
    try:
        program = parse(text)
    except SourceError as error:
        return {"trace": [], "exit_status": EXIT_FAULT, "error": str(error)}
    evaluator = Evaluator(program, builtins)
    try:
        evaluator.call("main", [], 0)
    except Trap as trap:
        return {"trace": list(evaluator.trace), "exit_status": trap.status, "error": None}
    except RecursionError:
        return {"trace": list(evaluator.trace), "exit_status": EXIT_FAULT, "error": "recursion"}
    return {"trace": list(evaluator.trace), "exit_status": EXIT_HALT, "error": None}
