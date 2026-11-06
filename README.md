# ATOMIC++

ATOMIC++ is a programming-language prototype with an interpreter, a native C/GCC
path, and Java output. Performance and safety guarantees are not yet established.

## Status: v0.6 -- shared typed IR in use

| Engine | Command | Result |
|---|---|---|
| Interpreter | `python atomic.py run file.atomic` | reference semantics |
| Native (C + gcc) | `python atomic.py build file.atomic` | .exe, -O2 |
| JVM (Java) | `python atomic.py java file.atomic --class MyMod` | .java for Fabric/Forge |

The interpreter, C emitter, and Java emitter now receive the same typed IR.
Output equality is tested only for the explicitly supported conformance subset;
see Known gaps below and [the IR design](arch/docs/TYPED_IR.md).

## Tests

Run the complete test and example conformance suite from this folder:

    python run_tests.py

It runs the unit tests, checks and interprets every example, and compares the
interpreter with native C and Java where their output is currently conformant.
Array and module examples remain interpreter-only; `variables.atpp` is skipped
because the interpreter prints booleans as `True`/`False`, while C and Java
store and print them as `1`/`0`. Float formatting also differs: for `3.14`,
the interpreter prints `3.14` and C currently prints `3.1400000000000001`.

The lower-level test files can also be run individually:

    python tests/test_interpreter.py    46 tests  OK
    python tests/test_semantic.py        7 tests  OK
    python tests/test_conformance.py    18 tests  OK   interpreter == native C
    python tests/test_java_backend.py   10 tests  OK   interpreter == javac
    python tests/test_diagnostics.py     4 tests  OK   diagnostic text is pinned
    python tests/test_ir.py               8 tests  OK   typed nodes and verifier

The unified runner was verified on 2026-11-06. Only trust this table if you re-run it. On 2026-11-05 the suite did **not**
match the previous claim in this file: the C preamble referenced an undefined macro, so
all 9 native conformance tests failed to compile while the README said "61 tests, all
green". That is fixed, but it is the reason every claim here is now paired with the
command that proves it.

## Known gaps

These are broken today and are not described anywhere as working:

- **`say` on a bool:** the interpreter prints `True`/`False`; C and Java store booleans
  as integer values and print `1`/`0`. Java comparison expressions can print `true`/`false`.
- **Float formatting:** C prints `3.14` as `3.1400000000000001`; interpreter and Java print `3.14`.
- **Arrays** work in the interpreter only; the C and Java backends reject them.
- **Modules:** the interpreter supports `math.add/sub/mul`; C and Java report that module
  calls are unsupported.
- **Floating-point arithmetic:** the interpreter and direct C/Java emitters can evaluate it,
  but the shared checker still rejects it to preserve its tested v0.5 diagnostic behavior.
- **No ATOMIC++ memory model.** The C backend uses string-literal pointers; Java relies on
  the JVM's memory manager. ATOMIC++ does not yet define ownership or manage heap values.

Typed IR design and verifier: `arch/docs/TYPED_IR.md`.
Full audit, feature matrix and roadmap: `arch/docs/AUDIT.md`.
Sourced research behind the design decisions: `arch/docs/LANGUAGE_RESEARCH.md`.

## Language

    make damage(base, power):
        give base * power / 2

    start:
        x = 2 + 3 * 4
        name = "ATOMIC++"
        rate = 3.5
        when x > 10:
            say "big"
        each i from 1 to 3:
            say damage(i, 2)
        stop

Keywords: `start stop say make use when each give true false from to`.
Equality is `is` / `is not`; comparisons `< > <= >=`; arithmetic `+ - * /`;
unary minus and grouping `(` `)` work. Blocks are indentation-based.

Values: int (64-bit, wrapping), float (double), text, bool.

## Design rules

1. One obvious way to write each construct.
2. Safe by default: checked division, defined overflow, no undefined behaviour.
3. Same program, same answer, on every backend.
4. Errors are diagnostics with line and column, never crashes.

## Commands

    python atomic.py run   examples/hello.atomic
    python atomic.py check examples/hello.atomic
    python atomic.py build examples/fib.atomic --out build/fib.exe
    python atomic.py java  examples_minecraft_mod.atomic --class AtomicMod
    python atomic.py c     examples/hello.atomic

By default, native executables and generated C are written under `build/`;
Java source and class files go under `build/java/`. Options: `--out NAME`,
`--class NAME`, `--O3`, `--native`.

## Minecraft mods

`python atomic.py java mod.atomic --class MyMod` writes `MyMod.java` under
`build/java/`. Copy it into `src/main/java/<package>/` in a Fabric or Forge
project, call its static methods from your mod initializer, and build with
Gradle. No dependencies are emitted, so it compiles inside the mod toolchain.

## Benchmarks

`bench/` holds the same workload in C, C++, Rust, Java, Node and Python with
`run_bench.py` measuring compile time, runtime, LOC and output equality.## Roadmap

`arch/docs/AUDIT.md` -- verified implementation matrix, risks, next milestone.
`arch/docs/MASTER_GOAL.md` -- the long-range target.
`arch/docs/LOOPHOLES.md` -- every weakness of every major language and its fix.
`arch/docs/ROADMAP.md` -- phase plan.
`arch/docs/LANGUAGE_RESEARCH.md` -- how Rust, Go, Zig, CPython, TypeScript, Swift, C#
and the JVM actually solved these problems, with sources.

M4.1 ("one truth") is done: comparison precedence is fixed, semantic analysis runs before
`run`, `build` and `java`, and diagnostic wording is pinned by a golden test.

Next milestone (M4.2): a typed IR that the backends consume, with a verifier, so a feature
cannot mean different things in different backends. Then arrays in the C backend.
