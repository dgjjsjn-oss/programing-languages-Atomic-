#!/usr/bin/env python3
#
# Copyright (c) 2026 ATOMIC++ Project Contributors / Project Owner
#
# All rights reserved.
#
# This repository and its contents are publicly available for viewing and
# educational reference only.
#
# No permission is granted to copy, modify, distribute, sublicense, sell,
# or commercially exploit any portion of this project without prior written
# permission from the copyright holder.
#
# The copyright holder reserves all rights to the source code, project
# architecture, documentation, designs, and original materials, subject to
# applicable law and third-party licenses.
#
# This notice does not override the licenses of third-party components
# included in or used by this project.
#

"""ATOMIC++ Phase 1 vertical slice interpreter.

A minimal, working interpreter for a subset of ATOMIC++ syntax.
Implements: variables, functions, conditions, loops, arrays, say/print,
and the `start:` entry point.

Usage:
    python interpreter.py examples/hello.atpp
"""

import sys
from typing import Any, List, Optional


# ---------------------------------------------------------------------------
# Token types
# ---------------------------------------------------------------------------

TT_INT = "INT"
TT_FLOAT = "FLOAT"
TT_STRING = "STRING"
TT_BOOL = "BOOL"
TT_ID = "ID"
TT_KEYWORD = "KEYWORD"
TT_OP = "OP"
TT_NEWLINE = "NEWLINE"
TT_INDENT = "INDENT"
TT_DEDENT = "DEDENT"
TT_EOF = "EOF"
TT_COLON = "COLON"
TT_LBRACKET = "LBRACKET"
TT_RBRACKET = "RBRACKET"
TT_LPAREN = "LPAREN"
TT_RPAREN = "RPAREN"
TT_COMMA = "COMMA"
TT_ASSIGN = "ASSIGN"   # '='
TT_DOT = "DOT"         # '.'


KEYWORDS = {
    "start", "stop", "say", "make", "use", "when", "each", "give",
    "true", "false", "from", "to", "and", "or", "not"
}

BINARY_OPS = {"+", "-", "*", "/", "is", "is not", "<", ">", "<=", ">="}

# Stable Internal Representation (IR) node types.
# The parser output dicts ARE the IR consumed by the interpreter and the
# future C backend. Shapes are frozen for the supported subset.
IR_PROGRAM = "program"
IR_FUNC = "func"
IR_VAR_ASSIGN = "var_assign"
IR_WHEN = "when"
IR_EACH = "each"
IR_SAY = "say"
IR_GIVE = "give"
IR_STOP = "stop"
IR_USE = "use"
IR_EXPR = "expr"
IR_BINOP = "binop"
IR_UNARY = "unary"
IR_CALL = "call"
IR_METHOD_CALL = "method_call"
IR_ARRAY = "array"
IR_ARRAY_INDEX = "array_index"
IR_ARRAY_ASSIGN = "array_assign"
IR_INT = "int"
IR_FLOAT = "float"
IR_STRING = "string"
IR_BOOL = "bool"
IR_VAR = "var"


class Token:
    def __init__(self, ttype: str, value: Any, line: int, col: int):
        self.ttype = ttype
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self):
        return f"Token({self.ttype}, {self.value!r}, L{self.line}C{self.col})"


class AtomicError(Exception):
    pass


def _i64(v: int) -> int:
    """Wrap an int to signed 64-bit two's complement."""
    v = int(v)
    v &= (1 << 64) - 1
    if v >= (1 << 63):
        v -= (1 << 64)
    return v


def _int_div(a: int, b: int) -> int:
    """C-style truncating integer division; caller checks b != 0."""
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q


# ---------------------------------------------------------------------------
# Lexer — line-by-line with indent tracking
# ---------------------------------------------------------------------------

