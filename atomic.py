#!/usr/bin/env python3
#
# Copyright (c) 2026 ATOMIC++ Project Contributors / Project Owner
#
# All rights reserved.
#
# This repository and its contents are publicly available for viewing and
# educational reference only.
#
# No permission is granted to copy, modify, distribute, sublicense, sell,
# or commercially exploit any portion of this project without prior written
# permission from the copyright holder.
#
# The copyright holder reserves all rights to the source code, project
# architecture, documentation, designs, and original materials, subject to
# applicable law and third-party licenses.
#
# This notice does not override the licenses of third-party components
# included in or used by this project.
#

"""ATOMIC++ command line.

Usage:
    python atomic.py run   file.atomic          interpret
    python atomic.py build file.atomic          compile to native (C + gcc)
    python atomic.py java  file.atomic          compile to .java (JVM, Minecraft)
    python atomic.py check file.atomic          semantic analysis only
    python atomic.py c     file.atomic          print generated C

Options:
    --out NAME      output binary name (build)
    --class NAME    Java class name (java, default AtomicMain)
    --O3            opt-in -O3 for build
    --native        opt-in -march=native for build
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(HERE, "build")
sys.path.insert(0, os.path.join(HERE, "vertical_slice"))

from interpreter import AtomicError, Interpreter, parse, tokenize  # noqa: E402
from ir import build_ir                                            # noqa: E402


def usage():
    print(__doc__)
    return 2


def report(path, diags):
    """Print analyzer diagnostics and return the process exit code."""
    for d in diags:
        print(f"{path}:{d['line']}:{d['col']}: {d['code']}: {d['message']}")
    print(f"{len(diags)} problem(s)")
    return 1


def checked_program(path, src):
    """Build the typed IR once and share it with checking and execution/codegen."""
    program = build_ir(parse(tokenize(src)))
    if program.diagnostics:
        report(path, program.diagnostics)
        return None
    return program


def main(argv):
    if len(argv) < 3:
        return usage()
    cmd, path = argv[1], argv[2]
    flags = argv[3:]
    if not os.path.exists(path):
        print(f"atomic: file not found: {path}")
        return 1
    src = open(path, encoding="utf-8-sig").read()

    try:
        if cmd == "run":
            program = checked_program(path, src)
            if program is None:
                return 1
            for line in Interpreter().run(program):
                print(line)
            return 0

        if cmd == "check":
            diags = build_ir(parse(tokenize(src))).diagnostics
            for d in diags:
                print(f"{path}:{d['line']}:{d['col']}: {d['code']}: {d['message']}")
            print(f"{len(diags)} problem(s)")
            return 1 if diags else 0

        if cmd == "c":
            program = checked_program(path, src)
            if program is None:
                return 1
            from c_backend import emit_c
            print(emit_c(program))
            return 0

        if cmd == "build":
            program = checked_program(path, src)
            if program is None:
                return 1
            from c_backend import compile_c, emit_c
            out = None
            if "--out" in flags:
                out = flags[flags.index("--out") + 1]
            if out is None:
                out = os.path.join(BUILD_DIR, os.path.basename(os.path.splitext(path)[0]) + ".exe")
            out = os.path.abspath(out)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            c_src = emit_c(program)
            compile_c(c_src, out,
                      portable="--native" not in flags,
                      march_native="--native" in flags,
                      optimization="-O3" if "--O3" in flags else "-O2")
            print(f"built: {out}")
            r = subprocess.run([out], capture_output=True, text=True)
            sys.stdout.write(r.stdout)
            if r.returncode != 0:
                sys.stderr.write(r.stderr)
                return r.returncode
            return 0

        if cmd == "java":
            program = checked_program(path, src)
            if program is None:
                return 1
            from java_backend import compile_java, emit_java
            cls = flags[flags.index("--class") + 1] if "--class" in flags else "AtomicMain"
            out_dir = os.path.join(BUILD_DIR, "java")
            os.makedirs(out_dir, exist_ok=True)
            java_src = emit_java(program, cls)
            compile_java(java_src, out_dir, cls)
            print(f"java: {os.path.join(out_dir, cls)}.java")
            r = subprocess.run(["cmd", "/c", "java", "-cp", out_dir, cls], capture_output=True, text=True)
            sys.stdout.write(r.stdout)
            if r.returncode != 0:
                sys.stderr.write(r.stderr)
                return r.returncode
            return 0

        return usage()
    except AtomicError as e:
        print(f"atomic error: {e}")
        return 1
    except SyntaxError as e:
        print(f"syntax error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
