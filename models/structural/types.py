"""Type aliases."""
from typing import Any, Set, Union, TypeVar, TYPE_CHECKING, Optional, Type

from ansible.playbook.task import Task
from ansible.playbook.block import Block
from ansible.parsing.yaml.objects import AnsibleBaseYAMLObject

import datetime

if TYPE_CHECKING:
    from ansible.playbook.base import Scalar, Value
    from .base import BaseObject
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

_BaseObj: Optional[Type['BaseObject']] = None

def _BaseObjectType() -> Type['BaseObject']:
    global _BaseObj
    if _BaseObj is None:
        from .base import BaseObject
        _BaseObj = BaseObject
    return _BaseObj


def convert_to_native(obj: Any) -> Any:
    native = _convert_to_native(obj)
    assert type(native) in (str, dict, list, float, int, type(None)) or isinstance(native, _BaseObjectType())
    return native

def _convert_to_native(obj: Any) -> Any:
    from .base import BaseObject  # Cyclic imports
    if isinstance(obj, (str, datetime.date)):
        return str(obj)
    if isinstance(obj, (list, set, tuple)):
        return [convert_to_native(sub) for sub in obj]
    if isinstance(obj, dict):
        return {convert_to_native(k): convert_to_native(v) for k, v in obj.items()}
    if isinstance(obj, int):
        return int(obj)
    if isinstance(obj, float):
        return float(obj)
    if isinstance(obj, type(None)):
        return None
    if isinstance(obj, _BaseObjectType()):
        # Assume it's properly converted
        return obj

    raise ValueError(f'Unknown type {type(obj)} for {obj}')
