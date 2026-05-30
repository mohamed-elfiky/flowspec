import argparse
import json
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

from lark import Lark, Token, Tree
from lark.indenter import Indenter

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = PROJECT_ROOT / "examples" / "transaction.fspec"


class FlowSpecIndenter(Indenter):
    NL_type = "_NL"
    OPEN_PAREN_types = []
    CLOSE_PAREN_types = []
    INDENT_type = "INDENT"
    DEDENT_type = "DEDENT"
    tab_len = 8


def build_parser() -> Lark:
    grammar_path = PROJECT_ROOT / "grammar.lark"
    if grammar_path.exists():
        grammar = grammar_path.read_text()
    else:
        grammar = files("flowspec").joinpath("grammar.lark").read_text()

    return Lark(
        grammar,
        parser="lalr",
        postlex=FlowSpecIndenter(),
        start="start",
        propagate_positions=True,
        maybe_placeholders=False,
    )


@dataclass
class StateVar:
    name: str
    type_tree: Tree
    domain: str | None = None


@dataclass
class Move:
    name: str
    quantifiers: list[Tree] = field(default_factory=list)
    guards: list[Tree] = field(default_factory=list)
    effects: list[tuple[Tree, str, Tree]] = field(default_factory=list)
    explicit_same: set[str] = field(default_factory=set)


@dataclass
class MessageField:
    name: str
    kind: str
    expr: Tree


@dataclass
class MessageDef:
    name: str
    fields: list[MessageField]


@dataclass
class Property:
    kind: str
    name: str
    exprs: list[Tree]


@dataclass
class Fairness:
    kind: str
    move_name: str


@dataclass
class Spec:
    name: str
    constants: list[str] = field(default_factory=list)
    assumptions: list[Tree] = field(default_factory=list)
    state_vars: list[StateVar] = field(default_factory=list)
    messages: list[MessageDef] = field(default_factory=list)
    initial_facts: list[Tree] = field(default_factory=list)
    moves: list[Move] = field(default_factory=list)
    properties: list[Property] = field(default_factory=list)
    fairness: list[Fairness] = field(default_factory=list)


@dataclass
class RenderContext:
    enum_values: set[str]
    state_vars: set[str]
    constants: set[str]
    bound_vars: set[str] = field(default_factory=set)


@dataclass
class SemanticDiagnostic:
    message: str
    severity: str
    line: int
    column: int


def tree_children(tree: Tree, name: str) -> list[Tree]:
    return [child for child in tree.children if isinstance(child, Tree) and child.data == name]


def first_tree(tree: Tree, name: str) -> Tree:
    matches = tree_children(tree, name)
    if not matches:
        raise ValueError(f"Expected {name} in {tree.data}")
    return matches[0]


def child_tokens(tree: Tree, token_type: str) -> list[Token]:
    return [child for child in tree.children if isinstance(child, Token) and child.type == token_type]


def parse_spec(tree: Tree) -> Spec:
    machine_doc = first_tree(tree, "machine_doc")
    machine_header = first_tree(machine_doc, "machine_header")
    name_tokens = child_tokens(machine_header, "NAME")
    if not name_tokens:
        raise ValueError("Machine header is missing a name")

    spec = Spec(name=str(name_tokens[0]))

    for section_wrapper in tree_children(machine_doc, "section"):
        if not section_wrapper.children or not isinstance(section_wrapper.children[0], Tree):
            continue

        section = section_wrapper.children[0]
        if section.data == "given_section":
            for item in tree_children(section, "given_item"):
                spec.constants.append(str(child_tokens(item, "NAME")[0]))
        elif section.data == "assume_section":
            for fact in tree_children(section, "fact_line"):
                spec.assumptions.append(first_tree(fact, "expr"))
        elif section.data == "state_section":
            for item in tree_children(section, "state_item"):
                names = child_tokens(item, "NAME")
                name = str(names[0])
                domain = str(names[1]) if child_tokens(item, "PER") else None
                spec.state_vars.append(StateVar(name=name, domain=domain, type_tree=first_tree(item, "type_expr")))
        elif section.data == "message_section":
            for item in tree_children(section, "message_item"):
                spec.messages.append(parse_message(item))
        elif section.data == "initially_section":
            for fact in tree_children(section, "fact_line"):
                spec.initial_facts.append(first_tree(fact, "expr"))
        elif section.data == "move_section":
            spec.moves.append(parse_move(section))
        elif section.data in {"bad_state_section", "always_section", "eventually_section"}:
            spec.properties.append(parse_property(section))
        elif section.data == "fairness_section":
            for item in tree_children(section, "fairness_item"):
                spec.fairness.append(parse_fairness(item))

    return spec


