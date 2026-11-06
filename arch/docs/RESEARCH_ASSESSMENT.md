# ATOMIC++ initial research and performance assessment

**Snapshot:** 2026-11-06
**Scope:** repository audit, locally available toolchains, focused compiler-backend research, and a reproducible host-language smoke baseline. This is a first decision memo, not a survey claiming to cover every language or optimization family in the long-term brief.

## What the repository is today

ATOMIC++ is a small Python implementation with an indentation-sensitive lexer/parser, a typed structured IR, a verifier, an IR interpreter, and two source emitters: C compiled by GCC and Java compiled by `javac`. There is no native optimizer or machine-code backend owned by ATOMIC++; optimized native code currently depends on GCC. The Java target uses JVM compilation and execution. The typed IR is the right boundary to preserve while the grammar and backends grow.

The current full runner passed **101 tests** and **30 example commands across 8 examples** on this snapshot. The only skipped example comparison is `variables.atpp`: C emits a 17-significant-digit round-trip spelling for `3.14` (`3.1400000000000001`), while Python and Java choose a shorter spelling (`3.14`). This alone does not show the stored binary64 values differ.

The current implementation now has cross-backend short-circuit boolean operations, scalar fixed-length arrays, bounds checks, array length, and a built-in imported `math` namespace. General source-file modules are not implemented. Arrays cannot be nested or passed as function parameters. Floating-point arithmetic is still rejected by the checked frontend, despite backend-level operations, so the language does not yet have a complete numeric contract.

## Main engineering bottlenecks

1. **Correctness and semantics:** parser, IR builder, interpreter and emitters still need differential edge-case tests. Float operation admission and output formatting are not yet one settled contract. The verifier has structured control flow but no CFG.
2. **Type inference:** unannotated function parameters currently default to integer, which blocks sound generic calls and array parameters. This is a semantic limitation before it is a backend optimization problem.
3. **Code generation:** emitted C and Java are hand-built strings. GCC/HotSpot can optimize target code, but ATOMIC++ does not expose rich optimization metadata, and there is no optimizer IR, CFG, SSA, profile data, or alias/escape analysis.
4. **Runtime/data model:** arrays now work, but the language still lacks a complete ownership, string, aggregate, error, and FFI model. C array allocations are tracked and freed at process exit; other backends rely on managed runtimes.
5. **Benchmark evidence:** the pre-existing benchmark omitted ATOMIC++, chose only the best of three runs, and treated the first language's output as its oracle. It was not evidence of ATOMIC++ speed. The runner now uses five runs and a fixed output oracle, but remains a host-toolchain smoke test with a fixed-input workload; it does not measure ATOMIC++.

## Local environment and constraints

Observed from this Windows 11 host:

| Tool or resource | Observation |
|---|---|
| Python | 3.13.14 |
| GCC / G++ | MinGW-W64 GCC 16.1.0 |
| Rust | rustc 1.99.1; Cargo is available |
| Java | OpenJDK / javac 21.0.12 |
| Node | v24.18.0 |
| Clang, `opt`, QBE, Wasmtime | Not found on PATH |
| CMake / Ninja | Available |
| Logical processors | 4 reported by Python |
| Free space on C: | about 2.69 GB at inspection time |

The user-provided target-machine description is an Intel Core i3-10110U with 8 GB RAM. Windows exposed only a generic `Intel64 Family 6 Model 142` processor string, and CIM hardware queries were denied, so the exact CPU/RAM report could not be independently verified in this session. No external hardware results are presented as local measurements.

LLVM's official Getting Started guide estimates an LLVM-only build at roughly 1–3 GB and a full LLVM plus Clang build at 15–20 GB, varying by configuration. With only about 2.69 GB free and no Clang installed, building LLVM now would consume most of the remaining storage and is not a responsible next step. Source: [LLVM build requirements](https://llvm.org/docs/GettingStarted.html).

## Targeted technology research and decision

