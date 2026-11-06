# ATOMIC++ Language Specification (Initial Draft)

**Status:** Draft — Phase 1 prototype  
**File extension:** `.atpp`  
**Entry point:** `start:` block  
**Interpreter and native compiler must implement identical rules.**

---

## 1. Design Goals (for beginners)

- A 10-year-old who has never coded should be able to read and write ATOMIC++.
- Keywords are ordinary English words: `say`, `make`, `when`, `each`, `use`, `give`, `start`, `stop`.
- No semicolons. No curly braces. Indentation shows structure.
- Safe by default: bounds-checked arrays, no null references, automatic memory cleanup.
- Compiles to native machine code via C (Phase 2), runs fast enough for games and tools.

---

## 2. Lexical Structure

### 2.1 Comments
A comment starts with `//` and runs to the end of the line.

```atpp
// This is a comment
```

### 2.2 Identifiers
Identifiers start with a letter or underscore, followed by letters, digits, or underscores.  
Examples: `x`, `player_hp`, `_temp`, `count2`.

### 2.3 Keywords (reserved)

| Keyword | Meaning |
|---------|---------|
| `start` | Program entry point |
| `stop`  | End program execution |
| `say`   | Print to output |
| `make`  | Define a function |
| `use`   | Import a module |
| `when`  | Conditional (if) |
| `each`  | Loop / iteration |
| `give`  | Return from a function |
| `true`  | Boolean true |
| `false` | Boolean false |

### 2.4 Literals

| Type | Example |
|------|---------|
| Integer | `0`, `42`, `-7` |
| Float | `3.14`, `-0.5` |
| String | `"hello"`, `"ATOMIC++"` |
| Boolean | `true`, `false` |

### 2.5 Operators

| Operator | Meaning |
|----------|---------|
| `+` | Addition / string concatenation |
| `-` | Subtraction / negation |
| `*` | Multiplication |
| `/` | Division |
| `is` | Equality comparison |
| `is not` | Inequality comparison |
| `<` | Less than |
| `>` | Greater than |
| `<=` | Less than or equal |
| `>=` | Greater than or equal |

---

## 3. Program Structure

Every ATOMIC++ program must contain exactly one `start:` block. Execution begins at the first statement inside `start:`.

```atpp
start:
    say "Hello, ATOMIC++"
    stop
```

---

## 4. Variables

Variables are created by assignment. The type is inferred from the value.

```atpp
start:
    hp = 100
    score = 0
    name = "Player"
    pi = 3.14
    alive = true
```

The *intent* is that a name keeps one type. The current implementation does **not**
enforce this (see §12 Known gaps), so the rule is not yet normative.

### 4.1 Names, scope and assignment (normative)

These rules are enforced identically by the interpreter, the C backend and the Java
backend. `tests/test_conformance.py` and `tests/test_java_backend.py` hold them in
place; changing a rule here means changing a test.

1. **Names are function-scoped.** There is no block scope. A `when` or `each` body
   does not open a new scope.
2. **Assignment mutates the existing name; it never shadows it.**

       start:
           x = 1
           when true:
               x = 2
           say x          // prints 2

3. **A function body cannot modify a caller's or a global variable by assignment.**
   Assigning a name inside a function always updates that function's frame, so a
   function's locals never leak out:

       make bump(a):
           g = a + 1     // a *local* g, even if a global g exists
           give g
       start:
           g = 0
           say bump(4)   // 5
           say g         // 0

   A function may still *read* globals.
4. **Loop variables persist after the loop**, holding the last value assigned. If the
   range is empty the name still exists and holds the start value.
5. **Iteration is independent of the body.** Assigning to the loop variable inside the
   body does not change how many times the loop runs or which values it takes.
6. **Functions are top-level.** Nested function definitions and closures are not
   supported by any backend; a nested `make` does not capture the enclosing locals.
7. **No cascading diagnostics.** One root cause produces exactly one diagnostic.

---

## 5. Functions

