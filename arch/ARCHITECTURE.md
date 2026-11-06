# ATOMIC++ Architecture

**Current milestone:** v0.7 development — typed IR backend consistency

**Implementation:** Python front end, native C via GCC, Java via `javac`
**Status:** Prototype. Feature support is limited to the tested subset below.

## Current pipeline

```text
source
  → lexer and parser (`vertical_slice/interpreter.py`)
  → parsed syntax dictionaries
  → name resolution and type construction (`vertical_slice/ir.py`)
  → typed `IRProgram` plus verifier diagnostics
       ├─ interpreter (`Interpreter.run`)
       ├─ C emitter → GCC → executable
       └─ Java emitter → javac → JVM class
```

`atomic.py` builds one `IRProgram` per command and shares that object with the
selected consumer. `run_source()` also lowers parsed syntax before interpreting
it. `semantic.analyze()` is a compatibility wrapper over the same IR builder;
there is no second semantic checker.

## Typed IR

The IR is defined in [TYPED_IR.md](docs/TYPED_IR.md). It consists of explicit
expression and statement classes with source spans. Every expression records a
language `Type`; the program stores global types and function signatures. The
IR is structured rather than CFG/SSA: branches and loops own nested statement
sequences, so there are no block IDs or branch targets to resolve yet.

`verify_ir()` checks IR shape and consistency before code generation. C and Java
map IR types to their target representation; they do not infer source types.
Both emitters retain a compatibility API that accepts parser output, but it
immediately builds and verifies typed IR.

## Backend support

| Feature | Interpreter | C/GCC | Java/JVM |
|---|---|---|---|
| Integer arithmetic, comparisons, functions, conditions, loops | Supported | Supported | Supported |
| Float values and direct backend arithmetic | Supported | Supported | Supported |
| Float arithmetic through checked CLI | Checker currently rejects it | Checker currently rejects it | Checker currently rejects it |
| Text literals and value equality | Supported | Supported | Supported |
| Text concatenation | Supported | Rejected explicitly | Supported |
| Boolean `not` / short-circuit `and` / `or` | Supported | Supported | Supported |
| Fixed-size mutable arrays of scalar types | Supported | Supported | Supported |
| `len(array)` and bounds checks | Supported | Supported | Supported |
| Imported built-in `math.add/sub/mul` | Supported | Supported | Supported |
| User-authored file modules and exports | Not supported | Not supported | Not supported |
| Boolean output formatting | `True`/`False` | `True`/`False` | `True`/`False` |

These are prototype capabilities, not performance or safety guarantees. The
README's Known gaps section records the current float-formatting difference
and the exact cross-backend examples excluded from the conformance runner.

## Numeric behavior

The interpreter applies signed 64-bit two's-complement wrapping to integer
operations. The C backend now implements integer `+`, `-`, `*`, and unary minus
using unsigned arithmetic followed by a bit-preserving copy into `int64_t`, so
the generated C does not invoke signed-overflow undefined behavior. Integer
division checks zero and handles `INT64_MIN / -1` explicitly. Inclusive C and
Java loops avoid incrementing past `INT64_MAX`.

The semantics still need broader formalization. The existing checker rejects
floating arithmetic to preserve its diagnostic contract even though direct
interpreter/C/Java operations can evaluate it. C prints a float such as `3.14`
as `3.1400000000000001`; this is an open conformance issue.

## Limitations

- Arrays are fixed-length, scalar-element arrays; nested arrays and arrays as
  function arguments are not supported. Empty literals default to `int[]`.
- The only module is the built-in `math` namespace (`add`, `sub`, `mul`).
  Cross-file modules, exports and cycle detection need a project loader.
- No records, generics, async, concurrency, package manager, or standard
  library beyond the current interpreter's small built-ins.
- C array literals use tracked heap storage released at process exit. There is
  no language-wide ownership, borrow, or lifetime system, and no dynamic text
  allocation strategy shared by the backends.
- There is no CFG, SSA, optimizer, parser fuzzer, or randomized differential
  generator yet.
- The compiler has no cross-platform CI. Current verification uses the local
  Windows toolchain.

Run `python run_tests.py` from the repository root. It runs the unit tests,
checks and interprets every example, and compares outputs for the examples that
are currently conformant across engines. Skipped examples are printed with the
reason; they are not counted as backend passes.
