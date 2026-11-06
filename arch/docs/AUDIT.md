# ATOMIC++ v0.5 — HONEST IMPLEMENTATION AUDIT

**Date:** 2026-11-05
**Audited tree:** `C:\Users\nasri\Desktop\ATOMIC ++\atomicpp`
**Method:** every source file read, every test suite executed, all five CLI commands run,
plus differential probes comparing the interpreter against the compiled C and Java output.

The previous README claimed "61 tests, all green". That claim was **false when this audit
began**: the C preamble referenced an undefined macro, so 8 of 9 native conformance tests
failed to compile, and the ninth passed for the wrong reason. Corrections made during the
audit are listed in §11.

---

## 1. Repository structure report

42 files. No dependencies outside the Python standard library. No build system — the
"build" is `gcc` invoked from Python.

```
atomicpp/
├── atomic.py                    CLI: run | check | c | build | java        (132 lines)
├── README.md                    status, language tour, test table
├── examples_minecraft_mod.atomic
├── AtomicMod.java               GENERATED ARTIFACT, committed by mistake
├── AtomicMod.class              GENERATED ARTIFACT, committed by mistake
├── modtest.exe / modtest.exe.c  experiment, not referenced by anything
├── vertical_slice/
│   ├── interpreter.py           lexer + parser + tree-walk interpreter   (~880 lines)
│   ├── semantic.py              diagnostics over the "IR"                 (~150 lines)
│   ├── ir.py                    AST -> dict relabelling                   (~80 lines)
│   ├── c_backend.py            type inference + C emitter + gcc driver    (~400 lines)
│   ├── java_backend.py         Java emitter + javac driver                (~230 lines)
│   └── examples/*.atpp          8 examples
├── tests/
│   ├── test_interpreter.py      42 tests
│   ├── test_semantic.py          7 tests
│   ├── test_conformance.py      14 tests   interpreter == native C
│   └── test_java_backend.py      6 tests   interpreter == javac
├── bench/                       bench.{c,cpp,rs,py,js}, Bench.java, run_bench.py
├── spec/LANGUAGE_SPEC.md
└── arch/
    ├── ARCHITECTURE.md
    └── docs/{MASTER_GOAL,ROADMAP,LOOPHOLES,BACKEND_DECISION,
              BENCHMARK_PLAN,MEMORY_MODEL_RESEARCH,LANGUAGE_RESEARCH}.md
```

**Toolchain present:** Python 3.13.14, gcc 16.1.0 (MinGW-W64 ucrt), javac 21.0.12,
rustc 1.99.1, node. **clang/LLVM: absent** (matches `BACKEND_DECISION.md`).
**Version control: none.** `git log` fails — this directory is not a repository.

Total source of the language itself: roughly 1,800 lines of Python.

---

## 2. Feature implementation matrix

Classification: **Full** = implemented and covered by a passing test · **Partial** = works
on some backends or some inputs · **Broken** = reachable but produces a wrong result or an
invalid artifact · **Missing** = not implemented.

### 2.1 Front end

