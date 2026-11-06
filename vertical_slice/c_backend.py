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

"""ATOMIC++ native backend -- typed C emitter + gcc driver.

Pipeline: parser AST -> type inference -> C source -> gcc -> native binary.

Supported (v2):
  - int (64-bit, wrapping), float (double), text (const char *), bool
  - arithmetic + - * /, unary -, grouping, comparisons
  - variables with inferred types, when, each, functions, recursion
  - say for int / float / text
  - give / stop / expr / use

Known gaps (raise AtomicError with a clear message): arrays, modules,
method calls, string concatenation, else branches.
"""

import os
import subprocess

try:
    from interpreter import AtomicError
except ImportError:
    from vertical_slice.interpreter import AtomicError

from ir import (FLOAT as IR_FLOAT, INT as IR_INT, BOOL as IR_BOOL, TEXT as IR_TEXT,
                Type, IRProgram, build_ir, loop_variables, verify_ir)

GCC = os.environ.get("ATOMIC_GCC", "gcc")

INT = "int64_t"
F64 = "double"
STR = "const char *"

_C_KEYWORDS = {
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if", "inline",
    "int", "long", "register", "restrict", "return", "short", "signed", "sizeof",
    "static", "struct", "switch", "typedef", "union", "unsigned", "void",
    "volatile", "while", "main", "_atomic_div",
}


def _ident(name: str) -> str:
    """Map an ATOMIC++ identifier to a safe C identifier."""
    if name in _C_KEYWORDS:
        return "a_" + name
    return name


def _c_escape(s: str) -> str:
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        else:
            out.append(ch)
    return "".join(out)


def _c_default(ctype: str) -> str:
    """Type-appropriate zero value, so a declared-but-never-assigned name is
    defined rather than holding uninitialised stack garbage."""
    if ctype == F64:
        return "0.0"
    if ctype == STR:
        return '""'
    if ctype == "atomic_array":
        return "(atomic_array){0, NULL}"
    return "0"


def _ty(e, env, ftypes, state):
    """Map the type already recorded on a typed IR expression to C."""
    ty = e.get("inferred_type")
    if ty == IR_INT or ty == IR_BOOL:
        return INT
    if ty == IR_FLOAT:
        return F64
    if ty == IR_TEXT:
        return STR
    if isinstance(ty, Type) and ty.name == "list":
        _array_element_c(ty.element)
        return "atomic_array"
    if ty is None:
        raise AtomicError("C backend requires typed IR expressions")
    raise AtomicError(f"C backend: unsupported IR type {ty}")


def _ctype(ty: Type) -> str:
    if ty in (IR_INT, IR_BOOL):
        return INT
    if ty == IR_FLOAT:
        return F64
    if ty == IR_TEXT:
        return STR
    if ty.name == "list":
        _array_element_c(ty.element)
        return "atomic_array"
    raise AtomicError(f"C backend: unsupported IR type {ty}")


def _array_element_c(element: Type) -> str:
    if element in (IR_INT, IR_BOOL):
        return "int64_t"
    if element == IR_FLOAT:
        return "double"
    if element == IR_TEXT:
        return "const char *"
    raise AtomicError(f"C backend: arrays of {element} are not supported")


