# ATOMIC++ Architecture — Compiler Design

**Status:** Draft — Phase 1 prototype  
**Target:** Windows machine with `gcc`/`g++` (MinGW) available, no LLVM installed.

---

## 1. Two Execution Paths

ATOMIC++ has two ways to run a `.atpp` file:

| Mode | Command | What happens | Speed | Use case |
|------|---------|-------------|-------|----------|
| Interpreted | `atomic++ run file.atpp` | Python interpreter executes the AST directly | Python speed | Learning, quick scripts |
| Compiled | `atomic++ build file.atpp` | Transpile to C → `gcc -O3` → native `.exe` | Near C++ | Games, tools, production |

Both paths must accept the same source code and produce the same output.

---

## 2. Compiler Pipeline

```
SOURCE CODE (.atpp text)
        │
        ▼
┌───────────────┐
│   LEXER       │  Chops text into tokens (keywords, numbers, strings, symbols)
└───────────────┘
        │
        ▼
┌───────────────┐
│   PARSER      │  Arranges tokens into an Abstract Syntax Tree (AST)
└───────────────┘
        │
        ▼
┌───────────────┐
│ SEMANTIC      │  Type checking, variable resolution, bounds-check setup
│   ANALYZER    │
└───────────────┘
        │
        ▼
      ┌───────┐
      │  AST  │  Intermediate representation (tree of program structure)
      └───────┘
        │        ├──────────────┐
        ▼        ▼              ▼
┌───────────────┐  ┌─────────────────────┐
│ INTERPRETER   │  │ C CODE EMITTER      │  (Phase 2)
│   (Phase 1)   │  │ walks AST, emits C  │
└───────────────┘  └─────────────────────┘
        │                     │
        ▼                     ▼
   Runs directly         gcc -O3 -march=native
                      compiles C → .exe
```

---

## 3. Components

### 3.1 Lexer
Converts raw text into a stream of tokens. Handles:
- Keywords (`start`, `stop`, `say`, `make`, `use`, `when`, `each`, `give`, `true`, `false`)
- Identifiers
- Integer and float literals
- String literals
- Operators (`+`, `-`, `*`, `/`, `is`, `is not`, `<`, `>`, `<=`, `>=`)
- Comments (`//`)

### 3.2 Parser
Builds an AST from tokens. Uses recursive descent (simple, readable, beginner-friendly). Produces nodes for:
- Program (list of statements)
- Function definition
- Variable assignment
- If / when statement
- Each / loop statement
- Binary expression
- Print statement
- Return (give) statement
- Array literal and index access

### 3.3 Semantic Analyzer
Walks the AST and checks:
- Variables are defined before use
- Types match (no adding a string to an integer without explicit conversion)
- Array indices are within bounds (where statically knowable)
- Functions return the declared type

### 3.4 Interpreter (Phase 1)
Tree-walking interpreter written in Python. Executes the AST directly:
- Maintains an environment (variable → value mapping)
- Evaluates expressions bottom-up
- Executes statements top-down
- Reports errors with source line numbers

### 3.5 C Code Emitter (Phase 2)
Walks the same AST and emits equivalent C code:
- Variables → C variables with inferred types
- Functions → C functions
- Loops → C `for` loops
- Conditions → C `if` statements
- Arrays → C arrays with bounds checks
- Output → `printf` calls

The emitted C is then compiled with `gcc -O3 -march=native` to produce a native `.exe`.

---

## 4. AST Node Types (Phase 1)

```
Program
  └─ statements: [Statement]

Statement
  ├─ VarAssign(name, value)
  ├─ FunctionDef(name, params, body)
  ├─ When(condition, then_body)
  ├─ Each(variable, start, end, body)
  ├─ Say(expression)
  ├─ Give(expression)
  └─ Stop

Expression
  ├─ IntegerLiteral(value)
  ├─ FloatLiteral(value)
  ├─ StringLiteral(value)
  ├─ BooleanLiteral(value)
  ├─ Variable(name)
  ├─ BinaryOp(left, op, right)
  ├─ Call(name, args)
  └─ ArrayIndex(array, index)
```

---

## 5. Design Decisions (recorded)

| Decision | Rationale |
|----------|-----------|
| Tree-walking interpreter in Python | Runs immediately; no compilation step needed for Phase 1 |
| C-transpile backend (not LLVM) | `gcc` is installed; LLVM is not. Building LLVM takes hours. C-transpile is the proven Nim playbook. |
| Recursive descent parser | Simple to understand, easy to debug, beginner-friendly |
| Indentation-based structure | No braces/semicolons; easier for beginners to read |
| ARC memory (planned Phase 2) | Automatic cleanup, no GC pauses, simpler than Rust borrow checker |

---

## 6. Conformance

The interpreter and C emitter must accept the same grammar. A shared test suite runs every `.atpp` example through both paths and compares output.
