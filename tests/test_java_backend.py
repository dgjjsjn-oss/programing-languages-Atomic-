#!/usr/bin/env python3
"""ATOMIC++ Java backend tests: interpreter output must equal javac output."""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vertical_slice"))

from interpreter import AtomicError, parse, tokenize, run_source
from java_backend import emit_java, compile_java


def _run_java(src: str):
    ast = parse(tokenize(src))
    java = emit_java(ast, "AtomicMain")
    out_dir = os.path.join(tempfile.gettempdir(), "atomicpp_java")
    compile_java(java, out_dir, "AtomicMain")
    r = subprocess.run(["java", "-cp", out_dir, "AtomicMain"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("java run failed: " + r.stderr)
    return [ln for ln in r.stdout.split("\n") if ln != ""]


class TestJavaBackend(unittest.TestCase):
    def test_boolean_operators_short_circuit(self):
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
        self.assertEqual(_run_java(src), expected)

    def test_arrays_conform(self):
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
        self.assertEqual(_run_java(src), expected)

    def test_java_array_index_bounds_check(self):
        src = "start:\n    xs = [1]\n    say xs[1]\n"
        java = emit_java(parse(tokenize(src)), "AtomicBounds")
        out_dir = os.path.join(tempfile.gettempdir(), "atomicpp_java_bounds")
        compile_java(java, out_dir, "AtomicBounds")
        result = subprocess.run(["java", "-cp", out_dir, "AtomicBounds"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Array index out of bounds: 1 (length 1)", result.stderr)

    def test_math_module_conforms(self):
        src = (
            "use math\n"
            "start:\n"
            "    say math.add(1, 2)\n"
            "    say math.mul(3, 4)\n"
            "    say math.add(9223372036854775807, 1)\n"
        )
        expected = ["3", "12", "-9223372036854775808"]
        self.assertEqual(run_source(src), expected)
        self.assertEqual(_run_java(src), expected)

    def test_arithmetic_loop_condition(self):
        src = (
            "start:\n"
            "    x = 2 + 3 * 4\n"
            "    say x\n"
            "    each i from 0 to 2:\n"
            "        when i is 1:\n"
            "            say i\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_java(src))

    def test_recursion(self):
        src = (
            "make fact(n):\n"
            "    when n is 0:\n"
            "        give 1\n"
            "    give n * fact(n - 1)\n"
            "start:\n"
            "    say fact(5)\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_java(src))

    def test_function_reads_global(self):
        src = (
            "make read_global():\n"
            "    give score\n"
            "start:\n"
            "    score = 42\n"
            "    say read_global()\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), ["42"])
        self.assertEqual(run_source(src), _run_java(src))

    def test_float_and_text(self):
        src = (
            "start:\n"
            "    a = 3.5\n"
            "    b = a * 2\n"
            "    say b\n"
            "    name = \"ATOMIC++\"\n"
            "    say name\n"
            "    when name is \"ATOMIC++\":\n"
            "        say \"match\"\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_java(src))

    def test_int_division(self):
        src = (
            "start:\n"
            "    a = 7 / 2\n"
            "    say a\n"
            "    b = 10 / 3\n"
            "    say b\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_java(src))

    def test_i64_wrap_and_maximum_loop(self):
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
        self.assertEqual(run_source(src), _run_java(src))

    def test_bool_condition_and_loop_variable(self):
        """bool lowers to long, and a loop variable stays readable afterwards."""
        src = (
            "start:\n"
            "    alive = true\n"
            "    when alive is true:\n"
            "        say \"alive\"\n"
            "    each i from 1 to 3:\n"
            "        alive = false\n"
            "    say i\n"
            "    when alive is false:\n"
            "        say \"falsy\"\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_java(src))

    def test_assignment_inside_when(self):
        src = (
            "start:\n"
            "    x = 1\n"
            "    when true:\n"
            "        x = 2\n"
            "    say x\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_java(src))

    def test_comparison_precedence(self):
        src = (
            "start:\n"
            "    when 1 + 2 > 3:\n"
            "        say \"wrong\"\n"
            "    when 2 * 3 is 6:\n"
            "        say \"right\"\n"
            "    say 1 + 2 * 3\n"
            "    stop\n"
        )
        self.assertEqual(run_source(src), _run_java(src))
        self.assertEqual(run_source(src), ["right", "7"])


if __name__ == "__main__":
    unittest.main()
