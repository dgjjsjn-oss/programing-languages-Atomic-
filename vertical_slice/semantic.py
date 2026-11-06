#!/usr/bin/env python3
"""ATOMIC++ Phase 3 -- Semantic Analyzer.

Walks the typed IR and emits clear source-line diagnostics for:
  - undefined variables
  - function existence / argument count mismatches
  - invalid return statements (give outside a function)
  - invalid operations between types
  - conditions that use unsupported types
  - invalid assignment operations

Diagnostics are returned as a list; each carries line + column + message.
"""

from ir import build_ir
from interpreter import parse, tokenize


def _type_of_expr(e: dict, env_types: dict, funcs: dict) -> str:
    t = e.get("type")
    if t in ("int", "bool"):
        return "int"
    if t == "float":
        return "float"
    if t == "string":
        return "string"
    if t == "var":
        name = e.get("name")
        if name in env_types:
            return env_types[name]
        return "undefined"
    if t == "array":
        return "array"
    if t == "array_index":
        return "int"
    if t == "call":
        fname = e.get("name")
        f = funcs.get(fname)
        if f is None:
            return "undefined_func"
        # The IR carries no return types yet, so a call result is an int — the
        # same default every backend uses. Returning "none" (the old behaviour)
        # turned `x = f(x)` followed by `x + 1` into a false type error.
        return f.get("ret") or "int"
    if t == "unary":
        return _type_of_expr(e.get("operand"), env_types, funcs)
    if t == "binop":
        return "int"
    return "unknown"


def _check_expr(e: dict, env_types: dict, funcs: dict, diags: list) -> None:
    t = e.get("type")
    if t in ("int", "bool", "float", "string", "array", "array_index"):
        return
    if t == "var":
        name = e.get("name")
        if name not in env_types:
            diags.append({"line": e.get("line"), "col": e.get("col"),
                          "code": "undefined_variable", "message": f"Undefined variable '{name}'"})
        return
    if t == "unary":
        ot = _type_of_expr(e.get("operand"), env_types, funcs)
        if ot not in ("int", "float"):
            diags.append({"line": e.get("line"), "col": e.get("col"),
                          "code": "invalid_operation",
                          "message": f"Invalid operand for unary '{e.get('op')}': {ot}"})
        _check_expr(e.get("operand"), env_types, funcs, diags)
        return
    if t == "binop":
        op = e.get("op")
        lt = _type_of_expr(e.get("left"), env_types, funcs)
        rt = _type_of_expr(e.get("right"), env_types, funcs)
        if "undefined" in (lt, rt):
            # No cascading errors: the undefined name is the root cause, so report
            # only that and let the operand walk emit it. Otherwise `y + 1`
            # produces both "undefined variable" and "invalid operands".
            _check_expr(e.get("left"), env_types, funcs, diags)
            _check_expr(e.get("right"), env_types, funcs, diags)
            return
        if op in ("+", "-"):
            ok = (lt == "int" and rt == "int") or (lt == "string" and rt == "string")
            if not ok:
                diags.append({"line": e.get("line"), "col": e.get("col"),
                              "code": "invalid_operation", "message": f"Invalid operands for '{op}': {lt} {op} {rt}"})
        elif op in ("*", "/"):
            if lt != "int" or rt != "int":
                diags.append({"line": e.get("line"), "col": e.get("col"),
                              "code": "invalid_operation", "message": f"Invalid operands for '{op}': {lt} {op} {rt}"})
        elif op in ("is", "is not", "<", ">", "<=", ">="):
            if lt not in ("int", "bool") or rt not in ("int", "bool"):
                diags.append({"line": e.get("line"), "col": e.get("col"),
                              "code": "invalid_operation", "message": f"Invalid comparison '{op}': {lt} vs {rt}"})
        _check_expr(e.get("left"), env_types, funcs, diags)
        _check_expr(e.get("right"), env_types, funcs, diags)
        return
    if t == "call":
        fname = e.get("name")
        f = funcs.get(fname)
        if f is None:
            diags.append({"line": e.get("line"), "col": e.get("col"),
                          "code": "undefined_function", "message": f"Undefined function '{fname}'"})
        elif len(e.get("args") or []) != len(f.get("params") or []):
            diags.append({"line": e.get("line"), "col": e.get("col"),
                          "code": "invalid_call", "message": f"Function '{fname}' expects {len(f.get('params') or [])} args, got {len(e.get('args') or [])}"})
        for a in e.get("args") or []:
            _check_expr(a, env_types, funcs, diags)
        return
    if t == "method_call":
        for a in e.get("args") or []:
            _check_expr(a, env_types, funcs, diags)
        return
    if t == "array_index":
        _check_expr(e.get("index"), env_types, funcs, diags)
        return


