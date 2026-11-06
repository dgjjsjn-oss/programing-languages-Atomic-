"""Typed, structured intermediate representation for ATOMIC++.

The parser's dictionaries are source syntax.  This module resolves names,
assigns a type to every expression, and creates a separate IR tree.  The
mapping-like ``get``/index accessors are a short-lived compatibility bridge for
the existing emitters while they are migrated to consume the typed metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional


@dataclass(frozen=True)
class Type:
    name: str
    element: Optional["Type"] = None

    def __str__(self) -> str:
        if self.name == "text":
            return "string"  # Preserve the existing diagnostic vocabulary.
        return f"list[{self.element}]" if self.name == "list" else self.name


INT = Type("int")
FLOAT = Type("float")
BOOL = Type("bool")
TEXT = Type("text")
VOID = Type("void")
UNKNOWN = Type("unknown")


def wrap_i64(value: int) -> int:
    """Apply the language's defined signed 64-bit wrapping to an integer."""
    value &= (1 << 64) - 1
    return value - (1 << 64) if value >= (1 << 63) else value


@dataclass(frozen=True)
class Span:
    line: int = 1
    col: int = 1


class IRNode:
    """Base node with a read-only adapter for legacy backend visitors."""

    legacy_type = ""

    def get(self, key: str, default: Any = None) -> Any:
        if key == "type":
            return self.legacy_type
        if key == "line":
            return self.span.line
        if key == "col":
            return self.span.col
        if key == "inferred_type":
            return getattr(self, "value_type", None)
        if key == "ir_kind":
            return type(self).__name__
        if key == "ret":
            return getattr(self, "return_type", default)
        if hasattr(self, key):
            return getattr(self, key)
        return default

    def __getitem__(self, key: str) -> Any:
        marker = object()
        value = self.get(key, marker)
        if value is marker:
            raise KeyError(key)
        return value


class Expr(IRNode):
    value_type: Type
    span: Span


@dataclass(frozen=True)
class Literal(Expr):
    value: Any
    value_type: Type
    span: Span

    @property
    def legacy_type(self) -> str:  # type: ignore[override]
        return {INT: "int", FLOAT: "float", BOOL: "bool", TEXT: "string"}.get(self.value_type, "literal")


@dataclass(frozen=True)
class Variable(Expr):
    name: str
    value_type: Type
    span: Span
    legacy_type = "var"


@dataclass(frozen=True)
class Unary(Expr):
    op: str
    operand: Expr
    value_type: Type
    span: Span
    legacy_type = "unary"


@dataclass(frozen=True)
class Arithmetic(Expr):
    op: str
    left: Expr
    right: Expr
    value_type: Type
    span: Span
    legacy_type = "binop"


@dataclass(frozen=True)
class Comparison(Expr):
    op: str
    left: Expr
    right: Expr
    value_type: Type
    span: Span
    legacy_type = "binop"


@dataclass(frozen=True)
class StringOperation(Expr):
    op: str
    left: Expr
    right: Expr
    value_type: Type
    span: Span
    legacy_type = "binop"


@dataclass(frozen=True)
class BooleanOperation(Expr):
    op: str
    operands: tuple[Expr, ...]
    value_type: Type
    span: Span
    legacy_type = "binop"


@dataclass(frozen=True)
class Call(Expr):
    name: str
    args: tuple[Expr, ...]
    value_type: Type
    span: Span
    legacy_type = "call"


@dataclass(frozen=True)
class ModuleCall(Expr):
    module: str
    method: str
    args: tuple[Expr, ...]
    value_type: Type
    span: Span
    legacy_type = "method_call"


@dataclass(frozen=True)
class ArrayLiteral(Expr):
    elements: tuple[Expr, ...]
    value_type: Type
    span: Span
    legacy_type = "array"


@dataclass(frozen=True)
class ArrayIndex(Expr):
    var: str
    index: Expr
    value_type: Type
    span: Span
    legacy_type = "array_index"


class Stmt(IRNode):
    span: Span


@dataclass(frozen=True)
class Assignment(Stmt):
    name: str
    expr: Expr
    span: Span
    legacy_type = "var_assign"


@dataclass(frozen=True)
class ArrayAssignment(Stmt):
    name: str
    index: Expr
    expr: Expr
    span: Span
    legacy_type = "array_assign"


@dataclass(frozen=True)
class Say(Stmt):
    expr: Expr
    span: Span
    legacy_type = "say"