| Feature | Status | Evidence / limit |
|---|---|---|
| Indentation-based blocks | Full | `Lexer.tokenize`; INDENT/DEDENT; inconsistent dedent is an error |
| Keywords `start stop say make use when each give true false from to` | Full | `KEYWORDS` |
| Identifier with `_` | Full | |
| Int literals | Full | wrapped to int64 on arithmetic |
| Float literals | Full | parsed when a `.` appears |
| String literals + `\n \t \" \\` escapes | Full | other escapes silently pass through the character |
| `//` comments, blank lines, EOF | Full | tested |
| Tabs vs spaces | **Broken** | indentation width = character count, so a tab counts as 1 space; mixing them mis-nests blocks silently |
| `and` / `or` / `not` | **Missing** | no boolean operators at all |
| `else` / `elif` | **Missing** | `when` has no else branch; documented as Phase 1 |
| `while`, `break`, `continue` | **Missing** | |
| Block comments, raw strings, multi-line strings | **Missing** | |
| Operator precedence between comparison and arithmetic | **Fixed in M4.1** | comparison is now the loosest level: `parse_expression → parse_comparison → parse_addsub → parse_muldiv → parse_primary`. `1 + 2 > 3` is false and `2 * 3 is 6` is true on all three backends. |
| Comparison chaining (`a < b < c`) | Missing | `parse_comparison` allows one comparison per expression |
| Unary minus / plus, grouping | Full | precedence and truncation covered by 7 interpreter tests |
| `each` inclusive bounds | Full | `range(start, end+1)` vs `for (i <= end)` |
| `each` body mutating the loop variable | Full | hidden-counter lowering; iteration unaffected |
| Nested loops | Full | 1 test |
| Function definition, params, `give`, recursion | Full | factorial/fib tests on all three backends |
| Closures / nested functions capturing locals | **Missing** | interpreter frame links to globals only; C and Java have no equivalent |
| Modules (`use math`) | **Partial** | interpreter hardcodes `math.add/sub/mul`; C backend raises; Java emits a call to a nonexistent class |
| Arrays: literal, read, write, bounds check | **Partial** | interpreter full (`list`, checked); C and Java reject |
| `len()` builtin | **Partial** | interpreter only |
| `stop` | **Partial** | interpreter: `SystemExit`; C/Java: `return 0/return` — inside a `text`-returning function C emits `return 0;`, i.e. a null pointer |

### 2.2 Type system and checking

| Feature | Status | Limit |
|---|---|---|
| Static typing | **Partial** | `c_backend._infer` iterates up to 15 times to a fixed point over `int64_t`/`double`/`const char *` |
| Local type inference | Partial | variable types come from the first non-null join of assigned expressions |
| Function parameter/return inference | Partial | all params start as `int64_t` and widen only when an argument is float/text |
| "A name keeps one type" (spec §4) | **Missing** | interpreter happily rebinds `x = 1` then `x = "s"`; backends infer one C type and the assignment then fails to compile |
| Semantic analysis in the run/build path | **Fixed in M4.1** | `atomic.py check_source()` analyses before `run`, `build` and `java`, so all four entry points reject the same programs |
| Semantic analysis accuracy | **Partial** | params are always typed `int`; every binop is typed `int`; `array_index` always `int` |
| Diagnostics have codes + line:col | Full | `undefined_variable`, `undefined_function`, `invalid_operation`, `invalid_call`, `invalid_return` |
| No cascading diagnostics | Full (fixed this audit) | `x = y + 1` now yields exactly 1 diagnostic, was 2 |
| Diagnostics text under test | **Missing** | no test asserts message wording; there is no golden corpus |

### 2.3 Backends

| Capability | Interpreter | C (`gcc`) | Java (`javac`) |
|---|---|---|---|
| int / float / text / bool values | yes | yes | yes |
| `say` of int / float / text | yes | yes | yes |
| `say` of bool | `True`/`False` | `1`/`0` | `1`/`0` — **divergent** |
| arithmetic, comparisons, `is` | yes | yes | yes |
| text equality (`is`) | yes | `strcmp` | `String.equals` |
| text concatenation (`+`) | yes | **rejected** | yes |
| `when`, `each`, functions, recursion | yes | yes | yes |
| arrays | yes | **rejected** | **rejected** |
| `math` module | yes | **rejected** | emits broken code |
| integer division by zero | clean error | `exit(1)` + stderr | `ArithmeticException` — **divergent message/behaviour** |
| int64 wrap on overflow | yes | yes (C `int64_t` wrap) | **no** (Java `long` wraps too, but the emitter casts, untested at the boundary) |

Generated artifacts: `AtomicMod.java` and `AtomicMod.class` are checked into the source
tree by `atomic.py java` writing next to the input. Build outputs are not separated from
sources.

### 2.4 Runtime and memory

| Feature | Status |
|---|---|
| Memory management | **Missing.** `MEMORY_MODEL_RESEARCH.md` selects ARC for Phase 1; no backend emits retaining code, and no backend allocates heap values. Text is a `const char *` pointing at a string literal, with no ownership. |
| Bounds checking | Interpreter only |
| Uninitialised reads | **Fixed this audit**: C locals are now emitted with type-default initialisers |
| Panic / error runtime | Division by zero only |
| GC / ARC / arenas / ownership | Missing (all four) |