def _c_expr_str(node, env, ftypes, state):
    if node.get("ir_kind") == "BooleanOperation":
        operands = node.operands
        op = node.op
        if op == "not":
            value = _c_expr_str(operands[0], env, ftypes, state)
            return f"(!(({value}) != 0))"
        if op in ("and", "or"):
            symbol = "&&" if op == "and" else "||"
            values = [f"(({_c_expr_str(item, env, ftypes, state)}) != 0)" for item in operands]
            return "(" + f" {symbol} ".join(values) + ")"
        raise AtomicError(f"C backend: unsupported boolean operation {op!r}")
    t = node.get("type")
    if t == "int":
        value = int(node["value"])
        if value == -(1 << 63):
            return "INT64_MIN"
        if value < 0:
            return f"(-INT64_C({-value}))"
        return f"INT64_C({value})"
    if t == "bool":
        # Must be an integer literal: Python's True/False would emit `True`,
        # which is not C. bool is represented as int64_t in this backend.
        return "1" if node["value"] else "0"
    if t == "float":
        return repr(float(node["value"]))
    if t == "string":
        return '"%s"' % _c_escape(str(node["value"]))
    if t == "array":
        element_type = _array_element_c(node.value_type.element)
        values = ", ".join(_c_expr_str(item, env, ftypes, state) for item in node.elements)
        source = f"({element_type}[]){{{values}}}" if values else "NULL"
        return f"_atomic_array_new({len(node.elements)}, sizeof({element_type}), {source})"
    if t == "array_index":
        element_type = _array_element_c(node.value_type)
        target = _ident(node.var)
        index = _c_expr_str(node.index, env, ftypes, state)
        return f"(({element_type} *){target}.data)[_atomic_index({target}.length, (int64_t)({index}))]"
    if t == "var":
        return _ident(node["name"])
    if t == "unary":
        inner = _c_expr_str(node["operand"], env, ftypes, state)
        if node["op"] == "-":
            ty = _ty(node["operand"], env, ftypes, state)
            if ty == F64:
                return f"(-({inner}))"
            return f"_atomic_neg((int64_t)({inner}))"
        return f"({inner})"
    if t == "binop":
        op = node["op"]
        a = _c_expr_str(node["left"], env, ftypes, state)
        b = _c_expr_str(node["right"], env, ftypes, state)
        lt = _ty(node["left"], env, ftypes, state)
        rt = _ty(node["right"], env, ftypes, state)
        if op in ("is", "is not"):
            if lt == STR and rt == STR:
                cmp = f"(strcmp({a}, {b}) == 0)"
                return cmp if op == "is" else f"(!{cmp})"
            return f"(({a}) == ({b}))" if op == "is" else f"(({a}) != ({b}))"
        if lt == STR or rt == STR:
            raise AtomicError("C backend: text arithmetic and concatenation not supported yet")
        if op == "/":
            if lt == F64 or rt == F64:
                return f"((double)({a}) / (double)({b}))"
            return f"_atomic_div({a}, {b})"
        sym = {"<": "<", ">": ">", "<=": "<=", ">=": ">=", "+": "+", "-": "-", "*": "*"}.get(op, op)
        if lt == F64 or rt == F64:
            return f"((double)({a}) {sym} (double)({b}))"
        if op in ("+", "-", "*"):
            return f"_atomic_{ {'+': 'add', '-': 'sub', '*': 'mul'}[op] }((int64_t)({a}), (int64_t)({b}))"
        return f"((int64_t)({a}) {sym} (int64_t)({b}))"
    if t == "call":
        if node.get("name") == "len":
            if len(node.args) == 1 and isinstance(node.args[0].get("inferred_type"), Type) and node.args[0].get("inferred_type").name == "list":
                array = _c_expr_str(node.args[0], env, ftypes, state)
                return f"((int64_t)({array}).length)"
            raise AtomicError("C backend: len is currently implemented for arrays only")
        args = ", ".join(_c_expr_str(a, env, ftypes, state) for a in node["args"])
        return f"{_ident(node['name'])}({args})"
    if t == "method_call":
        if node.module != "math" or node.method not in ("add", "sub", "mul") or len(node.args) != 2:
            raise AtomicError(f"C backend: unsupported module call {node.module}.{node.method}")
        a = _c_expr_str(node.args[0], env, ftypes, state)
        b = _c_expr_str(node.args[1], env, ftypes, state)
        if node.value_type == IR_FLOAT:
            symbol = {"add": "+", "sub": "-", "mul": "*"}[node.method]
            return f"((double)({a}) {symbol} (double)({b}))"
        helper = {"add": "_atomic_add", "sub": "_atomic_sub", "mul": "_atomic_mul"}[node.method]
        return f"{helper}((int64_t)({a}), (int64_t)({b}))"
    raise AtomicError(f"C backend: unsupported expression type {t}")


def _say_stmt(expr, env, ftypes, state, pad):
    if expr.get("inferred_type") == IR_BOOL:
        code = _c_expr_str(expr, env, ftypes, state)
        return f'{pad}printf("%s\\n", (({code}) != 0) ? "True" : "False");'
    ty = _ty(expr, env, ftypes, state)
    if ty == STR:
        if expr.get("type") == "string":
            return f'{pad}fputs("{_c_escape(str(expr["value"]))}", stdout); putchar(\'\\n\');'
        return f'{pad}printf("%s\\n", {_c_expr_str(expr, env, ftypes, state)});'
    code = _c_expr_str(expr, env, ftypes, state)
    if ty == F64:
        return f"{pad}_atomic_say_f64({code});"
    return f'{pad}printf("%" PRId64 "\\n", (int64_t)({code}));'


