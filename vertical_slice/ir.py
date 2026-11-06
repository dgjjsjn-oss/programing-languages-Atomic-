#!/usr/bin/env python3
"""ATOMIC++ Phase 3 -- Typed Intermediate Representation (IR).

The parser output (list of statement dicts) is the *parsed syntax* AST.
This module defines the typed ATOMIC++ IR that both the interpreter and the
C backend consume, independent of the exact source syntax.

IR node types (aliases of the IR_* constants in interpreter):
  program -> body: [statement]
  func    -> name, params, body
  var_assign -> name, expr
  array_assign -> name, index, expr
  when    -> cond, body
  each    -> var, start, end, body
  say     -> expr
  give    -> expr
  stop    -> (none)
  use     -> module
  expr     -> expr
  binop   -> op, left, right
  call    -> name, args
  method_call -> module, method, args
  array    -> elements
  array_index -> var, index
  int/float/string/bool/var -> value / name

Builder converts a parser statement list into a typed IR program.
"""

from interpreter import (
    IR_ARRAY, IR_ARRAY_ASSIGN, IR_ARRAY_INDEX, IR_BOOL, IR_BINOP, IR_CALL, IR_EACH,
    IR_EXPR, IR_FLOAT, IR_FUNC, IR_GIVE, IR_INT, IR_METHOD_CALL, IR_PROGRAM, IR_SAY,
    IR_STOP, IR_USE, IR_VAR, IR_VAR_ASSIGN, IR_STRING, IR_UNARY, IR_WHEN,
)


def _expr_ir(e: dict) -> dict:
    t = e.get("type")
    if t == "unary":
        return {"type": IR_UNARY, "op": e.get("op"), "operand": _expr_ir(e.get("operand")),
                "line": e.get("line"), "col": e.get("col")}
    if t == "binop":
        return {"type": IR_BINOP, "op": e.get("op"), "left": _expr_ir(e.get("left")), "right": _expr_ir(e.get("right")),
                "line": e.get("line"), "col": e.get("col")}
    if t == "call":
        return {"type": IR_CALL, "name": e.get("name"), "args": [_expr_ir(a) for a in e.get("args") or []],
                "line": e.get("line"), "col": e.get("col")}
    if t == "method_call":
        return {"type": IR_METHOD_CALL, "module": e.get("module"), "method": e.get("method"),
                "args": [_expr_ir(a) for a in e.get("args") or []], "line": e.get("line"), "col": e.get("col")}
    if t == "array":
        return {"type": IR_ARRAY, "elements": [_expr_ir(x) for x in e.get("elements") or []],
                "line": e.get("line"), "col": e.get("col")}
    if t == "array_index":
        return {"type": IR_ARRAY_INDEX, "var": e.get("var"), "index": _expr_ir(e.get("index")),
                "line": e.get("line"), "col": e.get("col")}
    return {"type": t, "value": e.get("value"), "name": e.get("name"), "line": e.get("line"), "col": e.get("col")}


def _stmt_ir(s: dict) -> dict:
    t = s.get("type")
    if t == "func":
        return {"type": IR_FUNC, "name": s.get("name"), "params": s.get("params") or [],
                "body": [_stmt_ir(x) for x in s.get("body") or []], "line": s.get("line"), "col": s.get("col")}
    if t in ("var_assign", "assign"):
        return {"type": IR_VAR_ASSIGN, "name": s.get("name"), "expr": _expr_ir(s.get("expr")),
                "line": s.get("line"), "col": s.get("col")}
    if t == "array_assign":
        return {"type": IR_ARRAY_ASSIGN, "name": s.get("name"), "index": _expr_ir(s.get("index")),
                "expr": _expr_ir(s.get("expr")), "line": s.get("line"), "col": s.get("col")}
    if t == "when":
        return {"type": IR_WHEN, "cond": _expr_ir(s.get("cond")), "body": [_stmt_ir(x) for x in s.get("body") or []],
                "line": s.get("line"), "col": s.get("col")}
    if t == "each":
        return {"type": IR_EACH, "var": s.get("var"), "start": _expr_ir(s.get("start")),
                "end": _expr_ir(s.get("end")), "body": [_stmt_ir(x) for x in s.get("body") or []],
                "line": s.get("line"), "col": s.get("col")}
    if t == "say":
        return {"type": IR_SAY, "expr": _expr_ir(s.get("expr")), "line": s.get("line"), "col": s.get("col")}
    if t == "give":
        return {"type": IR_GIVE, "expr": _expr_ir(s.get("expr")), "line": s.get("line"), "col": s.get("col")}
    if t == "stop":
        return {"type": IR_STOP, "line": s.get("line"), "col": s.get("col")}
    if t == "use":
        return {"type": IR_USE, "module": s.get("module"), "line": s.get("line"), "col": s.get("col")}
    if t == "expr":
        return {"type": IR_EXPR, "expr": _expr_ir(s.get("expr")), "line": s.get("line"), "col": s.get("col")}
    return {"type": t, "line": s.get("line"), "col": s.get("col")}


def build_ir(statements) -> dict:
    """Build a typed ATOMIC++ IR program from a parser statement list."""
    return {"type": IR_PROGRAM, "body": [_stmt_ir(s) for s in statements], "line": 1, "col": 1}
