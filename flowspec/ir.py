from dataclasses import dataclass, field

from lark import Tree


@dataclass
class StateVar:
    name: str
    type_tree: Tree
    domain: str | None = None


@dataclass
class Move:
    name: str
    line: int | None = None
    column: int | None = None
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
    line: int | None = None
    column: int | None = None


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
class SemanticDiagnostic:
    message: str
    severity: str
    line: int
    column: int
