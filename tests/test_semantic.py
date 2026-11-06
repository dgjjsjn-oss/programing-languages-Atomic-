#!/usr/bin/env python3
"""ATOMIC++ Phase 3 -- semantic analyzer tests.

Run with: python tests/test_semantic.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vertical_slice"))

from semantic import analyze


def _codes(diags):
    return sorted({d["code"] for d in diags})


class TestSemantic(unittest.TestCase):
    def test_valid_program_no_diagnostics(self):
        src = (
            "use math\n"
            "make double(n):\n"
            "    give n * 2\n"
            "start:\n"
            "    x = 5\n"
            "    say double(x)\n"
            "    say math.add(x, 2)\n"
            "    stop\n"
        )
        self.assertEqual(analyze(src), [])

    def test_undefined_variable(self):
        src = "start:\n    x = y + 1\n    stop\n"
        self.assertIn("undefined_variable", _codes(analyze(src)))

    def test_invalid_operation(self):
        src = 'start:\n    x = "a" - 1\n    stop\n'
        self.assertIn("invalid_operation", _codes(analyze(src)))

    def test_invalid_return(self):
        src = "start:\n    give 5\n    stop\n"
        self.assertIn("invalid_return", _codes(analyze(src)))

    def test_undefined_function(self):
        src = "start:\n    say nope(1)\n    stop\n"
        self.assertIn("undefined_function", _codes(analyze(src)))

    def test_math_module_must_be_imported(self):
        src = "start:\n    say math.add(1, 2)\n"
        self.assertIn("missing_import", _codes(analyze(src)))

    def test_nested_arrays_and_array_comparison_are_rejected(self):
        src = "start:\n    nested = [[1], [2]]\n    same = nested is nested\n"
        codes = _codes(analyze(src))
        self.assertIn("unsupported_array", codes)
        self.assertIn("invalid_operation", codes)

    def test_arg_count_mismatch(self):
        src = (
            "make f(a, b):\n"
            "    give a + b\n"
            "start:\n"
            "    say f(1)\n"
            "    stop\n"
        )
        self.assertIn("invalid_call", _codes(analyze(src)))

    def test_no_cascading_diagnostics(self):
        """One root cause must produce one diagnostic, not a cascade.

        `y + 1` with `y` undefined previously reported both `undefined_variable`
        and `invalid_operation`. Elm's error-message work calls this out as a
        core quality rule (elm-lang.org/news/compilers-as-assistants).
        """
        src = "start:\n    x = y + 1\n    stop\n"
        diags = analyze(src)
        self.assertEqual(len(diags), 1, f"expected 1 diagnostic, got {diags}")
        self.assertEqual(diags[0]["code"], "undefined_variable")


if __name__ == "__main__":
    unittest.main()