### 2.5 Tooling

| Tool | Status |
|---|---|
| CLI `run` / `check` / `c` / `build` / `java` | Full — all five exercised during the audit |
| Formatter | Missing |
| Linter / static analyzer | Partial (`check` only) |
| Test runner | ad-hoc `unittest` per file |
| Debugger, profiler | Missing |
| Language server, editor support | Missing |
| Package manager, project generator | Missing |
| Documentation generator | Missing |
| Benchmark runner | **Partial and misleading** — `bench/run_bench.py` measures C, C++, Rust, Java, Node and Python and contains **no ATOMIC++ entry** |

### 2.6 Tests

79 tests, all passing after the audit fixes: 46 interpreter, 7 semantic, 15 native
conformance, 7 Java conformance, 4 diagnostic-golden.

| Property | Status |
|---|---|
| Tests compare printed output | Yes — no test compares evaluated values directly |
| Every example covered by a test | Interpreter: yes (8 example tests). Native: no. Java: only via inline sources. |
| Error-message text covered | No |
| Golden/snapshot outputs | No |
| Fuzzing (valid or invalid programs) | No |
| Property tests | No |
| IR verifier tests | No IR verifier exists |
| Cross-platform tests | No — Windows/MinGW only |
| Sanitizer runs | No |

---

## 3. Compiler architecture — what actually runs today

Not the aspirational diagram in `ARCHITECTURE.md`. The real data flow:

```
 source .atomic
      │
      ▼
 ┌──────────┐   tokens (list[Token], each with line/col)
 │ Lexer    │──────────────────────────────────────┐
 └──────────┘                                      │
      │                                            │
      ▼                                            │
 ┌──────────┐   AST = list[dict]  (shapes frozen,  │
 │ Parser   │   no type objects, no classes)       │
 └──────────┘                                      │
      │                                            │
      ├───────────────────┬────────────────────┐   │
      │                   │                    │   │
      ▼                   ▼                    ▼   │
 ┌─────────┐        ┌───────────┐        ┌──────────────┐
 │ir.build │        │interpreter│        │c_backend     │
 │  _ir()  │        │ tree-walk │        │._infer + emit│
 └─────────┘        └───────────┘        └──────────────┘
      │                   │                    │
      ▼                   ▼                    ▼
 ┌─────────┐          output []          generated C ──gcc──> .exe
 │semantic │                                          
 │.analyze │            ┌──────────────────────────────┐
 └─────────┘            │java_backend: reuses          │
      │                 │c_backend._infer, emits .java │──javac/jvm──> output
      ▼                 └──────────────────────────────┘
 diagnostics
 (only for `check`)
```

Three facts this diagram exposes:

1. **`ir.py` is not the hub.** Its `build_ir()` output is consumed only by
   `semantic.py`. Both code generators walk the *parser's* dicts directly. The "IR" is a
   key-renaming pass, not a typed representation.
2. **`semantic.py` is off the critical path.** `run` and `build` never call it, so the
   checker and the code generators disagree about what a legal program is.
3. **The type model lives in `c_backend._infer`** and is imported by the Java backend.
   There is no language-level type representation — just three strings (`int64_t`,
   `double`, `const char *`) threaded through a fixed-point loop.

---

## 4. Technical risks