@dataclass(frozen=True)
class ExpressionStatement(Stmt):
    expr: Expr
    span: Span
    legacy_type = "expr"


@dataclass(frozen=True)
class Function(Stmt):
    name: str
    params: tuple[str, ...]
    body: tuple[Stmt, ...]
    return_type: Type
    local_types: dict[str, Type]
    span: Span
    legacy_type = "func"


@dataclass(frozen=True)
class Conditional(Stmt):
    cond: Expr
    body: tuple[Stmt, ...]
    span: Span
    legacy_type = "when"


@dataclass(frozen=True)
class Loop(Stmt):
    var: str
    start: Expr
    end: Expr
    body: tuple[Stmt, ...]
    span: Span
    legacy_type = "each"


@dataclass(frozen=True)
class Return(Stmt):
    expr: Expr
    span: Span
    legacy_type = "give"


@dataclass(frozen=True)
class Stop(Stmt):
    span: Span
    legacy_type = "stop"


@dataclass(frozen=True)
class Use(Stmt):
    module: str
    span: Span
    legacy_type = "use"


@dataclass(frozen=True)
class IRProgram(IRNode):
    body: tuple[Stmt, ...]
    global_types: dict[str, Type]
    function_types: dict[str, tuple[tuple[Type, ...], Type]]
    diagnostics: tuple[dict[str, Any], ...]
    span: Span = Span()
    function_locals: dict[str, dict[str, Type]] = field(default_factory=dict)
    legacy_type = "program"

    def __iter__(self):
        # Existing code generators iterate the program's top-level statements.
        return iter(self.body)


def _span(node: Any) -> Span:
    return Span(int(node.get("line") or 1), int(node.get("col") or 1))


def _diagnostic(code: str, message: str, span: Span) -> dict[str, Any]:
    return {"line": span.line, "col": span.col, "code": code, "message": message}


def _join_numeric(left: Type, right: Type) -> Type:
    if left == right and left in (INT, FLOAT):
        return left
    if left in (INT, FLOAT) and right in (INT, FLOAT):
        return FLOAT
    return UNKNOWN


