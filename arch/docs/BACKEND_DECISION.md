# ATOMIC++ Backend Decision

**Status:** Draft  
**Decision:** C-transpile backend for Phase 1 and Phase 2.

---

## 1. Constraint: Toolchain on This Machine

The development machine (`C:\Users\nasri\Desktop\ATOMIC ++`) has:

| Tool | Status |
|------|--------|
| `gcc` / `g++` (MinGW) | ✅ Installed |
| `python 3.13` | ✅ Installed |
| `node` / `npm` | ✅ Installed |
| `rustc` / `cargo` | ✅ Installed |
| `clang` | ❌ Not installed |
| `llvm` / `mlir` | ❌ Not installed |

Building LLVM from source requires hours, multiple gigabytes of disk, and complex C++ tooling. It is not practical for Phase 1.

---

## 2. Why C Generation

| Factor | C-transpile | LLVM backend |
|--------|-------------|--------------|
| Available on machine now | ✅ Yes (gcc) | ❌ No |
| Setup time | Minutes | Hours-days |
| Optimization level | `gcc -O3 -march=native` (excellent) | LLVM passes (slightly better in some cases) |
| Produces native `.exe` | ✅ Yes | ✅ Yes |
| Debuggable with standard tools | ✅ Yes (gdb) | ✅ Yes |
| Implementation complexity | Low | High |
| Proven by other languages | ✅ Nim (Python syntax → C → fast) | ✅ Rust, Swift, Clang |

**C-transpile is the pragmatic choice.** ATOMIC++ source is translated into equivalent C code, then `gcc -O3 -march=native` compiles it to a native Windows executable. This gives near-C++ speed without requiring LLVM.

---

## 3. What C Code Looks Like

ATOMIC++ source:
```atpp
start:
    say "Hello"
    x = 5 + 3
```

Emitted C (simplified):
```c
#include <stdio.h>
int main() {
    printf("Hello\n");
    int x = 5 + 3;
    return 0;
}
```

---

## 4. Future Backend Options

A future Phase may add an LLVM backend if:
- The project outgrows C-transpile optimizations.
- GPU code generation (NVPTX, SPIR-V) is needed.
- A contributor volunteers to build and maintain it.

The compiler architecture is designed so the frontend (lexer, parser, semantic analyzer, AST) is independent of the backend. Swapping from C-emitter to LLVM-emitter does not require redesigning the language.

---

## 5. Conclusion

**Phase 1-2 backend:** Transpile ATOMIC++ to C, compile with `gcc -O2` (default; `-O3` opt-in, `-march=native` opt-in for machine-specific builds).

**Justification:** Works on the development machine today, produces fast native executables, and keeps the implementation small enough to ship quickly.
