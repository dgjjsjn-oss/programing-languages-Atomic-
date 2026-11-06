#!/usr/bin/env python3
"""Reproducible host-language baseline; this is not an ATOMIC++ benchmark yet.

Workload: recursive fib(27), sum 1..20,000,000, and a 1,000,000-element array.
Reports five-run timing distributions and validates against a fixed expected result.
"""
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time

BENCH = os.path.dirname(os.path.abspath(__file__))
REPEATS = 5
EXPECTED = "196418\n200000010000000\n999999000000"


def loc(path):
    with open(path, encoding="utf-8-sig") as source:
        return sum(1 for line in source
                   if line.strip() and not line.lstrip().startswith(("//", "#")))


def resolve(cmd):
    exe = cmd[0]
    if exe.endswith(".exe") and not os.path.isabs(exe):
        return [os.path.join(BENCH, exe)] + list(cmd[1:])
    return cmd


def _resolve_cmd(cmd):
    """Resolve bare tool names through PATHEXT so CreateProcess finds them."""
    path = shutil.which(cmd[0])
    if path is None:
        raise SystemExit(f"toolchain not found: {cmd[0]}")
    return [path] + cmd[1:]


def measure_compile(cmd):
    cmd = _resolve_cmd(cmd)
    times = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        result = subprocess.run(cmd, cwd=BENCH, capture_output=True, text=True)
        times.append(time.perf_counter() - start)
        if result.returncode:
            raise SystemExit("COMPILE FAIL " + " ".join(cmd) + "\n" + result.stderr)
    return times


def measure_run(cmd):
    times = []
    output = None
    command = resolve(cmd)
    command = _resolve_cmd(command)
    for _ in range(REPEATS):
        start = time.perf_counter()
        result = subprocess.run(command, cwd=BENCH, capture_output=True, text=True)
        times.append(time.perf_counter() - start)
        if result.returncode:
            raise SystemExit("RUN FAIL " + " ".join(command) + "\n" + result.stderr)
        current = result.stdout.strip()
        if output is None:
            output = current
        elif current != output:
            raise SystemExit("NONDETERMINISTIC OUTPUT " + " ".join(command))
    if output != EXPECTED:
        raise SystemExit(f"WRONG OUTPUT {command!r}: {output!r} != {EXPECTED!r}")
    return times


LANG = [
    ("C", "bench.c", ["gcc", "-O2", "-o", "bench_c.exe", "bench.c"], ["bench_c.exe"]),
    ("C++", "bench.cpp", ["g++", "-O2", "-o", "bench_cpp.exe", "bench.cpp"], ["bench_cpp.exe"]),
    ("Rust", "bench.rs", ["rustc", "-O", "-o", "bench_rs.exe", "bench.rs"], ["bench_rs.exe"]),
    ("Java", "Bench.java", ["javac", "Bench.java"], ["java", "-cp", ".", "Bench"]),
    ("Node", "bench.js", None, ["node", "bench.js"]),
    ("Python", "bench.py", None, [sys.executable, "bench.py"]),
]

rows = []
for name, source, build, run in LANG:
    try:
        compile_times = measure_compile(build) if build else []
        run_times = measure_run(run)
        rows.append((name, compile_times, run_times, loc(os.path.join(BENCH, source)), None))
    except SystemExit as exc:
        rows.append((name, [], [], loc(os.path.join(BENCH, source)), str(exc)))

c_row = next((r for r in rows if r[0] == "C" and r[4] is None and r[2]), None)
base = statistics.median(c_row[2]) if c_row else None
rows.sort(key=lambda row: statistics.median(row[2]) if row[2] else float("inf"))
print(f"Host: {platform.platform()} | {platform.machine()} | {platform.processor()} | CPUs={os.cpu_count()}")
for command in ("gcc", "g++", "rustc", "javac", "java", "node"):
    resolved = shutil.which(command)
    result = subprocess.run([resolved, "--version"], capture_output=True, text=True) if resolved else None
    version = ((result.stdout or result.stderr).splitlines()[0]
               if result is not None and result.returncode == 0 else "unavailable")
    print(f"{command}: {version}")
print(f"Repeats: {REPEATS}; runtime includes process startup; compiler/JIT caches are not controlled.")
print("ATOMIC++ is not included: the existing files provide no equivalent language workload.")
print("")
print("LANG       COMPILE median [min,max] s      RUN min / median / max s       x slower  LOC")
print("-" * 92)
for name, compile_times, run_times, lines, error in rows:
    comp = (f"{statistics.median(compile_times):.3f} "
            f"[{min(compile_times):.3f},{max(compile_times):.3f}]") if compile_times else "n/a"
    if error:
        print(f"{name:<9} {'n/a':>26}  UNAVAILABLE: {error.splitlines()[0]}                      {lines:>3}")
        continue
    ratio = f"{statistics.median(run_times) / base:>8.1f}x" if base else "     n/a"
    print(f"{name:<9} {comp:>26}  {min(run_times):.4f} / {statistics.median(run_times):.4f} / {max(run_times):.4f}"
          f"  {ratio}  {lines:>3}")
print("-" * 92)
print("workload: fib(27) + sum 1..20,000,000 + 1,000,000-element array; output checked against a fixed oracle")