class Lexer:
    def __init__(self, text: str):
        self.text = text
        self.lines = text.split("\n")
        self.line_idx = 0
        self.line = 1

    def error(self, msg: str):
        raise SyntaxError(f"{msg} at line {self.line}")

    def tokenize_line(self, line_text: str, indent: int) -> List[Token]:
        """Tokenize a single stripped line, returning tokens."""
        tokens: List[Token] = []
        pos = 0
        col = 1 + indent  # column after indent

        while pos < len(line_text):
            ch = line_text[pos]

            # Skip spaces
            if ch in (" ", "\t"):
                pos += 1
                col += 1
                continue

            # Comment to end of line
            if ch == "/" and pos + 1 < len(line_text) and line_text[pos + 1] == "/":
                break

            # Punctuation
            if ch == ":":
                tokens.append(Token(TT_COLON, ":", self.line, col))
                pos += 1
                col += 1
                continue
            if ch == "[":
                tokens.append(Token(TT_LBRACKET, "[", self.line, col))
                pos += 1
                col += 1
                continue
            if ch == "]":
                tokens.append(Token(TT_RBRACKET, "]", self.line, col))
                pos += 1
                col += 1
                continue
            if ch == "(":
                tokens.append(Token(TT_LPAREN, "(", self.line, col))
                pos += 1
                col += 1
                continue
            if ch == ")":
                tokens.append(Token(TT_RPAREN, ")", self.line, col))
                pos += 1
                col += 1
                continue
            if ch == ",":
                tokens.append(Token(TT_COMMA, ",", self.line, col))
                pos += 1
                col += 1
                continue
            if ch == "=":
                tokens.append(Token(TT_ASSIGN, "=", self.line, col))
                pos += 1
                col += 1
                continue
            if ch == ".":
                tokens.append(Token(TT_DOT, ".", self.line, col))
                pos += 1
                col += 1
                continue

            # String
            if ch == '"':
                pos += 1
                col += 1
                chars = []
                while pos < len(line_text) and line_text[pos] != '"':
                    if line_text[pos] == "\\":
                        pos += 1
                        if pos < len(line_text):
                            nxt = line_text[pos]
                            esc = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
                            chars.append(esc.get(nxt, nxt))
                            pos += 1
                            col += 1
                    else:
                        chars.append(line_text[pos])
                        pos += 1
                        col += 1
                if pos >= len(line_text) or line_text[pos] != '"':
                    self.error("Unterminated string")
                pos += 1
                col += 1
                start_col = col - len(chars) - 2
                tokens.append(Token(TT_STRING, "".join(chars), self.line, start_col))
                continue

            # Number
            if ch.isdigit():
                num_str = ""
                is_float = False
                start_col = col
                while pos < len(line_text) and (line_text[pos].isdigit() or line_text[pos] == "."):
                    if line_text[pos] == ".":
                        is_float = True
                    num_str += line_text[pos]
                    pos += 1
                    col += 1
                if is_float:
                    tokens.append(Token(TT_FLOAT, float(num_str), self.line, start_col))
                else:
                    tokens.append(Token(TT_INT, int(num_str), self.line, start_col))
                continue

            # Multi-char operators: 'is not', '<=', '>=', 'is'
            remaining = line_text[pos:]
            if remaining.startswith("is not"):
                tokens.append(Token(TT_OP, "is not", self.line, col))
                pos += 6
                col += 6
                continue
            if remaining.startswith("<="):
                tokens.append(Token(TT_OP, "<=", self.line, col))
                pos += 2
                col += 2
                continue
            if remaining.startswith(">="):
                tokens.append(Token(TT_OP, ">=", self.line, col))
                pos += 2
                col += 2
                continue
            if remaining.startswith("is "):
                tokens.append(Token(TT_OP, "is", self.line, col))
                pos += 3
                col += 3
                continue
            if remaining.startswith("is"):
                tokens.append(Token(TT_OP, "is", self.line, col))
                pos += 2
                col += 2
                continue

            # Identifier / keyword
            if ch.isalpha() or ch == "_":
                name = ""
                start_col = col
                while pos < len(line_text) and (line_text[pos].isalnum() or line_text[pos] == "_"):
                    name += line_text[pos]
                    pos += 1
                    col += 1
                if name in KEYWORDS:
                    tokens.append(Token(TT_KEYWORD, name, self.line, start_col))
                else:
                    tokens.append(Token(TT_ID, name, self.line, start_col))
                continue

            # Single-char operators
            if ch in "+-*/<>":
                tokens.append(Token(TT_OP, ch, self.line, col))
                pos += 1
                col += 1
                continue

            self.error(f"Unexpected character {ch!r} at line {self.line}, column {col}")

        return tokens

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []
        indent_stack: List[int] = [0]

        for line_text in self.lines:
            self.line = self.line_idx + 1
            self.line_idx += 1

            # Count leading whitespace
            stripped = line_text.lstrip(" \t")
            indent = len(line_text) - len(stripped)

            # Skip empty lines and comment-only lines
            if stripped == "" or stripped.startswith("//"):
                continue

            # INDENT / DEDENT
            current = indent_stack[-1]
            if indent > current:
                indent_stack.append(indent)
                tokens.append(Token(TT_INDENT, indent, self.line, 1))
            elif indent < current:
                while indent_stack and indent_stack[-1] > indent:
                    popped = indent_stack.pop()
                    tokens.append(Token(TT_DEDENT, indent_stack[-1] if indent_stack else 0,
                                        self.line, 1))
                if indent_stack and indent_stack[-1] != indent:
                    self.error("Inconsistent indentation")

            # Tokenize content
            tokens.extend(self.tokenize_line(stripped, indent))
            tokens.append(Token(TT_NEWLINE, "\n", self.line, col=1 + indent))

        # Close remaining indents
        while len(indent_stack) > 1:
            indent_stack.pop()
            tokens.append(Token(TT_DEDENT, indent_stack[-1] if indent_stack else 0,
                                self.line, 1))

        tokens.append(Token(TT_EOF, None, self.line, 1))
        return tokens


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, ttype: str, value: Any = None) -> Token:
        tok = self.peek()
        if tok.ttype != ttype:
            raise SyntaxError(
                f"Expected {ttype}, got {tok.ttype} ({tok.value!r}) "
                f"at line {tok.line}, column {tok.col}"
            )
        if value is not None and tok.value != value:
            raise SyntaxError(
                f"Expected {value!r}, got {tok.value!r} "
                f"at line {tok.line}, column {tok.col}"
            )
        return self.advance()

    def parse(self):
        """Parse a full program: top-level funcs, then start: block, then stop."""
        statements = []

        # Zero or more top-level declarations (make, use) before start:
        while self.peek().ttype == TT_KEYWORD and self.peek().value in ("make", "use"):
            if self.peek().value == "make":
                statements.append(self.parse_function())
            else:
                statements.append(self.parse_use())
                self.expect(TT_NEWLINE)

        # Then the start block
        self.expect(TT_KEYWORD, "start")
        self.expect(TT_COLON)
        self.expect(TT_NEWLINE)
        self.expect(TT_INDENT)
        while self.peek().ttype != TT_DEDENT:
            stmt = self.parse_statement()
            statements.append(stmt)
            if stmt.get("type") not in ("when", "each"):
                self.expect(TT_NEWLINE)
        self.expect(TT_DEDENT)
        self.expect(TT_EOF)
        return statements

    def parse_statement(self):
        tok = self.peek()
        if tok.ttype == TT_KEYWORD:
            if tok.value == "say":
                return self.parse_say()
            if tok.value == "make":
                return self.parse_function()
            if tok.value == "when":
                return self.parse_when()
            if tok.value == "each":
                return self.parse_each()
            if tok.value == "give":
                return self.parse_give()
            if tok.value == "stop":
                self.advance()
                return {"type": "stop", "line": tok.line, "col": tok.col}
            if tok.value == "use":
                return self.parse_use()
        if tok.ttype == TT_ID:
            # Array index assignment: ID '[' expr ']' '=' expr
            if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].ttype == TT_LBRACKET:
                depth = 1
                i = self.pos + 2
                while i < len(self.tokens) and depth > 0:
                    if self.tokens[i].ttype == TT_LBRACKET:
                        depth += 1
                    elif self.tokens[i].ttype == TT_RBRACKET:
                        depth -= 1
                    if depth == 0:
                        break
                    i += 1
                if (i < len(self.tokens) and self.tokens[i].ttype == TT_RBRACKET
                        and i + 1 < len(self.tokens) and self.tokens[i + 1].ttype == TT_ASSIGN):
                    return self.parse_array_assign()
            # Assignment: ID '=' expr
            if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].ttype == TT_ASSIGN:
                return self.parse_assign()
            # Bare expression (e.g. function call)
            expr = self.parse_expression()
            return {"type": "expr", "expr": expr, "line": tok.line, "col": tok.col}
        raise SyntaxError(
            f"Unexpected token {tok.ttype} ({tok.value!r}) "
            f"at line {tok.line}, column {tok.col}"
        )

    def parse_assign(self):
        name_tok = self.expect(TT_ID)
        self.expect(TT_ASSIGN)
        expr = self.parse_expression()
        return {"type": "assign", "name": name_tok.value, "expr": expr,
                "line": name_tok.line, "col": name_tok.col}

    def parse_array_assign(self):
        name_tok = self.expect(TT_ID)
        self.expect(TT_LBRACKET)
        index = self.parse_expression()
        self.expect(TT_RBRACKET)
        self.expect(TT_ASSIGN)
        expr = self.parse_expression()
        return {"type": "array_assign", "name": name_tok.value, "index": index, "expr": expr,
                "line": name_tok.line, "col": name_tok.col}

    def parse_say(self):
        self.expect(TT_KEYWORD, "say")
        expr = self.parse_expression()
        return {"type": "say", "expr": expr, "line": expr["line"], "col": expr["col"]}

    def parse_function(self):
        self.expect(TT_KEYWORD, "make")
        name_tok = self.expect(TT_ID)
        self.expect(TT_LPAREN)
        params = []
        if self.peek().ttype != TT_RPAREN:
            while True:
                p = self.expect(TT_ID)
                params.append(p.value)
                if self.peek().ttype == TT_COMMA:
                    self.advance()
                else:
                    break
        self.expect(TT_RPAREN)
        self.expect(TT_COLON)
        self.expect(TT_NEWLINE)
        self.expect(TT_INDENT)
        body = []
        while self.peek().ttype != TT_DEDENT:
            stmt = self.parse_statement()
            body.append(stmt)
            if stmt.get("type") not in ("when", "each"):
                self.expect(TT_NEWLINE)
        self.expect(TT_DEDENT)
        return {
            "type": "func",
            "name": name_tok.value,
            "params": params,
            "body": body,
            "line": name_tok.line,
            "col": name_tok.col,
        }

    def parse_when(self):
        self.expect(TT_KEYWORD, "when")
        cond = self.parse_expression()
        self.expect(TT_COLON)
        self.expect(TT_NEWLINE)
        self.expect(TT_INDENT)
        body = []
        while self.peek().ttype != TT_DEDENT:
            stmt = self.parse_statement()
            body.append(stmt)
            if stmt.get("type") not in ("when", "each"):
                self.expect(TT_NEWLINE)
        self.expect(TT_DEDENT)
        return {
            "type": "when",
            "cond": cond,
            "body": body,
            "line": cond["line"],
            "col": cond["col"],
        }

    def parse_each(self):
        self.expect(TT_KEYWORD, "each")
        var_tok = self.expect(TT_ID)
        self.expect(TT_KEYWORD, "from")
        start_expr = self.parse_expression()
        self.expect(TT_KEYWORD, "to")
        end_expr = self.parse_expression()
        self.expect(TT_COLON)
        self.expect(TT_NEWLINE)
        self.expect(TT_INDENT)
        body = []
        while self.peek().ttype != TT_DEDENT:
            stmt = self.parse_statement()
            body.append(stmt)
            if stmt.get("type") not in ("when", "each"):
                self.expect(TT_NEWLINE)
        self.expect(TT_DEDENT)
        return {
            "type": "each",
            "var": var_tok.value,
            "start": start_expr,
            "end": end_expr,
            "body": body,
            "line": var_tok.line,
            "col": var_tok.col,
        }

    def parse_give(self):
        self.expect(TT_KEYWORD, "give")
        expr = self.parse_expression()
        return {"type": "give", "expr": expr, "line": expr["line"], "col": expr["col"]}

    def parse_use(self):
        self.expect(TT_KEYWORD, "use")
        mod = self.expect(TT_ID)
        return {"type": "use", "module": mod.value, "line": mod.line, "col": mod.col}

    # ---- expressions ----

    def parse_expression(self):
        return self.parse_or()

    def _boolean_node(self, op, operands):
        return {"type": "boolop", "op": op, "operands": tuple(operands),
                "line": operands[0]["line"], "col": operands[0]["col"]}

    def parse_or(self):
        node = self.parse_and()
        while self.peek().ttype == TT_KEYWORD and self.peek().value == "or":
            self.advance()
            right = self.parse_and()
            node = self._boolean_node("or", (node, right))
        return node

    def parse_and(self):
        node = self.parse_not()
        while self.peek().ttype == TT_KEYWORD and self.peek().value == "and":
            self.advance()
            right = self.parse_not()
            node = self._boolean_node("and", (node, right))
        return node

    def parse_not(self):
        if self.peek().ttype == TT_KEYWORD and self.peek().value == "not":
            tok = self.advance()
            operand = self.parse_not()
            node = self._boolean_node("not", (operand,))
            node["line"], node["col"] = tok.line, tok.col
            return node
        return self.parse_comparison()

    def parse_comparison(self):
        """Comparison is the LOOSEST operator (LANGUAGE_SPEC.md 2.5).

        `1 + 2 > 3` must group as `(1 + 2) > 3`. The earlier chain put comparison
        below multiplication, so comparisons bound tighter than arithmetic and
        produced silently wrong answers (`2 * 3 is 6` evaluated to 0).
        """
        node = self.parse_addsub()
        if self.peek().ttype == TT_OP and self.peek().value in ("is", "is not", "<", ">", "<=", ">="):
            op = self.advance().value
            right = self.parse_addsub()
            node = {"type": "binop", "op": op, "left": node, "right": right,
                    "line": node["line"], "col": node["col"]}
        return node

    def parse_addsub(self):
        node = self.parse_muldiv()
        while self.peek().ttype == TT_OP and self.peek().value in ("+", "-"):
            op = self.advance().value
            right = self.parse_muldiv()
            node = {"type": "binop", "op": op, "left": node, "right": right,
                    "line": node["line"], "col": node["col"]}
        return node

    def parse_muldiv(self):
        node = self.parse_primary()
        while self.peek().ttype == TT_OP and self.peek().value in ("*", "/"):
            op = self.advance().value
            right = self.parse_primary()
            node = {"type": "binop", "op": op, "left": node, "right": right,
                    "line": node["line"], "col": node["col"]}
        return node

    def parse_primary(self):
        tok = self.peek()
        if tok.ttype == TT_OP and tok.value in ("-", "+"):
            self.advance()
            operand = self.parse_primary()
            return {"type": "unary", "op": tok.value, "operand": operand,
                    "line": tok.line, "col": tok.col}
        if tok.ttype == TT_LPAREN:
            self.advance()
            inner = self.parse_expression()
            self.expect(TT_RPAREN)
            return inner
        if tok.ttype == TT_INT:
            self.advance()
            return {"type": "int", "value": tok.value, "line": tok.line, "col": tok.col}
        if tok.ttype == TT_FLOAT:
            self.advance()
            return {"type": "float", "value": tok.value, "line": tok.line, "col": tok.col}
        if tok.ttype == TT_STRING:
            self.advance()
            return {"type": "string", "value": tok.value, "line": tok.line, "col": tok.col}
        if tok.ttype == TT_KEYWORD and tok.value in ("true", "false"):
            self.advance()
            return {"type": "bool", "value": tok.value == "true",
                    "line": tok.line, "col": tok.col}
        if tok.ttype == TT_ID:
            self.advance()
            # Module access: math.add
            if self.peek().ttype == TT_DOT:
                self.advance()
                method = self.expect(TT_ID)
                self.expect(TT_LPAREN)
                args = []
                if self.peek().ttype != TT_RPAREN:
                    while True:
                        args.append(self.parse_expression())
                        if self.peek().ttype == TT_COMMA:
                            self.advance()
                        else:
                            break
                self.expect(TT_RPAREN)
                return {"type": "method_call", "module": tok.value, "method": method.value,
                        "args": args, "line": tok.line, "col": tok.col}
            # Function call
            if self.peek().ttype == TT_LPAREN:
                self.advance()
                args = []
                if self.peek().ttype != TT_RPAREN:
                    while True:
                        args.append(self.parse_expression())
                        if self.peek().ttype == TT_COMMA:
                            self.advance()
                        else:
                            break
                self.expect(TT_RPAREN)
                return {"type": "call", "name": tok.value, "args": args,
                        "line": tok.line, "col": tok.col}
            # Array index access: scores[0]
            if self.peek().ttype == TT_LBRACKET:
                self.advance()
                index = self.parse_expression()
                self.expect(TT_RBRACKET)
                return {"type": "array_index", "var": tok.value, "index": index,
                        "line": tok.line, "col": tok.col}
            return {"type": "var", "name": tok.value, "line": tok.line, "col": tok.col}
        if tok.ttype == TT_LBRACKET:
            self.advance()
            elements = []
            if self.peek().ttype != TT_RBRACKET:
                while True:
                    elements.append(self.parse_expression())
                    if self.peek().ttype == TT_COMMA:
                        self.advance()
                    else:
                        break
            self.expect(TT_RBRACKET)
            return {"type": "array", "elements": elements,
                    "line": tok.line, "col": tok.col}
        raise SyntaxError(f"Unexpected token {tok.ttype} ({tok.value!r}) "
                          f"at line {tok.line}, column {tok.col}")