| # | Risk | Why it matters | Evidence |
|---|---|---|---|
| R1 | **No version control** | No history, no branches, no revert, no regression-corpus discipline. A bad edit is unrecoverable. | `git log` → "not a git repository" |
| R2 | **Three independent implementations of the same semantics** | Every new feature must be written three times and kept in sync by hand. Drift is the default outcome. | 5 divergences found within one hour of probing; 4 of them were invisible to the test suite |
| R3 | **No shared semantic model** | `check`, `run` and `build` accept different programs. | `analyze()` never called by `run`/`build` |
| R4 | **Precedence bug** *(closed in M4.1)* | `1 + 2 > 3` silently evaluated as `1 + (2 > 3)` — wrong answers, not errors. Now fixed with a test per precedence level. | old chain `parse_addsub → parse_muldiv → parse_comparison → parse_primary` |
| R5 | **The conformance subset ≠ the language** | The suite proves interpreter==C only for programs C can compile: no arrays, no modules, no concatenation. The most-used data type in the interpreter is untested natively. | `c_backend` raises for array literals; `test_conformance` contains no array test |
| R6 | **Claims outrun code** | README said all tests pass while 8 failed. `MEMORY_MODEL_RESEARCH.md` says ARC is "Selected for Phase 1" though nothing allocates. `LOOPHOLES.md` says "6 tests, green" (stale). `BENCHMARK_PLAN.md` publishes C++/Python timings for a machine that is not this one. | read the files |
| R7 | **Benchmark harness cannot measure the project** | `run_bench.py` has no ATOMIC++ row, so no performance claim about ATOMIC++ can currently be produced. | `LANG = [C, C++, Rust, Java, Node, Python]` |
| R8 | **Scope vs capacity** | The master directive lists a standard library, GUI, networking, package registry, LSP, debugger and 16 example applications. The language core is 1,800 lines and cannot yet compile an array. | §8–§12 of the directive vs §2 of this audit |
| R9 | **Python performance ceiling** | `_infer` iterates the whole program up to 15 times; `emit_c` builds strings by concatenation. Fine at 100 lines, quadratic-feeling at 10k. | `_infer` loop bound is literally `range(15)` |

---

## 5. Missing foundations

Ordered by what unblocks the most:

1. **Version control and a regression corpus.** Nothing else is safe without R1.
2. **One semantic model, used by every entry point.** A single name-resolution and
   type-inference pass producing a typed IR that `run`, `check`, `c`, `build` and `java`
   all consume. This is the fix for R2, R3 and R5 simultaneously.
3. **A real IR with a verifier.** `ir.py` must carry types, not relabel keys. The verifier
   rejects a node whose declared type does not match its operands before any backend sees it.
4. **A diagnostics object with span, code and explanation**, plus a golden corpus of
   diagnostics. Codes exist; texts are untested; there is no explanation registry.
5. **Arrays as a language feature, not an interpreter detail** — the type model needs
   `array<T>` before the C backend can support them.
6. **A memory model that is either implemented or not claimed.** Delete the ARC claim or
   emit retaining code; do not do both silently.
7. **A fuzz target for the parser** (invalid program must never traceback) and a
   **random valid-program generator** with interpreter-vs-C differential comparison.
8. **Standard library** — nothing exists. `math` is three lambdas in the interpreter.
9. **Tooling** — formatter, LSP, test runner, package manager: all zero.

---

## 6. Recommended language specification work

`spec/LANGUAGE_SPEC.md` is a readable Phase 1 description but is not normative enough to
implement three backends against. It needs, in this order:

1. **A precedence table** with a number per level, and a test per row. (Today the table in
   §2.5 and the parser disagree — R4.)
2. **Numeric semantics as a table:** int is 64-bit two's complement wrapping; division
   truncates toward zero; `INT64_MIN / -1` is defined as `INT64_MIN`; float is IEEE-754
   binary64; no implicit int↔float↔bool coercion; division by zero is a clean error whose
   message is specified.
3. **Text semantics:** immutable, UTF-8, `+` concatenates, `is` compares by value,
   indexing is byte-based (or explicitly not supported).
4. **Name and scope rules** — now written as §4.1, and enforced by tests on all backends.
5. **Function semantics:** left-to-right argument evaluation, no closures, arity is an
   error, missing `give` returns the type's zero value.
6. **A conformance definition:** exactly which programs the suite must run through every
   backend, so R5 cannot recur silently.
7. **An error catalog:** every code, its plain-English explanation, and a minimal
   triggering program. Elm's `error-message-catalog` is the model.

---

## 7. Realistic development roadmap

Sized for one person on an i3-10110U / 8 GB, in the order that removes risk fastest.
Not calendar-driven: each row is done when its acceptance test passes.