def _c_stmt_str(node, indent, env, ftypes, state):
    t = node.get("type")
    pad = "    " * indent
    if t == "say":
        return _say_stmt(node["expr"], env, ftypes, state, pad)
    if t in ("var_assign", "assign"):
        return f'{pad}{_ident(node["name"])} = {_c_expr_str(node["expr"], env, ftypes, state)};'
    if t == "array_assign":
        element_type = _array_element_c(node.expr.value_type)
        target = _ident(node.name)
        index = _c_expr_str(node.index, env, ftypes, state)
        value = _c_expr_str(node.expr, env, ftypes, state)
        return (f"{pad}(({element_type} *){target}.data)["
                f"_atomic_index({target}.length, (int64_t)({index}))] = ({element_type})({value});")
    if t == "expr":
        return f'{pad}{_c_expr_str(node["expr"], env, ftypes, state)};'
    if t == "func":
        return f"{pad}/* function {node.get('name')} */"
    if t == "when":
        cond = _c_expr_str(node["cond"], env, ftypes, state)
        lines = [f"{pad}if (({cond}) != 0) {{"]
        for s in node["body"]:
            lines.append(_c_stmt_str(s, indent + 1, env, ftypes, state))
        lines.append(f"{pad}}}")
        return "\n".join(lines)
    if t == "each":
        var = _ident(node["var"])
        start = _c_expr_str(node["start"], env, ftypes, state)
        end = _c_expr_str(node["end"], env, ftypes, state)
        # Iterate a hidden counter and copy it into the user variable each pass.
        # Two reasons: the loop variable keeps its LAST value after the loop
        # (so `each i from 5 to 7` leaves i == 7, as the interpreter does), and
        # assigning to it inside the body cannot derail the iteration.
        depth = state.get("loop_depth", 0) + 1
        state["loop_depth"] = depth
        hidden = f"_atomic_i{depth}"
        end_name = f"_atomic_end{depth}"
        lines = [
            # Bind the loop variable to the start value first: when the range is
            # empty it is still defined, and `start` is evaluated exactly once.
            f"{pad}{var} = (int64_t)({start});",
            f"{pad}int64_t {end_name} = (int64_t)({end});",
            f"{pad}int64_t {hidden} = {var};",
            f"{pad}while ({hidden} <= {end_name}) {{",
            f"{pad}    {var} = {hidden};",
        ]
        for s in node["body"]:
            lines.append(_c_stmt_str(s, indent + 1, env, ftypes, state))
        lines.append(f"{pad}    if ({hidden} == {end_name}) break;")
        lines.append(f"{pad}    {hidden} = _atomic_add({hidden}, INT64_C(1));")
        lines.append(f"{pad}}}")
        state["loop_depth"] = depth - 1
        return "\n".join(lines)
    if t == "give":
        return f'{pad}return {_c_expr_str(node["expr"], env, ftypes, state)};'
    if t == "stop":
        return f"{pad}return 0;"
    if t == "use":
        return f"{pad}/* use {node.get('module')} */"
    raise AtomicError(f"C backend: unsupported statement type {t}")


def _decls(env, each_vars, exclude=()):
    """Declare every name in `env` at function scope.

    Loop variables are included on purpose: ATOMIC++ names are function-scoped,
    so `each i ...` makes `i` visible after the loop (LANGUAGE_SPEC.md 4.1).
    `each_vars` is kept in the signature for callers but no longer filters.
    """
    lines = []
    for name in sorted(env):
        if name in exclude:
            continue
        lines.append(f"    {env[name]} {_ident(name)} = {_c_default(env[name])};")
    return lines


def _c_func(f, env, ftypes, each_vars, state):
    info = ftypes[f["name"]]
    ret = info["ret"] or INT
    params = ", ".join(f"{info['params'][i]} {_ident(p)}" for i, p in enumerate(f["params"]))
    lines = [f"{ret} {_ident(f['name'])}({params}) {{"]
    lines += _decls(env, each_vars, exclude=set(f["params"]))
    body = [_c_stmt_str(s, 1, env, ftypes, state) for s in f.get("body") or []]
    lines += body
    if ret != "void" and (not body or not body[-1].lstrip().startswith("return")):
        lines.append("    return 0;")
    lines.append("}")
    return "\n".join(lines)


