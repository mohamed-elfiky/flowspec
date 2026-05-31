import json

from lark import Token, Tree

from flowspec.backends.tla import collect_enum_values
from flowspec.tree_utils import (
    base_lvalue_name,
    child_tokens,
    find_trees,
    first_tree,
    render_comp_op,
    simple_name_expr,
    tree_children,
)
from flowspec.ir import Move, SemanticDiagnostic, Spec


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

