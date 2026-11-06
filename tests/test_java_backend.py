#!/usr/bin/env python3
"""ATOMIC++ Java backend tests: interpreter output must equal javac output."""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vertical_slice"))

from interpreter import parse, tokenize, run_source
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