def parse_message(item: Tree) -> MessageDef:
    name = str(child_tokens(item, "NAME")[0])
    fields = []
    for field_tree in tree_children(item, "message_field"):
        field_name = str(child_tokens(field_tree, "NAME")[0])
        kind = "in" if child_tokens(field_tree, "IN") else "equals"
        fields.append(MessageField(name=field_name, kind=kind, expr=first_tree(field_tree, "expr")))
    return MessageDef(name=name, fields=fields)


def parse_move(section: Tree) -> Move:
    move_name = str(child_tokens(section, "NAME")[0])
    move = Move(name=move_name)

    for line in tree_children(section, "move_line"):
        if not line.children or not isinstance(line.children[0], Tree):
            continue
        item = line.children[0]
        if item.data == "quantifier_line":
            move.quantifiers.append(first_tree(item, "binding"))
        elif item.data == "if_line":
            move.guards.append(first_tree(item, "expr"))
        elif item.data in {"then_line", "otherwise_line"}:
            effect = first_tree(item, "effect")
            lvalue = first_tree(effect, "lvalue")
            operator = next(child for child in effect.children if isinstance(child, Token))
            expr = first_tree(effect, "expr")
            move.effects.append((lvalue, operator.type, expr))
        elif item.data == "same_line":
            move.explicit_same.add(render_lvalue(first_tree(item, "lvalue"), None))

    return move


def parse_property(section: Tree) -> Property:
    name = str(child_tokens(section, "NAME")[0])
    block = first_tree(section, "expr_block")
    exprs = [first_tree(line, "expr") for line in tree_children(block, "expr_line")]
    kind = {
        "bad_state_section": "bad",
        "always_section": "always",
        "eventually_section": "eventually",
    }[section.data]
    return Property(kind=kind, name=name, exprs=exprs)


def parse_fairness(item: Tree) -> Fairness:
    kind_tree = first_tree(item, "fairness_kind")
    kind_token = next(child for child in kind_tree.children if isinstance(child, Token))
    names = child_tokens(item, "NAME")
    return Fairness(kind=kind_token.type.lower(), move_name=str(names[0]))


def collect_enum_values(spec: Spec) -> set[str]:
    values: set[str] = set()
    for state_var in spec.state_vars:
        for enum_value in find_trees(state_var.type_tree, "enum_value"):
            names = child_tokens(enum_value, "NAME")
            if names:
                values.add(str(names[0]))
    return values


def find_trees(tree: Tree, name: str) -> list[Tree]:
    matches = []
    if tree.data == name:
        matches.append(tree)
    for child in tree.children:
        if isinstance(child, Tree):
            matches.extend(find_trees(child, name))
    return matches


def compile_tla(spec: Spec) -> str:
    ctx = RenderContext(
        enum_values=collect_enum_values(spec),
        state_vars={state_var.name for state_var in spec.state_vars},
        constants=set(spec.constants),
    )

    lines = [f"---- MODULE {spec.name} ----", "EXTENDS Naturals, Integers, Sequences", ""]

    if spec.constants:
        lines.extend(["CONSTANTS " + ", ".join(spec.constants), ""])

    for assumption in spec.assumptions:
        lines.append(f"ASSUME {render_expr(assumption, ctx)}")
    if spec.assumptions:
        lines.append("")

    state_names = [state_var.name for state_var in spec.state_vars]
    if state_names:
        lines.extend(["VARIABLES " + ", ".join(state_names), "", f"vars == <<{', '.join(state_names)}>>", ""])

    for message in spec.messages:
        lines.extend(render_message(message, ctx))
    if spec.messages:
        lines.extend(render_messages_set(spec, ctx))

    auto_type_ok = not any(prop.name == "TypeOK" for prop in spec.properties)
    if auto_type_ok:
        lines.extend(render_type_ok(spec, ctx))
    lines.extend(render_init(spec, ctx, include_type_ok=bool(spec.state_vars)))

    for move in spec.moves:
        lines.extend(render_move(move, state_names, ctx))

    lines.extend(render_next(spec))
    lines.extend(render_spec(spec))

    for prop in spec.properties:
        lines.extend(render_property(prop, ctx))

    lines.append("====")
    return "\n".join(lines) + "\n"


