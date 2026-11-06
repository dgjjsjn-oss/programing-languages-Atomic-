#!/usr/bin/env python3
"""ATOMIC++ vertical slice test suite.

Tests the Phase 1 interpreter against example .atpp files and error cases.
Run with: python -m pytest tests/  or  python tests/test_interpreter.py
"""

import os
import sys
import unittest

# Add vertical_slice to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vertical_slice"))

from interpreter import run_source, run_file, Interpreter, AtomicError, tokenize, parse

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "vertical_slice", "examples")


class TestExamples(unittest.TestCase):
    """Each example .atpp file must run without error and produce expected output."""

    def test_hello(self):
        out = run_file(os.path.join(EXAMPLES_DIR, "hello.atpp"))
        self.assertEqual(out, ["Hello, ATOMIC++"])

    def test_variables(self):
        out = run_file(os.path.join(EXAMPLES_DIR, "variables.atpp"))
        self.assertEqual(out, ["100", "0", "Player", "3.14", "True"])

    def test_conditions(self):
        out = run_file(os.path.join(EXAMPLES_DIR, "conditions.atpp"))
        self.assertEqual(out, ["Healthy"])

    def test_loops(self):
        out = run_file(os.path.join(EXAMPLES_DIR, "loops.atpp"))
        self.assertEqual(out, ["0", "1", "2", "3", "4", "5"])

    def test_functions(self):
        out = run_file(os.path.join(EXAMPLES_DIR, "functions.atpp"))
        self.assertEqual(out, ["7", "21"])

    def test_fib(self):
        out = run_file(os.path.join(EXAMPLES_DIR, "fib.atpp"))
        self.assertEqual(out, ["55"])

    def test_arrays(self):
        out = run_file(os.path.join(EXAMPLES_DIR, "arrays.atpp"))
        self.assertEqual(out, ["10", "20", "30"])

    def test_math_module(self):
        out = run_file(os.path.join(EXAMPLES_DIR, "math_module.atpp"))
        self.assertEqual(out, ["5", "20"])


class TestErrors(unittest.TestCase):
    """Error cases must produce clear messages, not crashes."""

    def test_undefined_variable(self):
        src = "start:\n    say x\n    stop\n"
        with self.assertRaises(AtomicError) as ctx:
            run_source(src)
        self.assertIn("Undefined variable", str(ctx.exception))

    def test_division_by_zero(self):
        src = "start:\n    x = 1 / 0\n    stop\n"
        with self.assertRaises(AtomicError) as ctx:
            run_source(src)
        self.assertIn("Division by zero", str(ctx.exception))

    def test_syntax_error(self):
        src = "start:\n    say \n    stop\n"
        with self.assertRaises(SyntaxError):
            run_source(src)


class TestLanguageFeatures(unittest.TestCase):
    """Small focused tests for individual features."""

    def test_integer_arithmetic(self):
        src = "start:\n    x = 10 + 20 * 2\n    say x\n    stop\n"
        out = run_source(src)
        self.assertEqual(out, ["50"])

    def test_string_concatenation(self):
        src = 'start:\n    x = "Hi " + "there"\n    say x\n    stop\n'
        out = run_source(src)
        self.assertEqual(out, ["Hi there"])

    def test_comparison(self):
        src = "start:\n    when 5 is 5:\n        say \"equal\"\n    stop\n"
        out = run_source(src)
        self.assertEqual(out, ["equal"])

    def test_boolean(self):
        src = "start:\n    x = true\n    when x is true:\n        say \"yes\"\n    stop\n"
        out = run_source(src)
        self.assertEqual(out, ["yes"])

    def test_function_with_no_return(self):
        src = "start:\n    say \"done\"\n    stop\n"
        out = run_source(src)
        self.assertEqual(out, ["done"])


