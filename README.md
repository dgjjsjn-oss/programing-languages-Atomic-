# ATOMIC++

ATOMIC++ is a programming-language prototype with an interpreter, a native C/GCC
path, and Java output. Performance and safety guarantees are not yet established.

## Status: v0.7 development -- shared typed IR and expanding conformance

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
interpreter with native C and Java where their output is conformant. Boolean
operators, short-circuiting, typed arrays, bounds checks, and the imported
`math` built-ins now run on all three engines. `variables.atpp` remains skipped
because the C backend uses 17-digit round-trip formatting for `3.14` while the
interpreter and Java print `3.14`; this is a text-format difference, not a
different stored binary64 value.

The unit-test counts change as regression coverage grows; use the full runner's
result as the verified count rather than this documentation as a fixed number.

The unified runner was verified on 2026-11-06. Only trust this table if you re-run it. On 2026-11-05 the suite did **not**
match the previous claim in this file: the C preamble referenced an undefined macro, so
all 9 native conformance tests failed to compile while the README said "61 tests, all
green". That is fixed, but it is the reason every claim here is now paired with the
command that proves it.

## Known gaps

These are broken today and are not described anywhere as working:

- **Float formatting:** C prints `3.14` as `3.1400000000000001`; interpreter and Java print `3.14`.
- **General modules:** only the built-in `math` module is implemented consistently.
  Source-file modules, exports, dependency graphs and cycle detection are not implemented.
- **Array limits:** arrays cannot be nested or passed as function parameters; empty literals default to integer arrays.
- **Floating-point arithmetic:** the interpreter and direct C/Java emitters can evaluate it,
  but the shared checker still rejects it to preserve its tested v0.5 diagnostic behavior.
- **No unified memory model.** C strings currently use literal pointers and C array
  buffers are released at process exit; Java and the interpreter use managed values.
  ATOMIC++ does not yet define user-visible ownership or lifetimes.

Typed IR design and verifier: `arch/docs/TYPED_IR.md`.
Full audit, feature matrix and roadmap: `arch/docs/AUDIT.md`.
Sourced research behind the design decisions: `arch/docs/LANGUAGE_RESEARCH.md`.
Current independent audit and toolchain/performance snapshot: `arch/docs/RESEARCH_ASSESSMENT.md`.

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

Values: int (64-bit, wrapping), float (binary64), text, bool, and fixed-length mutable arrays of scalar values.

Logical operators: `not`, `and`, `or`, with short-circuit evaluation.
Arrays support integer, float, boolean and text elements, including `[]` (an
empty integer array), indexing, indexed assignment and `len(array)`.
`use math` imports the built-in `math.add`, `math.sub`, and `math.mul` functions.

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

`python bench/run_bench.py` measures a fixed host-language workload in C, C++,
Rust, Java, Node and Python with five-run distributions and a fixed output
oracle. It does **not** include ATOMIC++; see
`arch/docs/RESEARCH_ASSESSMENT.md` for results and why this is not an ATOMIC++
performance claim.

## Roadmap

`arch/docs/AUDIT.md` -- verified implementation matrix, risks, next milestone.
`arch/docs/MASTER_GOAL.md` -- the long-range target.
`arch/docs/LOOPHOLES.md` -- every weakness of every major language and its fix.
`arch/docs/ROADMAP.md` -- phase plan.
`arch/docs/LANGUAGE_RESEARCH.md` -- how Rust, Go, Zig, CPython, TypeScript, Swift, C#
and the JVM actually solved these problems, with sources.

M4.1 ("one truth") is done: comparison precedence is fixed, semantic analysis runs before
`run`, `build` and `java`, and diagnostic wording is pinned by a golden test.

v0.6 established the shared typed IR. v0.7 development adds logical operators,
cross-backend arrays, and consistent built-in `math` calls. Float formatting,
general source modules, function parameter typing, and a formal numeric contract
remain open. See the research assessment for the targeted backend comparison
and current benchmark baseline.
