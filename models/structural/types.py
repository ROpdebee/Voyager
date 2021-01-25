"""Type aliases."""
from typing import Set, Union, TypeVar, TYPE_CHECKING

from ansible.playbook.task import Task
from ansible.playbook.block import Block
from ansible.parsing.yaml.objects import AnsibleBaseYAMLObject

if TYPE_CHECKING:
    from ansible.playbook.base import Scalar, Value
else:
    Scalar = Union[str, int, bool, float]
    # Cyclic types are annotated as object instead of Value, since cyclic types
    # aren't fully supported by mypy at the time of writing. This is arguably
    # better than Any, since using object will fail most of the type checks,
    # whereas using Any will pass all type checks. When nested data is needed,
    # use a dynamic type check and a cast first.
    Value = Union[Scalar, AnsibleBaseYAMLObject]

KwList = Set[str]

AnsTaskOrBlock = Union[Block, Task]
