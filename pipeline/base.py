"""Base pipeline stage."""
from typing import (
        Any, ClassVar, Dict, Generic, Iterable, Iterator, Mapping,
        Optional, Protocol, Sequence, Tuple, Type, TypeVar, Union,
        cast, final, get_origin, get_args, TYPE_CHECKING)

import collections.abc
import json
import operator

from abc import ABC, abstractmethod

import cattr
import click

from config import MainConfig
from models import Model
from util import capitalized_to_underscored


IDType = str


class WithID(Protocol):
    """Protocol for data with an ID."""
    @property
    def id(self) -> str:
        """Get the ID for the data."""
        ...


ResultType = TypeVar('ResultType', bound=WithID)
ConfigType = TypeVar('ConfigType', bound=MainConfig)

_converter = cattr.Converter()
_converter.register_structure_hook(
        Model, lambda o, t: t.from_json_obj(o))  # type: ignore[misc]
_converter.register_unstructure_hook(
        Model, operator.methodcaller('to_json_obj'))  # type: ignore[misc]


class CacheMiss(Exception):
    """Raised on cache miss."""


STAGES: Dict[Type['Stage[Any, Any]'], Type[Any]] = {}


class ResultMap(Mapping[str, ResultType]):
    """Result container.

    Contains a mapping from result IDs to """
    _storage: Mapping[IDType, ResultType]

    def __init__(
            self,
            data: Union[Mapping[str, ResultType], Iterable[ResultType]]
    ) -> None:
        """Initialize the result map with pre-existing data.

        The data can either be an iterable (set, list, sequence, ...) of
        results that implement the WithID protocol, or an already existing
        mapping that needs to be copied.
        """
        self._storage = {}

        if isinstance(data, collections.abc.Mapping):
            for k, v in data.items():
                self._storage[k] = v
        elif isinstance(data, collections.abc.Iterable):
            if TYPE_CHECKING:
                # mypy complains since Mapping is a subtype of Iterable and it
                # doesn't seem to understand that it can't be a mapping because
                # of the elif?
                assert not isinstance(data, collections.abc.Mapping)
            for v in data:
                self._storage[v.id] = v
        else:  # pragma: no cover
            raise TypeError('ResultMap data has to be Mapping or Iterable')

    def __iter__(self) -> Iterator[str]:
        """Get an iterator through the mapping."""
        return iter(self._storage)

    def __len__(self) -> int:
        """Get the size of the mapping."""
        return len(self._storage)

    def __getitem__(self, key: str) -> ResultType:
        """Get an item from the mapping."""
        return self._storage[key]

    def unstructure(self) -> Any:
        return _converter.unstructure(self._storage)

    @classmethod
    def structure(cls, obj: object, type_: type) -> 'ResultMap[ResultType]':
        data_type = get_args(type_)[0]
        return cls(_converter.structure(
                obj, Mapping[str, data_type]))  # type: ignore[misc,valid-type]


_converter.register_unstructure_hook(
        ResultMap, operator.methodcaller('unstructure'))
_converter.register_structure_hook(ResultMap[ResultType], ResultMap.structure)


def _extract_type_args_from_subclass(
        klass: Type['Stage[ResultType, ConfigType]']
) -> Optional[Tuple[Type[ResultType], Type[ConfigType]]]:
    try:
        base_type_annos = klass.__orig_bases__  # type: ignore[attr-defined]
    except AttributeError:
        return None

    for base_anno in base_type_annos:
        base = get_origin(base_anno)
        if base is Stage:
            return cast(
                    Tuple[Type[ResultType], Type[ConfigType]],
                    get_args(base_anno))
    # If we reach this, we could not find the type annotation.
    return None


