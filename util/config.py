"""Configuration utilities."""
from typing import (
        Any, Callable, Final, Generic, List, MutableMapping, Optional, TypeVar,
        Type, Union, overload, TYPE_CHECKING)

import click

from weakref import WeakKeyDictionary

_OptionType = TypeVar('_OptionType')
_ConfigType = TypeVar('_ConfigType', bound='Config')

DefaultFactoryType = Callable[[], _OptionType]
ConverterFunction = Callable[[Any], _OptionType]

if TYPE_CHECKING:
    ClickType = click.core._ConvertibleType
else:
    ClickType = object


class Option(Generic[_OptionType]):
    """Configuration options implementing the descriptor protocol.

    Configuration options contain the help text and type of the option.
    """

    help_text: Final[str]
    default: Optional[_OptionType]
    default_factory: Optional[DefaultFactoryType[_OptionType]]
    final: Final[bool]
    click_type: Optional[ClickType]
    converter: Optional[ConverterFunction[_OptionType]]

    _value_map: MutableMapping[object, _OptionType]

    def __init__(
            self, help_txt: str,
            default: Optional[_OptionType] = None,
            default_factory: Optional[DefaultFactoryType[_OptionType]] = None,
            click_type: Optional[ClickType] = None,
            converter: Optional[ConverterFunction[_OptionType]] = None,
            final: bool = False
    ) -> None:
        """Initialize with a help text.

        :param help_txt: The help text describing the option.
        :param default: A default value to use for the option, if absent.
        :param default_factory: A factory method for a default value.
        :param click_type: The click type to use in option parsing.
        :param converter: A conversion function to convert the click type into
                          the type of the option.
        :param final: Whether or not the option is final. If final, it cannot
                      be overridden by a subclassing configuration.
        """
        if (default is not None
                and default_factory is not None):
            raise TypeError(
                    'default and default_factory are mutually exclusive')

        if ((click_type is not None and converter is None)
                or (click_type is None and converter is not None)):
            raise TypeError(
                    'Either all of or none of click_type and converter need '
                    'to be specified')

        self.help_text = help_txt
        self.default = default
        self.default_factory = default_factory
        self.final = final
        self.click_type = click_type
        self.converter = converter

        self._value_map = WeakKeyDictionary()

    @overload
    def __get__(self, obj: None, owner: type) -> 'Option[_OptionType]':
        """See below."""
        ...

    @overload
    def __get__(
            self, obj: _ConfigType, owner: Type[_ConfigType]
    ) -> _OptionType:
        """See below."""
        ...

    def __get__(
            self, obj: Optional[_ConfigType],
            owner: Optional[Type[_ConfigType]]
    ) -> 'Union[Option[_OptionType], _OptionType]':
        """Get part of the descriptor protocol."""
        if obj is None:
            return self

        if obj not in self._value_map:
            if obj._parent_cfg is not None:
                return self.__get__(obj._parent_cfg, obj._parent_cfg.__class__)
            if self.default is not None:
                return self.default
            if self.default_factory is not None:
                default = self.default_factory()
                self._value_map[obj] = default
                return default

            raise click.BadParameter(
                    'This option is required.',
                    param_hint=f'--{self._get_attr_name(obj)}')

        return self._value_map[obj]

    def __set__(self, obj: _ConfigType, value: _OptionType) -> None:
        """Set part of the descriptor protocol."""
        if self.final and self.object_inherits_option(obj):
            raise AttributeError('Attribute is final')

        self._value_map[obj] = value

    def object_inherits_option(self, obj: _ConfigType) -> bool:
        """Check whether the given object inherits this option."""
        return self.class_inherits_option(obj.__class__)

    def class_inherits_option(self, cls: Type[_ConfigType]) -> bool:
        """Check whether the given class inherits this option."""
        for base in cls.__bases__:
            for attr in dir(base):
                if getattr(base, attr) is self:
                    return True
        return False

    def _get_attr_name(self, obj: _ConfigType) -> str:
        """Get the name of the attribute through introspection."""
        for attr_name in dir(obj.__class__):
            if getattr(obj.__class__, attr_name) is self:
                return attr_name
        raise TypeError('Cannot find attribute in object')

    @property
    def has_default(self) -> bool:
        """Check whether the option has a default value."""
        return self.default is not None or self.default_factory is not None


class Config:
    """Base class for configurations."""

    _parent_cfg: Optional['Config']

    def __init__(self, parent: Optional['Config'] = None) -> None:
        """Initialize."""
        self._parent_cfg = parent

    @classmethod
    def get_all_option_names(cls) -> List[str]:
        """Get all options defined in the configuration."""
        return [opt_name for opt_name in dir(cls)
                if isinstance(getattr(cls, opt_name), Option)]
