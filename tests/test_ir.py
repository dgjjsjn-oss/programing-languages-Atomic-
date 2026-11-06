"""Tests for the typed IR schema, type assignment, and verifier."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vertical_slice"))

from interpreter import parse, tokenize
from interpreter import Interpreter, AtomicError
from c_backend import emit_c
from java_backend import emit_java
from ir import (
    INT, FLOAT, BOOL, TEXT, Arithmetic, ArrayLiteral, Assignment, BooleanOperation, Call,
    Comparison, Conditional, Function, IRProgram, Literal, Return, Say, Span, Type,
    Variable, build_ir, verify_ir,
)


class TestTypedIRBuilder(unittest.TestCase):
    def test_builds_explicit_typed_nodes(self):
        source = (
            'make twice(n):\n'
            '    give n * 2\n'
            'start:\n'
            '    x = 1 + 2\n'
            '    flt = 2.0\n'
            '    ok = x > 2\n'
            '    words = ["a", "b"]\n'
            '    say twice(2)\n'
        )
        program = build_ir(parse(tokenize(source)))
        self.assertEqual(program.diagnostics, ())
        self.assertIsInstance(program.body[0], Function)
        self.assertIsInstance(program.body[1], Assignment)
        self.assertIsInstance(program.body[1].expr, Arithmetic)
        self.assertEqual(program.body[1].expr.value_type, INT)
        self.assertEqual(program.body[2].expr.value_type, FLOAT)
        self.assertIsInstance(program.body[3].expr, Comparison)
        self.assertEqual(program.body[3].expr.value_type, BOOL)
        self.assertIsInstance(program.body[4].expr, ArrayLiteral)
        self.assertEqual(program.body[4].expr.value_type, Type("list", TEXT))
        self.assertIsInstance(program.body[5], Say)
        self.assertIsInstance(program.body[5].expr, Call)

    def test_name_and_type_errors_are_reported_during_lowering(self):
        source = 'start:\n    bad = missing + 1\n    x = 1\n    x = "text"\n'
        diagnostics = build_ir(parse(tokenize(source))).diagnostics
        self.assertIn("undefined_variable", [d["code"] for d in diagnostics])
        self.assertIn("invalid_assignment", [d["code"] for d in diagnostics])
        # A bad name is the root cause; do not add a second arithmetic error.
        self.assertEqual(sum(d["code"] == "undefined_variable" for d in diagnostics), 1)


class TestIRVerifier(unittest.TestCase):
    def test_rejects_non_ir_root_and_missing_expression(self):
        self.assertEqual(verify_ir([])[0]["code"], "invalid_ir")
        program = IRProgram((Say(None, Span(2, 3)),), {}, {}, ())
        self.assertIn("missing its expression", verify_ir(program)[0]["message"])

    def test_rejects_invalid_expression_type_and_undefined_variable(self):
        bad_type = Literal(1, Type("made_up"), Span(1, 1))
        program = IRProgram((Say(bad_type, Span()), Say(Variable("lost", INT, Span(3, 4)), Span())), {}, {}, ())
        messages = [d["message"] for d in verify_ir(program)]
        self.assertTrue(any("invalid type" in message.lower() for message in messages))
        self.assertTrue(any("Undefined variable 'lost'" in message for message in messages))

    def test_rejects_malformed_arithmetic(self):
        expr = Arithmetic("*", Literal(1, INT, Span()), Literal("s", TEXT, Span()), INT, Span(4, 2))
        diagnostics = verify_ir(IRProgram((Say(expr, Span()),), {}, {}, ()))
        self.assertTrue(any("arithmetic" in d["message"].lower() for d in diagnostics))

    def test_malformed_ir_never_raises_python_exceptions(self):
        missing_child = Arithmetic("+", None, Literal(1, INT, Span()), INT, Span())
        child_program = IRProgram((Say(missing_child, Span()),), {}, {}, ())
        self.assertTrue(verify_ir(child_program))
        bad_tables = IRProgram((), None, {}, ())
        self.assertTrue(verify_ir(bad_tables))

    def test_rejects_bad_call_arity_and_return_type(self):
        fn = Function("f", ("n",), (Return(Literal("bad", TEXT, Span()), Span()),), INT, {"n": INT}, Span())
        call = Call("f", (), INT, Span(7, 5))
        program = IRProgram(
            (fn, Say(call, Span())), {}, {"f": ((INT,), INT)}, ()
        )
        messages = [d["message"] for d in verify_ir(program)]
        self.assertTrue(any("argument count" in message for message in messages))
        self.assertTrue(any("Return value type" in message for message in messages))

    def test_rejects_invalid_structured_control_block(self):
        condition = Comparison("is", Literal(1, INT, Span()), Literal(1, INT, Span()), BOOL, Span())
        malformed = IRProgram((Conditional(condition, [], Span()),), {}, {}, ())
        self.assertTrue(any("Block body" in d["message"] for d in verify_ir(malformed)))

    def test_boolean_operation_short_circuits_in_interpreter_and_is_explicitly_unavailable_in_backends(self):
        false_value = Literal(False, BOOL, Span())
        true_value = Literal(True, BOOL, Span())
        expression = BooleanOperation("and", (false_value, true_value), BOOL, Span())
        program = IRProgram((Say(expression, Span()),), {}, {}, ())
        self.assertEqual(verify_ir(program), [])
        output = Interpreter().run(program.body)
        self.assertIn("False", output)
        with self.assertRaisesRegex(AtomicError, "boolean operations are not supported"):
            emit_c(program)
        with self.assertRaisesRegex(AtomicError, "boolean operations are not supported"):
            emit_java(program)


if __name__ == "__main__":
    unittest.main()