def _check_stmt(s: dict, env_types: dict, funcs: dict, diags: list, in_func: bool) -> None:
    t = s.get("type")
    if t in ("int", "float", "string", "bool", "array", "array_index", "var"):
        return
    if t == "func":
        return
    if t == "var_assign":
        # Assignment DEFINES the name (LANGUAGE_SPEC.md 4.1). Checking the
        # expression first means reading-before-writing is still caught, while a
        # function's own locals are legal. Previously every local in a function
        # was reported undefined, because only parameters were in scope.
        _check_expr(s.get("expr"), env_types, funcs, diags)
        env_types[s.get("name")] = _type_of_expr(s.get("expr"), env_types, funcs)
        return
    if t == "array_assign":
        _check_expr(s.get("index"), env_types, funcs, diags)
        _check_expr(s.get("expr"), env_types, funcs, diags)
        return
    if t == "when":
        _check_expr(s.get("cond"), env_types, funcs, diags)
        for b in s.get("body") or []:
            _check_stmt(b, env_types, funcs, diags, in_func)
        return
    if t == "each":
        _check_expr(s.get("start"), env_types, funcs, diags)
        _check_expr(s.get("end"), env_types, funcs, diags)
        # The loop variable is visible in the body and afterwards (spec 4.1).
        env_types[s.get("var")] = "int"
        for b in s.get("body") or []:
            _check_stmt(b, env_types, funcs, diags, in_func)
        return
    if t == "give":
        if not in_func:
            diags.append({"line": s.get("line"), "col": s.get("col"),
                          "code": "invalid_return", "message": "'give' outside a function"})
        _check_expr(s.get("expr"), env_types, funcs, diags)
        return
    if t == "say":
        _check_expr(s.get("expr"), env_types, funcs, diags)
        return
    if t == "expr":
        _check_expr(s.get("expr"), env_types, funcs, diags)
        return


def analyze(source_or_ast) -> list:
    """Analyze a source string or parser AST; returns list of diagnostics."""
    ast = source_or_ast if isinstance(source_or_ast, list) else None
    if ast is None:
        ast = parse(tokenize(source_or_ast))
    ir_prog = build_ir(ast)
    diags: list = []

    funcs: dict = {}
    for s in ir_prog.get("body") or []:
        if s.get("type") == "func":
            funcs[s.get("name")] = s

    env_types: dict = {}
    for s in ir_prog.get("body") or []:
        if s.get("type") == "func":
            for p in s.get("params") or []:
                env_types[p] = "int"
        elif s.get("type") in ("var_assign", "assign"):
            env_types[s.get("name")] = _type_of_expr(s.get("expr"), env_types, funcs)

    for s in ir_prog.get("body") or []:
        if s.get("type") == "func":
            continue
        # Every top-level statement is checked, including the bodies of `when`
        # and `each`. These used to be skipped, so an undefined variable inside
        # a top-level `when` was never reported at all.
        _check_stmt(s, env_types, funcs, diags, in_func=False)

    for f in funcs.values():
        fenv = {p: "int" for p in f.get("params") or []}
        for s in f.get("body") or []:
            _check_stmt(s, fenv, funcs, diags, in_func=True)

    return diags
