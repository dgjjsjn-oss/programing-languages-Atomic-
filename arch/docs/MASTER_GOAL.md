# ATOMIC++ MASTER GOAL -- "5x better than any language"

## 0. One-sentence goal
ATOMIC++ must be the language a beginner can use to build ANYTHING (games, apps,
servers, tools) while being faster, safer, simpler and better-tooled than Python,
C, C++, C#, Rust and Zig -- with no bugs and no security weaknesses.

## 1. "5x" is measured per axis, not as one number
Raw runtime cannot be 5x faster than optimised C on identical algorithms on the
same CPU -- that is physics (the machine already executes those instructions).
The 5x comes from five axes, each with a hard, testable target:

| Axis                | Target vs best-in-class            | How we prove it                          |
|---------------------|------------------------------------|------------------------------------------|
| Developer speed     | 5x faster to working program       | timed task suite (10 programs, novices)  |
| Compile speed       | 5x faster than C++ (clang -O2)     | hyperfine on 10k/100k LOC corpus          |
| Runtime (compute)   | 1.0-1.5x of hand-written C         | benchmarks: fib, nbody, mandelbrot, json  |
| Runtime (memory)    | 2-5x faster than GC languages      | allocation-heavy games/servers            |
| Safety              | 0 memory-safety CVEs by design     | fuzzing + sanitizers + type system        |

Being honest about row 3 is what makes rows 1,2,4,5 credible. Claiming "5x
faster than C at everything" would be a false claim and is forbidden by the
proof rule: we publish numbers, not adjectives.

## 2. Where the speed actually comes from (engineering plan)
1. No GC stop-the-world: ARC + arenas + optional cycle collector.
2. Bounds checks removed by static proof (range analysis on typed IR/SSA).
3. Auto-vectorisation + cache-aware struct layout in the optimiser.
4. Whole-program devirtualisation and monomorphised generics (no boxing).
5. Parallelism that is safe by default (structured concurrency), so game
   loops and servers scale across cores without data races.
6. Fast compile: single-pass frontend, incremental compilation, cached SSA.

## 3. Feature set required to "build anything"
Core language:  variables, arithmetic (int64 exact), bool, text, arrays,
records/structs, enums + pattern matching, generics, functions/closures,
modules, error handling, iterators, operator overloading (opt-in).
Memory:         value types, references, ARC, arenas, explicit unsafe block.
Concurrency:    structured tasks, channels, atomic types, parallelism.
I/O:            files, sockets, timers, process, paths.
Game stack:     2D/3D math, ECS, input, audio, asset pipeline, windowing, GPU.
App stack:      GUI widgets, layout, events, accessibility.
Server stack:   HTTP, JSON, routing, DB drivers, TLS.
Tooling:        formatter, LSP, debugger, profiler, package registry, docs,
                test runner, benchmark harness, cross-compilation, hot reload.
Interop:        C ABI FFI, call C libraries (SDL, Vulkan, SQLite) directly.
Security:       safe-by-default, no null, checked arithmetic by default,
                capability-based file/net access, signed packages, SBOM.

## 4. Architecture that delivers it
Lexer -> Parser -> AST -> Typed IR -> Semantic analysis -> SSA IR ->
Optimiser (const-fold, DCE, inline, range/escape analysis, vectorise) ->
Backend. Backends: C (now, portable), LLVM or Cranelift (later, peak codegen),
plus the tree-walking interpreter as the reference semantics for differential
testing. Runtime: ARC/arena library, bounds-check elision metadata, panic
handler, scheduler.

## 5. No bugs, no weaknesses -- the verification ladder
L1 unit tests per component (frontend: 100% branch coverage target)
L2 differential tests: interpreter output == native output on every feature
L3 random program fuzzer: generate valid programs, compare both engines
L4 invalid-program fuzzer: every malformed input must give a clean diagnostic,
   never a crash, never a Python traceback
L5 sanitizers: ASan/UBSan on all native builds in CI
L6 property tests: arithmetic overflow, division, string ops, array bounds
L7 optimiser translation validation: optimised IR must match unoptimised
L8 security review per release: FFI boundary, package signing, capability model
L9 regression corpus: every fixed bug becomes a permanent test

## 6. Milestones and acceptance criteria
M1 Frontend complete (done: lexer, parser, 34 tests)
M2 Typed IR + semantic analysis (done: ir.py, semantic.py, 6 tests)
M3 Integer semantics + conformance (done: 64-bit wrap, trunc div, 6 tests)
M4 Full language surface: structs, enums, generics, text, arrays in native
M5 Optimiser: SSA + const-fold + DCE + inlining + bounds elision
M6 Native backend beyond the int subset (strings, floats, arrays, modules)
M7 Standard library: text, collections, math, io, time, json
M8 Game + server demo built entirely in ATOMIC++, benchmarked vs C/C++/Rust
M9 Tooling: formatter, LSP, debugger, profiler, package registry
M10 Security hardening + fuzzing campaign + signed release

## 7. Current measured state (proof, not promises)
- 34 interpreter tests pass.
- 6 native conformance tests pass (interpreter == gcc-compiled C).
- 6 semantic-analyzer tests pass.
- C backend: ints, bools, comparisons, when, each, functions, recursion, say,
  division guard, 64-bit wrap, C-keyword-safe identifiers.
- Known gaps: no strings/floats/arrays/structs in the native backend yet, no
  optimiser, no stdlib, no game stack. These are the M4-M9 work.
