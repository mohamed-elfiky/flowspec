import argparse
import tempfile
import time
from pathlib import Path

from flowspec.backends.tla import compile_tla
from flowspec.parser import build_parser, parse_spec
from flowspec.suite import DEFAULT_TLC_IMAGE, PROJECT_ROOT, ensure_docker_image, run_tlc_in_docker
from flowspec.validator import semantic_diagnostics


DEFAULT_SOURCE = PROJECT_ROOT / "examples" / "capability" / "progress_billing.fspec"


def run_once(parser, source_path: Path) -> dict[str, object]:
    source_text = source_path.read_text()

    started = time.perf_counter()
    tree = parser.parse(source_text)
    parsed = time.perf_counter()

    spec = parse_spec(tree)
    ir_built = time.perf_counter()

    diagnostics = semantic_diagnostics(spec)
    validated = time.perf_counter()

    tla = compile_tla(spec)
    compiled = time.perf_counter()

    return {
        "source_lines": len(source_text.splitlines()),
        "tla_lines": len(tla.splitlines()),
        "module": spec.name,
        "diagnostics": diagnostics,
        "tla": tla,
        "parse_ms": (parsed - started) * 1000,
        "ir_ms": (ir_built - parsed) * 1000,
        "validate_ms": (validated - ir_built) * 1000,
        "compile_ms": (compiled - validated) * 1000,
        "total_ms": (compiled - started) * 1000,
    }


def average(results: list[dict[str, object]], key: str) -> float:
    return sum(float(result[key]) for result in results) / len(results)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark FlowSpec parse, validation, compile, and optional TLC time.")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE, help="FlowSpec source to benchmark.")
    parser.add_argument("--iterations", type=int, default=5, help="Number of compiler iterations to average.")
    parser.add_argument("--tlc", action="store_true", help="Also run TLC once using the isolated Docker backend.")
    parser.add_argument(
        "--tlc-image",
        default=DEFAULT_TLC_IMAGE,
        help="Docker image used by TLC. Can also be set with FLOWSPEC_TLC_IMAGE.",
    )
    parser.add_argument(
        "--tlc-logs",
        action="store_true",
        help="Stream TLC stdout/stderr live during the benchmark TLC run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.iterations < 1:
        raise SystemExit("--iterations must be at least 1")

    source_path = args.source.resolve()
    parser = build_parser()
    results = [run_once(parser, source_path) for _ in range(args.iterations)]
    first = results[0]
    errors = [diagnostic for diagnostic in first["diagnostics"] if diagnostic.severity == "error"]

    display_path = source_path.relative_to(PROJECT_ROOT) if source_path.is_relative_to(PROJECT_ROOT) else source_path
    print(f"source: {display_path}")
    print(f"module: {first['module']}")
    print(f"iterations: {args.iterations}")
    print(f"source_lines: {first['source_lines']}")
    print(f"tla_lines: {first['tla_lines']}")
    print(f"semantic_errors: {len(errors)}")
    print(f"parse_ms_avg: {average(results, 'parse_ms'):.2f}")
    print(f"ir_ms_avg: {average(results, 'ir_ms'):.2f}")
    print(f"validate_ms_avg: {average(results, 'validate_ms'):.2f}")
    print(f"compile_ms_avg: {average(results, 'compile_ms'):.2f}")
    print(f"total_ms_avg: {average(results, 'total_ms'):.2f}")

    if errors:
        for error in errors:
            print(f"error: {error.message}")
        raise SystemExit(1)

    if args.tlc:
        ensure_docker_image(args.tlc_image)
        with tempfile.TemporaryDirectory(prefix="flowspec-benchmark-") as temp_dir:
            output_dir = Path(temp_dir)
            tla_path = output_dir / f"{first['module']}.tla"
            tla_path.write_text(str(first["tla"]))
            started = time.perf_counter()
            run_tlc_in_docker(tla_path, source_path, args.tlc_image, show_logs=args.tlc_logs)
            print(f"tlc_ms: {(time.perf_counter() - started) * 1000:.2f}")


if __name__ == "__main__":
    main()
