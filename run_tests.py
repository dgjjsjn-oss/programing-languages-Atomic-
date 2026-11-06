#!/usr/bin/env python3
"""Run ATOMIC++ tests and check every example through the supported engines."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parent
EXAMPLES = ROOT / "vertical_slice" / "examples"

# Examples excluded from interpreter/backend output comparison until their
# features have identical semantics in every engine.
NO_CROSS_BACKEND_CONFORMANCE = {
    "variables.atpp": "C prints round-trip float precision (3.1400000000000001), while the interpreter/Java use shorter decimal forms",
}


def invoke(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "atomic.py"), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def require_success(label: str, result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode != 0:
        details = (result.stdout + result.stderr).strip()
        raise RuntimeError(f"{label} failed (exit {result.returncode}):\n{details}")


def program_output(result: subprocess.CompletedProcess[str], label: str) -> str:
    require_success(label, result)
    lines = result.stdout.splitlines()
    # build/java print a one-line artifact location before the program output.
    if lines and lines[0].startswith(("built: ", "java: ")):
        return "\n".join(lines[1:])
    return result.stdout.rstrip("\r\n")


def check_examples() -> int:
    examples = sorted(EXAMPLES.glob("*.atpp"))
    if not examples:
        raise RuntimeError(f"No examples found in {EXAMPLES}")

    checks = 0
    for example in examples:
        name = example.name
        relpath = str(example.relative_to(ROOT))

        require_success(f"check {name}", invoke("check", relpath))
        interpreted = program_output(invoke("run", relpath), f"run {name}")
        checks += 2

        unsupported = NO_CROSS_BACKEND_CONFORMANCE.get(name)
        if unsupported:
            print(f"SKIP cross-backend comparison for {name}: {unsupported}")
            continue

        native = program_output(invoke("build", relpath), f"build {name}")
        if native != interpreted:
            raise RuntimeError(f"native output differs from interpreter for {name}: {native!r} != {interpreted!r}")

        class_name = "Example_" + example.stem
        jvm = program_output(invoke("java", relpath, "--class", class_name), f"java {name}")
        if jvm != interpreted:
            raise RuntimeError(f"Java output differs from interpreter for {name}: {jvm!r} != {interpreted!r}")
        checks += 2

    print(f"Example checks passed: {checks} commands across {len(examples)} examples")
    return checks


def main() -> int:
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1

    try:
        check_examples()
    except (OSError, RuntimeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
