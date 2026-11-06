# ATOMIC++ Benchmark Plan

**Status:** Draft  
**Goal:** Reproducible, honest performance measurements.

---

## 1. Honesty Rule

Never claim a universal speed multiplier (e.g. "4× faster than C++"). C++, Rust, and ATOMIC++ all compile to native machine code running on the same CPU. The achievable target is matching C++ within 1–2× while offering simpler syntax and safer defaults.

Benchmarks measure specific workloads. Results are published with full methodology, including cases where ATOMIC++ is slower.

---

## 2. Benchmark Categories

| Category | What it measures | Example test |
|----------|-----------------|--------------|
| Microbenchmark | Raw algorithmic speed | n-body, fib(40), mandelbrot |
| Memory | Allocation and access patterns | Array creation, traversal |
| Concurrency | Thread/task performance | Parallel sum, message passing |
| Compile time | Time from source to `.exe` | Small program, medium program |
| Binary size | Size of produced executable | Hello World |
| Startup | Time from launch to first output | Hello World |

---

## 3. Reference Benchmarks (from Benchmarks Game)

| Test | C++ time | Python time | ATOMIC++ target |
|------|----------|-------------|-----------------|
| n-body | 2.15s | 372s | ~2–3s |
| mandelbrot | 0.89s | 183s | ~1–2s |
| fib(40) | ~1s | ~30s | ~1–2s |

These are measured on the actual development hardware, not copied from other machines.

---

## 4. Required Benchmark Metadata

Every benchmark result must record:

1. Source code of the benchmark (in ATOMIC++ and comparison languages)
2. Compiler versions (e.g. `gcc 13.2.0`, Python 3.13.x)
3. Compiler flags (e.g. `-O3 -march=native`)
4. Machine specifications (CPU, RAM, OS)
5. Test inputs and expected outputs (correctness check)
6. Number of repeated measurements (minimum 5 runs)
7. Memory usage (peak RSS)
8. Whether the test was interpreted or natively compiled

---

## 5. Methodology

1. Write the benchmark in ATOMIC++.
2. Write an equivalent benchmark in C++ (and Python for reference).
3. Compile ATOMIC++ to C with `gcc -O3 -march=native`.
4. Compile C++ with `g++ -O3 -march=native`.
5. Run each 5 times, record min/mean/max.
6. Verify outputs match exactly.
7. Publish results in a table with all metadata above.

---

## 6. Comparison Languages

| Language | Why included |
|----------|--------------|
| C++ | Raw speed baseline |
| Rust | Safety + speed baseline |
| Python | Interpreted baseline (shows compiled benefit) |
| ATOMIC++ (interpreted) | Shows interpreter overhead |
| ATOMIC++ (compiled) | Shows native speed |

---

## 7. Output Format

Results are stored in `tests/benchmarks/results.md` and updated after each phase. Example:

```
# Benchmark Results — Phase 1

| Test | ATOMIC++ (interp) | ATOMIC++ (compiled) | C++ | Python |
|------|-------------------|---------------------|-----|--------|
| fib(40) | 45.2s | 1.3s | 1.1s | 38.0s |

Machine: Windows 11, AMD Ryzen 5, 16 GB RAM
gcc version: 13.2.0
Date: 2026-11-04
```