def semantic_diagnostics(spec: Spec) -> list[SemanticDiagnostic]:
    diagnostics: list[SemanticDiagnostic] = []
    state_names = {state_var.name for state_var in spec.state_vars}
    enum_by_state = {
        state_var.name: enum_values_for_type(state_var.type_tree)
        for state_var in spec.state_vars
        if enum_values_for_type(state_var.type_tree)
    }

    diagnostics.extend(check_initial_state(spec, state_names))

    for move in spec.moves:
        move_bound = {str(child_tokens(binding, "NAME")[0]) for binding in move.quantifiers}
        for lvalue, _, expr in move.effects:
            base_name = base_lvalue_name(lvalue)
            if base_name not in state_names:
                diagnostics.append(error_at(first_tree(lvalue, "name_ref"), f"Move '{move.name}' changes unknown state '{base_name}'."))
                continue
            diagnostics.extend(check_enum_assignment(base_name, expr, enum_by_state, move.name))
        for same_name in move.explicit_same:
            base = same_name.split("[", 1)[0].split(".", 1)[0]
            if base not in state_names:
                diagnostics.append(error_at(move_tree_placeholder(move), f"Move '{move.name}' marks unknown state '{base}' as same."))

        for expr in [*move.guards, *[effect_expr for _, _, effect_expr in move.effects]]:
            diagnostics.extend(check_unknown_references(expr, spec, bound=move_bound))

    for fact in spec.initial_facts:
        diagnostics.extend(check_enum_fact(fact, enum_by_state))
        diagnostics.extend(check_unknown_references(fact, spec))

    for prop in spec.properties:
        for expr in prop.exprs:
            diagnostics.extend(check_enum_fact(expr, enum_by_state))
            diagnostics.extend(check_unknown_references(expr, spec))

    return dedupe_diagnostics(diagnostics)


def check_initial_state(spec: Spec, state_names: set[str]) -> list[SemanticDiagnostic]:
    initialized = set()
    for fact in spec.initial_facts:
        state_name = assigned_state_name(fact)
        if state_name:
            initialized.add(state_name)
    return [
        warning_at(state_var.type_tree, f"State '{state_var.name}' is not initialized in Initially.")
        for state_var in spec.state_vars
        if state_var.name not in initialized and state_var.name in state_names
    ]


def check_enum_assignment(
    state_name: str,
    expr: Tree,
    enum_by_state: dict[str, set[str]],
    move_name: str,
) -> list[SemanticDiagnostic]:
    enum_values = enum_by_state.get(state_name)
    assigned_name = simple_name_or_none(expr)
    if enum_values and assigned_name and assigned_name not in enum_values:
        return [
            error_at(
                expr,
                f"Move '{move_name}' assigns '{assigned_name}' to '{state_name}', but allowed values are: {', '.join(sorted(enum_values))}.",
            )
        ]
    return []


def check_enum_fact(expr: Tree, enum_by_state: dict[str, set[str]]) -> list[SemanticDiagnostic]:
    assignment = state_assignment(expr)
    if not assignment:
        return []
    state_name, value_name, value_node = assignment
    enum_values = enum_by_state.get(state_name)
    if enum_values and value_name not in enum_values:
        return [
            error_at(
                value_node,
                f"'{value_name}' is not a valid value for '{state_name}'. Allowed values are: {', '.join(sorted(enum_values))}.",
            )
        ]
    return []


def check_unknown_references(expr: Tree, spec: Spec, bound: set[str] | None = None) -> list[SemanticDiagnostic]:
    enum_values = collect_enum_values(spec)
    known_globals = (
        {state_var.name for state_var in spec.state_vars}
        | set(spec.constants)
        | enum_values
        | {message.name for message in spec.messages}
        | {"Messages", "Nat", "Int", "BOOLEAN", "TRUE", "FALSE"}
    )
    diagnostics = []
    for name, node in referenced_names(expr, bound=bound or set()):
        if name not in known_globals:
            diagnostics.append(error_at(node, f"Unknown name '{name}'. Add it to State/Given or bind it with 'for some', 'some', or 'every'."))
    return diagnostics


def referenced_names(node: Tree | Token, bound: set[str]) -> list[tuple[str, Tree]]:
    if isinstance(node, Token):
        return []
    if node.data == "binding":
        names = child_tokens(node, "NAME")
        new_bound = bound | {str(names[0])}
        return referenced_names(first_tree(node, "expr"), new_bound)
    if node.data in {"forall_expr", "exists_expr", "no_expr"}:
        current_bound = set(bound)
        refs = []
        for binding in tree_children(node, "binding"):
            refs.extend(referenced_names(first_tree(binding, "expr"), current_bound))
            current_bound.add(str(child_tokens(binding, "NAME")[0]))
        exprs = [child for child in node.children if isinstance(child, Tree) and child.data == "expr"]
        for expr in exprs:
            refs.extend(referenced_names(expr, current_bound))
        return refs
    if node.data == "map_expr":
        names = child_tokens(node, "NAME")
        map_bound = bound | {str(names[0])}
        exprs = [child for child in node.children if isinstance(child, Tree) and child.data == "expr"]
        refs = referenced_names(exprs[0], bound)
        refs.extend(referenced_names(exprs[1], map_bound))
        return refs
    if node.data == "call_expr":
        refs = []
        names = child_tokens(node, "NAME")
        if names and str(names[0]) not in bound:
            refs.append((str(names[0]), node))
        for arg in tree_children(node, "call_arg"):
            refs.extend(referenced_names(first_tree(arg, "expr"), bound))
        return refs
    if node.data == "name_ref":
        names = child_tokens(node, "NAME")
        name = str(names[0])
        refs = [] if name in bound else [(name, node)]
        for suffix in tree_children(node, "index_suffix"):
            refs.extend(referenced_names(suffix, bound))
        return refs
    refs = []
    for child in node.children:
        if isinstance(child, Tree):
            refs.extend(referenced_names(child, bound))
    return refs


