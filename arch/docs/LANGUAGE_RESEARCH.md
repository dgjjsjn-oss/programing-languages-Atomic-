# LANGUAGE RESEARCH — what real language projects actually do

**Purpose:** every design decision in ATOMIC++ should be traceable to evidence, not taste.
This document studies the projects that already solved these problems, records what they
did, and states what ATOMIC++ should copy and what it should refuse to copy.

**Method:** primary sources only where possible — official dev guides, release notes,
design RFCs, conference papers. Claims I could not verify against a primary source are
marked **(unverified)**. Every claim carries a source at the end.

---

## 0. Summary: the ten findings that matter for ATOMIC++

| # | Finding | Source projects | Consequence for ATOMIC++ |
|---|---------|-----------------|--------------------------|
| 1 | Self-hosting is a bootstrap tax, not a virtue | Go, Rust, Zig, TypeScript | Do **not** self-host now. Python stays the implementation language. |
| 2 | LLVM is a compile-time tax; C-transpile is a legitimate long-term choice | Go (rejected LLVM), Zig (removing it) | Keep the C backend. Do not adopt LLVM. |
| 3 | A mid-level IR is what makes checking and optimizing possible | Rust (MIR), Zig (AIR) | Promote `ir.py` from an AST copy into a real typed IR, with a verifier. |
| 4 | Differential testing finds real compiler bugs without an oracle | Csmith, EMI, rustc | Turn the conformance suite into a random-program fuzzer. Highest value per hour. |
| 5 | Every bug must become a permanent test | LLVM, MSVC, GCC | Adopt as a hard project rule; keep a regression corpus. |
| 6 | Error messages are a language feature, and cheap to improve | Elm, Rust | Build a diagnostics catalog + a golden-output corpus. This is the beginner moat. |
| 7 | Reference counting is not free and does not collect cycles | Swift, ISMM'12, PLDI'22 | Do not promise ARC safety. Value semantics first; RC much later, if ever. |
| 8 | Incremental compilation is expensive to retrofit | rustc (queries retrofitted), Zig | Whole-program compilation. No query system until measurement demands it. |
| 9 | Feature minimalism is a maintenance strategy | Go | Small orthogonal core; libraries carry the breadth. |
| 10 | Source compatibility is a promise you must make early | Go 1, Swift | Write the compatibility policy **before** v1.0, not after. |

---

## 1. RUST — the reference architecture for a typed compiler

### 1.1 Pipeline

rustc is **not** organised as a sequence of passes. That is a deliberate architectural
choice made to enable incremental compilation.

```
invocation → lexer (rustc_lexer) → parser (rustc_parse) → AST (rustc_ast)
  → HIR  (rustc_hir)      desugared, still untyped
  → type inference / trait solving / typeck (on HIR; produces Ty<'tcx>)
  → THIR                  fully typed, used for pattern + exhaustiveness checks
  → MIR  (rustc_mir_build) CFG-based, no nested expressions, all types explicit
  → borrow check + dataflow (rustc_borrowck, on MIR)
  → MIR optimizations (rustc_mir_transform)
  → monomorphization collection
  → codegen MIR → LLVM IR → LLVM → object → link
```

`rustc_middle` is the "main crate": it owns `hir`, `thir`, `mir` (the *definition*), `ty`
(including `TyCtxt`/`tcx`, "the central context during most of compilation") and
`dep_graph`.
Source: <https://rustc-dev-guide.rust-lang.org/overview.html>

### 1.2 Why MIR exists — the single most transferable lesson

MIR was introduced by **RFC 1211** (2015). The RFC's own summary:

> Introduce a "mid-level IR" (MIR) into the compiler. The MIR desugars most of Rust's
> surface representation, leaving a simpler form that is well-suited to type-checking and
> translation.

The motivation explicitly cites features "almost infeasible to implement today but which
should be much easier given a MIR representation", including **non-lexical lifetimes**.
Source: <https://rust-lang.github.io/rfcs/1211-mir.html>

Niko Matsakis, announcing MIR: a "vastly simplified version of Rust — MIR — standing in
the middle", whose goals were Rust-specific optimizations before LLVM, non-zeroing drop,
and **"more precise type checking"** — MIR "will enable much more flexible borrowing"
because the old restrictions "stemmed from how the compiler represented programs."
Source: <https://blog.rust-lang.org/2016/04/19/MIR>

The dev guide states the design rule directly:

> The borrow checker operates on the MIR. An older implementation operated on the HIR.
> [...] the MIR is far less complex than HIR; the radical desugaring helps prevent bugs in
> the borrow checker [...] Even more importantly, using the MIR enables "non-lexical
> lifetimes", which are regions derived from control-flow graph.

Source: <https://rustc-dev-guide.rust-lang.org/borrow-check.html>

The MIR query chain is itself a clean model of staged IR construction, each step a
checkpoint: `mir_built` → `mir_promoted` (ready for borrow check) →
`mir_drops_elaborated_and_const_checked` (borrow check runs here, ready for optimization)
→ `optimized_mir` / `mir_for_ctfe`.
Source: <https://rustc-dev-guide.rust-lang.org/mir/passes.html>

### 1.3 Incremental compilation: the red-green algorithm

Queries are demand-driven; dependencies are discovered **at run time**, recorded as a
query DAG. After a run, the compiler saves the DAG plus result hashes. "Red" means the
result changed versus the previous run; "green" means it did not.

Two insights make it work:

1. If all inputs to Q are green, Q must produce the same value — do not re-run it.
2. Even with changed inputs, Q may still produce the same output. So after executing, always
   hash the result; Q can still be marked green.

`try-mark-green` is the core algorithm; it must demand the colour of each dependency **in
the original read order**, because a red subquery can change control flow and would
otherwise execute queries that should not run (causing ICEs).

Importantly, the results themselves are usually **not** cached to disk — only hashes.
Serializing cheap-to-recompute results "is not a particular win".
Sources: <https://rustc-dev-guide.rust-lang.org/queries/incremental-compilation.html>,
<https://rustc-dev-guide.rust-lang.org/queries/incremental-compilation-in-detail.html>

One nuance often repeated incorrectly: **Salsa is not used by rustc.** The dev guide says
Salsa is "inspired by (among other things) rustc's query system" but "**not** used directly
in rustc", with "no medium or long-term concrete plans to integrate it into the compiler."
Salsa is used in rust-analyzer, chalk, and Mun.
Source: <https://rustc-dev-guide.rust-lang.org/queries/salsa.html>

**Was retrofitting it hard?** Yes, and they say so: "the compiler wasn't originally built to
use a query system; the query system has been retrofitted into the compiler, so parts of it
are not query-fied yet." As of Nov 2022 only the steps between HIR and LLVM IR are
query-fied — not lexing, parsing, name resolution, macro expansion, or LLVM.
Source: <https://rustc-dev-guide.rust-lang.org/overview.html>

**Measured benefit** (community benchmark thread, 2017, large crates): full rebuild
3:11 → 2:29, while touching a file went 30.1s → 1.9s and a small change 30.2s → 2.2s
(~15×). Treat as indicative, not authoritative — it is a forum thread.
Source: <https://internals.rust-lang.org/t/help-us-benchmark-incremental-compilation/6153>