class TestNestedBlocks(unittest.TestCase):
    def test_nested_when(self):
        src = 'start:\n    when 1 is 1:\n        when 2 is 2:\n            say "deep"\n    stop\n'
        self.assertEqual(run_source(src), ["deep"])

    def test_nested_each(self):
        src = "start:\n    each i from 0 to 1:\n        each j from 0 to 1:\n            say i * 10 + j\n    stop\n"
        self.assertEqual(run_source(src), ["0", "1", "10", "11"])

    def test_when_in_function_with_give(self):
        src = (
            "make f(n):\n"
            "    when n > 5:\n"
            "        when n > 0:\n"
            "            give 100\n"
            "    give 300\n"
            "start:\n"
            "    say f(10)\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), ["100"])


class TestFunctionReturns(unittest.TestCase):
    def test_function_return_value(self):
        src = "make double(x):\n    give x * 2\nstart:\n    say double(21)\n    stop\n"
        self.assertEqual(run_source(src), ["42"])

    def test_function_recursion_factorial(self):
        src = (
            "make fact(n):\n"
            "    when n is 0:\n"
            "        give 1\n"
            "    give n * fact(n - 1)\n"
            "start:\n"
            "    say fact(5)\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), ["120"])

    def test_function_arg_count_mismatch(self):
        src = "make add(a, b):\n    give a + b\nstart:\n    say add(1)\n    stop\n"
        with self.assertRaises(AtomicError) as ctx:
            run_source(src)
        self.assertIn("args", str(ctx.exception))


class TestScopes(unittest.TestCase):
    def test_function_undefined_variable(self):
        src = "make f(x):\n    say y\n    give x\nstart:\n    say f(1)\n    stop\n"
        with self.assertRaises(AtomicError) as ctx:
            run_source(src)
        self.assertIn("Undefined variable", str(ctx.exception))

    def test_function_local_scope(self):
        src = (
            "make f(x):\n"
            "    y = x + 1\n"
            "    give y\n"
            "start:\n"
            "    z = 5\n"
            "    say f(2)\n"
            "    say z\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), ["3", "5"])


class TestArrays(unittest.TestCase):
    def test_empty_array(self):
        src = "start:\n    x = []\n    say \"empty\"\n    stop\n"
        self.assertEqual(run_source(src), ["empty"])

    def test_array_read(self):
        src = "start:\n    x = [1, 2, 3]\n    say x[1]\n    stop\n"
        self.assertEqual(run_source(src), ["2"])

    def test_array_write_and_read(self):
        src = "start:\n    x = [1, 2, 3]\n    x[0] = 99\n    say x[0]\n    stop\n"
        self.assertEqual(run_source(src), ["99"])

    def test_invalid_array_index(self):
        src = "start:\n    x = [1, 2]\n    say x[5]\n    stop\n"
        with self.assertRaises(AtomicError) as ctx:
            run_source(src)
        self.assertIn("bounds", str(ctx.exception).lower())


class TestErrorsAndParsing(unittest.TestCase):
    def test_incorrect_function_arg_count(self):
        src = "make add(a, b):\n    give a + b\nstart:\n    say add(1)\n    stop\n"
        with self.assertRaises(AtomicError):
            run_source(src)

    def test_invalid_syntax(self):
        src = "start:\n    say \n    stop\n"
        with self.assertRaises(SyntaxError):
            run_source(src)

    def test_indentation_error(self):
        src = "start:\n    say \"x\"\n  say \"y\"\n"
        with self.assertRaises(SyntaxError):
            run_source(src)

    def test_comments_blank_lines_eof(self):
        src = "// comment\n\nstart:\n    // another\n    say \"hi\"\n"
        self.assertEqual(run_source(src), ["hi"])


class TestDecimals(unittest.TestCase):
    def test_float_arithmetic(self):
        src = "start:\n    x = 3.5 + 0.5\n    say x\n    stop\n"
        self.assertEqual(run_source(src), ["4.0"])

    def test_integer_arithmetic(self):
        src = "start:\n    x = 2 + 3 * 4\n    say x\n    stop\n"
        self.assertEqual(run_source(src), ["14"])


class TestUnary(unittest.TestCase):
    def test_negative_literal(self):
        src = "start:\n    a = -7\n    say a\n    stop\n"
        self.assertEqual(run_source(src), ["-7"])

    def test_unary_on_variable(self):
        src = "start:\n    a = 7\n    b = -a\n    say b\n    stop\n"
        self.assertEqual(run_source(src), ["-7"])

    def test_unary_binds_tighter_than_multiply(self):
        src = "start:\n    a = 3\n    b = -a * 2\n    say b\n    stop\n"
        self.assertEqual(run_source(src), ["-6"])

    def test_double_negative(self):
        src = "start:\n    a = 5\n    b = --a\n    say b\n    stop\n"
        self.assertEqual(run_source(src), ["5"])

    def test_negative_division_truncates_toward_zero(self):
        src = "start:\n    a = 7\n    b = -a / 2\n    say b\n    stop\n"
        self.assertEqual(run_source(src), ["-3"])

    def test_unary_plus_is_identity(self):
        src = "start:\n    a = +5\n    say a\n    stop\n"
        self.assertEqual(run_source(src), ["5"])

    def test_grouping_changes_precedence(self):
        src = "start:\n    a = (2 + 3) * 4\n    say a\n    stop\n"
        self.assertEqual(run_source(src), ["20"])

    def test_nested_grouping(self):
        src = "start:\n    a = ((1 + 2) * (3 + 4))\n    say a\n    stop\n"
        self.assertEqual(run_source(src), ["21"])


class TestPrecedence(unittest.TestCase):
    """Comparison binds loosest; arithmetic binds tighter (LANGUAGE_SPEC.md 2.5).

    Regression: comparisons used to parse below multiplication, so
    `2 * 3 is 6` evaluated to 0 and `1 + 2 > 3` to 1.
    """

    def test_comparison_is_looser_than_addition(self):
        src = "start:\n    say 1 + 2 > 3\n    stop\n"
        self.assertEqual(run_source(src), ["False"])

    def test_comparison_is_looser_than_multiplication(self):
        src = "start:\n    say 2 * 3 is 6\n    stop\n"
        self.assertEqual(run_source(src), ["True"])

    def test_arithmetic_still_binds_tighter(self):
        src = "start:\n    say 1 + 2 * 3\n    stop\n"
        self.assertEqual(run_source(src), ["7"])

    def test_comparison_right_operand_may_be_an_expression(self):
        src = "start:\n    x = 3\n    say x is 1 + 2\n    stop\n"
        self.assertEqual(run_source(src), ["True"])


if __name__ == "__main__":
    unittest.main()
