# ATOMIC++ v0.6 Typed IR

## Pipeline

```text
source → lexer → parser dictionaries → name/type resolution → typed IR
                                                        ├→ interpreter
                                                        ├→ C emitter → GCC
                                                        └→ Java emitter → javac
```

`ir.py` owns the language type values, typed node classes, name resolution,
expression typing, and `verify_ir`. The parsed dictionaries are input syntax;
they are not the execution or code-generation representation. The small
mapping-style accessors on IR nodes are a compatibility aid for the existing
visitors, and expose the inferred type without recomputing it.

## Types and nodes

Scalar types are `int`, `float`, `bool`, `text`, `void`, and the internal
`unknown` recovery type. Lists use `list[element_type]`. Function signatures
are stored on `IRProgram`; current unannotated parameters default to `int`,
while return types are inferred from `give` expressions.

Expressions are distinct nodes for literals, variables, unary operations,
arithmetic, comparisons, string operations, boolean operations, calls, module
calls, list literals, and list indexing. Statements cover assignment, list
element assignment, output, expression statements, functions, conditions,
inclusive loops, returns, stop, and module use. Each node carries a source span;
each expression carries a `Type`.

The parser lowers `not`, `and`, and `or` into `BooleanOperation`. Precedence is
`not`, comparisons, `and`, then `or`; C and Java preserve short-circuiting.
There is no CFG or block-ID
representation yet: control flow is a structured tree, so the verifier checks
that nested bodies are valid sequences instead of resolving branch targets.

## Verifier

`verify_ir(program)` checks the root and node classes, expression/result types,
literal/type agreement, names, arithmetic and comparisons, list element/index
types, function signatures and argument counts, return types, and structured
block bodies. The builder runs it before returning the program. Backends also
verify directly supplied IR before emitting code. The verifier returns source
located diagnostics rather than throwing on malformed IR.

## Backend responsibilities and current limits

- The interpreter executes `IRProgram.body` directly. It retains the existing
  runtime messages and value behavior.
- The C emitter reads inferred types from IR and uses IR symbol/function tables
  to declare values. Its former fixed-point `_infer` pass has been removed.
- The Java emitter uses the same IR metadata and no longer imports type
  inference or helpers from the C backend.
- C, Java, and the interpreter support fixed-length mutable arrays of `int`,
  `float`, `bool`, and `text`, including empty arrays (typed as `int[]`),
  indexing, assignment, `len(array)`, and bounds checks. Nested arrays and
  arrays passed through function parameters are not supported yet. C owns a
  tracked allocation per literal and releases those buffers at process exit;
  Java and the interpreter use their managed array objects. Array assignment
  aliases the same mutable array value.
- `use math` imports the same three built-ins (`add`, `sub`, `mul`) on each
  engine. Integer results wrap to signed 64-bit. User-authored modules,
  exported declarations, cross-file imports and dependency-cycle detection are
  still out of scope because there is no project/module loader yet.
- The legacy semantic rule currently rejects floating-point arithmetic even
  though the interpreter and direct code generators can evaluate it. This is
  retained to keep the existing diagnostic contract; it needs a separate
  language-semantics decision and conformance tests.
- Bool values lower to integer storage in C/Java but print as `True`/`False`
  across engines. Float formatting differs: C uses 17 significant digits for
  round-trip output; Python and Java use shorter forms. This is a formatting
  difference, not evidence of distinct stored values.

## Test commands

Run `python run_tests.py` from the repository root. `tests/test_ir.py` covers
typed construction, type/name diagnostics, malformed trees, invalid types,
arithmetic, calls, returns, and nested blocks. The conformance suites execute
generated C/Java and compare their output to the interpreter. Unsupported
examples are printed as skips, not counted as backend passes.