| Milestone | Work | Acceptance test |
|---|---|---|
| **M3.5 (done in this audit)** | Make the three backends agree on scope, loop variables and bool literals; kill cascading diagnostics | 69 tests green, including 5 new regressions |
| **M4.1 — one truth (done)** | Fix comparison precedence; call `analyze()` from `run`/`build`/`java`; golden corpus for diagnostic text; fix the analyzer crash on `when`; check `when`/`each` bodies | 79 tests green; `check`, `build` and `run` reject the same programs; `1 + 2 > 3` is false on all three backends |
| **M4.2 — typed IR** | `ir.py` carries types; `verify_ir()` checks operands and returns; backends consume IR, not parser dicts | IR verifier rejects a hand-built malformed node; all suites still green |
| **M4.3 — arrays everywhere** | `array<T>` in the type model; emit C arrays with bounds checks; emit Java arrays | conformance tests for literal/read/write/out-of-bounds on interpreter + C + Java |
| **M4.4 — initialization discipline** | Git repo; all suites run in one command; artifacts out of the source tree | `python run_tests.py` exits 0; `git status` clean after a build |
| **M5 — differential fuzzer** | Well-typed random program generator; compare interpreter vs C vs Java | ≥1,000 generated programs, zero disagreements, no compiler traceback |
| **M6 — performance baseline** | Add ATOMIC++ to `bench/`; measure this machine honestly; delete fabricated numbers from `BENCHMARK_PLAN.md` | a results table with real timings, compile times and binary sizes |
| **M7 — standard library seed** | `text` (length, slice, contains, split), `math` (abs, min, max, sqrt), `io` (read file, write file) with tests per backend | every function has a test on each backend that supports it |

Deferred until the above is real: records/structs, enums, generics, concurrency, GUI,
networking, package registry, LSP.

---

## 8. Benchmark strategy

The current plan cannot produce a valid ATOMIC++ number. Required changes:

1. **Add ATOMIC++ to `run_bench.py`** — one row compiled via `atomic.py build`, one
   interpreted. Today the harness benchmarks six languages and not this one.
2. **Delete the invented table** in `BENCHMARK_PLAN.md` (C++ 2.15 s, Python 372 s,
   "AMD Ryzen 5, 16 GB RAM"). It does not describe this machine, so it cannot describe
   this project's performance.
3. **Report four numbers per workload:** runtime (best of 5, min/median), compile time
   (front end vs gcc separately), binary size, and peak RSS.
4. **Correctness gate before timing:** the output checksum must match across languages or
   the row is reported as `DIFF`, never timed.
5. **Bring-your-own baseline:** `gcc -O2` is the honest comparison, because ATOMIC++ emits
   C and gcc does the optimizing. Any claim beyond "within a small factor of gcc -O2 on
   int/float workloads" is unsupported by this architecture.
6. **What is not measurable yet:** string, array, hash-map, JSON, networking, concurrency
   and startup-time benchmarks — the features do not exist. Say so instead of estimating.

---

## 9. Testing strategy

Current: 4 `unittest` files, 69 tests, differential where the backends overlap.
Target, in priority order:

1. **One runner** — `python run_tests.py` runs all suites and exits non-zero on any
   failure, so "all green" is one reproducible command.
2. **Golden diagnostics corpus** — `tests/diagnostics/<code>/*.atomic` plus the expected
   message, diffed like TypeScript baselines. Diagnostic text becomes reviewable.
3. **Per-backend conformance gate** — a table of language features × backends; a feature
   marked "supported" must have a differential test, and a missing test fails the gate.
   This is the structural fix for R5.
4. **Invalid-program fuzzer** — random byte/grammar mutations through the lexer and parser;
   the invariant is "a clean diagnostic, never a traceback". Cheap, purely Python.
5. **Well-typed program generator** — the Csmith/EMI model: generate only programs the
   type checker accepts, run all three backends, compare output. Needs M4.2 first.
6. **Optimizer differential mode** — once any pass exists, `-O0` vs `-O2` output must be
   identical (Alive2 / Crellvm lesson: the optimizer is where silent miscompiles live).
7. **Numeric edge matrix** — `INT64_MIN`, `INT64_MIN / -1`, overflow wrap, `0.1 + 0.2`,
   `nan`, `-0.0`, negative-zero printing, empty text, empty array. Partially covered today.

Rule to adopt, from LLVM/MSVC practice: **a bug is not fixed until a test reproduces it.**

---

## 10. The exact next milestone

