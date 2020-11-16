"""CLI interface utilities."""
from typing import (
        Callable, Dict, Generic, NamedTuple, Optional, Type, TypedDict,
        TypeVar, Union, cast, get_args, get_origin, get_type_hints, overload,
        TYPE_CHECKING)

import functools
import inspect

import click
import click.core

from util.misc import capitalized_to_dashed, underscored_to_dashed
from util.config import Config, Option
if TYPE_CHECKING:
    from config import MainConfig
    from pipeline.base import Stage, ResultMap, ResultType
else:
    MainConfig = 'MainConfig'
    ResultType = TypeVar('ResultType')

    class DummyMeta(type):
        """Dummy meta class."""

        def __getitem__(self, name: str) -> object:
            """Prevent subscript errors."""
            return None

    class Stage(metaclass=DummyMeta):
        """Dummy stage class to prevent circular imports."""

        pass

    class ResultMap(Generic[ResultType]):
        """Dummy result map to prevent circular imports."""

        pass


_ConfigType = TypeVar('_ConfigType', bound=MainConfig)
_OptionType = TypeVar('_OptionType')
_ResultType = TypeVar('_ResultType')

_MainCommandType = Callable[[_ConfigType], None]
_SubCommandType = Callable[[_ConfigType], ResultMap[ResultType]]
_CommandType = Union[
        _MainCommandType[_ConfigType],
        _SubCommandType[_ConfigType, ResultType]]
_MainWrapperType = Callable[[click.Context], None]
_SubWrapperType = Callable[[click.Context], ResultMap[ResultType]]
_WrapperType = Union[
        _MainWrapperType,
        _SubWrapperType[ResultType]]


class _ConfigOption(NamedTuple, Generic[_OptionType]):
    name: str
    type_: _OptionType
    option: Option[_OptionType]


class _OptionKwargs(TypedDict, total=False):
    help: str


def register_command(
        command: _MainCommandType[_ConfigType]
) -> click.core.Group:
    """Register main commands for the CLI program."""
    config_type = _get_configuration_type(command)

    wrapper = _create_cli_option_wrapper(command, config_type)
    wrapper = click.group(chain=True)(wrapper)

    return wrapper


def register_subcommand(
        parent_command: click.core.Group,
        config_type: Type[_ConfigType],
        stage: Type[Stage[ResultType, _ConfigType]]
) -> _WrapperType[ResultType]:
    """Register a subcommand to a main command."""
    command_name = capitalized_to_dashed(stage.__name__).lower()
    wrapper = _create_cli_option_wrapper(stage.process, config_type)
    help_text = stage.__doc__
    return parent_command.command(
            name=command_name, help=help_text)(wrapper)


@overload
def _create_cli_option_wrapper(
        f: _MainCommandType[_ConfigType],
        config_type: Type[_ConfigType]
) -> _MainWrapperType:
    ...


@overload
def _create_cli_option_wrapper(
        f: _SubCommandType[_ConfigType, ResultType],
        config_type: Type[_ConfigType]
) -> _SubWrapperType[ResultType]:
    ...


def _create_cli_option_wrapper(
        f: _CommandType[_ConfigType, ResultType],
        config_type: Type[_ConfigType]
) -> _WrapperType[ResultType]:
    """Create any wrapper."""
    config_options = _get_configuration_options(config_type)

    @functools.wraps(f)
    def wrapper(
            ctx: click.Context,
            **kwargs: object
    ) -> Optional[ResultMap[ResultType]]:
        return f(_args_to_config(ctx, config_type, config_options, **kwargs))

    for config_option in config_options.values():
        wrapper = _wrap_function_for_option(wrapper, config_option)

    wrapper = click.pass_context(wrapper)
    return wrapper


def _get_configuration_type(
        f: _MainCommandType[_ConfigType]
) -> Type[_ConfigType]:
    """Get the configuration type from a command function.

    Configurations are expected to be the first parameter to the function.
    """
    sig = inspect.signature(f)
    try:
        first_param = sig.parameters[next(iter(sig.parameters))]
        anno = first_param.annotation
    except (StopIteration, KeyError):
        raise TypeError(
                'Function without arguments cannot be used as a command')
    if anno is first_param.empty:
        raise TypeError(
                'Function needs to be type-annotated to be used as a command')

    if not issubclass(anno, Config):
        raise TypeError(
                'Function needs to take configuration as first argument')

    return cast(Type[_ConfigType], anno)


def _get_configuration_options(
        configuration_type: Type[_ConfigType]
) -> Dict[str, _ConfigOption]:
    """Extract the configuration options from a configuration class."""
    config_options: Dict[str, _ConfigOption] = {}

    for opt_name, opt_type in get_type_hints(configuration_type).items():
        if get_origin(opt_type) is not Option:
            continue
        opt = getattr(configuration_type, opt_name)
        # Ignore options that cannot be overridden in the sub-configuration
        if opt.final and opt.class_inherits_option(configuration_type):
            continue

        type_ = get_args(opt_type)[0]
        if opt.click_type is not None:
            type_ = opt.click_type
        config_options[opt_name] = _ConfigOption(opt_name, type_, opt)

    return config_options


def _wrap_function_for_option(
        f: _WrapperType[ResultType],
        config_option: _ConfigOption
) -> _WrapperType[ResultType]:
    """Wrap a command wrapper with a click argument parser."""
    option_name = underscored_to_dashed(config_option.name)

    # Create a partial wrapper that already incorporates the option name and
    # the type, add keywords for the common arguments later.
    if config_option.type_ is bool:
        part = _create_partial_wrapper_for_flag(f, config_option, option_name)
    else:
        def part(kwargs: _OptionKwargs) -> _WrapperType[ResultType]:
            return click.option(
                    f'--{option_name}', type=config_option.type_, **kwargs)(f)

    _, _, option = config_option
    help_text = option.help_text
    if not option.has_default:
        help_text += ' (required)'
    kwargs = _OptionKwargs(help=help_text)
    return part(kwargs)


def _create_partial_wrapper_for_flag(
        f: _WrapperType[ResultType], option: _ConfigOption, option_name: str
) -> Callable[[_OptionKwargs], _WrapperType[ResultType]]:
    """Create a partial wrapper for a flag option."""
    flag_name = f'--{option_name}/--no-{option_name}'

    def part(kwargs: _OptionKwargs) -> _WrapperType[ResultType]:
        return click.option(
            # Set default to None so we can distinguish between flags that have
            # been set by the user, and flags that haven't been set and should
            # be inherited from the parent configuration.
            # Don't change type to the boolean type, for some reason it chooses
            # a bad overload and resolves click.option to Any -> Any, making
            # the returned function untyped.
            flag_name, type=option.type_, default=None, **kwargs)(f)

    return part


def _args_to_config(
        ctx: click.Context, config_type: Type[_ConfigType],
        config_options: Dict[str, _ConfigOption], **kwargs: object
) -> _ConfigType:
    """Create a configuration object from the arguments."""
    # Create configuration or extend the existing one.
    cfg = config_type(ctx.obj)

    # Set the configuration values
    for opt_name, opt_value in kwargs.items():
        # Skip parameters that haven't been set in this command
        if opt_value is None:
            continue

        _, _, option = config_options[opt_name]
        if option.converter is not None:
            opt_value = option.converter(opt_value)

        setattr(cfg, opt_name, opt_value)

    ctx.obj = cfg
    return cfg
