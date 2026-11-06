#!/usr/bin/env python3
"""ATOMIC++ Java backend -- emit Java source from the parser AST.

Target use: Minecraft (Fabric / Forge) mods, Android, and any JVM library.
The emitted class is plain Java 17+ with no dependencies, so it drops into a
Gradle project unchanged.

Type mapping: int/bool -> long, float -> double, text -> String.
Local variables are hoisted to the top of the method because ATOMIC++ block
scoping is function-scoped (same as Python).
"""

import os
import subprocess

try:
    from interpreter import AtomicError
    from c_backend import _infer, F64, STR, INT
except ImportError:
    from vertical_slice.interpreter import AtomicError
    from vertical_slice.c_backend import _infer, F64, STR, INT

_J_KEYWORDS = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
    "class", "const", "continue", "default", "do", "double", "else", "enum",
    "extends", "final", "finally", "float", "for", "goto", "if", "implements",
    "import", "instanceof", "int", "interface", "long", "native", "new",
    "package", "private", "protected", "public", "return", "short", "static",
    "strictfp", "super", "switch", "synchronized", "this", "throw", "throws",
    "transient", "try", "void", "volatile", "while", "var", "record", "sealed",
    "yield", "null", "true", "false",
}

_JTYPE = {INT: "long", F64: "double", STR: "String"}


def _jident(name: str) -> str:
    if name in _J_KEYWORDS:
        return "a_" + name
    return name


def _jtype(ctype: str) -> str:
    return _JTYPE.get(ctype, "long")


def _default(ctype: str) -> str:
    if ctype == F64:
        return "0.0"
    if ctype == STR:
        return '""'
    return "0"


def _j_escape(s: str) -> str:
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


def _expr(e, env, ftypes, state, in_main):
    t = e.get("type")
    if t == "int":
        return str(e["value"]) + "L"
    if t == "float":
        return repr(float(e["value"]))
    if t == "string":
        return '"%s"' % _j_escape(str(e["value"]))
    if t == "bool":
        # bool is typed as long in this backend (see _JTYPE), so a bare Java
        # boolean literal would not compile against a `long` variable.
        return "1L" if e["value"] else "0L"
    if t == "var":
        return _jident(e["name"])
    if t == "unary":
        inner = _expr(e["operand"], env, ftypes, state, in_main)
        return f"(-({inner}))" if e["op"] == "-" else f"({inner})"
    if t == "binop":
        op = e["op"]
        a = _expr(e["left"], env, ftypes, state, in_main)
        b = _expr(e["right"], env, ftypes, state, in_main)
        from c_backend import _ty
        lt = _ty(e["left"], env, ftypes, state)
        rt = _ty(e["right"], env, ftypes, state)
        if op == "is":
            if lt == STR and rt == STR:
                return f"({a}.equals({b}))"
            return f"(({a}) == ({b}))"
        if op == "is not":
            if lt == STR and rt == STR:
                return f"(!{a}.equals({b}))"
            return f"(({a}) != ({b}))"
        sym = {"<": "<", ">": ">", "<=": "<=", ">=": ">=",
               "+": "+", "-": "-", "*": "*", "/": "/"}.get(op, op)
        return f"(({a}) {sym} ({b}))"
    if t == "call":
        args = ", ".join(_expr(a, env, ftypes, state, in_main) for a in e["args"])
        return f"{_jident(e['name'])}({args})"
    if t == "method_call":
        args = ", ".join(_expr(a, env, ftypes, state, in_main) for a in e["args"])
        return f"{_jident(e['module'])}.{_jident(e['method'])}({args})"
    raise AtomicError(f"Java backend: unsupported expression type {t}")