### 1.4 Compile time: the cost of all this

Rust's own project goal admits the shape of the problem: compiler speed rose "roughly 3x"
over 2016–2023, driven by "profile-driven incremental work", and that is now
"diminishing returns" — plus the new trait solver and Polonius "currently cause significant
compile-time regressions".
Source: <https://goals.rust-lang.org/2026/compiler-performance-optimization.html>

Background-2023: mean reductions of 13% compile time, 15% peak memory, 7% binary size,
with the admission "There is no low-hanging fruit remaining."
Parallel front-end (`-Z threads=8`): single-threaded parallel front-end is typically 0–2%
**slower** than serial (machinery cost); multi-threaded "up to 50%".
Source: <https://blog.rust-lang.org/2023/11/09/parallel-rustc/>

Monomorphization — the price of generics without boxing: "fast programs, but it comes at the
cost of compile time [...] and binary size."
Source: <https://rustc-dev-guide.rust-lang.org/backend/monomorph.html>

### 1.5 Testing stack

- **compiletest** — "the main test harness of the Rust test suite", many thousands of tests
  in suites (`ui`, `run-make`, `codegen`, `pretty`, ...), configured by `//@` directive
  comments. Directives are inline metadata in the test file itself — no external config.
  <https://rustc-dev-guide.rust-lang.org/tests/compiletest.html>
- **Crater** — compiles and tests every crate on crates.io to detect ecosystem breakage.
  A check run takes "~3–4 days", build-and-test "5–6 days"; Linux x86_64 only; not part of
  CI; it "executes malicious code" so it must be sandboxed.
  <https://rustc-dev-guide.rust-lang.org/tests/crater.html>, <https://github.com/rust-lang/crater>
- **Fuzzing** — defined in the dev guide as "any testing methodology that involves
  compiling a wide variety of programs in an attempt to uncover bugs in rustc", aimed
  primarily at **ICEs**. Practical advice worth stealing: avoid generating machine code
  (`--emit=mir`), and use `-Zvalidate-mir`.
  <https://rustc-dev-guide.rust-lang.org/fuzzing.html>
- **rustc-perf** — benchmarks after every merged PR, plus on-demand perf runs comparing two
  commit hashes. <https://rustc-dev-guide.rust-lang.org/tests/perf.html>

### 1.6 Error messages as policy

The dev guide's diagnostics chapter is effectively a style guide. Verbatim rules:

