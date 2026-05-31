from importlib.resources import files
from pathlib import Path

from lark import Lark, Token, Tree
from lark.indenter import Indenter

from flowspec.tree_utils import child_tokens, first_tree, tree_children
from flowspec.ir import Fairness, MessageDef, MessageField, Move, Property, Spec, StateVar


PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent


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
            move.explicit_same.add(render_lvalue_key(first_tree(item, "lvalue")))

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


def render_lvalue_key(lvalue: Tree) -> str:
    name_ref = first_tree(lvalue, "name_ref")
    rendered = str(child_tokens(name_ref, "NAME")[0])
    for suffix in tree_children(name_ref, "index_suffix"):
        suffix_names = child_tokens(suffix, "NAME")
        if suffix_names and not tree_children(suffix, "expr"):
            rendered += "." + str(suffix_names[0])
        else:
            rendered += "[" + first_tree(suffix, "expr").pretty() + "]"
    return rendered
