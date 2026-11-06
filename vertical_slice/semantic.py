"""Compatibility API for diagnostics produced while building typed IR."""

from ir import build_ir
from interpreter import parse, tokenize


def analyze(source_or_ast) -> list[dict]:
    """Return name/type diagnostics from the same pass that builds typed IR."""
    ast = source_or_ast if isinstance(source_or_ast, list) else parse(tokenize(source_or_ast))
    return list(build_ir(ast).diagnostics)
