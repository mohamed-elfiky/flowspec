import re
from pathlib import Path

from flowspec.backends.tla import TRACE_MOVE_VAR
from flowspec.ir import Property, Spec


INVARIANT_RE = re.compile(r"Invariant ([A-Za-z_][A-Za-z0-9_]*) is violated")
STATE_RE = re.compile(r"^State \d+:", re.MULTILINE)
MOVE_RE = re.compile(rf"{re.escape(TRACE_MOVE_VAR)}\s*=\s*\"([^\"]+)\"")
STATE_VALUE_RE = re.compile(r"^\s*/\\\s+([A-Za-z_][A-Za-z0-9_]*)\s*=", re.MULTILINE)


def narrate_tlc_failure(output: str, spec: Spec, source_path: Path) -> str | None:
    violated = violated_property(output)
    states = trace_states(output)
    moves = trace_moves(states)
    if not violated and not moves:
        return None

    lines = ["FlowSpec counterexample", ""]
    if violated:
        lines.append(f"Property violated: {describe_property(violated, spec, source_path)}")
    else:
        lines.append("Property violated: TLC reported a model-checking failure.")

    source_lines = read_source_lines(source_path)
    violated_prop = find_property(violated, spec) if violated else None
    if violated_prop and source_lines:
        block = source_block(source_lines, violated_prop.line)
        if block:
            lines.extend(["", "Property source:"])
            lines.extend(indent_block(block))

    if moves:
        lines.extend(["", "Move path:"])
        move_locations = {move.name: move for move in spec.moves}
        counts: dict[str, int] = {}
        for index, move_name in enumerate(moves, 1):
            counts[move_name] = counts.get(move_name, 0) + 1
            move = move_locations.get(move_name)
            location = source_location(source_path, move.line if move else None)
            suffix = f" ({location})" if location else ""
            repeated = " repeated" if counts[move_name] > 1 else ""
            lines.append(f"  {index}. {move_name}{suffix}{repeated}")

        seen_blocks = set()
        lines.extend(["", "Move source:"])
        for move_name in moves:
            if move_name in seen_blocks:
                continue
            seen_blocks.add(move_name)
            move = move_locations.get(move_name)
            block = source_block(source_lines, move.line if move else None) if source_lines else []
            if block:
                lines.extend(indent_block(block))
                lines.append("")
        if lines[-1] == "":
            lines.pop()

    final_state = states[-1] if states else ""
    relevant_values = final_state_values(final_state)
    if relevant_values:
        lines.extend(["", "Final state excerpt:"])
        for value in relevant_values[:12]:
            lines.append(f"  {value}")

    lines.extend(["", "This is generated from TLC's counterexample trace using FlowSpec move metadata."])
    return "\n".join(lines)


def violated_property(output: str) -> str | None:
    match = INVARIANT_RE.search(output)
    return match.group(1) if match else None


def trace_states(output: str) -> list[str]:
    matches = list(STATE_RE.finditer(output))
    states = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(output)
        states.append(output[start:end].strip())
    return states


def trace_moves(states: list[str]) -> list[str]:
    moves = []
    for state in states:
        match = MOVE_RE.search(state)
        if not match:
            continue
        move = match.group(1)
        if move != "Init":
            moves.append(move)
    return moves


def final_state_values(state: str) -> list[str]:
    values = []
    for line in state.splitlines():
        stripped = line.strip()
        if not stripped.startswith("/\\"):
            continue
        if f"/\\ {TRACE_MOVE_VAR} =" in stripped:
            continue
        if STATE_VALUE_RE.match(stripped):
            values.append(stripped.removeprefix("/\\").strip())
    return values


def describe_property(name: str, spec: Spec, source_path: Path) -> str:
    prop = find_property(name, spec)
    if prop is None:
        return name
    kind = {
        "bad": "bad state",
        "always": "invariant",
        "eventually": "eventual property",
    }.get(prop.kind, prop.kind)
    location = source_location(source_path, prop.line)
    suffix = f" ({location})" if location else ""
    return f"{name} [{kind}]{suffix}"


def find_property(name: str, spec: Spec) -> Property | None:
    for prop in spec.properties:
        if prop.name == name:
            return prop
        if prop.kind == "bad" and name == f"No{prop.name}":
            return prop
    return None


def source_location(source_path: Path, line: int | None) -> str | None:
    if line is None:
        return None
    try:
        display_path = source_path.relative_to(Path.cwd())
    except ValueError:
        display_path = source_path
    return f"{display_path}:{line}"


def read_source_lines(source_path: Path) -> list[str]:
    try:
        return source_path.read_text().splitlines()
    except OSError:
        return []


def source_block(lines: list[str], start_line: int | None) -> list[str]:
    if start_line is None or start_line < 1 or start_line > len(lines):
        return []

    start_index = start_line - 1
    while start_index > 0 and not is_top_level_block_header(lines[start_index]):
        start_index -= 1

    end_index = start_index + 1
    while end_index < len(lines):
        line = lines[end_index]
        if end_index > start_index and is_top_level_block_header(line):
            break
        end_index += 1

    block = lines[start_index:end_index]
    while block and not block[-1].strip():
        block.pop()
    return block


def is_top_level_block_header(line: str) -> bool:
    return line.startswith(("Move:", "Bad state:", "Always:", "Eventually:", "Fairness:"))


def indent_block(block: list[str]) -> list[str]:
    return [f"  {line}" for line in block]
