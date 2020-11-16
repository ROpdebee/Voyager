"""Base models and traits, without mixins etc."""
import abc

from .types import Value
from .provenance import GraphvizMixin, SMGraph, pformat


class BaseFile(abc.ABC):
    """A RoleFile is a generic file found in a role."""
    def __init__(self, file_name: str) -> None:
        self._file_name = file_name

    @property
    def file_name(self) -> str:
        return self._file_name


class BaseObject(abc.ABC, GraphvizMixin):
    """Base class for role objects."""
    pass


class BaseVariable(BaseObject):
    """Base class for variables in a role."""
    def __init__(self, name: str, value: Value) -> None:
        self._name = name
        self._value = value

    @property
    def name(self) -> str:
        return self._name

    @property
    def value(self) -> Value:
        return self._value

    def gv_visit(self, g: SMGraph) -> None:
        g.add_node(self, label=pformat(self.name))
        self.gv_visit_builtin(g, 'value', self.value)


class BaseBlock(BaseObject):
    """A Block represents a list of tasks, or other blocks."""
    pass


class BaseTask(BaseObject):
    """A Task represents a single task in a block."""
    pass


class DefaultsTrait:
    pass


class ConstantsTrait:
    pass


class TasksTrait:
    pass


class HandlersTrait:
    pass
