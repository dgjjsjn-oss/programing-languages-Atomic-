#!/usr/bin/env python3
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
    return "0"


def _join(a, b):
    if a is None:
        return b
    if b is None:
        return a
    if a == b:
        return a
    if {a, b} == {INT, F64}:
        return F64
    raise AtomicError(f"C backend: incompatible types {a} and {b}")


def _ty(e, env, ftypes, state):
    """Infer the C type of an expression."""
    t = e.get("type")
    if t == "int":
        return INT
    if t == "bool":
        return INT
    if t == "float":
        return F64
    if t == "string":
        return STR
    if t == "var":
        return env.get(e.get("name"), INT)
    if t == "unary":
        return _ty(e.get("operand"), env, ftypes, state)
    if t == "binop":
        op = e.get("op")
        lt = _ty(e.get("left"), env, ftypes, state)
        rt = _ty(e.get("right"), env, ftypes, state)
        if op in ("is", "is not", "<", ">", "<=", ">="):
            return INT
        if op == "+" and lt == STR and rt == STR:
            raise AtomicError("C backend: text concatenation not supported yet")
        if lt == STR or rt == STR:
            raise AtomicError("C backend: text arithmetic not supported yet")
        if lt == F64 or rt == F64:
            return F64
        return INT
    if t == "call":
        f = ftypes.get(e.get("name"))
        argts = [_ty(a, env, ftypes, state) for a in (e.get("args") or [])]
        if f is None:
            return INT
        params = f["params"]
        for i, at in enumerate(argts):
            if i < len(params):
                new = _join(params[i], at)
                if new != params[i]:
                    params[i] = new
                    state["changed"] = True
        return f["ret"] or INT
    if t == "method_call":
        for a in e.get("args") or []:
            _ty(a, env, ftypes, state)
        return INT
    if t == "array":
        raise AtomicError("C backend: array literals not supported yet")
    if t == "array_index":
        raise AtomicError("C backend: array indexing not supported yet")
    return INT


def _walk(stmts, env, ftypes, state, each_vars):
    rets = []
    for s in stmts:
        t = s.get("type")
        if t in ("var_assign", "assign"):
            ty = _ty(s.get("expr"), env, ftypes, state)
            new = _join(env.get(s["name"]), ty)
            if env.get(s["name"]) != new:
                env[s["name"]] = new
                state["changed"] = True
        elif t == "each":
            env[s["var"]] = INT
            each_vars.add(s["var"])
            _ty(s.get("start"), env, ftypes, state)
            _ty(s.get("end"), env, ftypes, state)
            rets += _walk(s.get("body") or [], env, ftypes, state, each_vars)
        elif t == "when":
            _ty(s.get("cond"), env, ftypes, state)
            rets += _walk(s.get("body") or [], env, ftypes, state, each_vars)
        elif t == "give":
            rets.append(_ty(s.get("expr"), env, ftypes, state))
        elif t in ("say", "expr"):
            _ty(s.get("expr"), env, ftypes, state)
    return rets


def _infer(ast):
    funcs = [s for s in ast if s.get("type") == "func"]
    body = [s for s in ast if s.get("type") not in ("func", "use")]
    ftypes = {f["name"]: {"params": [INT] * len(f["params"]), "ret": None} for f in funcs}
    top_env, fn_envs, each_vars = {}, {}, set()
    for _ in range(15):
        state = {"changed": False}
        top_env = {}
        _walk(body, top_env, ftypes, state, each_vars)
        fn_envs = {}
        for f in funcs:
            env = {p: ftypes[f["name"]]["params"][i] for i, p in enumerate(f["params"])}
            rets = _walk(f.get("body") or [], env, ftypes, state, each_vars)
            fn_envs[f["name"]] = env
            rt = None
            for r in rets:
                rt = _join(rt, r)
            if rt and rt != ftypes[f["name"]]["ret"]:
                ftypes[f["name"]]["ret"] = rt
                state["changed"] = True
        if not state["changed"]:
            break
    return top_env, fn_envs, ftypes, each_vars