def enum_values_for_type(type_tree: Tree) -> set[str]:
    values = set()
    for enum_value in find_trees(type_tree, "enum_value"):
        names = child_tokens(enum_value, "NAME")
        if names:
            values.add(str(names[0]))
    if values:
        return values
    one_of = find_trees(type_tree, "one_of_type")
    for tree in one_of:
        set_literals = tree_children(tree, "set_literal")
        for literal in set_literals:
            for expr in tree_children(literal, "expr"):
                name = simple_name_or_none(expr)
                if name:
                    values.add(name)
    return values


def state_assignment(expr: Tree) -> tuple[str, str, Tree] | None:
    comparisons = find_trees(expr, "comparison")
    for comparison in comparisons:
        comp_ops = tree_children(comparison, "comp_op")
        if not comp_ops or render_comp_op(comp_ops[0]) != "=":
            continue
        sum_exprs = [child for child in comparison.children if isinstance(child, Tree) and child.data == "sum_expr"]
        if len(sum_exprs) != 2:
            continue
        left = base_name_or_none(sum_exprs[0])
        right = simple_name_or_none(sum_exprs[1])
        if left and right:
            return left, right, sum_exprs[1]
    return None


def assigned_state_name(expr: Tree) -> str | None:
    comparisons = find_trees(expr, "comparison")
    for comparison in comparisons:
        comp_ops = tree_children(comparison, "comp_op")
        if not comp_ops or render_comp_op(comp_ops[0]) != "=":
            continue
        sum_exprs = [child for child in comparison.children if isinstance(child, Tree) and child.data == "sum_expr"]
        if len(sum_exprs) != 2:
            continue
        left = base_name_or_none(sum_exprs[0])
        if left:
            return left
    return None


def base_name_or_none(expr: Tree) -> str | None:
    name_refs = find_trees(expr, "name_ref")
    if not name_refs:
        return simple_name_or_none(expr)
    names = child_tokens(name_refs[0], "NAME")
    return str(names[0]) if names else None


def simple_name_or_none(expr: Tree) -> str | None:
    try:
        return simple_name_expr(expr)
    except ValueError:
        return None


def error_at(node: Tree, message: str) -> SemanticDiagnostic:
    return diagnostic_at(node, message, "error")


def warning_at(node: Tree, message: str) -> SemanticDiagnostic:
    return diagnostic_at(node, message, "warning")


def diagnostic_at(node: Tree, message: str, severity: str) -> SemanticDiagnostic:
    meta = getattr(node, "meta", None)
    return SemanticDiagnostic(
        message=message,
        severity=severity,
        line=max(getattr(meta, "line", 1) - 1, 0),
        column=max(getattr(meta, "column", 1) - 1, 0),
    )


def move_tree_placeholder(move: Move) -> Tree:
    for expr in move.guards:
        return expr
    for lvalue, _, _ in move.effects:
        return lvalue
    raise ValueError(f"Move '{move.name}' has no diagnostic anchor")


def dedupe_diagnostics(diagnostics: list[SemanticDiagnostic]) -> list[SemanticDiagnostic]:
    seen = set()
    result = []
    for diagnostic in diagnostics:
        key = (diagnostic.message, diagnostic.line, diagnostic.column, diagnostic.severity)
        if key in seen:
            continue
        seen.add(key)
        result.append(diagnostic)
    return result


def diagnostics_json(diagnostics: list[SemanticDiagnostic]) -> str:
    return json.dumps([diagnostic.__dict__ for diagnostic in diagnostics], indent=2)


def render_message(message: MessageDef, ctx: RenderContext) -> list[str]:
    params = [field.name for field in message.fields if field.kind == "in"]
    signature = f"{message.name}({', '.join(params)})" if params else message.name
    fields = []
    for field in message.fields:
        if field.kind == "in":
            value = field.name
        elif field.name == "type" and is_simple_name_expr(field.expr):
            value = quote(simple_name_expr(field.expr))
        else:
            value = render_expr(field.expr, ctx)
        fields.append(f"{field.name} |-> {value}")
    return [f"{signature} ==", f"  [{', '.join(fields)}]", ""]


