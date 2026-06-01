import argparse
from contextlib import nullcontext
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from flowspec.backends.tla import compile_tla
from flowspec.parser import build_parser, parse_spec


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUPPORTED_EXAMPLES = [
    PROJECT_ROOT / "examples" / "transaction.fspec",
    PROJECT_ROOT / "examples" / "account.fspec",
    PROJECT_ROOT / "examples" / "payment.fspec",
    PROJECT_ROOT / "examples" / "wallet_topup.fspec",
    PROJECT_ROOT / "examples" / "2pc.fspec",
]
DEFAULT_TLC_IMAGE = os.environ.get("FLOWSPEC_TLC_IMAGE", "ghcr.io/mohamed-elfiky/flowspec-tlc:0.0.1")
DEFAULT_TLC_JAR = os.environ.get("FLOWSPEC_TLC_JAR")


def compile_example(source_path: Path) -> str:
    parser = build_parser()
    tree = parser.parse(source_path.read_text())
    return compile_tla(parse_spec(tree))


def write_tla(source_path: Path, output_dir: Path) -> Path:
    tla = compile_example(source_path)
    module_name = module_name_from_tla(tla)
    output_path = output_dir / f"{module_name}.tla"
    output_path.write_text(tla)
    return output_path


def module_name_from_tla(tla: str) -> str:
    first_line = tla.splitlines()[0]
    return first_line.removeprefix("---- MODULE ").removesuffix(" ----")


def run_tlc(tla_path: Path, source_path: Path, tlc_jar: Path, show_logs: bool = False) -> None:
    cfg_path = copy_cfg_for(tla_path, source_path)
    if cfg_path is None:
        print(f"SKIP TLC {tla_path.stem}: no examples/{tla_path.stem}.cfg")
        return

    result = run_tlc_process(
        ["java", "-jar", str(tlc_jar), "-deadlock", "-config", str(cfg_path), str(tla_path)],
        cwd=tla_path.parent,
        show_logs=show_logs,
    )
    if result.returncode != 0:
        print_captured_output(result)
        raise SystemExit(result.returncode)
    print(f"PASS TLC {tla_path.stem}")


def run_tlc_in_docker(tla_path: Path, source_path: Path, image: str, show_logs: bool = False) -> None:
    cfg_path = copy_cfg_for(tla_path, source_path)
    if cfg_path is None:
        print(f"SKIP TLC {tla_path.stem}: no matching .cfg")
        return

    result = run_tlc_process(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp",
            "-e",
            "JAVA_TOOL_OPTIONS=",
            "-e",
            "LD_PRELOAD=",
            "--entrypoint",
            "env",
            "-v",
            f"{tla_path.parent}:/input:ro",
            "-w",
            "/tmp",
            image,
            "-i",
            "PATH=/opt/java/openjdk/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "HOME=/tmp",
            "LANG=C.UTF-8",
            "java",
            "-jar",
            "/opt/tla2tools.jar",
            "-deadlock",
            "-metadir",
            "/tmp/tlc-states",
            "-config",
            f"/input/{cfg_path.name}",
            f"/input/{tla_path.name}",
        ],
        show_logs=show_logs,
    )
    if result.returncode != 0:
        print_captured_output(result)
        raise SystemExit(result.returncode)
    print(f"PASS TLC {tla_path.stem}")


def run_tlc_process(command: list[str], cwd: Path | None = None, show_logs: bool = False) -> subprocess.CompletedProcess[str]:
    if show_logs:
        return subprocess.run(command, cwd=cwd, text=True, check=False)
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def print_captured_output(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)


def ensure_docker_image(image: str) -> None:
    result = subprocess.run(
        ["docker", "image", "inspect", image],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            "TLC Docker image is not available.\n"
            f"Build it with: docker build -f docker/tlc/Dockerfile -t {image} ."
        )


def copy_cfg_for(tla_path: Path, source_path: Path) -> Path | None:
    cfg_path = tla_path.with_suffix(".cfg")
    candidates = [
        source_path.with_name(f"{tla_path.stem}.cfg"),
        source_path.with_suffix(".cfg"),
        PROJECT_ROOT / "examples" / f"{tla_path.stem}.cfg",
    ]
    source_cfg = next((candidate for candidate in candidates if candidate.exists()), None)
    if source_cfg is None:
        return None
    cfg_path.write_text(source_cfg.read_text())
    return cfg_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile supported FlowSpec examples and optionally run TLC.")
    parser.add_argument(
        "sources",
        nargs="*",
        type=Path,
        help="Optional .fspec files to run. Defaults to the supported example suite.",
    )
    parser.add_argument("--tlc", action="store_true", help="Run TLC for examples with matching .cfg files.")
    parser.add_argument(
        "--tlc-backend",
        choices=["docker", "host"],
        default="docker",
        help="Where to run TLC. Docker is the default isolated backend.",
    )
    parser.add_argument(
        "--tlc-image",
        default=DEFAULT_TLC_IMAGE,
        help="Docker image used by the TLC backend. Can also be set with FLOWSPEC_TLC_IMAGE.",
    )
    parser.add_argument(
        "--tlc-jar",
        type=Path,
        default=Path(DEFAULT_TLC_JAR) if DEFAULT_TLC_JAR else None,
        help="Path to tla2tools.jar for --tlc-backend host. Can also be set with FLOWSPEC_TLC_JAR.",
    )
    parser.add_argument(
        "--tlc-logs",
        action="store_true",
        help="Stream TLC stdout/stderr live instead of only printing output when TLC fails.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        help="Write generated .tla and copied .cfg files to this directory instead of a temporary directory.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.tlc and args.tlc_backend == "host" and args.tlc_jar is None:
        raise SystemExit("Set --tlc-jar or FLOWSPEC_TLC_JAR to run TLC on the host.")
    if args.tlc and args.tlc_backend == "docker":
        ensure_docker_image(args.tlc_image)

    sources = args.sources or SUPPORTED_EXAMPLES
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        output_context = nullcontext(str(args.output_dir))
    else:
        output_context = tempfile.TemporaryDirectory(prefix="flowspec-suite-")

    with output_context as output_path:
        output_dir = Path(output_path)
        for source_path in sources:
            source_path = source_path.resolve()
            tla_path = write_tla(source_path, output_dir)
            display_path = source_path.relative_to(PROJECT_ROOT) if source_path.is_relative_to(PROJECT_ROOT) else source_path
            print(f"PASS compile {display_path} -> {tla_path.name}")
            if args.output_dir:
                print(f"WROTE TLA {tla_path}")
            if args.tlc:
                if args.tlc_backend == "docker":
                    run_tlc_in_docker(tla_path, source_path, args.tlc_image, show_logs=args.tlc_logs)
                else:
                    run_tlc(tla_path, source_path, args.tlc_jar, show_logs=args.tlc_logs)


if __name__ == "__main__":
    main()