class _Builder:
    def __init__(self, ast: list[dict[str, Any]]):
        self.ast = ast
        self.diags: list[dict[str, Any]] = []
        self.functions: dict[str, tuple[tuple[Type, ...], Type]] = {}
        self.function_nodes: dict[str, dict[str, Any]] = {}
        for stmt in ast:
            if stmt.get("type") == "func":
                name = stmt.get("name")
                params = tuple(INT for _ in stmt.get("params", ()))
                self.functions[name] = (params, INT)
                self.function_nodes[name] = stmt
        self.globals: dict[str, Type] = {}

    def issue(self, code: str, message: str, node: Any) -> None:
        self.diags.append(_diagnostic(code, message, _span(node)))

    def expr(self, node: Optional[dict[str, Any]], env: dict[str, Type]) -> Expr:
        if not isinstance(node, dict):
            self.issue("invalid_ir", "Missing expression", {})
            return Literal(0, INT, Span())

        kind = node.get("type")
        span = _span(node)
        if kind in ("int", "float", "string", "bool"):
            ty = {"int": INT, "float": FLOAT, "string": TEXT, "bool": BOOL}[kind]
            value = wrap_i64(node.get("value")) if ty == INT else node.get("value")
            return Literal(value, ty, span)
        if kind == "var":
            name = node.get("name")
            ty = env.get(name, self.globals.get(name))
            if ty is None:
                self.issue("undefined_variable", f"Undefined variable '{name}'", node)
                ty = UNKNOWN
            return Variable(name, ty, span)
        if kind == "unary":
            operand = self.expr(node.get("operand"), env)
            if operand.value_type not in (INT, FLOAT, UNKNOWN):
                self.issue("invalid_operation", f"Invalid operand for unary '{node.get('op')}': {operand.value_type}", node)
            return Unary(node.get("op"), operand, operand.value_type, span)
        if kind == "binop":
            op = node.get("op")
            left = self.expr(node.get("left"), env)
            right = self.expr(node.get("right"), env)
            lt, rt = left.value_type, right.value_type
            if op in ("is", "is not", "<", ">", "<=", ">="):
                if lt != UNKNOWN and rt != UNKNOWN and not (
                    lt == rt or (lt in (INT, FLOAT) and rt in (INT, FLOAT))
                ):
                    self.issue("invalid_operation", f"Invalid comparison '{op}': {lt} vs {rt}", node)
                return Comparison(op, left, right, BOOL, span)
            if op == "+" and lt == TEXT and rt == TEXT:
                return StringOperation(op, left, right, TEXT, span)
            result = _join_numeric(lt, rt)
            # The v0.5 checker only admitted integer arithmetic. Preserve that
            # public diagnostic behavior for now even though native emitters
            # can already print some floating-point expressions.
            if op in ("+", "-", "*", "/") and (lt != INT or rt != INT):
                if UNKNOWN not in (lt, rt):
                    self.issue("invalid_operation", f"Invalid operands for '{op}': {lt} {op} {rt}", node)
            if result == UNKNOWN and UNKNOWN not in (lt, rt):
                if not any(d["line"] == span.line and d["col"] == span.col for d in self.diags):
                    self.issue("invalid_operation", f"Invalid operands for '{op}': {lt} {op} {rt}", node)
            return Arithmetic(op, left, right, result, span)
        if kind == "call":
            name = node.get("name")
            args = tuple(self.expr(arg, env) for arg in node.get("args") or ())
            if name == "len":
                if len(args) != 1:
                    self.issue("invalid_call", f"Function 'len' expects 1 args, got {len(args)}", node)
                elif args[0].value_type != TEXT and args[0].value_type.name != "list" and args[0].value_type != UNKNOWN:
                    self.issue("invalid_operation", "Function 'len' expects text or a list", node)
                return Call(name, args, INT, span)
            signature = self.functions.get(name)
            if signature is None:
                self.issue("undefined_function", f"Undefined function '{name}'", node)
                return Call(name, args, UNKNOWN, span)
            params, result = signature
            if len(args) != len(params):
                self.issue("invalid_call", f"Function '{name}' expects {len(params)} args, got {len(args)}", node)
            return Call(name, args, result, span)
        if kind == "method_call":
            args = tuple(self.expr(arg, env) for arg in node.get("args") or ())
            module, method = node.get("module"), node.get("method")
            if module != "math" or method not in ("add", "sub", "mul"):
                self.issue("unsupported_module", f"Unsupported module operation '{module}.{method}'", node)
                result = UNKNOWN
            elif len(args) != 2:
                self.issue("invalid_call", f"Function '{module}.{method}' expects 2 args, got {len(args)}", node)
                result = UNKNOWN
            else:
                result = _join_numeric(args[0].value_type, args[1].value_type)
                if result == UNKNOWN and UNKNOWN not in (args[0].value_type, args[1].value_type):
                    self.issue("invalid_operation", f"Function '{module}.{method}' expects numeric args", node)
            return ModuleCall(module, method, args, result, span)
        if kind == "array":
            elements = tuple(self.expr(item, env) for item in node.get("elements") or ())
            elem_type = elements[0].value_type if elements else UNKNOWN
            for item in elements[1:]:
                if item.value_type != elem_type and UNKNOWN not in (item.value_type, elem_type):
                    self.issue("invalid_operation", "Array elements must have one type", node)
                    elem_type = UNKNOWN
            return ArrayLiteral(elements, Type("list", elem_type), span)
        if kind == "array_index":
            name = node.get("var")
            target = env.get(name, self.globals.get(name))
            index = self.expr(node.get("index"), env)
            if index.value_type not in (INT, UNKNOWN):
                self.issue("invalid_operation", "Array index must be an int", node)
            if target is None:
                self.issue("undefined_variable", f"Undefined variable '{name}'", node)
                target = UNKNOWN
            if target.name != "list" and target != UNKNOWN:
                self.issue("invalid_operation", f"Cannot index value of type {target}", node)
            return ArrayIndex(name, index, target.element if target.name == "list" else UNKNOWN, span)

        self.issue("invalid_ir", f"Unsupported expression '{kind}'", node)
        return Literal(0, UNKNOWN, span)

    def block(self, nodes: Iterable[dict[str, Any]], env: dict[str, Type], in_function: bool) -> tuple[Stmt, ...]:
        result: list[Stmt] = []
        for node in nodes:
            kind = node.get("type")
            span = _span(node)
            if kind in ("assign", "var_assign"):
                expr = self.expr(node.get("expr"), env)
                name = node.get("name")
                previous = env.get(name)
                if previous is not None and previous != expr.value_type and UNKNOWN not in (previous, expr.value_type):
                    self.issue("invalid_assignment", f"Cannot assign {expr.value_type} to '{name}' of type {previous}", node)
                if previous is None or previous == UNKNOWN:
                    env[name] = expr.value_type
                result.append(Assignment(name, expr, span))
            elif kind == "array_assign":
                index = self.expr(node.get("index"), env)
                expr = self.expr(node.get("expr"), env)
                name = node.get("name")
                arr_type = env.get(name, UNKNOWN)
                if arr_type.name != "list" and arr_type != UNKNOWN:
                    self.issue("invalid_operation", f"Cannot assign an element of type {arr_type}", node)
                elif arr_type.name == "list" and arr_type.element not in (expr.value_type, UNKNOWN):
                    self.issue("invalid_assignment", f"Cannot assign {expr.value_type} to list of {arr_type.element}", node)
                if index.value_type not in (INT, UNKNOWN):
                    self.issue("invalid_operation", "Array index must be an int", node)
                result.append(ArrayAssignment(name, index, expr, span))
            elif kind == "say":
                result.append(Say(self.expr(node.get("expr"), env), span))
            elif kind == "expr":
                result.append(ExpressionStatement(self.expr(node.get("expr"), env), span))
            elif kind == "when":
                cond = self.expr(node.get("cond"), env)
                if cond.value_type not in (BOOL, INT, FLOAT, UNKNOWN):
                    self.issue("invalid_operation", f"Condition must be bool, got {cond.value_type}", node)
                result.append(Conditional(cond, self.block(node.get("body") or (), env, in_function), span))
            elif kind == "each":
                start, end = self.expr(node.get("start"), env), self.expr(node.get("end"), env)
                for bound in (start, end):
                    if bound.value_type not in (INT, UNKNOWN):
                        self.issue("invalid_operation", "Loop bounds must be integers", node)
                var = node.get("var")
                env[var] = INT
                result.append(Loop(var, start, end, self.block(node.get("body") or (), env, in_function), span))
            elif kind == "give":
                value = self.expr(node.get("expr"), env)
                if not in_function:
                    self.issue("invalid_return", "'give' outside a function", node)
                result.append(Return(value, span))
            elif kind == "stop":
                result.append(Stop(span))
            elif kind == "use":
                result.append(Use(node.get("module"), span))
            elif kind == "func":
                # Top-level function nodes are inserted in a separate pass.
                continue
            else:
                self.issue("invalid_ir", f"Unsupported statement '{kind}'", node)
        return tuple(result)

    def build(self) -> IRProgram:
        top_body: list[dict[str, Any]] = []
        for stmt in self.ast:
            if stmt.get("type") != "func":
                top_body.append(stmt)

        # Function results can flow through calls. Re-lower a small bounded
        # number of times (at most one pass per function plus one) until the
        # signatures settle, then retain diagnostics from the final pass only.
        typed_top: tuple[Stmt, ...] = ()
        functions: list[Function] = []
        function_locals: dict[str, dict[str, Type]] = {}
        for _ in range(max(1, len(self.function_nodes) + 1)):
            self.diags = []
            self.globals = {}
            typed_top = self.block(top_body, self.globals, False)
            functions = []
            function_locals = {}
            changed = False
            for name, stmt in self.function_nodes.items():
                params, prior_return = self.functions[name]
                env = dict(zip(stmt.get("params") or (), params))
                body = self.block(stmt.get("body") or (), env, True)
                returns = [s.expr.value_type for s in _walk_statements(body) if isinstance(s, Return)]
                return_type = prior_return
                if returns:
                    return_type = returns[0]
                    for found in returns[1:]:
                        if found != return_type:
                            joined = _join_numeric(return_type, found)
                            if joined == UNKNOWN:
                                self.issue("invalid_return", f"Function '{name}' returns incompatible types", stmt)
                            return_type = joined
                if return_type != prior_return:
                    self.functions[name] = (params, return_type)
                    changed = True
                function_locals[name] = dict(env)
                functions.append(Function(name, tuple(stmt.get("params") or ()), body,
                                          return_type, dict(env), _span(stmt)))
            if not changed:
                break

        # Keep functions first, as every existing backend expects.
        body = tuple(functions) + typed_top
        program = IRProgram(body, dict(self.globals), dict(self.functions), tuple(self.diags), function_locals=function_locals)
        verifier_diags = verify_ir(program)
        if verifier_diags:
            existing_spans = {(d["line"], d["col"]) for d in self.diags}
            verifier_diags = [d for d in verifier_diags if (d["line"], d["col"]) not in existing_spans]
            program = IRProgram(body, dict(self.globals), dict(self.functions), tuple(self.diags + verifier_diags), function_locals=function_locals)
        return program


