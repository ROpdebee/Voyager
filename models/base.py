"""Base models."""
from typing import Type, TypeVar

import abc
import json

from models.serialize import CONVERTER

_Self = TypeVar('_Self', bound='Model')


class Model(abc.ABC):
    """Base model defining interface for serialization/deserialization."""

    @classmethod
    def from_json_str(cls: Type[_Self], json_str: str) -> _Self:
        """Parse from a JSON string."""
        json_obj = json.loads(json_str)
        return cls.from_json_obj(json_obj)

    @classmethod
    def from_json_obj(cls: Type[_Self], json_obj: object) -> _Self:
        """Deserialize from a JSON object."""
        return CONVERTER.structure(json_obj, cls)

    def to_json_str(self) -> str:
        """Serialize to a JSON string."""
        json_obj = self.to_json_obj()
        return json.dumps(json_obj)

    def to_json_obj(self) -> object:
        """Serialize to a JSON object."""
        return CONVERTER.unstructure(self)

    @property
    @abc.abstractmethod
    def id(self) -> str:
        """Get the ID of the data."""
        raise NotImplementedError()