> Write in plain simple English. If your message, when shown on a – possibly small – screen
> (which hasn't been cleaned for a while), cannot be understood by a normal programmer, who
> just came out of bed after a night partying, it's too complex.

> Error, Warning, Note, and Help messages start with a lowercase letter and do not end with
> punctuation.

> When emitting a message with span, try to reduce the span to the smallest amount possible
> that still signifies the issue.

> Try not to emit multiple error messages for the same error.

> Rust's learning curve is rather steep, and the compiler messages are an important learning
> tool.

And on error codes: "We generally try to assign each error message a unique code like
`E0123` [...] **All error codes have an associated explanation: new error codes must
include them**." Explanations, governed by RFC 1567, "should help users understand why their
code cannot be accepted", not hand out copy-paste fixes. Messages are structured
(`#[derive(Diagnostic)]`) and localizable via Fluent.
Sources: <https://rustc-dev-guide.rust-lang.org/diagnostics.html>,
<https://rustc-dev-guide.rust-lang.org/diagnostics/error-codes.html>

### 1.7 What ATOMIC++ should copy / avoid

**Copy:** the IR ladder (syntax → typed IR → mid-level IR), the "one checkpoint query per
stage" mental model, compiletest's inline-directive design, the diagnostics style guide, the
error-code-with-explanation rule, per-PR perf gating.

**Avoid:** retrofitting a query system; monomorphizing generics before there is profiling
data; parallel compilation as a first move.

---

## 2. GO — the minimalism and bootstrap playbook

### 2.1 Why no LLVM

From the official FAQ, on the compiler technology:

> At the beginning of the project we considered using LLVM for `gc` but decided it was too
> large and slow to meet our performance goals. More important in retrospect, starting with
> LLVM would have made it harder to introduce some of the ABI and related changes, such as
> stack management, that Go requires but are not part of the standard C setup.

> `Gc` is written in Go with a recursive descent parser and uses a custom loader, also
> written in Go but based on the Plan 9 loader, to generate ELF/Mach-O/PE binaries.

Source: <https://go.dev/doc/faq>

That second quote is the whole backend strategy in one sentence: parse by hand, emit your own
object format, skip the framework. It is exactly the position ATOMIC++ is in with
emit-C + gcc.

### 2.2 Why Go compiles fast

The official claim is qualitative — "it should take at most a few seconds to build a large
executable on a single computer" — and the *reason*, per Rob Pike's *Go at Google*, is
dependency management: the compiler reads export data from object files, which he calls
"the biggest reason Go compiles are faster than C or C++ compiles".
Sources: <https://go.dev/doc/faq>, <https://go.dev/talks/2012/splash.article>

There is also a language-design angle, which matters more for ATOMIC++:

> the language has been designed to be easy to analyze and can be parsed without a symbol
> table. This makes it much easier to build tools such as debuggers, dependency analyzers
> [...] and IDE plug-ins.

> It is a key design decision of Go that parsing be possible without type information.

Source: <https://go.dev/doc/faq>

ATOMIC++ currently violates this: `start:` blocks and indentation mean the parser needs no
symbol table, which is good — but `parse()` hard-requires exactly one `start:` block and a
terminal `stop`, so it is not a general tree-sitter-friendly grammar yet.

### 2.3 Shared type checker between compiler and tools

`go/types` is "the data types and implements the algorithms for type-checking of Go
packages"; imports are decoupled behind `Config.Importer`, "relieving the type checker from"
I/O and build-system concerns. The compiler does not literally import it — there is
`types2`, "a port of `go/types` to use the syntax package's AST instead of `go/ast`" — and
crucially the two **share tests**: "the go/types package [...] and
cmd/compile/internal/types2 have shared tests in src/internal/types/testdata, and both type
checkers should be checked if anything changes there."
Sources: <https://pkg.go.dev/go/types>,
<https://go.dev/src/cmd/compile/README>

That shared-testdata trick is a direct answer to ATOMIC++'s problem of keeping
`semantic.py`, the interpreter, and two backends honest.

### 2.4 Bootstrapping history — the machine-translated compiler

The original compiler was in C because "of the difficulties of bootstrapping—you'd need a Go
compiler to set up a Go environment", and it started as yacc/bison over a Plan 9 C compiler.
In Go 1.5 it became Go by **automatic translation**:

> Most important, the compiler was actually moved by automatic translation of the C code into
> Go. It is in effect the same program in a different language. It is not a new
> implementation of the compiler so we expect the process will not have introduced new
> compiler bugs.

> It was a genuine (machine assisted) translation [...] The automatic translation [...]
> resulted in unidiomatic Go code that performs poorly compared to well-written Go.

Sources: <https://go.dev/doc/go1.5>, <https://golang.google.cn/talks/2010/gofrontend-gcc-summit-2010.pdf>

Today `dist` does build-current-with-previous: build `cmd/dist` with an older Go, build the
1.x toolchain and `go_bootstrap` with that, then "rebuild Go 1.x compiler toolchain with
itself", then the rest of the stdlib with `go_bootstrap`. Installing from source lists four
bootstrap options, including "Compile a toolchain from Go 1.4, the last Go release with a
compiler written in C."
Sources: <https://go.dev/src/cmd/dist/README>, <https://go.dev/doc/install/source>

**Lesson:** a language that is serious about self-hosting must maintain a bootstrap chain
forever, and the transition itself is best done by mechanical translation, not a rewrite.

### 2.5 Compatibility as a promise

> It is intended that programs written to the Go 1 specification will continue to compile and
> run correctly, unchanged, over the lifetime of that specification [...] programs that work
> today should continue to work even as future "point" releases of Go 1 arise.

> Compatibility is at the source level. Binary compatibility for compiled packages is not
> guaranteed.

Performance is explicitly outside the promise.
Source: <https://go.dev/doc/go1compat>

### 2.6 Feature minimalism, in their own words

> Every language contains novel features and omits someone's favorite feature. Go was designed
> with an eye on felicity of programming, speed of compilation, orthogonality of concepts [...]
> Your favorite feature may be missing because it doesn't fit, because it affects compilation
> speed or clarity of design, or because it would make the fundamental system model too
> difficult.

Source: <https://go.dev/doc/faq>

Rob Pike, *Less is exponentially more*: Go starts from "C, fix some obvious flaws, remove
crud, add a few missing features"; Go is for people who "don't want to care about a language
that has so much less. Even if, in the end, it offers so much more."
Source: <https://commandcenter.blogspot.com/2012/06/less-is-exponentially-more.html>

Rob Pike, *Simplicity is Complicated*: "Adding features to Go would not make it better, just
bigger. That would make Go less interesting by being less different." / "Of course, there
must be some features. But which ones? The right ones!"
Source: <https://go.dev/talks/2015/simplicity-is-complicated.slide>

Rob Pike, *Go at Google*: "Go's purpose is therefore not to do research into programming
language design; it is to improve the working environment for its designers and their
coworkers. Go is more about software engineering than programming language research."

Russ Cox, *Experiment, Simplify, Ship*: "A third way we simplify is by removing
functionality when it has turned out to be less useful or less important than we expected."
Sources: <https://go.dev/talks/2012/splash.article>, <https://go.dev/blog/experiment>

### 2.7 Testing

- `go test` recompiles each package with `*_test.go` files; as part of building the test
  binary it "runs go vet on the package and its test source files [...] If go vet finds any
  problems, go test reports those and does not run the test binary." A directory named
  `testdata` is always ignored, reserved for fixtures.
- The top-level `test` dir holds black-box/regression/error-output tests;
  `cmd/dist test` drives `go test std cmd`.
- `cmd/go` uses txtar "script" tests.
Sources: <https://pkg.go.dev/cmd/go/internal/test>, <https://go.googlesource.com/go/+/refs/heads/master/test/README.md>

### 2.8 gopls

Built on shared packages (`go/packages`, `go/types`, `go/analysis`), not a separate
implementation. The design doc's motivation is latency: "each tool will no longer have to
individually run the type-checker on each invocation, instead there will be a long-running"
server. The unit that type-checks is the **package**, while the editor's unit is the
**file**, so gopls maps files→packages and tracks transitive dependents.
Sources: <https://go.dev/gopls/design/design>,
<https://go.dev/gopls/design/implementation>

### 2.9 What ATOMIC++ should copy / avoid

**Copy:** no LLVM; hand-written recursive descent; parse without type information; one
shared type checker feeding compiler, linter and language server; a written compatibility
promise before 1.0; "remove it when it turns out not to matter".

**Avoid:** treating minimalism as an excuse to skip the standard library. Go ships a large
batteried stdlib *precisely because* the language is small. ATOMIC++'s promise is "build
anything"; that breadth has to live in libraries.

---

## 3. ZIG — the cautionary tale about rewriting

### 3.1 Pipeline and IRs

Source bytes → tokens → AST → **ZIR** → **AIR** → MIR → machine code.

`AstGen` produces ZIR, "the last untyped IR": a complete ZIR file can be turned into AIR and
machine code "without any memory access into the AST tree token list, node list, or source
bytes." AIR is "produced by Sema and consumed by codegen. Unlike ZIR where there is one
instance for an entire source file, **each function gets its own `Air` instance**."
Sema is lazy, starting from the entry point and analysing only referenced declarations —
which is why some errors only appear when a declaration is used.
Sources: <https://github.com/ziglang/zig/blob/master/lib/std/zig/Zir.zig>,
<https://github.com/ziglang/zig/blob/master/src/Air.zig>, <https://mitchellh.com/zig/sema>

### 3.2 Incremental compilation without a query engine

Zig's design (Matthew Lugg) is a useful alternative model to rustc's:

- Granularity is an **`AnalUnit`** — one function or one container-level declaration.
- During analysis each unit **registers dependency edges**. On update, those edges decide
  what to re-analyse. Units are up-to-date / outdated / "potentially outdated" (PO), with a
  PO-dependency counter that promotes units as soon as their last PO dependee resolves.
- Work is bounded by a non-incremental build; it may over-analyse but **never analyses the
  same unit twice**.
- The early pipeline is **not** incremental: "At the start of an update, parsing and `AstGen`
  are run over every changed file, as a whole", then an old→new ZIR index mapping is built.
- The **`InternPool`** is immutable-by-Index — values never change meaning, so an outdated
  type is simply recreated at a new Index instead of generating a dependency per type query.
  Explicit trade: a little extra work for a much simpler system.

Source: <https://gist.github.com/mlugg/73b3e60c803006f3556d87c9ed3e8a0e>

Status: opt-in with `zig build -fincremental --watch`; long experimental, then in 0.16
"usable with both the self-hosted ELF linker and the LLVM Backend", where reworking type
resolution so "the compiler's internal dependency graph acyclic" meant changes "previously
recompiled almost the entire compiler now complete in milliseconds."
Source: <https://ziglang.org/download/0.16.0/release-notes.html>

### 3.3 LLVM was 70% of compile time

> In the early days, Zig was but a thin frontend in front of LLVM. This was instrumental for
> getting started quickly [...] Now, the training wheels [...] are coming off, and LLVM is
> transitioning into an optional component.

LLVM was **≥70% of total compile time** even in Debug. The replacement plan is self-hosted
backends plus **in-place binary patching** (granularity = top-level declarations, PIE code
with a GOT for calls — deliberately coupled frontend/backend design) and eventually hot code
swapping.
Source: <https://kristoff.it/blog/zig-new-relationship-llvm/>

Progress: in 0.15.x the self-hosted x86_64 backend became the default in Debug, and "the Zig
core team have been building the Zig compiler almost exclusively with the self-hosted x86
backend instead of LLVM, **cutting the build from 1–2 minutes to a few seconds**."
Also: Zig emits LLVM **bitcode** directly rather than linking libLLVM, "part of our efforts
toward entirely eliminating the LLVM dependency".
Sources: <https://ziglang.org/download/0.15.1/release-notes.html>,
<https://ziglang.org/download/0.14.0/release-notes.html>

### 3.4 comptime: generics without special syntax

> The Zig compiler is, in effect, an interpreter for Zig itself.

A generic container is "a function that returns a `type`":

```zig
fn List(comptime T: type) type {
    return struct { items: []T, len: usize };
}
```

No preprocessor, no macros, no template dialect; "Zig uses comptime capabilities to
implement generic data structures without introducing any special-case syntax." Loris Cro's
argument against macros: they are "brittle because they basically are programs that
manipulate the syntax of your source code [...] Things lose some of their semantic meaning
and just become tokens"; comptime "use[s] the language itself to manipulate part of the
language in a more semantic way."
Sources: <https://ziglang.org/learn/overview>,
<https://stackoverflow.blog/2023/10/02/no-surprises-on-any-system-q-and-a-with-loris-cro-of-zig>

### 3.5 No hidden control flow, no hidden allocation

> There is **no hidden control flow**, no hidden memory allocations, no preprocessor, and no
> macros. If Zig code doesn't look like it's jumping away to call a function, then it isn't.

Hidden control flow examples cited: D `@property`, operator overloading in C++/D/Rust,
exceptions in C++/D/Go. Allocation is the library's problem, not the language's: "There is no
`new` keyword or any other language feature that uses a heap allocator [...] The entire
concept of the heap is managed by library and application code." Allocating stdlib functions
take an `Allocator` parameter.
Source: <https://ziglang.org/learn/why_zig_rust_d_cpp>

On errors, Andrew Kelley: "We do not have warnings. Only errors" — and the compiler should do
more than compile (built-in formatter, unused-variable errors).
Source: <https://gotopia.tech/articles/233/zig-programming-language-and-linters>

### 3.6 Package management: no central registry

Loris Cro, 2022: the package manager "will be part of the compiler instead of being a
separate executable"; it "**will not assume the presence of a central package index. We don't
plan to create an official package index**"; version resolution "similar to Go's Minimal
Version Selection".
Source: <https://kristoff.it/blog/zig-self-hosted-now-what/>

The security model is in `build.zig.zon`: each dependency provides `url` **and** `hash`, and
"**This field is the source of truth; packages do not come from a url; they come from a
hash. url is just one of many possible mirrors**". From the original proposal: "Dependencies
are even stricter than version locking - they are source-locked [...] even a compromised
third party provider cannot compromise your build."
Sources: <https://github.com/ziglang/zig/blob/master/doc/build.zig.zon.md>,
<https://github.com/ziglang/zig/issues/943>

### 3.7 The rewrite toll — read this before starting a big refactor

On the self-hosted compiler, Kelley said they "knew perfectly well that rewrites are really,
really hard and we chose to pay this price now in order to invest in better foundations for
the future. A two year slowdown is nothing compared to the increased productivity that the
new codebase will afford us." The cost: bug fixes "put on hold since fixing the bootstrap
compiler was ultimately useless", and accepted proposals "piling up because it would have
required implementing everything twice." His own comment: "Sooooooooo much time was sunk
into the self-hosted compiler."

In the same interview he describes how the compiler itself was actually developed: "it was
definitely incremental and I've been developing it open source since the very beginning. It
was very rare that there was a big un-merged branch."
Sources: <https://kristoff.it/blog/zig-self-hosted-now-what/>,
<https://sourcegraph.com/blog/zig-programming-language-revisiting-design-approach>

### 3.8 What ATOMIC++ should copy / avoid

**Copy:** typed-then-lowered IRs where each function gets its own unit; declared
"no hidden control flow"; allocation passed explicitly; hash-as-source-of-truth dependencies;
"only errors, never warnings"; the *practice* of small always-mergeable commits.

**Avoid:** the multi-year rewrite. ATOMIC++ is at v0.5 with three working engines; a
ground-up replatform is how projects die. Fix and extend in place.

---

## 4. CPYTHON — what a non-self-hosted implementation costs and buys

### 4.1 Pipeline

```
tokenize (Parser/tokenizer.c)
  → parse tokens to AST (PEG parser since 3.9; Grammar/python.gram)
  → symbol table + CFG → code object (Python/compile.c)
  → _PyEval_EvalFrameDefault() eval loop (Python/ceval.c)
```

AST node kinds are defined in ASDL (`Parser/Python.asdl`) with generated C (`asdl_c.py`). The
eval loop is a `switch` **generated** from `Python/bytecodes.c`, using computed gotos where
available. The 3.9 PEG parser "generates an AST directly without creating a parse tree."
Sources: <https://github.com/python/cpython/blob/main/InternalDocs/compiler.md>,
<https://github.com/python/cpython/blob/main/InternalDocs/interpreter.md>

### 4.2 The specializing adaptive interpreter (PEP 659)

3.11+ uses *quickening*: adaptive instructions carry a counter and specialize when it hits
zero, with inline data-cache entries holding cached type/version data; specialization is
local and cheap to undo. Result: 3.11 ≈25% faster than 3.10 on pyperformance.
Sources: <https://peps.python.org/pep-0659>, <https://docs.python.org/3/whatsnew/3.11.html>

This is the single best argument for a *tree-walking interpreter as reference semantics*: the
fast path can be bolted on later without changing the language.

### 4.3 The cost of the C API

PEP 620 (Victor Stinner) states the mechanism: while implementation details are exposed
through the C API, "evolution of CPython internals would be less limited by C API backward
compatibility issues" — hiding them would make radical optimizations like tagged pointers
possible. The API is tiered (public / Limited API + Stable ABI / internal in
`Include/internal/` behind `Py_BUILD_CORE`), with PEP 387 deprecation periods and a promise
that the Stable ABI never breaks.
Sources: <https://peps.python.org/pep-0620>,
<https://devguide.python.org/developer-workflow/c-api/>

### 4.4 Process

Language changes go through PEPs with a core-team sponsor; PEP 1 names the Steering Council
as accepting authority. Continuous integration is **buildbots**: dedicated machines that
checkout, compile Python, and "Run the test suite using strenuous settings".
Fuzzing is via OSS-Fuzz (`cpython3` with targets in `Modules/_xxtestfuzz/`, plus
`python3-libraries`) with CIFuzz wiring so PRs touching a module trigger its fuzzers; Atheris
is the Python-side fuzzer.
Sources: <https://devguide.python.org/developer-workflow/lang-changes/>,
<https://devguide.python.org/testing/buildbots/>, <https://devguide.python.org/testing/oss-fuzz/>

### 4.5 What ATOMIC++ should copy

The **AST → CFG → bytecode** staging, and the idea that the interpreter's fast path is a
separate concern from the language. Also: `testdata`-style split between unit tests and
error-output tests, and OSS-Fuzz-style continuous fuzzing of the *parser* (ATOMIC++'s
"invalid program must never traceback" rule is exactly a fuzz target).

---

## 5. TYPESCRIPT — self-hosting, and abandoning it

### 5.1 Pipeline

Scanner (tokens + trivia) → parser (`SourceFile`-rooted syntax tree) → **binder** (creates
symbols; "the first part of the type checking process") → **checker** ("a 40k line function
which does a huge amount of work") → emitter (a chain of transformers: ESNext, ES2020 …
ES2015, then print). Layering: core compiler → Language Service → tsserver.
The checker is deliberately lazy: "it does not calculate any information until it is
required", and a new checker is created per language-service request because creation is
cheap.
Sources: <https://github.com/microsoft/TypeScript-Compiler-Notes/blob/main/intro/README.md>,
<https://github.com/microsoft/TypeScript/wiki/Architectural-Overview>,
<https://github.com/microsoft/TypeScript/wiki/Compiler-Internals>

### 5.2 Bootstrapping

> TypeScript is built in TypeScript. The compiler uses a "last known good" version of the
> TypeScript to bootstrap, you can find this version in `/lib`.

Each release's `tsc` is produced by the previously shipped `tsc`. Microsoft's 2025 note on
the native port observes the consequence: the compiler "runs on Node.js, which means it
requires a JavaScript runtime to execute", and self-hosting "creates a bootstrapping
problem".
Sources: <https://github.com/microsoft/TypeScript-Compiler-Notes/blob/main/intro/README.md>,
<https://devblogs.microsoft.com/typescript/typescript-native-port/>

**The 2025–26 development:** TypeScript 7.0 is a **Go port** (there is a `go.work` at the
repo root); 6.0 was the last TypeScript-based release. Microsoft's announcement claims
roughly 10× native performance gains. This is the most recent large-scale evidence that
*picking your implementation language for compiler performance later* is a legitimate,
if expensive, move.
Sources: <https://github.com/microsoft/TypeScript>,
<https://devblogs.microsoft.com/typescript/typescript-native-port/>

### 5.3 Baselines: the testing idea worth stealing outright

Three test systems: **Baselines** ("file-based snapshot tests, each test verifies the
compiler's output based on an input file", with `// @target: es5`-style directives),
**Fourslash** (language-service tests), and unit tests. `gulp runtests` runs them, `gulp diff`
reviews the changes, `gulp baseline-accept` accepts them.

The conformance discipline is stated on the wiki: keep a test in `tests/cases/conformance`,
"verify that the baseline agrees with the spec", and open/reopen bugs when a baseline
diverges from the spec.
Sources: <https://github.com/microsoft/TypeScript-Compiler-Notes/blob/main/intro/README.md>,
<https://github.com/microsoft/TypeScript/wiki/Spec-conformance-testing>

**This is the cheapest possible way to build a diagnostics corpus:** every compiler output —
generated C, generated Java, error message, IR dump — becomes a checked-in golden file.
Diffing a baseline is how you notice an unintended change.

---

## 6. SWIFT, C#, JVM — three answers to memory and one to tooling

### 6.1 Swift: ARC inserted in the optimizer, use-based lifetimes

"ARC is mainly driven by the Swift compiler which inserts retain and release operations";
the compiler inserts a `retain` when a reference begins and a `release` immediately after its
**last use**, so lifetimes are use-based rather than brace-scoped. ARC optimizations live in
`lib/SILOptimizer/ARC`. After OSSA lowering, "retain and release operations are never
implicit in SIL and always must be explicitly performed where needed" — i.e. ownership is
made explicit in a mid-level IR, exactly the MIR argument again.
Sources: <https://www.swift.org/documentation/swift-compiler/>,
<https://developer.apple.com/videos/play/wwdc2021/10216>,
<https://github.com/swiftlang/swift/blob/main/docs/SIL/Instructions.md>

What it buys: "values are deallocated as soon as their last strong reference is removed" — no
collection phase, no heap rescan. What it costs: cycles leak unless the programmer breaks
them, and Apple admits the fix is not free — "In addition to carrying a performance cost,
weak and unowned references can expose bugs if you are not careful with class design."
Weak refs also need runtime machinery (side tables), and retain/release stay atomic even in
Swift 6.
Sources: <https://docs.swift.org/swift-book/documentation/the-swift-programming-language/automaticreferencecounting/>,
<https://forums.swift.org/t/i-made-swift-6-prove-the-race-was-gone-arc-still-used-atomic-retain-release/89912>

### 6.2 C# / .NET: generational compacting GC + tiered JIT

Heap split into gen 0 (short-lived, collected most often), gen 1 (buffer), gen 2
(long-lived); survivors are promoted. Rationale stated plainly: "It's faster to compact the
memory for a portion of the managed heap than for the entire managed heap", plus the
generational hypothesis, and "the garbage collector doesn't have to reexamine the objects in
generations 1 and 2 each time it performs a collection of generation 0." Large objects go to
a separate LOH that is usually not compacted.

Compacting allocation is a pointer bump — "almost as fast as allocating memory from the
stack" — and contiguity preserves locality. Collection is mark → relocate → compact, and
compaction is skipped when nothing died.
Source: <https://learn.microsoft.com/en-us/dotnet/standard/garbage-collection/fundamentals>

Tiering: tier 1 = quick JIT or precompiled ReadyToRun, tier 2 = optimized code in the
background, default since .NET Core 3.0. R2R trades code quality for startup: "Ahead-of-time
generated code is not as highly optimized as code produced by the JIT. To address this issue,
tiered compilation will replace commonly used ReadyToRun methods with JIT-generated methods."
Sources: <https://learn.microsoft.com/en-us/dotnet/core/runtime-config/compilation>,
<https://learn.microsoft.com/en-us/dotnet/core/deploying/ready-to-run>

### 6.3 JVM: the bytecode is the contract

The class file is "the hardware- and operating system-independent binary format used to
represent compiled classes and interfaces", and everything about GC and instruction
re-optimization "left to the discretion of the JVM". The format is versioned
(`major.minor`), a JVM supports a contiguous range, and preview features are flagged by minor
version 65535.
Sources: <https://docs.oracle.com/javase/specs/jvms/se20/html/jvms-4.html>,
<https://docs.oracle.com/en/java/javase/26/docs/specs/jvms26.pdf>

HotSpot: interpreter + C1 (fast to compile, less optimized) + C2 (slower, better code), with
five tiered levels (0 interpreter … 4 C2 full optimizing).
Sources: <https://docs.oracle.com/en/java/javase/11/jrockit-hotspot/compilation-optimization.html>,
<https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/>

javac is deliberately dumb because the JIT is smart: JEP 348 notes "In modern JVM
implementations, Just-In-Time (JIT) compilers do an excellent job of optimizing bytecode at
run time", and JEP 280 moved string concatenation to `invokedynamic` so the *JIT* chooses the
strategy instead of baking it into bytecode.
Sources: <https://openjdk.org/jeps/348>, <https://openjdk.org/jeps/280>

### 6.4 RC vs tracing: the actual numbers

- **Shahriyar, Blackburn, Frampton, "Down for the Count?" (ISMM 2012):** "an existing modern
  implementation of reference counting has an average **30% overhead compared to tracing**",
  and their optimizations "completely eliminate that overhead", bringing RC "on par with…
  a well tuned mark-sweep collector" (19 DaCapo/SPEC benchmarks). RC alone also "cannot
  collect all garbage" and needs backup tracing.
  <https://www.steveblackburn.org/pubs/papers/rc-ismm-2012.pdf>
- **Zhao, Blackburn, McKinley, "Low-Latency, High-Throughput Garbage Collection" (PLDI 2022,
  LXR):** hybrid — RC primary + concurrent tracing for cycles. On Lucene with a generous heap,
  **6× throughput with 30× lower 99.9th-percentile latency** than a production collector.
  <https://arxiv.org/abs/2210.17175>
- **Hertz & Berger, OOPSLA 2005:** tracing in a 5× heap can match explicit `malloc`/`free`;
  GC needs extra memory to reach parity.
  <https://people.cs.umass.edu/~emery/pubs/gcvsmalloc.pdf>

**Conclusion for ATOMIC++:** "ARC = automatic and safe" is false as stated. RC costs ~30% in
a naive implementation, leaks cycles, and needs atomic-ish bookkeeping across threads. Value
semantics + arenas + an explicit `unsafe` boundary is the honest early position; RC is a
later, measured decision.

### 6.5 Swift on compatibility: three separate knobs

- Swift 5's primary goal was ABI stability, so "a stable Swift runtime [could] be deployed by
  OS vendors"; achieved March 2019, and "The ABI is now declared stable for Swift 5 on Apple
  platforms."
- ABI stability is **per-platform**, not global.
- **Language mode is separate from ABI**: "The language compatibility setting is a purely
  compile-time feature that is used to control source compatibility. It does not affect ABI."
- ABI stability alone was not enough — **library evolution** needed `@frozen` / `@inlinable`
  / `@usableFromInline`, an explicit trade "between performance and future flexibility" — and
  **module stability** arrived only in 5.1 with a textual module interface.
Sources: <https://www.swift.org/blog/swift-5-released/>,
<https://www.swift.org/blog/abi-stability-and-more>,
<https://www.swift.org/blog/library-evolution/index.html>,
<https://www.swift.org/blog/swift-5.1-released/>

---

## 7. THE RESEARCH LITERATURE ON COMPILER CORRECTNESS

This is the part most hobby languages skip, and it is where the cheapest wins are.

### 7.1 Csmith — randomised differential testing needs no oracle

**Yang, Chen, Eide, Regehr, "Finding and Understanding Bugs in C Compilers", PLDI 2011.**
Reported "more than **325 previously unknown bugs**"; "Every compiler we tested was found to
crash and also to silently generate wrong code when presented with valid input."

The method: generate programs covering a large subset of C "while avoiding the undefined and
unspecified behaviors that would destroy its ability to automatically find wrong-code bugs",
then **compare outputs across compilers**. The key property:

> Randomized differential testing has the advantage that **no oracle for test results is
> needed**. It exploits the idea that if one has multiple, deterministic implementations of
> the same specification, all implementations must produce the same result from the same valid
> input.

Programs print a checksum of global state; disagreement is the signal.
Sources: <https://dl.acm.org/doi/10.1145/1993498.1993532>,
<https://users.cs.utah.edu/~regehr/papers/pldi11-preprint.pdf>

**ATOMIC++ already has the two deterministic implementations** — the interpreter and the C
backend — and the conformance test is exactly this oracle. The missing piece is a **program
generator**.

### 7.2 EMI — equivalence modulo input removes the need for a second compiler

**Le, Afshari, Su, "Compiler Validation via Equivalence Modulo Input", PLDI 2014.** Profile
the program on input *I*, then generate variants by deleting/inserting code that is never
executed under *I*; all variants must produce the same output for *I*.

Results (Feb–Nov 2013): **GCC 94 reported / 65 confirmed / 37 fixed; LLVM 61 / 56 / 20;
total 155 / 121 / 57.** Bug types: wrong code 82, crashes 19, performance 20.
Source: <https://fm.csl.sri.com/SSFT14/PLDI14-Orion.pdf>

### 7.3 Translation validation — the optimiser is the dangerous component

- **Crellvm (PLDI 2018):** augment LLVM to emit a proof with each optimization, checked by a
  Coq-verified checker; found "four new miscompilation bugs" in `mem2reg` and `gvn`, all
  long-standing. Motivation slide, bluntly: "testing alone cannot guarantee a high level of
  reliability."
  <https://sf.snu.ac.kr/publications/crellvm.pdf>
- **Alive2 (PLDI 2021), Lopes, Lee, Hur, Liu, Regehr:** bounded translation validation for
  LLVM. "By running Alive2 over LLVM's unit test suite, we discovered and reported **47 new
  bugs, 28 of which have been fixed**", plus eight patches to the LLVM Language Reference.
  <https://web.ist.utl.pt/nuno.lopes/pubs/alive2-pldi21.pdf>

Relevance: the moment ATOMIC++ gets an optimizer, an opt-off/opt-on differential mode is
mandatory (the master goal's L7 already says this; this is the evidence that it is not
paranoia).

### 7.4 Property-based testing of compilers — minutes on a laptop

**Pałka, Claessen, Russo, Hughes, "Testing an Optimising Compiler by Generating Random Lambda
Terms", AST 2011.** Generator produces **well-typed** lambda terms; property = optimizations
must not change meaning. "After around 20,000 tests we triggered an optimiser failure, and
automatically simplified it to a program with just a few constructs" — "in a few minutes on
an ordinary laptop", on GHC.
Source: <https://www.cse.chalmers.se/~russo/publications_files/AST2011.pdf>

**Midtgaard et al., "Effect-driven QuickChecking of compilers", ICFP 2017:** grammar-based
generation mostly produces ill-typed OCaml programs; the fix is to drive generation by the
type-and-effect system. Direct lesson: **the generator must emit only well-typed ATOMIC++
programs**, otherwise you fuzz the parser and learn nothing about semantics.
Source: <https://dl.acm.org/doi/10.1145/3110259>

**Goldstein, Cutler, Dickstein, Pierce, Head, "Property-Based Testing in Practice", ICSE
2024:** interview study of 30 practitioners whose domains include compilers. Observations:
differential properties are "a natural place to use property based testing"; passing tests
mislead if generators never reach buggy code; PBT must be as fast as unit tests.
Source: <https://www.cis.upenn.edu/~bcpierce/papers/icse24-pbt-in-practice>

### 7.5 Alastair Reid on trusting a specification

**"Trustworthy Specifications of ARM v8-A and v8-M System Level Architecture", FMCAD 2016.**
Three properties of a spec: scope, applicability, trustworthiness — "whether the specification
can be trusted to reflect the behaviour of all processors implementing the specification."

What he actually did, all transferable:

1. **Test the spec against many independent expressions of it** — "to defend against
   common-mode failure. In the process, we have also found bugs in all those artifacts:
   testing specifications is very much a two-way street."
2. **Use a self-checking conformance suite as the oracle** — ARM's Architecture Validation
   Suite, "over 11,000 test programs with a combined runtime of over 2.5 billion
   instructions"; "each test prints PASSED or FAILED."
3. **Random instruction-sequence testing as a complement** to directed tests, requiring trace
   comparison between at least two models.
4. **Measure coverage, not vibes** — their coverage measurement found a `+0.0/−0.0` rounding
   branch that was never exercised.
5. **Build a virtuous cycle / multiple users** so fixes flow back into one master spec.
6. **Continuous integration on every spec change** — "This was critical."
Source: <https://alastairreid.github.io/papers/fmcad2016-trustworthy.pdf>

**(Unverified):** there is no talk by Reid titled "How to test a compiler"; the FMCAD paper
above plus "Creating Formal Specifications of the Arm Processor Architecture" (ACSD 2018) and
"How can you trust formally verified software?" (BCS 2017) carry the substance.

### 7.6 Every bug becomes a test

- **LLVM:** "The regression tests are small pieces of code that test a specific feature of
  LLVM or trigger a specific bug [...] Typically, when a bug is found in LLVM, a regression
  test containing just enough code to reproduce the problem should be written."
  <https://llvm.org/docs/TestingGuide.html>
- **MSVC:** "The PR contains **both the fix and at least one new regression test** based on
  the bug report", and fuzzing findings are "capture[d] into a smaller regression test so
  that we can detect the same problem earlier". They also name the limit: "The main problem
  with using only traditional regression tests for an optimizing compiler is that
  optimizations tend to be invisible from a testing perspective."
  <https://devblogs.microsoft.com/cppblog/testing-the-msvc-compiler-backend>
- **Scale, measured:** Sun, Le, Zhang, Su, "Toward Understanding Compiler Bugs in GCC and
  LLVM" (ISSTA 2016) mined **11,142 GCC regression test cases** by bug label; median
  regression test size is 21 lines for GCC, 16 for LLVM.
  <https://people.inf.ethz.ch/suz/publications/issta16-compiler-bug-study.pdf>

### 7.7 Error messages: Elm is the best-documented case

- **"Compiler Errors for Humans" (Elm 0.15.1, 2015):** every message has a useful hint; colour
  used for scanning (red = the problem, blue = separator); layout reveals detail as needed —
  "General context is above the code. It is very short and hints at what is wrong."
  <https://elm-lang.org/news/compiler-errors-for-humans>
- **`elm/error-message-catalog`:** "A set of Elm programs to trigger every possible error
  message. Once we build a fairly complete set of error messages, we can use them to start
  improving error message quality overall."
  <https://github.com/elm/error-message-catalog>
- **"Compilers as Assistants" (0.16):** the catalog-driven loop — community reports → **type
  diffs** (show only the differing parts of large types) → **elimination of cascading
  errors** ("there are no more cascading errors in Elm 0.16"); "Users' reports of confusing
  error messages actually motivated most of the improvements in this release."
  <https://elm-lang.org/news/compilers-as-assistants>
- **"The Syntax Cliff" (0.19.1):** error quality determines whether beginners survive syntax
  errors, and compiler authors are subject to **survivorship bias**; "I only understood its
  magnitude once elm/error-message-catalog got going."
  <https://elm-lang.org/news/the-syntax-cliff>

Two properties are worth naming explicitly because ATOMIC++ can implement both cheaply:
**no cascading errors** (one root cause must not produce ten diagnostics) and **type diffs**
(print the part of the type that differs, not the whole type).

---

## 8. Crafting Interpreters — the right architecture for a one-person project

- Tree-walk interpreter: simple, portable, slow. Native code: fast, complex, platform-specific.
  Bytecode "sits in the middle. It retains the portability of a tree walker" while resembling
  machine code.
- clox merges parse and codegen into **one pass**. Nystrom's stated reason is not nostalgia:
  "we're taking an old-school approach [...] We're doing it because it keeps our compiler
  simpler, which is a real asset when programming in C." He also flags the limit:
  "Single-pass compilers like we're going to build don't work well for all languages."
- Expressions are handled with **Pratt / precedence climbing**: assign each operator a binding
  power, then after parsing a left operand keep consuming operators whose precedence is at
  least the current minimum, recursing with a higher minimum on the right — the `+1` is what
  keeps it left-associative. "A Pratt parser isn't a recursive descent parser, but it's still
  recursive."
- In the VM, `run()` is not recursive: "the nested expression tree is flattened out into a
  linear series of instructions."
Sources: <https://craftinginterpreters.com/compiling-expressions.html>,
<https://craftinginterpreters.com/a-virtual-machine.html>

---

## 9. Decisions recorded for ATOMIC++ (with the evidence behind each)

### D1 — Implementation language: stay on Python. Do not self-host.
Evidence: Go needed a permanent bootstrap chain and a mechanical C→Go translation; TypeScript
maintains a "last known good" compiler and, in 2025–26, moved to Go for ~10× speed; Zig sank
about two years into a self-hosted rewrite. A one-person project on an i3/8GB machine cannot
afford any of that. Revisit only if Python becomes the measured bottleneck for *users*, not
for the author.

### D2 — Backend strategy: keep emit-C + gcc. Reject LLVM.
Evidence: Go rejected LLVM as "too large and slow" and kept a custom loader; Zig found LLVM
was ≥70% of compile time and is removing it from the Debug path, cutting its self-build from
1–2 minutes to seconds. ATOMIC++ gets -O2/-O3, LTO and sanitizers for free by emitting C. The
cost — C's own UB is reachable if the emitter is wrong — is answered by the conformance and
differential tests, not by switching backends.

### D3 — Promote `ir.py` to a real typed IR, with a verifier.
Evidence: MIR exists because "the old restrictions stemmed from how the compiler represented
programs" (Matsakis); the borrow checker was moved off HIR because MIR "is far less complex"
and "the radical desugaring helps prevent bugs". Zig splits ZIR (file-level, untyped) from AIR
(function-level, typed). ATOMIC++'s `ir.py` today only renames the parser's dict keys — it
carries no types, so no backend can be checked against it. That is the single highest-leverage
structural change available.

### D4 — Build a random program generator before building an optimizer.
Evidence: Csmith found 325+ bugs across every compiler it tested with **no oracle**, because
differential testing needs only two deterministic implementations; EMI found 155 bugs with one
compiler; Pałka et al. found a GHC optimizer bug in ~20,000 well-typed generated terms, in
minutes, on a laptop. Generator must emit **well-typed** programs (Midtgaard et al.). For
ATOMIC++ the oracle already exists: interpreter vs. C vs. Java.

### D5 — Adopt "no cascading errors" and a diagnostics catalog.
Evidence: Elm's entire error-quality program is built on `error-message-catalog`; Rust's guide
says "Try not to emit multiple error messages for the same error" and requires an explanation
for every error code. ATOMIC++ already emits codes (`undefined_variable`, `invalid_operation`,
`invalid_call`, `invalid_return`, `undefined_function`) but has no test asserting the *text*
of any message and no rule against cascades — `semantic.analyze` will happily emit the same
undefined variable twice.

### D6 — Memory: value semantics + arenas; no ARC promise.
Evidence: naive RC is ~30% slower than tracing before optimization (ISMM 2012), RC cannot
collect cycles, and Swift pushes cycle-breaking onto the programmer with `weak`/`unowned` at
"a performance cost". Hertz & Berger: tracing matches explicit malloc only with ~5× heap.
Therefore: ints/floats/bools are values; text is immutable; mutation is explicit; an
`unsafe`/FFI boundary is documented as unsafe. Claim nothing the implementation does not
enforce.

### D7 — No incremental compilation, no query system, until measured.
Evidence: rustc had to retrofit queries ("parts of it are not query-fied yet"), and its best
incremental wins still require whole-crate work like borrow checking. Zig needed a whole
dependency-tracking design (`AnalUnit`, `InternPool`) to do it *without* queries. At
ATOMIC++'s size, whole-program compilation in Python is milliseconds-to-seconds; measure
before designing.

### D8 — Compatibility: write the policy before v1.0.
Evidence: Go promises source-level compatibility forever and explicitly excludes performance;
Swift separates *language mode* from *ABI*, stabilizes ABI per platform, and needed separate
*frozen/resilient* and *module stability* work afterwards. ATOMIC++ should promise: programs
valid on v1.0 keep compiling, `check` may add warnings, no silent semantic changes — and
publish an opt-in `--lang-version` mode only when a break is genuinely unavoidable.

### D9 — Package dependencies keyed by hash, not URL or registry.
Evidence: Zig's `build.zig.zon` — "packages do not come from a url; they come from a hash. url
is just one of many possible mirrors", "source-locked" so "even a compromised third party
provider cannot compromise your build" — and the explicit decision not to run a central
index. That is the right starting point for a project with no infrastructure budget.

### D10 — Golden-file (baseline) testing for every compiler output.
Evidence: TypeScript's baseline system — "file-based snapshot tests, each test verifies the
compiler's output based on an input file" — with `gulp diff` to review and `baseline-accept`
to accept. For ATOMIC++ the outputs are: generated C, generated Java, diagnostic text, and
IR dumps. Checking them in makes unintended codegen changes visible in review.

---

## 10. What is still missing from this research

Honest gaps, so nobody mistakes this document for complete:

1. **No measured ATOMIC++ baseline yet.** Every claim above is about *other* projects. The
   benchmark suite exists (`bench/`) but this document cites no number produced by it.
2. **Median-size data for error-message corpora** — Elm's catalog has no published statistics,
   so "how many messages does a language need" is unknown.
3. **No primary source for a GCC "test per bug" policy statement**; the convention is
   documented indirectly by the ISSTA 2016 study (files named `prNNNNN.c`).
4. **Exact rustc incremental numbers** from the 2016 blog post could not be read (rate
   limited); the 2017 forum figures are used instead and are weaker evidence.
5. **No Go compile-speed benchmark from a primary source** — only "at most a few seconds".
6. **No Apple-published ARC-vs-GC benchmark** — Apple's claims are architectural, and the
   quantitative RC evidence comes from the Jikes RVM lineage, not Swift.

---

## 11. Sources

**Rust:** rustc dev guide `overview`, `mir`, `mir/passes`, `borrow-check`, `queries`,
`queries/incremental-compilation[-in-detail]`, `queries/salsa`, `tests/compiletest`,
`tests/crater`, `tests/perf`, `diagnostics`, `diagnostics/error-codes`, `fuzzing`,
`backend/monomorph`, `building/bootstrapping`; RFC 1211; Rust blog 2016-04-19 (MIR),
2023-11-09 (parallel rustc); goals.rust-lang.org 2026 compiler performance; crater repo.

**Go:** `go.dev/doc/faq`; `go.dev/doc/go1compat`; `go.dev/doc/go1.5`;
`go.dev/doc/install/source`; `go.dev/src/cmd/compile/README`; `go.dev/src/cmd/dist/README`;
`go.dev/gopls/design/{design,implementation}`; `pkg.go.dev/go/types`;
`pkg.go.dev/cmd/go/internal/test`; Rob Pike *Less is exponentially more*, *Simplicity is
Complicated*, *Go at Google*; Russ Cox *Experiment, Simplify, Ship*, *Go, Open Source,
Community*.

**Zig:** `ziglang.org/learn/{overview,why_zig_rust_d_cpp}`; `lib/std/zig/Zir.zig`;
`src/Air.zig`; `src/target.zig`; `doc/build.zig.zon.md`; issue #943; release notes 0.9.0,
0.14.0, 0.15.1, 0.16.0; kristoff.it "A new relationship with LLVM" and "Zig
self-hosted: now what?"; mlugg incremental-compilation overview gist; mitchellh.com
AstGen/Sema; sourcegraph.com Zig retrospective interview.

**CPython:** `InternalDocs/{compiler,parser,interpreter}.md`; devguide `compiler`,
`testing/buildbots`, `testing/oss-fuzz`, `developer-workflow/{lang-changes,c-api}`;
PEP 1, PEP 620, PEP 659; What's New in 3.11; google/atheris.

**TypeScript:** `TypeScript-Compiler-Notes/intro/README.md`; wiki `Architectural-Overview`,
`Compiler-Internals`, `Spec-conformance-testing`; devblogs.microsoft.com
`typescript-native-port`.

**Swift:** swift.org `documentation/swift-compiler`; blog `swift-5-released`,
`abi-stability-and-more`, `abi-stability-and-apple`, `library-evolution`, `swift-5.1-released`;
The Swift Programming Language "Automatic Reference Counting"; `docs/SIL/{Instructions,
Ownership,SIL}.md`; WWDC21 "ARC in Swift".

**C# / JVM:** learn.microsoft.com `dotnet/standard/garbage-collection/fundamentals`,
`dotnet/core/runtime-config/compilation`, `dotnet/core/deploying/ready-to-run`; JVMS §4
(SE 8/20/25/26); Oracle HotSpot compilation docs; JEP 280, JEP 348.

**Papers:** Yang/Chen/Eide/Regehr PLDI 2011 (Csmith); Le/Afshari/Su PLDI 2014 (EMI);
Kang et al. PLDI 2018 (Crellvm); Lopes et al. PLDI 2021 (Alive2); Pałka/Claessen/Russo/Hughes
AST 2011; Midtgaard et al. ICFP 2017; Goldstein et al. ICSE 2024; Reid FMCAD 2016; Sun/Le/
Zhang/Su ISSTA 2016; Shahriyar/Blackburn/Frampton ISMM 2012; Zhao/Blackburn/McKinley PLDI
2022; Hertz/Berger OOPSLA 2005.

**Elm / tutorials:** elm-lang.org news `compiler-errors-for-humans`,
`compilers-as-assistants`, `the-syntax-cliff`; `elm/error-message-catalog`;
craftinginterpreters.com chapters 17 and 19; llvm.org TestingGuide.
