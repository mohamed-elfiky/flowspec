import argparse
from pathlib import Path

from flowspec.backends.tla import compile_tla
from flowspec.ir import Fairness, MessageDef, MessageField, Move, Property, SemanticDiagnostic, Spec, StateVar
from flowspec.parser import build_parser, parse_spec
from flowspec.validator import diagnostics_json, semantic_diagnostics

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = PROJECT_ROOT / "examples" / "transaction.fspec"

__all__ = [
    "Fairness",
    "MessageDef",
    "MessageField",
    "Move",
    "Property",
    "SemanticDiagnostic",
    "Spec",
    "StateVar",
    "build_parser",
    "compile_tla",
    "diagnostics_json",
    "parse_spec",
    "semantic_diagnostics",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse or compile a FlowSpec source file.")
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Path to a .fspec file. Defaults to examples/transaction.fspec.",
    )
    parser.add_argument(
        "--tree",
        action="store_true",
        help="Print the Lark parse tree instead of generated TLA+.",
    )
    parser.add_argument(
        "--diagnostics-json",
        action="store_true",
        help="Print semantic diagnostics as JSON. Exits nonzero when errors are present.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write generated TLA+ to this path instead of stdout.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = args.source.read_text()

    parser = build_parser()
    tree = parser.parse(source)
    spec = parse_spec(tree)

    if args.tree:
        print(tree.pretty())
        return

    if args.diagnostics_json:
        diagnostics = semantic_diagnostics(spec)
        print(diagnostics_json(diagnostics))
        if any(diagnostic.severity == "error" for diagnostic in diagnostics):
            raise SystemExit(1)
        return

    output = compile_tla(spec)
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