| Technology | What it offers | ATOMIC++ assessment now |
|---|---|---|
| GCC through generated C | Mature optimizing compiler, ABI/linker/toolchain integration, installed and already used by the project. GCC documents broad `-O2` optimization including inlining, interprocedural passes, vectorization and scheduling; exact enabled passes vary by target/version. | **Keep for the release/native path now.** It is the highest-confidence route to useful native code without adding a large dependency. Measure generated ATOMIC++ programs before claiming its output quality. Source: [GCC optimization options](https://gcc.gnu.org/onlinedocs/gcc/Optimize-Options.html). |
| LLVM | Reusable target-independent code generation, optimization passes, native and JIT facilities, wide ecosystem. LLVM documents instruction selection, scheduling, register allocation and code emission stages. | **Re-evaluate later, do not install/build now.** It could become a direct native backend if measured C-emitter limits justify its integration and storage cost. An LLVM rewrite is not justified by current benchmarks. Sources: [LLVM code generator](https://llvm.org/docs/CodeGenerator.html), [LLVM build requirements](https://llvm.org/docs/GettingStarted.html). |
| Cranelift | Retargetable code generator with x86-64, AArch64, s390x and RISC-V backends; Wasmtime reports broad fuzzing/differential validation and focuses on fast code generation. Its own project describes API stability as not yet guaranteed and positions Rust debug builds as a key fit. | **Strong candidate for a later fast-development/JIT experiment**, not a default release-backend replacement. It is a Rust/Cargo dependency and would add integration/build surface. Its speed/code-quality trade-offs need ATOMIC++-specific measurements. Sources: [Cranelift status and targets](https://github.com/bytecodealliance/wasmtime/blob/main/cranelift/README.md), [Cranelift goals in rustc](https://github.com/bytecodealliance/wasmtime/blob/main/cranelift/rustc.md). |
| QBE | Deliberately small compiler backend with a compact SSA-like IL and a small set of architecture backends. Its repository currently lists AMD64 and ARM64 targets. | **Possible small prototype**, especially to compare compile time and implementation burden. It is less suitable than GCC/LLVM if broad target coverage is the immediate goal. Sources: [QBE IL](https://c9x.me/compile/doc/il-v1.0.html), [QBE implementation/targets](https://github.com/8l/qbe). |
| MLIR | Extensible multi-level IR with dialects and progressive lowering; designed to preserve high-level loop, tensor, vector, GPU and target abstractions longer than a low-level IR. | **Do not adopt yet.** It is attractive for future tensor/GPU compilation, but ATOMIC++ has not yet stabilized scalar semantics, modules, or array types. Introducing its dialect ecosystem now would add complexity before a demonstrated need. Sources: [MLIR rationale](https://mlir.llvm.org/docs/Rationale/Rationale/), [MLIR language reference](https://mlir.llvm.org/docs/LangRef/). |
| LLVM ORC JIT | Modular JIT linking, eager/lazy compilation, concurrency, symbol dependency tracking and removable code. | **Future option** if an interactive run loop or long-lived application needs JIT behavior. It is not needed to fix current compile/run semantics. Source: [LLVM ORC design](https://llvm.org/docs/ORCv2.html). |
| Rust, C++, Java, Node, Python | Useful comparison ecosystems already installed. Rust/C++ can provide optimized native baselines; Java and Node include managed-runtime/JIT startup behavior; Python gives an interpreted baseline. | Compare by workload and mode. No language-level winner can be inferred from one synthetic benchmark or one machine. |

The language survey in the long-term prompt is intentionally staged. Fortran, Ada, D, Nim, Swift, Go, C#, OCaml, Julia, PyPy, Mojo, Carbon, Chapel, WebAssembly engines, and GPU infrastructures should be compared when a specific workload or feature makes them relevant. A broad feature-by-feature essay before the language can express representative workloads would not answer the performance question with evidence.

## Reproducible host baseline (not an ATOMIC++ result)

Command: `python bench/run_bench.py` from the repository root. Source is in `bench/`. Each language computes recursive `fib(27)`, the sum from 1 through 20,000,000, and a one-million-element integer array sum. The runner performs five compile invocations where applicable and five process launches, validates each result against `196418`, `200000010000000`, and `999999000000`, and reports min/median/max. Compile settings: GCC/G++ `-O2`, Rust `-O`, Java 21 default `javac` plus JVM launch; Node and Python execute source directly. Runtime includes process startup. Peak memory was not measured. Caches, antivirus effects and machine-load outliers are not controlled. The benchmark does not include ATOMIC++ and its constant workload may be simplified by optimizing compilers, so use it as a harness/host smoke check, not a performance ranking.

| Language | Compile median [min,max] s | Runtime min / median / max s |
|---|---:|---:|
| C | 1.622 [1.248, 2.196] | 0.0665 / 0.0841 / 0.2458 |
| C++ | 3.745 [3.529, 4.917] | 0.1239 / 0.1752 / 0.4231 |
| Rust | 3.073 [2.146, 5.711] | 0.0655 / 0.0760 / 1.9124 |
| Java | 1.749 [1.695, 2.184] | 0.2137 / 0.2572 / 0.2843 |
| Node | n/a | 0.2722 / 0.2843 / 0.7498 |
| Python | n/a | 4.6555 / 4.9698 / 5.7542 |

Version snapshot: GCC/G++ 16.1.0, rustc 1.99.1, javac/OpenJDK 21.0.12, Node 24.18.0, Python 3.13.14. Every run returned the fixed expected output. Rust's 1.9124-second maximum illustrates why the distribution is more informative than a single best run. No speed claim about ATOMIC++ follows from this table.

## Most realistic route to high performance

1. Make the language's integer, float, bool, text, array, call, error and module rules normative and differentially tested.
2. Replace implicit parameter defaults with explicit/inferred function signatures; improve diagnostics and eliminate backend-specific semantic inference.
3. Add measurements for ATOMIC++ interpreter, generated C/GCC, and Java on equivalent non-constant workloads. Record compile stages, startup, memory and distributions.
4. Profile generated code before adding optimization. Start with low-risk constant folding and dead-code elimination only if profiles show a real bottleneck; keep transformations validated against interpreter semantics.
5. Add a CFG/SSA layer only when a concrete optimization needs it. The current structured tree is easier to validate for the present feature set.
6. Prototype an alternate backend only after there are representative programs and a stable runtime/ABI. Cranelift is the best candidate to test for fast development builds; GCC remains the economical AOT backend; LLVM/MLIR remain conditional on demonstrated multi-target, JIT, tensor or GPU needs.

## First experiments

- Add a same-source conformance generator that runs programs through interpreter, C, and Java, with deterministic seeds and saved failing examples.
- Create representative ATOMIC++ benchmarks once the language has enough input/I/O facilities to prevent constant-folding the whole workload. Include arithmetic, loops, calls, arrays and strings separately; add optimized C++/Rust equivalents and verify outputs.
- Measure compiler front-end/lowering time, C emission, GCC time, JVM compile time and process startup separately. Add peak-memory measurement on Windows without adding dependencies.
- Compare generated C with equivalent hand-written C under identical GCC flags; this isolates emitter/code-shape overhead from the target compiler.
- Prototype a tiny backend comparison only after the workload exists: GCC-through-C vs QBE or Cranelift, tracking compilation time, execution time, binary size, target support and integration cost.

## Evidence classification

- **Established techniques:** optimizing AOT compilers, SSA, code generation, JITs, and multi-level IR are established. This project does not yet implement a CFG/SSA optimizer.
- **Adaptation:** using GCC as the current ATOMIC++ native optimizer and considering Cranelift for fast development builds are evidence-informed adaptations, not new inventions.
- **Original hypotheses:** ATOMIC++-specific compiler pipelines, memory layouts, and cost models remain hypotheses until prototype measurements and correctness tests support them.