**M4.1 — "one truth" — is complete** (see §11). The next milestone is **M4.2 — a typed IR
that the backends actually consume.**

Why this is next: `ir.py` today only relabels the parser's dictionary keys and is used by
nothing but the analyzer. Both code generators walk the parser AST directly, and the only
type model in the project is three C type-name strings inside `c_backend._infer`. That is
the structural reason a feature can mean different things in different backends (R2, R5),
and it is the blocker for arrays, records and any optimizer.

Work, in order:

1. **Give the IR real types.** A `Type` value (`int`, `float`, `text`, `bool`, `array<T>`,
   `fn(params) -> ret`) attached to every IR node, computed once by a shared pass.
2. **Write `verify_ir(program)`.** It rejects, with a diagnostic rather than a crash: an
   operator whose operand types are wrong, a `give` whose type does not match the function's
   return type, a call with the wrong arity, a branch into a nonexistent block, an unknown node.
3. **Make both backends read the IR**, not the parser output. `emit_c` then needs no
   `_infer` fixed-point loop of its own, which also removes the 15-iteration whole-program
   scan (R9).
4. **Test the verifier** with hand-built malformed nodes, one per rule.

Acceptance: `tests/test_ir.py` exercises the verifier; a deliberately malformed IR is
rejected with a clear message; every existing suite still green; generated C and Java for
all 8 examples is byte-identical to what M4.1 produced (no silent codegen drift).

Deliberately not in M4.2: arrays, records, generics, the optimizer, the standard library.
M4.3 (arrays) becomes a small, additive change once the type model exists.

---

## 11. Changes made during this audit

Five defects fixed, each with a regression test. No feature was removed.

| Defect | Symptom | Fix |
|---|---|---|
| C preamble used `ATOMIC_UNUSED` without defining it | every native build failed; 8/9 conformance tests errored | define the macro for GCC/non-GCC |
| Bool literals emitted Python's `True`/`False` into C | `when true:` produced C that would not compile | emit `1`/`0` |
| Interpreter assignments wrote to the global frame | a function's local `g` overwrote a global `g` (`5,5` vs native `5,0`) | `Env` frame class; functions write locally, read up to globals |
| Loop variables vanished after the loop in C/Java, and kept `end+1` there | `say i` after `each i from 5 to 7` gave an error in one backend, `7` in another, `8` in a third | hidden counter lowered to `i = start; for (h = i; h <= end; h++) { i = h; }` in both backends; interpreter binds the start value |
| Cascading diagnostic | `x = y + 1` reported both `invalid_operation` and `undefined_variable` | suppress the type error when an operand is undefined |

Also: C locals are now initialised to type defaults (an empty-range loop could otherwise
read uninitialised stack), and `LANGUAGE_SPEC.md` gained §4.1 (normative scope rules) and
§12 (known gaps) so the specification stops promising behaviour the code does not have.

Then, inside M4.1 (the next milestone, completed in the same session):

| Defect | Symptom | Fix |
|---|---|---|
| Comparisons bound tighter than arithmetic | `1 + 2 > 3` → `1`, `2 * 3 is 6` → `0`. Silent wrong answers on every backend. | moved `parse_comparison` above `parse_addsub`; 4 interpreter tests + conformance + Java tests pin each level |
| `ir.py` never imported `IR_WHEN` | `analyze()` raised `NameError` on **any program containing `when`**, so `check` crashed with a traceback instead of reporting — and no semantic test used `when`, so it was never caught | added the missing import |
| Analyzer skipped top-level `when`/`each` bodies | an undefined variable inside a top-level `when` was never reported | every non-function top-level statement is now checked |
| Analyzer reported every function local as undefined | `make f(a): b = a + 1` produced a false `undefined_variable` for `b` | assignment now defines the name; the expression is checked first, so read-before-write is still caught |
| Analyzer typed every call result as `none` | `x = f(x)` followed by `x + 1` produced a false `invalid_operation` | unknown return types default to `int`, as every backend does |
| Analyzer did not know loop variables | `x = x + i` inside `each i ...` reported `i` undefined | `each` adds its variable to the scope before checking the body |

Test total moved 53 green / 8 error → **79 green** (46 + 7 + 15 + 7 + 4).
