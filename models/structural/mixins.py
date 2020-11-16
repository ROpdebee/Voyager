"""Mixin classes."""

from typing import (
    Callable,
    ClassVar,
    Collection,
    Generic,
    Mapping,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
    cast,
    overload
)

import abc
import re
import weakref

import ansible.playbook as anspb
import ansible as ans

from .base import (
    BaseBlock,
    BaseObject,
    BaseFile,
    BaseTask,
    BaseVariable
)

from .types import KwList, Value

# Any object
ObjectType = TypeVar('ObjectType', bound=BaseObject)

# A variable object
VariableType = TypeVar('VariableType', bound=BaseVariable)

# A block object
BlockType = TypeVar('BlockType', bound=BaseBlock)

# A task object
TaskType = TypeVar('TaskType', bound=BaseTask)

# Any file
FileType = TypeVar('FileType', bound=BaseFile)

# Any parent object
ParentType = TypeVar('ParentType')

# The source of a transformation
SourceType = TypeVar('SourceType')


class ObjectContainerMixin(
        abc.ABC, Generic[SourceType, ObjectType], Sequence[ObjectType]
):
    """Mixin for containers of role objects."""
    def __init__(
            self, *args: object, elements: Collection[SourceType],
            factory: Optional[Callable[[SourceType], ObjectType]] = None,
            **kwargs: object
    ) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[call-arg]
        self._elements: Sequence[ObjectType]

        if factory is None:
            self._elements = tuple((cast(ObjectType, e) for e in elements))
        else:
            self._elements = tuple((factory(e) for e in elements))

    def __len__(self) -> int:
        return len(self._elements)

    @overload
    def __getitem__(self, i: int) -> ObjectType:
        ...

    @overload
    def __getitem__(self, s: slice) -> Sequence[ObjectType]:
        ...

    def __getitem__(
            self, idx: Union[int, slice]
    ) -> Union[ObjectType, Sequence[ObjectType]]:
        return self._elements[idx]


class ChildObjectMixin(Generic[ParentType]):
    """Mixin for role objects with a parent, such as tasks."""
    def __init__(
            self, *args: object, parent: ParentType, **kwargs: object
    ) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[call-arg]
        self._parent = weakref.ref(parent)

    @property
    def parent(self) -> ParentType:
        p = self._parent()
        if p is None:
            raise RuntimeError('parent has been GCed')
        return p


class KeywordsMixin:
    """Mixin for objects accepting base keywords."""

    _interested_kw_names: ClassVar[KwList]
    _misc_kw_names: ClassVar[KwList]

    def __init_subclass__(
            cls,
            ans_type: Type[anspb.base.Base] = anspb.base.Base,
            extra_kws: KwList = set()
    ) -> None:
        new_interested_kws = ((extra_kws | {'name'}) - getattr(
                cls, '_interested_kw_names', set()))
        all_kws = cls.get_all_kws(ans_type)
        assert new_interested_kws.issubset(all_kws)

        for kw_name in new_interested_kws:
            def getter(self: KeywordsMixin, kw_name: str = kw_name) -> object:
                return getattr(self, f'_{kw_name}')
            setattr(cls, kw_name, property(getter))

        cls._interested_kw_names = (
                new_interested_kws
                | getattr(cls, '_interested_kw_names', set()))
        cls._misc_kw_names = (
                (all_kws | getattr(cls, '_misc_kw_names', set()))
                    - cls._interested_kw_names)

    @staticmethod
    def get_all_kws(ans_type: Type[anspb.base.Base]) -> KwList:
        kw_attrs = [
                kw for kw in dir(ans_type)
                if isinstance(
                        getattr(ans_type, kw), anspb.attribute.FieldAttribute)]
        return {m.group(1) for kw in kw_attrs
                if (m := re.match(r'^_*(.+)$', kw)) is not None}

    def get_kw_value(
            self, ds: anspb.base.Base, kw_name: str
    ) -> Optional[Value]:
        val = ds._attributes[kw_name]
        return (self.transform(kw_name, val)
                if val is not ans.utils.sentinel.Sentinel
                else self.get_default(kw_name))

    def get_default(self, name: str) -> Optional[Value]:
        default_factory = getattr(self, f'_{name}_default', lambda: None)
        return cast(Optional[Value], default_factory())

    def transform(self, name: str, val: Value) -> Value:
        transformer = getattr(self, f'_transform_{name}', lambda x: x)
        return cast(Value, transformer(val))

    def __init__(
            self, *args: object, ds: anspb.base.Base, **kwargs: object
    ) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[call-arg]

        for interested_kw_name in self._interested_kw_names:
            setattr(self, f'_{interested_kw_name}',
                    self.get_kw_value(ds, interested_kw_name))

        self._misc_kws: Mapping[str, Value] = {
                kw_name: kw_val for kw_name in self._misc_kw_names
                if (kw_val := self.get_kw_value(ds, kw_name)) is not None}

    @property
    def misc_keywords(self) -> Mapping[str, Value]:
        """Get a mapping of other keywords."""
        return self._misc_kws
