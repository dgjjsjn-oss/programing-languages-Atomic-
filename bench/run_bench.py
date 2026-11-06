#!/usr/bin/env python3
"""Cross-language benchmark runner: identical workload, same machine.

Workload: fib(27) recursive + 20M loop sum + 1M-element array fill/sum.
Measures: compile time, wall runtime (best of 3), source LOC, output correctness.
"""
import os
import subprocess
import time

BENCH = os.path.dirname(os.path.abspath(__file__))


def loc(path):
    n = 0
    for line in open(path, encoding="utf-8"):
        s = line.strip()
        if s and not s.startswith("//") and not s.startswith("#"):
            n += 1
    return n


def _resolve(cmd):
    exe = cmd[0]
    if exe.endswith(".exe") and not os.path.isabs(exe):
        return [os.path.join(BENCH, exe)] + list(cmd[1:])
    return cmd


def compile_cmd(cmd, runs=1):
    best = 1e9
    for _ in range(runs):
        t0 = time.perf_counter()
        r = subprocess.run(cmd, cwd=BENCH, capture_output=True, text=True)
        t1 = time.perf_counter()
        if r.returncode != 0:
            raise SystemExit("COMPILE FAIL " + " ".join(cmd) + "\n" + r.stderr)
        best = min(best, t1 - t0)
    return best


def run_cmd(cmd, runs=3):
    best = 1e9
    out = ""
    cmd = _resolve(cmd)
    for _ in range(runs):
        t0 = time.perf_counter()
        r = subprocess.run(cmd, cwd=BENCH, capture_output=True, text=True)
        t1 = time.perf_counter()
        if r.returncode != 0:
            raise SystemExit("RUN FAIL " + " ".join(cmd) + "\n" + r.stderr)
        out = r.stdout.strip()
        best = min(best, t1 - t0)
    return best, out


LANG = [
    ("C",      "bench.c",    ["gcc", "-O2", "-o", "bench_c.exe", "bench.c"],        ["bench_c.exe"]),
    ("C++",    "bench.cpp",  ["g++", "-O2", "-o", "bench_cpp.exe", "bench.cpp"],    ["bench_cpp.exe"]),
    ("Rust",   "bench.rs",   ["rustc", "-O", "-o", "bench_rs.exe", "bench.rs"],     ["bench_rs.exe"]),
    ("Java",   "Bench.java", ["javac", "Bench.java"],                               ["java", "-cp", ".", "Bench"]),
    ("Node",   "bench.js",   None,                                                  ["node", "bench.js"]),
    ("Python", "bench.py",   None,                                                  ["python", "bench.py"]),
]

rows = []
expected = None
for name, src, build, run in LANG:
    ct = compile_cmd(build, 3) if build else 0.0
    rt, out = run_cmd(run, 3)
    if expected is None:
        expected = out
    ok = "MATCH" if out == expected else "DIFF"
    rows.append((name, ct, rt, loc(os.path.join(BENCH, src)), ok))

rows.sort(key=lambda r: r[2])
base = rows[0][2]
print("")
print("LANGUAGE   COMPILE(s)  RUNTIME(s)  x_slower   LOC  OUTPUT")
print("-" * 60)
for name, ct, rt, lines, ok in rows:
    print(f"{name:<10} {ct:>9.3f}  {rt:>10.4f}  {rt/base:>8.1f}x  {lines:>4}  {ok}")
print("-" * 60)
print("workload: fib(27) + sum 1..20,000,000 + 1,000,000-element array")
print("runtime = best of 3 runs, wall clock, includes process startup")
