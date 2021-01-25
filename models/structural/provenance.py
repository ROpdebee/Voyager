"""Structural model provenance."""
from typing import ClassVar, Dict, Optional, Sequence, Union, TYPE_CHECKING, cast

import abc

from pathlib import Path
from pprint import pformat as pformat  # re-export  # noqa

if TYPE_CHECKING:
    from .mixins import KeywordsMixin
    from .types import Value
else:
    Value = str
    KeywordsMixin = str

import graphviz as gv

class GraphvizMixin:

    _gv_color: ClassVar[str]
    _gv_shape: ClassVar[str]

    def __init_subclass__(
            cls, *args: object,
            gv_color: Optional[str] = None,
            gv_shape: Optional[str] = None,
            **kwargs: object
    ) -> None:
        cls._gv_color = gv_color or 'black'
        cls._gv_shape = gv_shape or 'rect'

    @abc.abstractmethod
    def gv_visit(self, graph: 'SMGraph') -> None:
        """Visit the object and dump it and its children to a graph."""
        ...

    def gv_visit_child(self, graph: 'SMGraph', attr_name: str) -> None:
        child = getattr(self, attr_name)
        child.gv_visit(graph)
        graph.add_edge(self, child, label=attr_name)

    def gv_visit_children(
            self, graph: 'SMGraph',
            attr_name: str,
            children: Optional[Sequence['GraphvizMixin']] = None,
    ) -> None:
        if children is None:
            children = getattr(self, attr_name)
        for child_pos, child in enumerate(children):
            child.gv_visit(graph)
            graph.add_edge(self, child, label=f'{attr_name}[{child_pos}]')

    def gv_visit_keywords(self: KeywordsMixin, graph: 'SMGraph') -> None:  # type: ignore[misc]
        parent_id = str(id(self))
        for kw in set(self._interested_kw_names):
            if getattr(self, kw) is None:
                continue
            cast(GraphvizMixin, self).gv_visit_builtin(graph, kw, getattr(self, kw), parent_id)
        for kw, val in self.misc_keywords.items():
            cast(GraphvizMixin, self).gv_visit_builtin(graph, kw, val, parent_id)


    def gv_visit_builtin(
            self, graph: 'SMGraph', attr_name: str,
            child: Union[Value], parent_id: Optional[str] = None
    ) -> None:
        if parent_id is None:
            parent_id = str(id(self))

        if isinstance(child, (list, set, tuple)):
            self.gv_visit_sequence(graph, attr_name, child, parent_id)
        elif isinstance(child, dict):
            self.gv_visit_dict(graph, attr_name, child, parent_id)
        else:
            node_id = graph.get_free_id()
            graph.add_simple_node(node_id, str(child))
            graph.add_simple_edge(parent_id, node_id, attr_name)

    def gv_visit_sequence(
            self, graph: 'SMGraph', attr_name: str,
            child_list: Sequence[Value], parent_id: str
    ) -> None:
        for (idx, child) in enumerate(child_list):
            self.gv_visit_builtin(
                    graph, f'{attr_name}[{idx}]', child, parent_id)

    def gv_visit_dict(
            self, graph: 'SMGraph', attr_name: str,
            child_dict: Dict[str, Value], parent_id: str
    ) -> None:
        for (child_key, child_value) in child_dict.items():
            self.gv_visit_builtin(
                    graph, f'{attr_name}.{child_key}', child_value, parent_id)

    def dump_to_dot(
            self, dot_path: Path, format: 'gv.backend._FormatValue'
    ) -> Path:
        print(str(dot_path))
        g = SMGraph(filename=str(dot_path), format=format)
        #g.attr(rankdir='LR')
        self.gv_visit(g)
        return Path(g.render())


class SMGraph(gv.Digraph):
    """Custom Digraph for structural model."""
    _free_id = 0

    def add_simple_node(self, node_id: str, label: str) -> None:
        self.node(node_id, label=label)

    def add_simple_edge(
            self, parent_id: str, child_id: str, label: str
    ) -> None:
        self.edge(parent_id, child_id, label=label)

    def add_node(self, obj: GraphvizMixin, label: Optional[str]) -> None:
        lbl = f'{obj.__class__.__name__}:\n{label}'
        self.node(
                str(id(obj)), label=lbl, shape=obj._gv_shape,
                color=obj._gv_color)

    def add_edge(
            self, parent: GraphvizMixin, child: GraphvizMixin, label: str
    ) -> None:
        self.edge(str(id(parent)), str(id(child)), label=label)

    def get_free_id(self) -> str:
        self._free_id += 1
        return str(self._free_id - 1)