def _walk_statements(stmts: Iterable[Stmt]):
    for stmt in stmts:
        yield stmt
        if isinstance(stmt, (Conditional, Loop, Function)):
            yield from _walk_statements(stmt.body)


def loop_variables(stmts: Iterable[Stmt]) -> set[str]:
    """Return loop names for backend declaration placement."""
    names: set[str] = set()
    for stmt in stmts:
        if isinstance(stmt, Loop):
            names.add(stmt.var)
            names.update(loop_variables(stmt.body))
        elif isinstance(stmt, (Conditional, Function)):
            names.update(loop_variables(stmt.body))
    return names


def build_ir(statements: list[dict[str, Any]]) -> IRProgram:
    """Resolve names, infer types, lower parsed syntax, and verify the result."""
    return _Builder(statements).build()


def verify_ir(program: Any) -> list[dict[str, Any]]:
    """Validate a structured IR tree without executing or compiling it."""
    diags: list[dict[str, Any]] = []

    def error(message: str, node: Any = None) -> None:
        span = getattr(node, "span", Span())
        if not isinstance(span, Span):
            span = Span()
        diags.append(_diagnostic("invalid_ir", message, span))

    if not isinstance(program, IRProgram):
        return [_diagnostic("invalid_ir", "IR root must be an IRProgram", Span())]
    if not isinstance(program.body, tuple):
        error("Program body must be a sequence", program)
        return diags
    if not isinstance(program.global_types, dict):
        error("Program global type table must be a mapping", program)
        return diags
    if not isinstance(program.function_types, dict):
        error("Program function type table must be a mapping", program)
        return diags
    valid_types = {INT, FLOAT, BOOL, TEXT, VOID, UNKNOWN}

    def valid_type(value: Any) -> bool:
        if not isinstance(value, Type):
            return False
        if value in valid_types:
            return True
        return value.name == "list" and value.element != VOID and valid_type(value.element)

    for name, ty in program.global_types.items():
        if not isinstance(name, str) or not valid_type(ty):
            error("Program contains an invalid global binding", program)
    for name, signature in program.function_types.items():
        if not isinstance(name, str) or not isinstance(signature, tuple) or len(signature) != 2:
            error("Program contains an invalid function signature", program)
        elif not isinstance(signature[0], tuple) or not all(valid_type(arg) for arg in signature[0]) or not valid_type(signature[1]):
            error("Program contains an invalid function type", program)

    known_exprs = (Literal, Variable, Unary, Arithmetic, Comparison, StringOperation,
                   BooleanOperation, Call, ModuleCall, ArrayLiteral, ArrayIndex)
    known_stmts = (Assignment, ArrayAssignment, Say, ExpressionStatement, Function,
                   Conditional, Loop, Return, Stop, Use)

    def check_expr(expr: Any, env: dict[str, Type]) -> None:
        if not isinstance(expr, known_exprs):
            error("Expected an expression node", expr)
            return
        if not valid_type(getattr(expr, "value_type", None)):
            error("Expression has an invalid type", expr)
        if isinstance(expr, Literal):
            value_matches = (
                (expr.value_type == INT and isinstance(expr.value, int) and not isinstance(expr.value, bool)
                 and -(1 << 63) <= expr.value <= (1 << 63) - 1)
                or (expr.value_type == FLOAT and isinstance(expr.value, float))
                or (expr.value_type == BOOL and isinstance(expr.value, bool))
                or (expr.value_type == TEXT and isinstance(expr.value, str))
                or (expr.value_type == UNKNOWN)
            )
            if not value_matches:
                error("Literal value does not match its type", expr)
        if isinstance(expr, (Arithmetic, StringOperation, Comparison)):
            check_expr(expr.left, env)
            check_expr(expr.right, env)
            if not isinstance(expr.left, Expr) or not isinstance(expr.right, Expr):
                return
            lt, rt = expr.left.value_type, expr.right.value_type
            if isinstance(expr, Arithmetic):
                if expr.op not in ("+", "-", "*", "/") or lt not in (INT, FLOAT, UNKNOWN) or rt not in (INT, FLOAT, UNKNOWN):
                    error("Invalid arithmetic operation or operand type", expr)
                expected = _join_numeric(lt, rt)
                if expected != UNKNOWN and expr.value_type != expected:
                    error("Arithmetic result type does not match its operands", expr)
            elif isinstance(expr, StringOperation):
                if expr.op != "+" or lt != TEXT or rt != TEXT or expr.value_type != TEXT:
                    error("Invalid string operation or result type", expr)
            else:
                compatible = lt == rt or (lt in (INT, FLOAT) and rt in (INT, FLOAT))
                valid_operator = expr.op in ("is", "is not", "<", ">", "<=", ">=")
                valid_operands = compatible and (
                    expr.op in ("is", "is not") or lt in (INT, FLOAT, UNKNOWN)
                )
                if not valid_operator or not valid_operands or expr.value_type != BOOL:
                    error("Invalid comparison operation or result type", expr)
        elif isinstance(expr, Unary):
            check_expr(expr.operand, env)
            if not isinstance(expr.operand, Expr):
                return
            if expr.op not in ("-", "+") or expr.operand.value_type not in (INT, FLOAT, UNKNOWN):
                error("Invalid unary operation or operand type", expr)
        elif isinstance(expr, Variable):
            if expr.name not in env:
                error(f"Undefined variable '{expr.name}'", expr)
            elif env[expr.name] not in (expr.value_type, UNKNOWN) and expr.value_type != UNKNOWN:
                error(f"Variable '{expr.name}' has inconsistent types", expr)
        elif isinstance(expr, BooleanOperation):
            if not isinstance(expr.operands, tuple):
                error("Boolean operands must be a sequence", expr)
                return
            if expr.op not in ("and", "or", "not") or expr.value_type != BOOL:
                error(f"Unknown boolean operation '{expr.op}'", expr)
            if (expr.op == "not" and len(expr.operands) != 1) or (expr.op in ("and", "or") and len(expr.operands) < 2):
                error("Boolean operation has the wrong number of operands", expr)
            for item in expr.operands:
                check_expr(item, env)
                if isinstance(item, Expr) and item.value_type not in (BOOL, UNKNOWN):
                    error("Boolean operands must have type bool", item)
        elif isinstance(expr, Call):
            if not isinstance(expr.args, tuple):
                error("Call arguments must be a sequence", expr)
                return
            for item in expr.args:
                check_expr(item, env)
            if any(not isinstance(item, Expr) for item in expr.args):
                return
            signature = program.function_types.get(expr.name)
            if expr.name == "len":
                if len(expr.args) != 1:
                    error("len expects one argument", expr)
                elif expr.args[0].value_type != TEXT and (not isinstance(expr.args[0].value_type, Type) or expr.args[0].value_type.name != "list"):
                    error("len expects text or a list", expr)
            elif signature is None:
                error(f"Call to undefined function '{expr.name}'", expr)
            elif not isinstance(signature, tuple) or len(signature) != 2 or not isinstance(signature[0], tuple):
                error(f"Function '{expr.name}' has an invalid signature", expr)
            else:
                params, result_type = signature
                if len(expr.args) != len(params):
                    error(f"Function '{expr.name}' has the wrong argument count", expr)
                for arg, param_type in zip(expr.args, params):
                    if arg.value_type not in (param_type, UNKNOWN):
                        error(f"Function '{expr.name}' argument has the wrong type", arg)
                if expr.value_type != result_type and UNKNOWN not in (expr.value_type, result_type):
                    error(f"Call '{expr.name}' has an incorrect result type", expr)
        elif isinstance(expr, ModuleCall):
            if not isinstance(expr.args, tuple):
                error("Module call arguments must be a sequence", expr)
                return
            for item in expr.args:
                check_expr(item, env)
            if any(not isinstance(item, Expr) for item in expr.args):
                return
            if expr.module != "math" or expr.method not in ("add", "sub", "mul"):
                error("Unsupported module operation", expr)
            elif len(expr.args) != 2 or any(a.value_type not in (INT, FLOAT, UNKNOWN) for a in expr.args):
                error("Invalid math module arguments", expr)
        elif isinstance(expr, ArrayLiteral):
            if not isinstance(expr.elements, tuple):
                error("Array elements must be a sequence", expr)
                return
            for item in expr.elements:
                check_expr(item, env)
            if any(not isinstance(item, Expr) for item in expr.elements):
                return
            if not isinstance(expr.value_type, Type) or expr.value_type.name != "list":
                error("Array literal must have a list type", expr)
            elif any(item.value_type not in (expr.value_type.element, UNKNOWN) for item in expr.elements):
                error("Array element type does not match its list type", expr)
        elif isinstance(expr, ArrayIndex):
            check_expr(expr.index, env)
            if not isinstance(expr.index, Expr):
                return
            if expr.index.value_type not in (INT, UNKNOWN):
                error("Array index must have type int", expr)
            target = env.get(expr.var)
            if target is None:
                error(f"Undefined variable '{expr.var}'", expr)
            elif not isinstance(target, Type):
                error("Indexed variable has an invalid type", expr)
            elif target.name != "list" and target != UNKNOWN:
                error("Indexed variable must have a list type", expr)
            elif target.name == "list" and expr.value_type not in (target.element, UNKNOWN):
                error("Index result type does not match list element type", expr)

    def check_block(block: Any, env: dict[str, Type], in_function: bool = False,
                    return_type: Type = VOID) -> None:
        if not isinstance(block, tuple):
            error("Block body must be a sequence")
            return
        for stmt in block:
            if not isinstance(stmt, known_stmts):
                error("Unknown statement node", stmt)
                continue
            if isinstance(stmt, Assignment):
                if stmt.expr is None:
                    error("Statement is missing its expression", stmt)
                elif not isinstance(stmt.expr, Expr):
                    check_expr(stmt.expr, env)
                else:
                    check_expr(stmt.expr, env)
                    prior = env.get(stmt.name)
                    if prior is not None and prior not in (stmt.expr.value_type, UNKNOWN) and stmt.expr.value_type != UNKNOWN:
                        error(f"Assignment changes type of '{stmt.name}'", stmt)
                    env[stmt.name] = stmt.expr.value_type
            elif isinstance(stmt, (Say, ExpressionStatement)):
                if stmt.expr is None:
                    error("Statement is missing its expression", stmt)
                else:
                    check_expr(stmt.expr, env)
            elif isinstance(stmt, Return):
                if stmt.expr is None:
                    error("Return is missing its expression", stmt)
                else:
                    check_expr(stmt.expr, env)
                    if isinstance(stmt.expr, Expr):
                        compatible = stmt.expr.value_type == return_type or _join_numeric(stmt.expr.value_type, return_type) == FLOAT
                        if in_function and not compatible and UNKNOWN not in (stmt.expr.value_type, return_type):
                            error("Return value type does not match function return type", stmt)
                if not in_function:
                    error("Return appears outside a function", stmt)
            elif isinstance(stmt, ArrayAssignment):
                check_expr(stmt.index, env)
                check_expr(stmt.expr, env)
                if isinstance(stmt.index, Expr) and stmt.index.value_type not in (INT, UNKNOWN):
                    error("Array index must have type int", stmt)
                target = env.get(stmt.name)
                if target is None:
                    error(f"Undefined variable '{stmt.name}'", stmt)
                elif not isinstance(target, Type):
                    error("Array target has an invalid type", stmt)
                elif isinstance(stmt.expr, Expr) and target.name == "list" and stmt.expr.value_type not in (target.element, UNKNOWN):
                    error("Array assignment has the wrong element type", stmt)
            elif isinstance(stmt, Conditional):
                check_expr(stmt.cond, env)
                check_block(stmt.body, env, in_function, return_type)
            elif isinstance(stmt, Loop):
                check_expr(stmt.start, env)
                check_expr(stmt.end, env)
                env[stmt.var] = INT
                check_block(stmt.body, env, in_function, return_type)
            elif isinstance(stmt, Function):
                if not valid_type(stmt.return_type):
                    error("Function has an invalid return type", stmt)
                if not isinstance(stmt.params, tuple):
                    error("Function parameters must be a sequence", stmt)
                    continue
                fn_env = dict(program.global_types)
                signature = program.function_types.get(stmt.name)
                if not isinstance(signature, tuple) or len(signature) != 2 or not isinstance(signature[0], tuple) or len(signature[0]) != len(stmt.params):
                    error("Function signature is missing or inconsistent", stmt)
                else:
                    fn_env.update(zip(stmt.params, signature[0]))
                check_block(stmt.body, fn_env, True, stmt.return_type)

    check_block(program.body, {})
    return diags
