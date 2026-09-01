from __future__ import annotations

KEYWORDS = ("func", "let", "if", "else", "while", "out", "return")

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

WORD_MASK = (1 << 32) - 1


class SourceError(ValueError):
    pass


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
            return {"kind": "const", "value": token[1] & WORD_MASK}
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


def locals_of(function: dict) -> list:
    names = list(function["params"])

    def walk_statements(statements: list) -> None:
        for statement in statements:
            kind = statement["kind"]
            if kind in ("let", "assign") and statement["name"] not in names:
                names.append(statement["name"])
            if kind == "if":
                walk_statements(statement["then"])
                walk_statements(statement["otherwise"])
            elif kind == "while":
                walk_statements(statement["body"])

    walk_statements(function["body"])
    return names
