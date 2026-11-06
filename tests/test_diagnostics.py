#!/usr/bin/env python3
"""ATOMIC++ diagnostic golden tests.

The *wording* of a diagnostic is part of the interface: beginners read it, and
tests that only assert an error code will happily accept garbage text. This file
pins the exact message for every diagnostic the analyzer can emit.

Modelled on Elm's error-message-catalog and TypeScript's baselines: when a
message changes, this test fails and the new text has to be reviewed and
accepted deliberately.

Run with: python tests/test_diagnostics.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vertical_slice"))

from semantic import analyze


# (source, expected code, expected message)
GOLDEN = [
    (
        "start:\n    say x\n    stop\n",
        "undefined_variable",
        "Undefined variable 'x'",
    ),
    (
        "start:\n    say nope(1)\n    stop\n",
        "undefined_function",
        "Undefined function 'nope'",
    ),
    (
        "start:\n    give 5\n    stop\n",
        "invalid_return",
        "'give' outside a function",
    ),
    (
        "make f(a, b):\n    give a\nstart:\n    say f(1)\n    stop\n",
        "invalid_call",
        "Function 'f' expects 2 args, got 1",
    ),
    (
        'start:\n    x = "a" - 1\n    stop\n',
        "invalid_operation",
        "Invalid operands for '-': string - int",
    ),
    (
        "start:\n    x = 1.5 * 2.0\n    stop\n",
        "invalid_operation",
        "Invalid operands for '*': float * float",
    ),
]


class TestDiagnosticGolden(unittest.TestCase):
    def test_golden_messages(self):
        for src, code, message in GOLDEN:
            with self.subTest(src=src):
                diags = analyze(src)
                self.assertEqual(len(diags), 1, f"expected 1 diagnostic for {src!r}, got {diags}")
                self.assertEqual(diags[0]["code"], code)
                self.assertEqual(diags[0]["message"], message)

    def test_diagnostics_carry_a_location(self):
        for src, _, _ in GOLDEN:
            with self.subTest(src=src):
                d = analyze(src)[0]
                self.assertIsInstance(d["line"], int)
                self.assertIsInstance(d["col"], int)
                self.assertGreater(d["line"], 0)
                self.assertGreater(d["col"], 0)

    def test_valid_program_is_silent(self):
        src = (
            "make double(n):\n"
            "    m = n * 2\n"
            "    give m\n"
            "start:\n"
            "    x = 5\n"
            "    when x > 1:\n"
            "        x = double(x)\n"
            "    each i from 1 to 2:\n"
            "        x = x + i\n"
            "    say x\n"
            "    stop\n"
        )
        self.assertEqual(analyze(src), [])

    def test_function_locals_are_not_reported_undefined(self):
        """A function assigning its own local used to be a false positive."""
        src = (
            "make f(a):\n"
            "    b = a + 1\n"
            "    give b\n"
            "start:\n"
            "    say f(1)\n"
            "    stop\n"
        )
        self.assertEqual(analyze(src), [])


if __name__ == "__main__":
    unittest.main()