def render_messages_set(spec: Spec, ctx: RenderContext) -> list[str]:
    finite_messages = []
    parameterized_messages = []
    for message in spec.messages:
        domain_fields = [field for field in message.fields if field.kind == "in"]
        if not domain_fields:
            finite_messages.append(message.name)
            continue
        bindings = ", ".join(f"{field.name} \\in {render_expr(field.expr, ctx)}" for field in domain_fields)
        args = ", ".join(field.name for field in domain_fields)
        parameterized_messages.append(f"{{{message.name}({args}) : {bindings}}}")

    pieces = []
    if finite_messages:
        pieces.append("{" + ", ".join(finite_messages) + "}")
    pieces.extend(parameterized_messages)

    if not pieces:
        return []
    return ["Messages ==", "  " + " \\cup ".join(pieces), ""]


def is_simple_name_expr(expr: Tree) -> bool:
    try:
        simple_name_expr(expr)
    except ValueError:
        return False
    return True


def simple_name_expr(expr: Tree) -> str:
    node: Tree | Token = expr
    while isinstance(node, Tree) and node.data in {
        "expr",
        "implication",
        "or_expr",
        "and_expr",
        "not_expr",
        "quant_expr",
        "comparison",
        "sum_expr",
        "product_expr",
        "atom",
    }:
        tree_kids = [child for child in node.children if isinstance(child, Tree)]
        token_kids = [child for child in node.children if isinstance(child, Token)]
        if token_kids:
            raise ValueError("Expression is not a simple name")
        if len(tree_kids) != 1:
            raise ValueError("Expression is not a simple name")
        node = tree_kids[0]

    if isinstance(node, Tree) and node.data == "name_ref":
        suffixes = tree_children(node, "index_suffix")
        if suffixes:
            raise ValueError("Expression is not a simple name")
        return str(child_tokens(node, "NAME")[0])
    raise ValueError("Expression is not a simple name")


def render_type_ok(spec: Spec, ctx: RenderContext) -> list[str]:
    if not spec.state_vars:
        return []
    lines = ["TypeOK =="]
    for state_var in spec.state_vars:
        type_expr = render_type_expr(state_var.type_tree, ctx)
        if state_var.domain:
            type_expr = f"[{state_var.domain} -> {type_expr}]"
        lines.append(f"  /\\ {state_var.name} \\in {type_expr}")
    lines.append("")
    return lines


def render_init(spec: Spec, ctx: RenderContext, include_type_ok: bool) -> list[str]:
    lines = ["Init =="]
    facts = spec.initial_facts or []
    if include_type_ok:
        lines.append("  /\\ TypeOK")
    for fact in facts:
        lines.append(f"  /\\ {render_expr(fact, ctx)}")
    if not spec.state_vars and not facts:
        lines.append("  /\\ TRUE")
    lines.append("")
    return lines


def render_move(move: Move, state_vars: list[str], ctx: RenderContext) -> list[str]:
    body = [render_expr(expr, ctx) for expr in move.guards]
    body.extend(render_effect(effect, ctx) for effect in move.effects)

    changed = {base_lvalue_name(lvalue) for lvalue, _, _ in move.effects}
    unchanged = [name for name in state_vars if name not in changed]
    if unchanged:
        body.append(f"UNCHANGED <<{', '.join(unchanged)}>>")

    if not body:
        body.append("TRUE")

    if move.quantifiers:
        bindings = ", ".join(render_binding(binding, ctx) for binding in move.quantifiers)
        lines = [
            f"{move.name} ==",
            f"  /\\ \\E {bindings}:",
            *render_conjunction(body, indent="    "),
            "",
        ]
    else:
        lines = [f"{move.name} ==", *[f"  /\\ {line}" for line in body], ""]
    return lines


def render_effect(effect: tuple[Tree, str, Tree], ctx: RenderContext) -> str:
    lvalue, operator, expr = effect
    indexed_update = render_indexed_update(lvalue, expr, ctx)
    if operator == "BECOMES":
        if indexed_update:
            return indexed_update
        return f"{render_next_lvalue(lvalue, ctx)} = {render_expr(expr, ctx)}"
    if operator == "STAYS":
        return f"{render_lvalue(lvalue, ctx)} = {render_expr(expr, ctx)}"
    if operator == "GAINS":
        indexed_gain = render_indexed_gain(lvalue, expr, ctx)
        if indexed_gain:
            return indexed_gain
        name = render_lvalue(lvalue, ctx)
        return f"{name}' = {name} \\cup {{{render_expr(expr, ctx)}}}"
    raise ValueError(f"Unsupported effect operator {operator}")