def _stmt(s, indent, env, ftypes, state, each_vars, in_main):
    from c_backend import _ty
    t = s.get("type")
    pad = "    " * indent
    if t == "say":
        return f"{pad}System.out.println({_expr(s['expr'], env, ftypes, state, in_main)});"
    if t in ("var_assign", "assign"):
        return f"{pad}{_jident(s['name'])} = {_expr(s['expr'], env, ftypes, state, in_main)};"
    if t == "expr":
        return f"{pad}{_expr(s['expr'], env, ftypes, state, in_main)};"
    if t == "when":
        cond = _expr(s["cond"], env, ftypes, state, in_main)
        test = cond if _is_boolean_expr(s["cond"]) else f"(({cond}) != 0)"
        lines = [f"{pad}if ({test}) {{"]
        for x in s["body"]:
            lines.append(_stmt(x, indent + 1, env, ftypes, state, each_vars, in_main))
        lines.append(f"{pad}}}")
        return "\n".join(lines)
    if t == "each":
        var = _jident(s["var"])
        start = _expr(s["start"], env, ftypes, state, in_main)
        end = _expr(s["end"], env, ftypes, state, in_main)
        # Hidden counter, same reason as the C backend: the loop variable keeps
        # its last value afterwards, and body assignments cannot skip iterations.
        depth = state.get("loop_depth", 0) + 1
        state["loop_depth"] = depth
        hidden = f"_atomic_i{depth}"
        lines = [
            # Bind to the start value first: defined even for an empty range, and
            # the start expression is evaluated exactly once.
            f"{pad}{var} = (long)({start});",
            f"{pad}for (long {hidden} = {var}; {hidden} <= (long)({end}); {hidden}++) {{",
            f"{pad}    {var} = {hidden};",
        ]
        for x in s["body"]:
            lines.append(_stmt(x, indent + 1, env, ftypes, state, each_vars, in_main))
        lines.append(f"{pad}}}")
        state["loop_depth"] = depth - 1
        return "\n".join(lines)
    if t == "give":
        return f"{pad}return {_expr(s['expr'], env, ftypes, state, in_main)};"
    if t == "stop":
        return f"{pad}return;" if in_main else f"{pad}return 0;"
    if t == "use":
        return f"{pad}/* use {s.get('module')} */"
    if t == "func":
        return f"{pad}/* method {s.get('name')} */"
    raise AtomicError(f"Java backend: unsupported statement type {t}")


def _is_boolean_expr(e) -> bool:
    """True when an expression already yields a Java boolean.

    Comparisons lower to Java comparisons, which ARE boolean; everything else
    (ints, floats, bools-as-long) needs `!= 0` to become a condition.
    """
    return e.get("type") == "binop" and e.get("op") in ("is", "is not", "<", ">", "<=", ">=")


def _decls(env, each_vars, exclude=()):
    """Declare every name at method scope, including loop variables.

    ATOMIC++ names are function-scoped: a loop variable stays readable after
    the loop, so it is declared here and only assigned by the `for`.
    """
    lines = []
    for name in sorted(env):
        if name in exclude:
            continue
        lines.append(f"        {_jtype(env[name])} {_jident(name)} = {_default(env[name])};")
    return lines


def emit_java(ast, class_name="AtomicMain") -> str:
    """Emit a complete, dependency-free Java class."""
    top_env, fn_envs, ftypes, each_vars = _infer(ast)
    state = {"changed": False}
    body = [s for s in ast if s.get("type") not in ("func", "use")]
    funcs = [s for s in ast if s.get("type") == "func"]

    out = [f"public class {class_name} {{", ""]
    for f in funcs:
        info = ftypes[f["name"]]
        ret = _jtype(info["ret"] or INT)
        params = ", ".join(
            f"{_jtype(info['params'][i])} {_jident(p)}" for i, p in enumerate(f["params"])
        )
        out.append(f"    static {ret} {_jident(f['name'])}({params}) {{")
        out += _decls(fn_envs[f["name"]], each_vars, exclude=set(f["params"]))
        body_lines = []
        for x in f.get("body") or []:
            body_lines.append(_stmt(x, 2, fn_envs[f["name"]], ftypes, state, each_vars, False))
        out += body_lines
        if not body_lines or not body_lines[-1].lstrip().startswith("return"):
            out.append(f"        return {_default(info['ret'] or INT)};")
        out.append("    }")
        out.append("")
    out.append("    public static void main(String[] args) {")
    out += _decls(top_env, each_vars)
    for x in body:
        out.append(_stmt(x, 2, top_env, ftypes, state, each_vars, True))
    out.append("    }")
    out.append("}")
    return "\n".join(out)


def compile_java(java_source: str, out_dir: str, class_name: str = "AtomicMain") -> str:
    """Write <class>.java, compile with javac, return the class directory."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, class_name + ".java")
    with open(path, "w", encoding="utf-8") as f:
        f.write(java_source)
    r = subprocess.run(["javac", "-d", out_dir, path], capture_output=True, text=True)
    if r.returncode != 0:
        raise AtomicError(f"Java compilation failed:\n{r.stderr}")
    return out_dir