Functions are defined with `make` and return values with `give`.

```atpp
make add(a, b):
    give a + b

start:
    say add(3, 4)
```

Functions without a `give` statement return nothing.

---

## 6. Conditions

```atpp
start:
    hp = 100
    when hp is 0:
        say "Game Over"
        stop
    when hp < 50:
        say "Low health"
```

An `else` branch is not required in Phase 1.

---

## 7. Loops

```atpp
start:
    each i from 0 to 5:
        say i
```

This loops `i` from 0 up to and including 5. Both bounds are inclusive.

The loop variable is bound before the first iteration and keeps its last value
afterwards (§4.1 rules 4-5), so `each i from 5 to 7` leaves `i` equal to `7` and
`each i from 5 to 3` leaves `i` equal to `5`.

---

## 8. Collections (Arrays)

The current implementation supports fixed-length mutable arrays of `int`,
`float`, `bool`, and `text`, created with a literal. An empty literal defaults
to `int[]`. Nested arrays, array comparison, and arrays as function parameters
are rejected by semantic analysis.

```atpp
start:
    scores = [10, 20, 30]
    say scores[0]
```

Array access and assignment are bounds-checked. `len(array)` returns its fixed
element count. Array variables are references: assigning or passing an array
value aliases its elements (array parameters are not yet supported). The C
backend copies literal elements into tracked allocations and frees those
allocations when the process exits; Java and the interpreter use managed arrays.

---

## 9. Modules

```atpp
use math
start:
    say math.add(2, 3)
```

Current supported scope: `use math` imports the built-in namespace with exported
`add`, `sub`, and `mul` operations. Calls without the import are rejected.
User-authored modules, visibility declarations, file resolution, and circular
dependency detection are not implemented yet.

---

## 10. Error Handling

Phase 1: runtime errors (division by zero, out-of-bounds array access, undefined variable) print a message with the source line and stop the program.

Compiler diagnostics follow two rules:

- **No cascading.** An undefined name used inside an expression reports
  `undefined_variable` only, never also `invalid_operation`.
- **Every diagnostic has a stable code** (`undefined_variable`, `undefined_function`,
  `invalid_operation`, `invalid_call`, `invalid_return`) and a `line:column` pointing at
  the smallest span that identifies the problem. Codes are part of the interface and are
  covered by tests.

Future phases: `Result` type and explicit error handling.

---

## 11. Example Program

```atpp
// fib.atpp — compute Fibonacci numbers

make fib(n):
    when n is 0:
        give 0
    when n is 1:
        give 1
    give fib(n - 1) + fib(n - 2)

start:
    say fib(10)
    stop
```

Expected output:
```
55
```

---

## 12. Known gaps between this specification and the implementation

This section exists so the specification never describes a feature the code does not
have. Each entry is a bug or a missing feature, not a design decision.

| Gap | Actual behaviour today |
|-----|------------------------|
| Float output formatting | C uses 17-significant-digit round-trip formatting; the interpreter and Java use shorter decimal output. Values are binary64, and comparison of formatted strings does not prove a numeric mismatch. |
| Arrays | Fixed-length mutable scalar arrays (int/float/bool/text) are supported in all engines. Empty literals default to int arrays. Nested arrays and array function parameters are not supported. |
| Modules | `use math` and `math.add/sub/mul` work consistently. User modules, exports, cross-file resolution, and cycle detection await a module loader. |
| Logical boolean operators | `not`, `and`, and `or` are supported with short-circuit evaluation. |
| "A name keeps one type" (§4) | Not enforced anywhere. |
| Semantic analysis of types | The analyzer knows only four coarse types (`int`, `float`, `string`, `array`), types every function parameter as `int`, and cannot see inside arrays or modules. It catches undefined names and arity errors, not type errors. |

## 13. Conformance Rule

The Phase 1 Python interpreter and the Phase 2 C-transpile compiler must produce identical output for every valid program in the shared subset. Automated conformance tests enforce this.