def render_indexed_update(lvalue: Tree, expr: Tree, ctx: RenderContext) -> str | None:
    name_ref = first_tree(lvalue, "name_ref")
    suffixes = tree_children(name_ref, "index_suffix")
    if not suffixes:
        return None
    base = str(child_tokens(name_ref, "NAME")[0])
    path = render_except_path(suffixes, ctx)
    return f"{base}' = [{base} EXCEPT {path} = {render_expr(expr, ctx)}]"


def render_indexed_gain(lvalue: Tree, expr: Tree, ctx: RenderContext) -> str | None:
    name_ref = first_tree(lvalue, "name_ref")
    suffixes = tree_children(name_ref, "index_suffix")
    if not suffixes:
        return None
    base = str(child_tokens(name_ref, "NAME")[0])
    path = render_except_path(suffixes, ctx)
    current_value = render_lvalue(lvalue, ctx)
    return f"{base}' = [{base} EXCEPT {path} = {current_value} \\cup {{{render_expr(expr, ctx)}}}]"


def render_except_path(suffixes: list[Tree], ctx: RenderContext) -> str:
    rendered = "!"
    for suffix in suffixes:
        suffix_names = child_tokens(suffix, "NAME")
        if suffix_names and not tree_children(suffix, "expr"):
            rendered += "." + str(suffix_names[0])
        else:
            rendered += "[" + render_expr(first_tree(suffix, "expr"), ctx) + "]"
    return rendered


def render_next(spec: Spec) -> list[str]:
    if not spec.moves:
        return ["Next ==", "  \\/ FALSE", ""]
    return ["Next ==", *[f"  \\/ {move.name}" for move in spec.moves], ""]


def render_spec(spec: Spec) -> list[str]:
    lines = ["Spec ==", "  /\\ Init", "  /\\ [][Next]_vars"]
    for fairness in spec.fairness:
        operator = "WF" if fairness.kind == "weak" else "SF"
        lines.append(f"  /\\ {operator}_vars({fairness.move_name})")
    lines.append("")
    return lines


def render_property(prop: Property, ctx: RenderContext) -> list[str]:
    rendered_exprs = [render_expr(expr, ctx) for expr in prop.exprs]
    body = render_conjunction(rendered_exprs, indent="  ")
    if prop.kind == "eventually":
        expr = " /\\ ".join(rendered_exprs) if rendered_exprs else "TRUE"
        return [f"{prop.name} ==", f"  <>({expr})", ""]
    if prop.kind == "bad":
        return [f"{prop.name} ==", *body, "", f"No{prop.name} ==", f"  ~({prop.name})", ""]
    return [f"{prop.name} ==", *body, ""]


def render_conjunction(parts: list[str], indent: str) -> list[str]:
    return [f"{indent}/\\ {part}" for part in parts] if parts else [f"{indent}/\\ TRUE"]


def render_type_expr(tree: Tree, ctx: RenderContext) -> str:
    if tree.data == "type_expr":
        return render_type_expr(first_type_child(tree), ctx)
    if tree.data == "one_of_type":
        enum_values = tree_children(tree, "enum_value")
        if enum_values:
            values = [quote(str(child_tokens(value, "NAME")[0])) for value in enum_values]
            return "{" + ", ".join(values) + "}"
        return render_expr(first_tree(tree, "set_literal"), ctx)
    if tree.data == "table_type":
        names = child_tokens(tree, "NAME")
        range_type = first_tree(tree, "type_expr")
        return f"[{names[0]} -> {render_type_expr(range_type, ctx)}]"
    if tree.data == "set_type":
        return f"SUBSET {render_type_expr(first_tree(tree, 'type_expr'), ctx)}"
    if tree.data == "sequence_type":
        return f"Seq({render_type_expr(first_tree(tree, 'type_expr'), ctx)})"
    if tree.data == "record_type":
        fields = []
        for field in tree_children(tree, "record_field"):
            name = str(child_tokens(field, "NAME")[0])
            expr = first_tree(field, "expr")
            fields.append(f"{name}: {render_expr(expr, ctx)}")
        return "[" + ", ".join(fields) + "]"
    if tree.data == "simple_type":
        name = str(child_tokens(tree, "NAME")[0])
        lowered = name.lower()
        if lowered in {"bool", "boolean"}:
            return "BOOLEAN"
        if lowered in {"int", "integer"}:
            return "Int"
        if lowered in {"nat", "natural"}:
            return "Nat"
        return name
    raise ValueError(f"Unsupported type expression {tree.data}")


def first_type_child(tree: Tree) -> Tree:
    for child in tree.children:
        if isinstance(child, Tree):
            return child
    raise ValueError("Missing type expression")