# ---------------------------------------------------------------------------
# Interpreter
# ---------------------------------------------------------------------------

class Env:
    """A variable frame.

    ATOMIC++ names are *function-scoped* (see LANGUAGE_SPEC.md 4.1): `when` and
    `each` bodies do not open a new frame, so an assignment inside them mutates
    the variable it names. A function call gets one fresh frame whose parent is
    the global frame, read-only upwards: a function can read globals but writing
    a name always creates/updates a local, which is why a function's locals never
    leak out. Loop variables live in the enclosing frame, so they are still
    readable after the loop, matching the C and Java backends.
    """

    __slots__ = ("vars", "parent")

    def __init__(self, parent: "Env" = None):
        self.vars: dict = {}
        self.parent = parent

    def get(self, name: str):
        env = self
        while env is not None:
            if name in env.vars:
                return True, env.vars[name]
            env = env.parent
        return False, None

    def set(self, name: str, value) -> None:
        self.vars[name] = value


class Interpreter:
    def __init__(self):
        self.globals = Env()
        self.functions: dict = {}
        self.output: List[str] = []

    def say(self, value):
        self.output.append(str(value))

    def eval_expr(self, node, env: dict):
        ntype = node["type"]
        if ntype == "int":
            return node["value"]
        if ntype == "float":
            return node["value"]
        if ntype == "string":
            return node["value"]
        if ntype == "bool":
            return node["value"]
        if ntype == "var":
            name = node["name"]
            found, value = env.get(name)
            if found:
                return value
            raise AtomicError(
                f"Undefined variable '{name}' at line {node['line']}, column {node['col']}"
            )
        if ntype == "unary":
            v = self.eval_expr(node["operand"], env)
            if node["op"] == "-":
                if isinstance(v, int) and not isinstance(v, bool):
                    return _i64(-v)
                return -v
            return v
        if ntype == "binop":
            if node.get("ir_kind") == "BooleanOperation":
                op = node["op"]
                operands = node["operands"]
                if op == "not":
                    return not bool(self.eval_expr(operands[0], env))
                if op == "and":
                    for operand in operands:
                        if not bool(self.eval_expr(operand, env)):
                            return False
                    return True
                if op == "or":
                    for operand in operands:
                        if bool(self.eval_expr(operand, env)):
                            return True
                    return False
                raise AtomicError(f"Unknown boolean operator {op}")
            left = self.eval_expr(node["left"], env)
            right = self.eval_expr(node["right"], env)
            op = node["op"];
            is_int = lambda a, b: isinstance(a, int) and not isinstance(a, bool) and isinstance(b, int) and not isinstance(b, bool)
            if op == "+":
                if is_int(left, right):
                    return _i64(left + right)
                return left + right
            if op == "-":
                if is_int(left, right):
                    return _i64(left - right)
                return left - right
            if op == "*":
                if is_int(left, right):
                    return _i64(left * right)
                return left * right
            if op == "/":
                if right == 0:
                    raise AtomicError(
                        f"Division by zero at line {node['line']}, column {node['col']}"
                    )
                if is_int(left, right):
                    return _int_div(left, right)
                return left / right
            if op == "is":
                return left == right
            if op == "is not":
                return left != right
            if op == "<":
                return left < right
            if op == ">":
                return left > right
            if op == "<=":
                return left <= right
            if op == ">=":
                return left >= right
            raise AtomicError(f"Unknown operator {op}")
        if ntype == "array_index":
            arr = self.eval_expr({"type": "var", "name": node["var"],
                                 "line": node["line"], "col": node["col"]}, env)
            idx = self.eval_expr(node["index"], env)
            if not isinstance(arr, list):
                raise AtomicError(f"Array expected, got {type(arr).__name__} at line {node['line']}, column {node['col']}")
            if idx < 0 or idx >= len(arr):
                raise AtomicError(f"Array index out of bounds: {idx} (length {len(arr)}) at line {node['line']}, column {node['col']}")
            return arr[idx]
        if ntype == "call":
            name = node["name"]
            args = [self.eval_expr(a, env) for a in node["args"]]
            if name in self.functions:
                func = self.functions[name]
                if len(args) != len(func["params"]):
                    raise AtomicError(
                        f"Function {name} expects {len(func['params'])} args, got {len(args)}"
                    )
                local_env = Env(self.globals)
                for p, v in zip(func["params"], args):
                    local_env.set(p, v)
                return self.execute_block(func["body"], local_env)
            if name == "len" and len(args) == 1:
                return len(args[0])
            raise AtomicError(f"Unknown function '{name}' at line {node['line']}")
        if ntype == "method_call":
            module = node["module"]
            method = node["method"]
            if module not in getattr(self, "imports", set()):
                raise AtomicError(f"Module '{module}' was not imported")
            args = [self.eval_expr(a, env) for a in node["args"]]
            if module == "math":
                ops = {"add": lambda a, b: a + b,
                       "sub": lambda a, b: a - b,
                       "mul": lambda a, b: a * b}
                if method in ops:
                    value = ops[method](*args)
                    if all(isinstance(arg, int) and not isinstance(arg, bool) for arg in args):
                        return _i64(value)
                    return value
            raise AtomicError(f"Unknown module.method '{module}.{method}'")
        if ntype == "array":
            return [self.eval_expr(e, env) for e in node["elements"]]
        raise AtomicError(f"Unknown expression type {ntype}")

    def execute_block(self, block, env: dict):
        for stmt in block:
            result = self.execute_stmt(stmt, env)
            if result is not None and isinstance(result, dict) and result.get("type") == "return":
                return result["value"]
        return None

    def execute_stmt(self, stmt, env: dict):
        stype = stmt["type"]
        if stype == "say":
            val = self.eval_expr(stmt["expr"], env)
            self.say(val)
        elif stype in ("assign", "var_assign"):
            val = self.eval_expr(stmt["expr"], env)
            env.set(stmt["name"], val)
        elif stype == "expr":
            self.eval_expr(stmt["expr"], env)
        elif stype == "func":
            # Functions are top-level: their frame's parent is the global frame.
            # Nested closures are not supported by any backend yet.
            self.functions[stmt["name"]] = {
                "params": stmt["params"],
                "body": stmt["body"],
            }
        elif stype == "when":
            cond = self.eval_expr(stmt["cond"], env)
            if cond:
                result = self.execute_block(stmt["body"], env)
                if result is not None:
                    return {"type": "return", "value": result}
        elif stype == "each":
            start_val = self.eval_expr(stmt["start"], env)
            end_val = self.eval_expr(stmt["end"], env)
            if not isinstance(start_val, int) or not isinstance(end_val, int):
                raise AtomicError("Loop bounds must be integers")
            # The loop variable is bound even when the range is empty, so
            # `each i from 5 to 3` leaves i == 5 in every backend rather than
            # being undefined here and zero in native code.
            env.set(stmt["var"], start_val)
            for i in range(start_val, end_val + 1):
                env.set(stmt["var"], i)
                result = self.execute_block(stmt["body"], env)
                if result is not None:
                    return {"type": "return", "value": result}
        elif stype == "give":
            val = self.eval_expr(stmt["expr"], env)
            return {"type": "return", "value": val}
        elif stype == "stop":
            raise SystemExit(0)
        elif stype == "use":
            # Phase 1: built-in 'math' module is available implicitly
            pass
        elif stype == "array_assign":
            arr = self.eval_expr({"type": "var", "name": stmt["name"], "line": stmt["line"], "col": stmt["col"]}, env)
            idx = self.eval_expr(stmt["index"], env)
            val = self.eval_expr(stmt["expr"], env)
            if not isinstance(arr, list):
                raise AtomicError(f"Array expected, got {type(arr).__name__} at line {stmt['line']}, column {stmt['col']}")
            if idx < 0 or idx >= len(arr):
                raise AtomicError(f"Array index out of bounds: {idx} (length {len(arr)}) at line {stmt['line']}, column {stmt['col']}")
            arr[idx] = val
        else:
            raise AtomicError(f"Unknown statement type {stype}")

    def run(self, statements):
        if hasattr(statements, "body") and hasattr(statements, "imports"):
            self.imports = set(statements.imports)
            statements = statements.body
        try:
            self.execute_block(statements, self.globals)
        except SystemExit:
            pass
        return self.output


def tokenize(text: str) -> List[Token]:
    if text and text[0] == "\ufeff":
        text = text[1:]
    return Lexer(text).tokenize()


def parse(tokens: List[Token]):
    return Parser(tokens).parse()


def run_source(text: str):
    tokens = tokenize(text)
    ast = parse(tokens)
    # The interpreter executes the same resolved, typed tree passed onward to
    # code generation; parsed syntax dictionaries stop at this boundary.
    from ir import build_ir
    program = build_ir(ast)
    interp = Interpreter()
    try:
        interp.run(program)
    except SystemExit:
        pass
    return interp.output


def run_file(path: str):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return run_source(text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python interpreter.py <file.atpp>")
        sys.exit(1)
    try:
        output = run_file(sys.argv[1])
        for line in output:
            print(line)
    except SystemExit:
        sys.exit(0)
    except (SyntaxError, AtomicError) as e:
        print(f"Error: {e}")
        sys.exit(1)
