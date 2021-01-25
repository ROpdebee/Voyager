"""Mixin classes."""

from typing import (
    Any,
    Callable,
    ClassVar,
    Collection,
    Dict,
    Generic,
    Mapping,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
    Protocol
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


# Any file
FileType = TypeVar('FileType', bound=BaseFile)

# Any parent object
ParentType = TypeVar('ParentType')

# Any object which can have a parent
ObjectWithParentType = TypeVar('ObjectWithParentType', bound='_CanSetParent')

# The source of a transformation
SourceType = TypeVar('SourceType')


class _CanSetParent(Protocol):
    @property
    def parent(self) -> Any:
        ...

    @parent.setter
    def parent(self, parent: Any) -> None:
        ...


class ObjectContainerMixin(
        abc.ABC, Sequence[ObjectWithParentType]
):
    """Mixin for containers of role objects."""
    def __init__(
            self, *args: object, elements: Collection[ObjectWithParentType],
            **kwargs: object
    ) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[call-arg]
        self._elements = tuple(elements)
        for e in self._elements:
            e.parent = self

    def __len__(self) -> int:
        return len(self._elements)

    @overload
    def __getitem__(self, i: int) -> ObjectWithParentType:
        ...

    @overload
    def __getitem__(self, s: slice) -> Sequence[ObjectWithParentType]:
        ...

    def __getitem__(
            self, idx: Union[int, slice]
    ) -> Union[ObjectWithParentType, Sequence[ObjectWithParentType]]:
        return self._elements[idx]


class ChildObjectMixin(Generic[ParentType]):
    """Mixin for role objects with a parent, such as tasks."""
    def __init__(
            self, *args: object, **kwargs: object
    ) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[call-arg]
        self._parent: Optional['weakref.ReferenceType[ParentType]'] = None

    @property
    def parent(self) -> ParentType:
        assert self._parent is not None
        p = self._parent()
        if p is None:
            raise RuntimeError('parent has been GCed')
        return p

    @parent.setter
    def parent(self, parent: ParentType) -> None:
        self._parent = weakref.ref(parent)


_KwMixin = TypeVar('_KwMixin', bound='KeywordsMixin')
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

    @classmethod
    def get_kw_value(
            cls, ds: anspb.base.Base, kw_name: str
    ) -> Optional[Value]:
        val = ds._attributes[kw_name]
        return (cls.transform(kw_name, val)
                if val is not ans.utils.sentinel.Sentinel
                else cls.get_default(kw_name))

    @classmethod
    def get_default(cls, name: str) -> Optional[Value]:
        default_factory = getattr(cls, f'_{name}_default', lambda: None)
        return cast(Optional[Value], default_factory())

    @classmethod
    def transform(cls, name: str, val: Value) -> Value:
        transformer = getattr(cls, f'_transform_{name}', lambda x: x)
        return cast(Value, transformer(val))

    def __init__(
            self, *args: object, kws: Dict[str, Value], **kwargs: object
    ) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[call-arg]

        self._raw_kws = kws
        for interested_kw_name in self._interested_kw_names:
            if interested_kw_name in kws:
                kw_value = kws[interested_kw_name]
            else:
                kw_value = self.get_default(interested_kw_name)
            setattr(self, f'_{interested_kw_name}', kw_value)

        self._misc_kws: Mapping[str, Value] = {
                kw_name: kw_val for kw_name in self._misc_kw_names
                if (kw_val := kws.get(kw_name)) is not None}


    @classmethod
    def from_ans_object(cls: Type[_KwMixin], *args: object, ds: anspb.base.Base, **kwargs: object) -> _KwMixin:
        kws: Dict[str, Value] = {}
        for kw_name in (cls._interested_kw_names | cls._misc_kw_names):
            val = cls.get_kw_value(ds, kw_name)
            # HACK: Apparently Ansible doesn't use a sentinel for vars, so even if it's empty, it would be included. Don't want that
            # Putting it here because it affects both Task and Block types.
            if val is not None and kw_name != 'vars' and bool(val):
                kws[kw_name] = val
        return cls(*args, kws=kws, **kwargs)


    def unstructure(self) -> Mapping[str, Value]:
        return self._raw_kws


    @property
    def misc_keywords(self) -> Mapping[str, Value]:
        """Get a mapping of other keywords."""
        return self._misc_kws
