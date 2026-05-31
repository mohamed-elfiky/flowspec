from lark import Token, Tree


def tree_children(tree: Tree, name: str) -> list[Tree]:
    return [child for child in tree.children if isinstance(child, Tree) and child.data == name]

def first_tree(tree: Tree, name: str) -> Tree:
    matches = tree_children(tree, name)
    if not matches:
        raise ValueError(f"Expected {name} in {tree.data}")
    return matches[0]

def child_tokens(tree: Tree, token_type: str) -> list[Token]:
    return [child for child in tree.children if isinstance(child, Token) and child.type == token_type]

def find_trees(tree: Tree, name: str) -> list[Tree]:
    matches = []
    if tree.data == name:
        matches.append(tree)
    for child in tree.children:
        if isinstance(child, Tree):
            matches.extend(find_trees(child, name))
    return matches

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

def lvalue_suffixes(lvalue: Tree) -> list[Tree]:
    name_ref = first_tree(lvalue, "name_ref")
    return tree_children(name_ref, "index_suffix")

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

def base_lvalue_name(tree: Tree) -> str:
    name_ref = first_tree(tree, "name_ref")
    return str(child_tokens(name_ref, "NAME")[0])