def render_expr(node: Tree | Token, ctx: RenderContext) -> str:
    if isinstance(node, Token):
        return render_token(node, ctx)

    if node.data in {"expr", "quant_expr", "atom"}:
        return render_expr(first_expr_child(node), ctx)
    if node.data == "implication":
        return render_binary_right_assoc(node, "=>", ctx)
    if node.data == "or_expr":
        return render_binary_flat(node, "OR", "\\/", ctx)
    if node.data == "and_expr":
        return render_binary_flat(node, "AND", "/\\", ctx)
    if node.data == "not_expr":
        if len(node.children) == 2:
            return f"~({render_expr(node.children[1], ctx)})"
        return render_expr(first_expr_child(node), ctx)
    if node.data == "forall_expr":
        return render_quantified(node, "\\A", ctx)
    if node.data == "exists_expr":
        return render_quantified(node, "\\E", ctx)
    if node.data == "no_expr":
        binding = first_tree(node, "binding")
        expr = next(child for child in node.children if isinstance(child, Tree) and child.data == "expr")
        return f"~(\\E {render_binding(binding, ctx)}: {render_expr(expr, ctx)})"
    if node.data == "comparison":
        return render_comparison(node, ctx)
    if node.data == "sum_expr":
        return render_token_joined(node, ctx)
    if node.data == "product_expr":
        return render_token_joined(node, ctx)
    if node.data == "scalar_literal":
        return render_expr(first_expr_child(node), ctx)
    if node.data == "subset_expr":
        return f"SUBSET {render_name_ref(first_tree(node, 'name_ref'), ctx)}"
    if node.data == "call_expr":
        names = child_tokens(node, "NAME")
        args = [render_call_arg(child, ctx) for child in tree_children(node, "call_arg")]
        return f"{names[0]}({', '.join(args)})"
    if node.data == "name_ref":
        return render_name_ref(node, ctx)
    if node.data == "set_literal":
        return "{" + ", ".join(render_expr(child, ctx) for child in node.children if isinstance(child, Tree)) + "}"
    if node.data == "map_expr":
        names = child_tokens(node, "NAME")
        exprs = [child for child in node.children if isinstance(child, Tree) and child.data == "expr"]
        return f"[{names[0]} \\in {render_expr(exprs[0], ctx)} |-> {render_expr(exprs[1], ctx)}]"
    if node.data == "binding":
        return render_binding(node, ctx)

    raise ValueError(f"Unsupported expression node {node.data}")


def first_expr_child(tree: Tree) -> Tree | Token:
    for child in tree.children:
        if isinstance(child, (Tree, Token)):
            return child
    raise ValueError(f"Missing expression child in {tree.data}")


def render_binary_right_assoc(tree: Tree, operator: str, ctx: RenderContext) -> str:
    exprs = [child for child in tree.children if isinstance(child, Tree)]
    if len(exprs) == 1:
        return render_expr(exprs[0], ctx)
    return f"({render_expr(exprs[0], ctx)} {operator} {render_expr(exprs[1], ctx)})"


def render_binary_flat(tree: Tree, token_type: str, operator: str, ctx: RenderContext) -> str:
    parts = []
    for child in tree.children:
        if isinstance(child, Tree):
            parts.append(render_expr(child, ctx))
    if len(parts) == 1:
        return parts[0]
    return "(" + f" {operator} ".join(parts) + ")"


def render_quantified(tree: Tree, operator: str, ctx: RenderContext) -> str:
    bindings = tree_children(tree, "binding")
    names = {str(child_tokens(binding, "NAME")[0]) for binding in bindings}
    scoped_ctx = RenderContext(ctx.enum_values, ctx.state_vars, ctx.constants, ctx.bound_vars | names)
    expr = next(child for child in tree.children if isinstance(child, Tree) and child.data == "expr")
    return f"{operator} {', '.join(render_binding(binding, scoped_ctx) for binding in bindings)}: {render_expr(expr, scoped_ctx)}"


def render_comparison(tree: Tree, ctx: RenderContext) -> str:
    exprs = [child for child in tree.children if isinstance(child, Tree) and child.data == "sum_expr"]
    if len(exprs) == 1:
        set_literals = [child for child in tree.children if isinstance(child, Tree) and child.data == "set_literal"]
        type_exprs = [child for child in tree.children if isinstance(child, Tree) and child.data == "type_expr"]
        if not set_literals and not type_exprs:
            return render_expr(exprs[0], ctx)

    token_types = [child.type for child in tree.children if isinstance(child, Token)]
    left = render_expr(exprs[0], ctx)
    if len(exprs) > 1:
        right = render_expr(exprs[1], ctx)
    elif tree_children(tree, "set_literal"):
        right = render_expr(first_tree(tree, "set_literal"), ctx)
    else:
        right = ""

    comp_ops = tree_children(tree, "comp_op")
    if comp_ops:
        return f"{left} {render_comp_op(comp_ops[0])} {right}"
    if token_types == ["INTERSECTS"]:
        return f"({left} \\cap {right}) # {{}}"
    if token_types == ["IS", "NOT"]:
        return f"{left} # {right}"
    if token_types in (["IS", "ONE", "OF"], ["IS", "IN"]):
        return f"{left} \\in {right}"
    if token_types in (["IS", "A", "TABLE", "FROM", "NAME", "TO"], ["IS", "TABLE", "FROM", "NAME", "TO"]):
        return render_type_comparison(left, tree, ctx)
    if token_types in (["IS", "A", "SET", "OF"], ["IS", "SET", "OF"]):
        return render_type_comparison(left, tree, ctx)
    if token_types in (["IS", "A", "SUBSET", "OF"], ["IS", "SUBSET", "OF"]):
        return f"{left} \\subseteq {right}"
    if token_types == ["IS"]:
        return f"{left} = {right}"

    raise ValueError(f"Unsupported comparison form {token_types}")