class Stage(ABC, Generic[ResultType, ConfigType]):
    """Base class for pipeline stages.

    Override `run` and `report_results` for custom logic.
    Call `process` as a client.
    """

    # NOTE: `run` isn't included as an abstract method because each stage
    # defines their arguments in terms of their requirements, and that leads
    # to problems with type checking (technically they're not subclasses
    # because the overridden methods aren't co(ntra)variant in their arguments)

    config: ConfigType

    __requires__: ClassVar[Sequence[Type['Stage']]]  # type: ignore[type-arg]

    def __init__(self, config: ConfigType) -> None:
        """Initialize."""
        self.config = config

    @abstractmethod
    def report_results(self, results: ResultMap[ResultType]) -> None:
        """Report the results."""
        ...

    @property
    @abstractmethod
    def cache_file_name(self) -> str:
        """Get the file name for the cache file."""
        raise NotImplementedError()

    @final
    @classmethod
    def process(
            cls, config: ConfigType, dependency: bool = False
    ) -> ResultMap[ResultType]:
        """Process the stage.

        Report results if the report flag is set in the config.
        If the stage was processed previously and its results are cached,
        return the cached results.
        """
        stage = cls(config)
        from_cache = False

        # Always try to load from cache if it's a dependency
        if (config.cache and not config.force) or dependency:
            try:
                results = stage.load_cache_results()
                from_cache = True
            except CacheMiss:
                results = stage._run_with_input()
        else:
            results = stage._run_with_input()

        if config.cache and not from_cache:
            stage.store_cache_results(results)

        if config.report and not (dependency and from_cache):
            stage.report_results(results)

        return results

    @final
    def _run_with_input(self) -> ResultMap[ResultType]:
        """Run the stage, first getting the result of the requirement."""

        # Try getting the results of the requirement stage. Will only work
        # if the results are cached, or when the required configuration is
        # known
        input_data: Dict[str, ResultMap] = {}  # type: ignore[type-arg]
        for req in self.__requires__:
            param_name = capitalized_to_underscored(req.__name__)
            try:
                input_data[param_name] = req.process(
                        self.config, dependency=True)
            except (AttributeError, click.BadParameter) as exc:
                # Issues with the configuration
                name = self.__class__.__name__
                req_name = req.__name__
                raise click.UsageError(
                        f'Stage {name} requires results of Stage {req_name}, '
                        'but the dependency has not been cached and cannot be '
                        'executed due to missing configuration. Re-run with '
                        f'{req_name} OPTIONS... {name} OPTIONS...') from exc

        return cast(
                ResultMap[ResultType],
                self.run(**input_data))  # type: ignore[attr-defined]

    @final
    def store_cache_results(self, results: ResultMap[ResultType]) -> None:
        """Cache the results of a run."""
        cache_path = self.config.output_directory / self.cache_file_name
        try:
            with cache_path.open('w') as f_cache:
                json.dump(
                        results.unstructure(), f_cache,
                        sort_keys=True, indent=4)
        except OSError:  # pragma: no cover
            pass

    @final
    def load_cache_results(self) -> ResultMap[ResultType]:
        """Load the results of a previous run from the cache.

        Raises `CacheMiss` when not found in the cache.
        """
        cache_path = self.config.output_directory / self.cache_file_name
        target_type: Type[ResultType] = self._extract_result_type()
        result_type = Mapping[str, target_type]  # type: ignore[valid-type]
        try:
            with cache_path.open('r') as f_cache:
                # Convert to Dict, then to ResultMap, since cattr tries to take
                # both key and value type args from ResultMap generics
                # otherwise
                return ResultMap(_converter.structure(
                        json.load(f_cache), result_type))  # type: ignore[misc]
        except OSError:
            raise CacheMiss()
        except json.JSONDecodeError as exc:
            print(exc)
            raise CacheMiss()

    @classmethod
    def _extract_result_type(cls) -> Type[ResultType]:
        """Extract the result type through introspection on the subclass."""
        type_args = _extract_type_args_from_subclass(cls)
        # Should already have been checked by init_subclass
        assert type_args is not None and len(type_args) >= 2
        return type_args[0]

    def __init_subclass__(
            cls,
            requires: Union[  # type: ignore[type-arg]
                Sequence['Type[Stage]'], 'Type[Stage]', None] = None
    ) -> None:
        """Register the subclasses as a pipeline stage."""
        super().__init_subclass__()
        type_args = _extract_type_args_from_subclass(cls)
        if type_args is None or not type_args:
            raise TypeError(
                    'Pipeline stage must instantiate type arguments for base '
                    'Stage')
        if not issubclass(type_args[1], MainConfig):
            raise TypeError(
                    'Pipeline stage configuration must be a subtype of '
                    'MainConfig')
        if requires is None:
            requires = []
        if isinstance(requires, type):  # single argument
            requires = (requires, )

        # TODO(ROpdebee): Some type checking of the requirements should be
        #                 performed. Not implemented yet, since there's not
        #                 really an elegant way to parametrize for a variable
        #                 number of types. Maybe check the run method?

        STAGES[cls] = type_args[1]
        cls.__requires__ = requires