PREAMBLE = [
    "#include <stdio.h>",
    "#include <stdlib.h>",
    "#include <string.h>",
    "#include <stdint.h>",
    "#include <inttypes.h>",
    "#include <stddef.h>",
    "",
    "#if defined(__GNUC__)",
    "#define ATOMIC_UNUSED __attribute__((unused))",
    "#else",
    "#define ATOMIC_UNUSED",
    "#endif",
    "",
    "typedef struct { size_t length; void *data; } atomic_array;",
    "typedef struct atomic_allocation { void *data; struct atomic_allocation *next; } atomic_allocation;",
    "static atomic_allocation *_atomic_allocations = NULL;",
    "static int _atomic_cleanup_registered = 0;",
    "static void _atomic_cleanup(void) {",
    "    while (_atomic_allocations) { atomic_allocation *n = _atomic_allocations->next; free(_atomic_allocations->data); free(_atomic_allocations); _atomic_allocations = n; }",
    "}",
    "static void *_atomic_array_data(size_t count, size_t width, const void *source) {",
    "    if (count == 0) return NULL;",
    '    if (width != 0 && count > SIZE_MAX / width) { fputs("Array allocation too large\\n", stderr); exit(1); }',
    "    void *data = malloc(count * width);",
    '    if (!data) { fputs("Array allocation failed\\n", stderr); exit(1); }',
    "    memcpy(data, source, count * width);",
    "    atomic_allocation *entry = (atomic_allocation *)malloc(sizeof *entry);",
    '    if (!entry) { free(data); fputs("Array allocation failed\\n", stderr); exit(1); }',
    "    entry->data = data; entry->next = _atomic_allocations; _atomic_allocations = entry;",
    "    if (!_atomic_cleanup_registered) { atexit(_atomic_cleanup); _atomic_cleanup_registered = 1; }",
    "    return data;",
    "}",
    "static atomic_array _atomic_array_new(size_t count, size_t width, const void *source) {",
    "    atomic_array result = { count, _atomic_array_data(count, width, source) }; return result;",
    "}",
    "static size_t _atomic_index(size_t length, int64_t index) {",
    '    if (index < 0 || (uint64_t)index >= length) { fprintf(stderr, "Array index out of bounds: %" PRId64 " (length %zu)\\n", index, length); exit(1); }',
    "    return (size_t)index;",
    "}",
    "",
    "static int64_t _atomic_from_bits(uint64_t bits) {",
    "    int64_t result;",
    "    memcpy(&result, &bits, sizeof result);",
    "    return result;",
    "}",
    "static int64_t _atomic_add(int64_t a, int64_t b) {",
    "    return _atomic_from_bits((uint64_t)a + (uint64_t)b);",
    "}",
    "static int64_t _atomic_sub(int64_t a, int64_t b) {",
    "    return _atomic_from_bits((uint64_t)a - (uint64_t)b);",
    "}",
    "static int64_t _atomic_mul(int64_t a, int64_t b) {",
    "    return _atomic_from_bits((uint64_t)a * (uint64_t)b);",
    "}",
    "static int64_t _atomic_neg(int64_t a) {",
    "    return _atomic_from_bits((uint64_t)0 - (uint64_t)a);",
    "}",
    "static int64_t _atomic_div(int64_t a, int64_t b) {",
    '    if (b == 0) { fprintf(stderr, "Division by zero\\n"); exit(1); }',
    "    if (a == INT64_MIN && b == -1) return a;",
    "    return a / b;",
    "}",
    "",
    "static ATOMIC_UNUSED void _atomic_say_f64(double v) {",
    "    char buf[64];",
    '    if (v != v) { printf("nan\\n"); return; }',
    '    snprintf(buf, sizeof buf, "%.17g", v);',
    "    if (!strchr(buf, '.') && !strchr(buf, 'e') && !strchr(buf, 'E')",
    "        && !strchr(buf, 'n') && !strchr(buf, 'i')) strcat(buf, \".0\");",
    '    printf("%s\\n", buf);',
    "}",
    "",
]


def emit_c(ast) -> str:
    """Emit C from typed IR (AST input remains accepted as a compatibility API)."""
    program = ast if isinstance(ast, IRProgram) else build_ir(ast)
    invalid = verify_ir(program)
    if invalid:
        raise AtomicError("Invalid typed IR: " + invalid[0]["message"])
    top_env = {name: _ctype(ty) for name, ty in program.global_types.items()}
    fn_envs = {name: {key: _ctype(ty) for key, ty in values.items()}
               for name, values in program.function_locals.items()}
    ftypes = {
        name: {"params": [_ctype(ty) for ty in sig[0]], "ret": _ctype(sig[1])}
        for name, sig in program.function_types.items()
    }
    each_vars = loop_variables(program.body)
    state = {"changed": False}
    body = [s for s in program if s.get("type") not in ("func", "use")]
    funcs = [s for s in program if s.get("type") == "func"]

    out = list(PREAMBLE)
    for name, ty in sorted(top_env.items()):
        out.append(f"static {ty} {_ident(name)} = {_c_default(ty)};")
    if top_env:
        out.append("")
    for f in funcs:
        out.append(_c_func(f, fn_envs[f["name"]], ftypes, each_vars, state))
        out.append("")
    out.append("int main(void) {")
    # Top-level bindings are file-scope variables so functions can read them.
    for s in body:
        out.append(_c_stmt_str(s, 1, top_env, ftypes, state))
    if not any(s.get("type") == "stop" for s in body):
        out.append("    return 0;")
    out.append("}")
    return "\n".join(out)


def compile_c(c_source: str, exe_path: str, portable: bool = True, march_native: bool = False, optimization: str = "-O2") -> str:
    """Write C source and compile with gcc. Returns exe path."""
    tmp_c = exe_path + ".c"
    with open(tmp_c, "w", encoding="utf-8") as f:
        f.write(c_source)
    cmd = [GCC, optimization]
    if not portable and march_native:
        cmd.append("-march=native")
    cmd += ["-o", exe_path, tmp_c]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise AtomicError(f"C compilation failed:\n{r.stderr}")
    return exe_path
