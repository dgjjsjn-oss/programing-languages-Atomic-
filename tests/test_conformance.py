#!/usr/bin/env python3
"""ATOMIC++ Phase 2/5 -- interpreter vs C compiler conformance tests.

For programs in the supported subset, run in the interpreter and via the
native C backend (gcc), then compare outputs.

Run with: python tests/test_conformance.py
"""

import os
import subprocess
import tempfile
import unittest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vertical_slice"))

from interpreter import AtomicError, parse, tokenize, run_source
from c_backend import emit_c, compile_c


def _run_c(src: str):
    ast = parse(tokenize(src))
    c = emit_c(ast)
    exe = os.path.join(tempfile.gettempdir(), "atomicpp_conformance.exe")
    compile_c(c, exe, portable=True, march_native=False)
    r = subprocess.run([exe], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"C backend failed: {r.stderr}")
    return [ln for ln in r.stdout.split("\n") if ln != ""]


class TestConformance(unittest.TestCase):
    def test_boolean_operators_short_circuit_across_backends(self):
        src = (
            "make noisy():\n"
            "    say 999\n"
            "    give true\n"
            "start:\n"
            "    say false and noisy()\n"
            "    say true or noisy()\n"
            "    say not (false or false)\n"
            "    say (2 + 3 is 5) and true\n"
            "    say not 1 is 2\n"
            "    say true or false and false\n"
        )
        expected = ["False", "True", "True", "True", "True", "True"]
        self.assertEqual(run_source(src), expected)
        self.assertEqual(_run_c(src), expected)

    def test_conformance_arithmetic_when_each(self):
        src = (
            "start:\n"
            "    x = 2 + 3 * 4\n"
            "    say x\n"
            "    each i from 0 to 2:\n"
            "        when i is 1:\n"
            "            say i\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_c(src))

    def test_conformance_recursion(self):
        src = (
            "make fact(n):\n"
            "    when n is 0:\n"
            "        give 1\n"
            "    give n * fact(n - 1)\n"
            "start:\n"
            "    say fact(5)\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_c(src))

    def test_conformance_bool_compare(self):
        src = (
            "start:\n"
            "    when 3 > 2:\n"
            "        when 2 is not 2:\n"
            "            say \"no\"\n"
            "        say \"yes\"\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_c(src))


    def test_conformance_int_division_and_overflow(self):
        src = (
            "start:\n"
            "    x = 10 / 3\n"
            "    say x\n"
            "    y = 7 / 2\n"
            "    say y\n"
            "    big = 9223372036854775807 + 1\n"
            "    say big\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_c(src))

    def test_conformance_i64_wrap_and_maximum_loop(self):
        src = (
            "start:\n"
            "    maximum = 9223372036854775807\n"
            "    minimum = maximum + 1\n"
            "    say minimum\n"
            "    say maximum * 2\n"
            "    say -minimum\n"
            "    each i from maximum to maximum:\n"
            "        say i\n"
            "    stop\n"
        )
        expected = ["-9223372036854775808", "-2", "-9223372036854775808", "9223372036854775807"]
        self.assertEqual(run_source(src), expected)
        self.assertEqual(run_source(src), _run_c(src))

    def test_conformance_division_by_zero(self):
        src = "start:\n    x = 5 / 0\n    stop\n"
        with self.assertRaises(Exception):
            run_source(src)
        # The native *build* must succeed; the failure has to come from the
        # runtime guard. An earlier preamble bug made this test pass because
        # gcc rejected the generated C, which proved nothing about division.
        c = emit_c(parse(tokenize(src)))
        exe = os.path.join(tempfile.gettempdir(), "atomicpp_divzero.exe")
        compile_c(c, exe, portable=True, march_native=False)
        r = subprocess.run([exe], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Division by zero", r.stderr)


    def test_conformance_c_keyword_identifiers(self):
        src = (
            "start:\n"
            "    int = 4\n"
            "    for = 6\n"
            "    main = int + for\n"
            "    say main\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_c(src))


    def test_conformance_unary_minus(self):
        src = (
            "start:\n"
            "    a = 7\n"
            "    b = -a / 2\n"
            "    say b\n"
            "    c = -(3 + 4)\n"
            "    say c\n"
            "    d = -5 + 2\n"
            "    say d\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_c(src))


    def test_conformance_float_arithmetic(self):
        src = (
            "start:\n"
            "    a = 3.5\n"
            "    b = a * 2\n"
            "    say b\n"
            "    c = 1 / 2.0\n"
            "    say c\n"
            "    d = 0.1 + 0.2\n"
            "    say d\n"
            "    e = (1.5 + 2.5) * 2\n"
            "    say e\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_c(src))

    def test_conformance_text_values(self):
        src = (
            "start:\n"
            "    name = \"ATOMIC++\"\n"
            "    say name\n"
            "    say \"100% ready\"\n"
            "    when name is \"ATOMIC++\":\n"
            "        say \"match\"\n"
            "    when name is not \"other\":\n"
            "        say \"different\"\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_c(src))

    # --- semantic consistency regressions (see LANGUAGE_SPEC.md 4.1, 6.1) ---

    def test_conformance_bool_literal_in_condition(self):
        """Bool literals lower to valid C and print the interpreter's spelling."""
        src = (
            "start:\n"
            "    alive = true\n"
            "    when alive is true:\n"
            "        say \"alive\"\n"
            "    when alive is not false:\n"
            "        say \"not false\"\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_c(src))

    def test_conformance_assignment_inside_when_and_each(self):
        """Blocks share the enclosing frame: assignment mutates, never shadows."""
        src = (
            "start:\n"
            "    x = 1\n"
            "    when true:\n"
            "        x = 2\n"
            "    say x\n"
            "    when x is 2:\n"
            "        each i from 1 to 3:\n"
            "            x = x + i\n"
            "    say x\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_c(src))

    def test_conformance_function_locals_stay_local(self):
        """A function writing a name must not overwrite a global of that name."""
        src = (
            "make bump(a):\n"
            "    g = a + 1\n"
            "    give g\n"
            "start:\n"
            "    g = 0\n"
            "    say bump(4)\n"
            "    say g\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_c(src))

    def test_conformance_function_reads_global(self):
        src = (
            "make read_global():\n"
            "    give score\n"
            "start:\n"
            "    score = 42\n"
            "    say read_global()\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), ["42"])
        self.assertEqual(run_source(src), _run_c(src))

    def test_arrays_conform_across_interpreter_and_c(self):
        src = (
            "start:\n"
            "    empty = []\n"
            "    say len(empty)\n"
            "    values = [4, 5]\n"
            "    values[0] = 9\n"
            "    say values[0]\n"
            "    words = [\"a\", \"b\"]\n"
            "    words[1] = \"c\"\n"
            "    say words[1]\n"
            "    ratios = [2.5]\n"
            "    say ratios[0]\n"
            "    flags = [true, false]\n"
            "    say flags[1]\n"
        )
        expected = ["0", "9", "c", "2.5", "False"]
        self.assertEqual(run_source(src), expected)
        self.assertEqual(_run_c(src), expected)

    def test_c_array_index_bounds_check(self):
        src = "start:\n    xs = [1]\n    say xs[1]\n"
        c = emit_c(parse(tokenize(src)))
        exe = os.path.join(tempfile.gettempdir(), "atomicpp_array_bounds.exe")
        compile_c(c, exe, portable=True, march_native=False)
        result = subprocess.run([exe], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Array index out of bounds: 1 (length 1)", result.stderr)

    def test_math_module_conforms_across_interpreter_and_c(self):
        src = (
            "use math\n"
            "start:\n"
            "    say math.add(1, 2)\n"
            "    say math.mul(3, 4)\n"
            "    say math.add(9223372036854775807, 1)\n"
        )
        expected = ["3", "12", "-9223372036854775808"]
        self.assertEqual(run_source(src), expected)
        self.assertEqual(_run_c(src), expected)

    def test_conformance_empty_range_binds_loop_variable(self):
        """An empty range still defines the name (LANGUAGE_SPEC.md 4.1 rule 4)."""
        src = (
            "start:\n"
            "    each i from 5 to 3:\n"
            "        say i\n"
            "    say i\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_c(src))

    def test_conformance_loop_variable_after_loop(self):
        """Names are function-scoped, so a loop variable survives the loop."""
        src = (
            "start:\n"
            "    total = 0\n"
            "    each i from 5 to 7:\n"
            "        total = total + i\n"
            "    say i\n"
            "    say total\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_c(src))

    def test_conformance_comparison_precedence(self):
        """Comparison is loosest, and the grouping must match in native code."""
        src = (
            "start:\n"
            "    when 1 + 2 > 3:\n"
            "        say \"wrong\"\n"
            "    when 2 * 3 is 6:\n"
            "        say \"right\"\n"
            "    say 1 + 2 * 3\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_c(src))
        self.assertEqual(run_source(src), ["right", "7"])


if __name__ == "__main__":
    unittest.main()