def _c_expr_str(node, env, ftypes, state):
    t = node.get("type")
    if t == "int":
        return str(node["value"])
    if t == "bool":
        # Must be an integer literal: Python's True/False would emit `True`,
        # which is not C. bool is represented as int64_t in this backend.
        return "1" if node["value"] else "0"
    if t == "float":
        return repr(float(node["value"]))
    if t == "string":
        return '"%s"' % _c_escape(str(node["value"]))
    if t == "var":
        return _ident(node["name"])
    if t == "unary":
        inner = _c_expr_str(node["operand"], env, ftypes, state)
        if node["op"] == "-":
            ty = _ty(node["operand"], env, ftypes, state)
            if ty == F64:
                return f"(-({inner}))"
            return f"((int64_t)(-({inner})))"
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
        if op == "/":
            if lt == F64 or rt == F64:
                return f"((double)({a}) / (double)({b}))"
            return f"_atomic_div({a}, {b})"
        sym = {"<": "<", ">": ">", "<=": "<=", ">=": ">=", "+": "+", "-": "-", "*": "*"}.get(op, op)
        if lt == F64 or rt == F64:
            return f"((double)({a}) {sym} (double)({b}))"
        return f"((int64_t)({a}) {sym} (int64_t)({b}))"
    if t == "call":
        args = ", ".join(_c_expr_str(a, env, ftypes, state) for a in node["args"])
        return f"{_ident(node['name'])}({args})"
    if t == "method_call":
        raise AtomicError("C backend: module method calls not supported yet")
    raise AtomicError(f"C backend: unsupported expression type {t}")


def _say_stmt(expr, env, ftypes, state, pad):
    ty = _ty(expr, env, ftypes, state)
    if ty == STR:
        if expr.get("type") == "string":
            return f'{pad}fputs("{_c_escape(str(expr["value"]))}", stdout); putchar(\'\\n\');'
        return f'{pad}printf("%s\\n", {_c_expr_str(expr, env, ftypes, state)});'
    code = _c_expr_str(expr, env, ftypes, state)
    if ty == F64:
        return f"{pad}_atomic_say_f64({code});"
    return f'{pad}printf("%lld\\n", (int64_t)({code}));'


def _c_stmt_str(node, indent, env, ftypes, state):
    t = node.get("type")
    pad = "    " * indent
    if t == "say":
        return _say_stmt(node["expr"], env, ftypes, state, pad)
    if t in ("var_assign", "assign"):
        return f'{pad}{_ident(node["name"])} = {_c_expr_str(node["expr"], env, ftypes, state)};'
    if t == "array_assign":
        raise AtomicError("C backend: arrays not supported yet")
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
        lines = [
            # Bind the loop variable to the start value first: when the range is
            # empty it is still defined, and `start` is evaluated exactly once.
            f"{pad}{var} = (int64_t)({start});",
            f"{pad}for (int64_t {hidden} = {var}; {hidden} <= (int64_t)({end}); {hidden}++) {{",
            f"{pad}    {var} = {hidden};",
        ]
        for s in node["body"]:
            lines.append(_c_stmt_str(s, indent + 1, env, ftypes, state))
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
    "",
    "#if defined(__GNUC__)",
    "#define ATOMIC_UNUSED __attribute__((unused))",
    "#else",
    "#define ATOMIC_UNUSED",
    "#endif",
    "",
    "static long long _atomic_div(long long a, long long b) {",
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
    """Emit typed C source from the parser AST."""
    top_env, fn_envs, ftypes, each_vars = _infer(ast)
    state = {"changed": False}
    body = [s for s in ast if s.get("type") not in ("func", "use")]
    funcs = [s for s in ast if s.get("type") == "func"]

    out = list(PREAMBLE)
    for f in funcs:
        out.append(_c_func(f, fn_envs[f["name"]], ftypes, each_vars, state))
        out.append("")
    out.append("int main(void) {")
    out += _decls(top_env, each_vars)
    for s in body:
        out.append(_c_stmt_str(s, 1, top_env, ftypes, state))
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