def render_type_comparison(left: str, tree: Tree, ctx: RenderContext) -> str:
    type_exprs = [child for child in tree.children if isinstance(child, Tree) and child.data == "type_expr"]
    if not type_exprs:
        raise ValueError("Type comparison is missing a type expression")
    token_types = [child.type for child in tree.children if isinstance(child, Token)]
    if "TABLE" in token_types:
        domains = child_tokens(tree, "NAME")
        return f"{left} \\in [{domains[0]} -> {render_type_expr(type_exprs[0], ctx)}]"
    return f"{left} \\in {render_type_expr(type_exprs[0], ctx)}"


def render_comp_op(tree: Tree) -> str:
    token = next(child for child in tree.children if isinstance(child, Token))
    return {
        "EQUAL": "=",
        "NOT_EQUAL": "#",
        "IN": "\\in",
        "LTE": "<=",
        "LT": "<",
        "GTE": ">=",
        "GT": ">",
    }[token.type]


def render_token_joined(tree: Tree, ctx: RenderContext) -> str:
    parts = []
    for child in tree.children:
        if isinstance(child, Tree):
            parts.append(render_expr(child, ctx))
        elif isinstance(child, Token):
            parts.append(render_token(child, ctx))
    return " ".join(parts)


def render_binding(tree: Tree, ctx: RenderContext) -> str:
    name = str(child_tokens(tree, "NAME")[0])
    expr = first_tree(tree, "expr")
    return f"{name} \\in {render_expr(expr, ctx)}"


def render_call_arg(tree: Tree, ctx: RenderContext) -> str:
    names = child_tokens(tree, "NAME")
    expr = first_tree(tree, "expr")
    if names:
        return f"{names[0]} |-> {render_expr(expr, ctx)}"
    return render_expr(expr, ctx)


def render_lvalue(tree: Tree, ctx: RenderContext | None) -> str:
    return render_name_ref(first_tree(tree, "name_ref"), ctx)


def render_next_lvalue(tree: Tree, ctx: RenderContext) -> str:
    return render_name_ref(first_tree(tree, "name_ref"), ctx, prime_base=True)


def render_name_ref(tree: Tree, ctx: RenderContext | None, prime_base: bool = False) -> str:
    name = str(child_tokens(tree, "NAME")[0])
    if ctx and name in ctx.enum_values and name not in ctx.state_vars and name not in ctx.constants and name not in ctx.bound_vars:
        rendered = quote(name)
    else:
        rendered = name
    if prime_base:
        rendered += "'"
    for suffix in tree_children(tree, "index_suffix"):
        suffix_names = child_tokens(suffix, "NAME")
        if suffix_names and not tree_children(suffix, "expr"):
            rendered += "." + str(suffix_names[0])
        else:
            rendered += "[" + render_expr(first_tree(suffix, "expr"), ctx or RenderContext(set(), set(), set())) + "]"
    return rendered


def base_lvalue_name(tree: Tree) -> str:
    name_ref = first_tree(tree, "name_ref")
    return str(child_tokens(name_ref, "NAME")[0])


def render_token(token: Token, ctx: RenderContext) -> str:
    value = str(token)
    if token.type == "TRUE":
        return "TRUE"
    if token.type == "FALSE":
        return "FALSE"
    if token.type == "STRING":
        return value
    if token.type == "NAME" and value in ctx.enum_values and value not in ctx.state_vars and value not in ctx.constants and value not in ctx.bound_vars:
        return quote(value)
    if token.type == "PLUS":
        return "+"
    if token.type == "PLUS_WORD":
        return "\\cup"
    if token.type == "MINUS":
        return "-"
    if token.type == "EXCEPT":
        return "\\"
    if token.type == "STAR":
        return "*"
    if token.type == "SLASH":
        return "\\div"
    return value


def quote(value: str) -> str:
    return '"' + value + '"'


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
