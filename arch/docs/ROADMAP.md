# ATOMIC++ Roadmap

**Status:** Draft  
**Principles:** No feature is claimed complete until implemented and tested. No universal speed promises. Free forever.

---

## Phase 1 — Language Prototype & Introductory Examples

**Goal:** A working Python-based interpreter that runs a small subset of ATOMIC++ syntax.

### Deliverables
- Lexer: keywords, identifiers, literals, operators, comments
- Parser: recursive descent, builds AST
- Semantic analyzer: variable-before-use, type mismatch detection
- Interpreter: tree-walking execution with line-numbered errors
- REPL or `atomic++ run file.atpp`
- Built-in `say`, `make`, `when`, `each`, `give`, `start`, `stop`
- Integer, float, string, boolean types
- Arrays with bounds checking
- Vertical slice test suite (see below)

### Acceptance Tests
1. `hello.atpp` prints "Hello, ATOMIC++"
2. `variables.atpp` assigns and reads variables of all types
3. `conditions.atpp` uses `when` correctly
4. `loops.atpp` uses `each` correctly
5. `functions.atpp` defines and calls functions with `give`
6. `arrays.atpp` creates arrays and accesses elements
7. `bounds.atpp` out-of-bounds access produces a clear error, not a crash
8. `undefined.atpp` using an undefined variable produces a clear error
9. `div_zero.atpp` division by zero produces a clear error
10. Interpreter and (future) compiler produce identical output on shared subset

### Duration
Estimated: 1–2 weeks (part-time)

---

## Phase 2 — Native Compilation Workflow

**Goal:** Transpile `.atpp` to C, compile with `gcc -O3 -march=native`, produce `.exe`.

### Deliverables
- C code emitter (walks AST, emits C)
- Build driver: `atomic++ build file.atpp`
- Runtime library (ARC memory, bounds checks, I/O)
- `atomic++ run` still works for interpreted mode
- Command-line demos: calculator, file organizer, text search

### Acceptance Tests
1. Compiled `hello.atpp` produces `hello.exe` and runs
2. Compiled output matches interpreted output exactly
3. `gcc -O3 -march=native` flags applied
4. Conformance test: 10 shared-subset programs pass both paths

### Duration
Estimated: 3–4 weeks

---

## Phase 3 — Standard Library, Testing, Tooling

**Goal:** Batteries included but lean.

### Deliverables
- Standard library: math, strings, files, threads, collections
- Unit test runner (`atomic++ test`)
- Formatter (`atomic++ fmt`)
- Linter (`atomic++ lint`)
- Project templates (`atomic++ new my_app`)
- Diagnostics: clear error messages with source locations

### Acceptance Tests
1. All standard library functions have unit tests
2. Formatter produces stable output
3. Linter catches common mistakes (unused variables, shadowing)
4. `atomic++ new` generates a compilable project

### Duration
Estimated: 4–6 weeks

---

## Phase 4 — Documentation, Packages, Editor Support

**Goal:** Learn and share without cost.

### Deliverables
- Official documentation (`docs/`)
- Beginner tutorial ("The ATOMIC++ Book")
- Package manager (`atomic++ add <package>`, `atomic++ build`)
- Language Server Protocol (LSP) for editor completion/diagnostics
- Debugger integration (gdb)
- Offline-capable examples

### Acceptance Tests
1. Tutorial examples all run successfully
2. Package manager installs a local package
3. LSP provides completions in VS Code (tested)
4. All demos run offline

### Duration
Estimated: 6–8 weeks

---

## Phase 5 — Graphics, Games, Graphics Interop

**Goal:** ATOMIC++ can be used for games and graphical applications.

### Deliverables
- OpenGL/DirectX bindings via C FFI
- 2D window example
- Simple game with movement and collision
- Graphics performance demonstration
- Clear distinction: language vs. graphics library

### Acceptance Tests
1. A window opens and renders a frame
2. Keyboard input moves an object
3. Game loop runs at 60 FPS on test hardware

### Duration
Estimated: 8–10 weeks

---

## Phase 6 — Advanced Optimization, Concurrency, AI, Cross-Platform

**Goal:** Production-ready systems language.

### Deliverables
- Async/await and lightweight tasks
- Channels and locks for safe concurrency
- SIMD and auto-vectorization hints
- Cross-compilation (Windows → Linux/macOS)
- Local AI model inference example (using free libraries)
- LLVM backend evaluation (optional)

### Acceptance Tests
1. Parallel sum benchmark scales with CPU cores
2. No data races detected in safe concurrency code
3. Cross-compiled binary runs on target platform
4. AI example runs offline with a small local model

### Duration
Estimated: 10–14 weeks

---

## Vertical Slice (Immediate)

Before Phase 1 is considered complete, build a fully tested vertical slice:

- `vertical_slice/interpreter.py` — minimal interpreter
- `vertical_slice/examples/` — 5 working `.atpp` files
- `tests/test_interpreter.py` — automated tests for all examples
- All tests pass

**Definition of done:** Every example runs, every test passes, every error case produces a clear message.
