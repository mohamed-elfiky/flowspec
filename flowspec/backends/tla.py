from dataclasses import dataclass, field

from lark import Token, Tree

from flowspec.tree_utils import (
    base_lvalue_name,
    child_tokens,
    find_trees,
    first_tree,
    is_simple_name_expr,
    lvalue_suffixes,
    render_comp_op,
    simple_name_expr,
    tree_children,
)
from flowspec.ir import Fairness, MessageDef, Move, Property, Spec


@dataclass
class RenderContext:
    enum_values: set[str]
    state_vars: set[str]
    constants: set[str]
    bound_vars: set[str] = field(default_factory=set)


def collect_enum_values(spec: Spec) -> set[str]:
    values: set[str] = set()
    for state_var in spec.state_vars:
        for enum_value in find_trees(state_var.type_tree, "enum_value"):
            names = child_tokens(enum_value, "NAME")
            if names:
                values.add(str(names[0]))
    return values


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
    body.extend(render_effects(move.effects, ctx))

    changed = {base_lvalue_name(lvalue) for lvalue, operator, _ in move.effects if operator != "STAYS"}
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


def render_effects(effects: list[tuple[Tree, str, Tree]], ctx: RenderContext) -> list[str]:
    lines = []
    next_effects_by_base: dict[str, list[tuple[Tree, str, Tree]]] = {}
    for effect in effects:
        lvalue, operator, _ = effect
        if operator == "STAYS":
            lines.append(render_effect(effect, ctx))
            continue
        base = base_lvalue_name(lvalue)
        next_effects_by_base.setdefault(base, []).append(effect)

    for grouped_effects in next_effects_by_base.values():
        lines.append(render_next_effect_group(grouped_effects, ctx))
    return lines


def render_next_effect_group(effects: list[tuple[Tree, str, Tree]], ctx: RenderContext) -> str:
    if len(effects) == 1:
        return render_effect(effects[0], ctx)

    first_lvalue, _, _ = effects[0]
    base = base_lvalue_name(first_lvalue)
    suffixes_by_effect = [(effect, lvalue_suffixes(effect[0])) for effect in effects]

    if all(not suffixes for _, suffixes in suffixes_by_effect):
        if all(operator == "GAINS" for _, operator, _ in effects):
            name = render_lvalue(first_lvalue, ctx)
            additions = [f"{{{render_expr(expr, ctx)}}}" for _, _, expr in effects]
            return f"{name}' = {name} \\cup " + " \\cup ".join(additions)
        raise ValueError(f"State '{base}' has multiple next-state assignments in one move.")

    if any(not suffixes for _, suffixes in suffixes_by_effect):
        raise ValueError(f"State '{base}' mixes whole-value and indexed assignments in one move.")

    updates = []
    seen_paths = set()
    for (lvalue, operator, expr), suffixes in suffixes_by_effect:
        path = render_except_path(suffixes, ctx)
        if path in seen_paths:
            raise ValueError(f"State '{base}' assigns the same indexed path more than once in one move.")
        seen_paths.add(path)
        if operator == "BECOMES":
            updates.append(f"{path} = {render_expr(expr, ctx)}")
        elif operator == "GAINS":
            updates.append(f"{path} = {render_lvalue(lvalue, ctx)} \\cup {{{render_expr(expr, ctx)}}}")
        else:
            raise ValueError(f"Unsupported next-state effect operator {operator}")
    return f"{base}' = [{base} EXCEPT {', '.join(updates)}]"


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

