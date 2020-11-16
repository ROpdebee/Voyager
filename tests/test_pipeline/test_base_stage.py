"""Tests for base Stage."""
from typing import Type, TYPE_CHECKING

import json
from enum import Enum
from pathlib import Path

import attr
import click
import pytest
import _pytest

from config import MainConfig
from models.base import Model
import pipeline.base as base
from pipeline.base import CacheMiss, ResultMap, Stage


@attr.s(auto_attribs=True)
class MyModel(Model):
    """Test model for stage result type."""
    number: int
    string: str
    boolean: bool

    @property
    def id(self) -> str:
        return self.string


CACHE_NAME = 'cache.json'
TEST_DATA_CACHE = ResultMap(
        [MyModel(1, 'test', False), MyModel(2, 'test2', True)])
TEST_DATA_RUN = ResultMap(
        [MyModel(3, 'Ran', False), MyModel(4, 'Ran 2', True)])
CONFIG = MainConfig()

# Forward declarations of classes created in fixtures.
if TYPE_CHECKING:
    class MyStage(Stage[MyModel, MainConfig]):
        has_run: bool
        has_reported: bool
        reported_data: ResultMap[MyModel]


@pytest.fixture(scope='function', autouse=True)
def clean_stages() -> None:
    base.STAGES = {}


@pytest.fixture()
def my_stage() -> Type['MyStage']:
    if TYPE_CHECKING:
        return MyStage

    class MyStage(Stage[MyModel, MainConfig]):
        has_run: bool = False
        has_reported: bool = False

        cache_file_name = CACHE_NAME

        reported_data: ResultMap[MyModel] = []

        def run(self) -> ResultMap[MyModel]:
            self.__class__.has_run = True
            return TEST_DATA_RUN

        def report_results(self, results: ResultMap[MyModel]) -> None:
            self.__class__.has_reported = True
            self.__class__.reported_data = results

    return MyStage


class CacheState(Enum):
    ABSENT = 1
    PRESENT = 2
    BROKEN = 3


@pytest.fixture()
def stage_cache(request: _pytest.fixtures.SubRequest, tmp_path: Path) -> Path:
    cache_path = tmp_path / 'test_data' / CACHE_NAME
    cache_path.parent.mkdir()
    cache_state = request.param
    if cache_state is CacheState.BROKEN:
        cache_path.write_text('broken json')
    elif cache_state is CacheState.PRESENT:
        with cache_path.open('w') as f_cache:
            json.dump(
                    {k: v.to_json_obj() for k, v in TEST_DATA_CACHE.items()},
                    f_cache)

    return tmp_path


@pytest.mark.parametrize(
        'stage_cache, cache_miss',
        [
            (CacheState.ABSENT, True),
            (CacheState.PRESENT, False),
            (CacheState.BROKEN, True)],
        indirect=['stage_cache'])
def test_stage_load_cache(
        stage_cache: Path,
        cache_miss: bool,
        my_stage: Type['MyStage']
) -> None:
    config = MainConfig(CONFIG)
    config.dataset = 'test_data'
    config.output = stage_cache
    stage = my_stage(config)

    if cache_miss:
        with pytest.raises(CacheMiss):
            stage.load_cache_results()
    else:
        results = stage.load_cache_results()
        assert results == TEST_DATA_CACHE


def test_stage_store_cache(
        tmp_path: Path,
        my_stage: Type['MyStage']
) -> None:
    config = MainConfig(CONFIG)
    config.dataset = 'test_data'
    config.output = tmp_path
    config.output_directory.mkdir()
    stage = my_stage(config)
    cache_file = config.output_directory / CACHE_NAME

    stage.store_cache_results(TEST_DATA_CACHE)

    assert cache_file.is_file()
    assert (json.loads(cache_file.read_text())
            == {k: v.to_json_obj() for k, v in TEST_DATA_CACHE.items()})


@pytest.mark.parametrize(
        'stage_cache, should_use_cache, should_have_used_cache',
        [
            # If cache option is disabled, cache shouldn't be used
            (CacheState.ABSENT, False, False),
            (CacheState.PRESENT, False, False),
            (CacheState.BROKEN, False, False),
            # Cache option enabled, cache missing -> Run
            (CacheState.ABSENT, True, False),
            # Cache option enabled, cache present -> Use cache
            (CacheState.PRESENT, True, True),
            # Cache option enabled, cache broken -> Run
            (CacheState.BROKEN, True, False)],
        indirect=['stage_cache'])
def test_stage_use_caching(
        stage_cache: Path,
        should_use_cache: bool,
        should_have_used_cache: bool,
        my_stage: Type['MyStage']
) -> None:
    config = MainConfig(CONFIG)
    config.cache = should_use_cache
    config.dataset = 'test_data'
    config.output = stage_cache

    output = my_stage.process(config)

    assert my_stage.has_run != should_have_used_cache
    if should_have_used_cache:
        assert output == TEST_DATA_CACHE
    else:
        assert output == TEST_DATA_RUN

    if should_use_cache:
        cache_path = config.output_directory / CACHE_NAME
        assert cache_path.is_file()
        assert (json.loads(cache_path.read_text())
                == {k: v.to_json_obj() for k, v in output.items()})


@pytest.mark.parametrize('stage_cache', iter(CacheState), indirect=True)
@pytest.mark.parametrize('should_use_cache', [True, False])
@pytest.mark.parametrize('should_report', [True, False])
def test_stage_reporting(
        stage_cache: Path,
        should_use_cache: bool,
        should_report: bool,
        my_stage: Type['MyStage']
) -> None:
    config = MainConfig(CONFIG)
    config.cache = should_use_cache
    config.report = should_report
    config.dataset = 'test_data'
    config.output = stage_cache

    output = my_stage.process(config)

    # Report when it should report
    assert my_stage.has_reported == should_report
    if should_report:
        # Report the correct results based on the cache state
        assert my_stage.reported_data == output

    if should_use_cache:
        cache_path = config.output_directory / CACHE_NAME
        assert cache_path.is_file()
        assert (json.loads(cache_path.read_text())
                == {k: v.to_json_obj() for k, v in output.items()})


def test_extract_type_args(my_stage: Type['MyStage']) -> None:
    type_args = base._extract_type_args_from_subclass(my_stage)

    assert type_args == (MyModel, MainConfig)


def test_extract_type_no_base() -> None:
    class MyStage:
        ...

    type_args = base._extract_type_args_from_subclass(MyStage)  # type: ignore

    assert type_args is None


def test_extract_type_wrong_base() -> None:
    class MyStage(Model):
        ...

    type_args = base._extract_type_args_from_subclass(MyStage)  # type: ignore

    assert type_args is None


@pytest.mark.xfail(
        raises=TypeError,
        reason='Cannot test this, raises type error because missing type '
               'parameters cause the subclassing to fail already.')
def test_extract_type_no_anno() -> None:
    class MyStage(Stage):   # type: ignore
        def run(self) -> ResultMap[MyModel]:
            ...

        def report_results(self, results: ResultMap[MyModel]) -> None:
            ...

        @property
        def cache_file_name(self) -> str:
            ...

    type_args = base._extract_type_args_from_subclass(MyStage)

    assert type_args is None


def test_extract_type_multi_base() -> None:
    class MyStage(Model, Stage[MyModel, MainConfig]):
        def run(self) -> ResultMap[MyModel]:
            ...

        def report_results(self, results: ResultMap[MyModel]) -> None:
            ...

        @property
        def cache_file_name(self) -> str:
            ...

        @property
        def id(self) -> str:
            ...

    type_args = base._extract_type_args_from_subclass(MyStage)

    assert type_args == (MyModel, MainConfig)


def test_extract_type_indirect_base() -> None:
    class IndirectStage(Stage[MyModel, MainConfig]):
        ...

    class MyStage(IndirectStage):
        def run(self) -> ResultMap[MyModel]:
            ...

        def report_results(self, results: ResultMap[MyModel]) -> None:
            ...

        @property
        def cache_file_name(self) -> str:
            ...

    type_args = base._extract_type_args_from_subclass(MyStage)

    assert type_args == (MyModel, MainConfig)


def test_extract_result_type(my_stage: Type['MyStage']) -> None:
    assert my_stage._extract_result_type() == MyModel


def test_subclass_save_config() -> None:
    class MyConfig(MainConfig):
        ...

    class MyStage(Stage[MyModel, MyConfig]):
        def run(self) -> ResultMap[MyModel]:
            ...

        def report_results(self, results: ResultMap[MyModel]) -> None:
            ...

        @property
        def cache_file_name(self) -> str:
            ...

    assert base.STAGES[MyStage] == MyConfig


def test_subclass_wrong_config() -> None:
    class MyConfig:
        ...

    with pytest.raises(TypeError):
        class MyStage(Stage[MyModel, MyConfig]):  # type: ignore
            def run(self) -> ResultMap[MyModel]:
                ...

            def report_results(self, results: ResultMap[MyModel]) -> None:
                ...

            @property
            def cache_file_name(self) -> str:
                ...


def test_subclass_no_anno() -> None:
    with pytest.raises(TypeError):
        class MyStage(Stage):  # type: ignore
            def run(self) -> ResultMap[MyModel]:
                ...

            def report_results(self, results: ResultMap[MyModel]) -> None:
                ...

            @property
            def cache_file_name(self) -> str:
                ...


class FirstStage(Stage[MyModel, MainConfig]):
    def run(self) -> ResultMap[MyModel]:
        return ResultMap(TEST_DATA_RUN)

    def report_results(self, results: ResultMap[MyModel]) -> None:
        ...

    @property
    def cache_file_name(self) -> str:
        return 'test.json'


class NewData(Model):
    _id: str

    @property
    def id(self) -> str:
        return self._id

    def __init__(self, id_: str) -> None:
        self._id = id_


class SecondStage(Stage[NewData, MainConfig]):
    def run(self) -> ResultMap[NewData]:
        return ResultMap([NewData('append'), NewData('test')])

    def report_results(self, results: ResultMap[NewData]) -> None:
        ...

    @property
    def cache_file_name(self) -> str:
        return 'test.json'


class MyConfig(MainConfig):
    option: str


class ThirdStage(Stage[NewData, MyConfig]):
    def run(self) -> ResultMap[NewData]:
        return ResultMap([NewData(self.config.option)])

    def report_results(self, results: ResultMap[NewData]) -> None:
        ...

    @property
    def cache_file_name(self) -> str:
        return 'test.json'


def test_stage_requires() -> None:
    class RequireStage(
            Stage[NewData, MainConfig], requires=FirstStage
    ):
        def run(
                self, first_stage: ResultMap[MyModel]
        ) -> ResultMap[NewData]:
            transformed = [
                NewData(m.string * m.number) for m in first_stage.values()]
            return ResultMap(transformed)

        def report_results(self, results: ResultMap[NewData]) -> None:
            ...

        @property
        def cache_file_name(self) -> str:
            return 'test.json'

    config = MainConfig(CONFIG)
    config.cache = False
    config.report = False
    config.dataset = 'test_data'
    output = RequireStage.process(config)

    assert ([d.id for d in output.values()]
            == ['RanRanRan', 'Ran 2Ran 2Ran 2Ran 2'])


def test_stage_multi_requires() -> None:
    class RequireStage(
            Stage[NewData, MainConfig],
            requires=[FirstStage, SecondStage]
    ):
        def run(
                self,
                first_stage: ResultMap[MyModel],
                second_stage: ResultMap[NewData]
        ) -> ResultMap[NewData]:
            transformed = []
            for m in first_stage.values():
                for n in second_stage.values():
                    transformed.append(NewData(m.string + ' ' + n.id))

            return ResultMap(transformed)

        def report_results(self, results: ResultMap[NewData]) -> None:
            ...

        @property
        def cache_file_name(self) -> str:
            return 'test.json'

    config = MainConfig(CONFIG)
    config.cache = False
    config.report = False
    config.dataset = 'test_data'
    output = RequireStage.process(config)

    assert ([d.id for d in output.values()]
            == ['Ran append', 'Ran test', 'Ran 2 append', 'Ran 2 test'])


def test_stage_requires_wrong_config() -> None:
    class RequireStage(Stage[NewData, MainConfig], requires=ThirdStage):
        def run(self, third_stage: ResultMap[NewData]) -> ResultMap[NewData]:
            ...

        def report_results(self, results: ResultMap[NewData]) -> None:
            ...

        @property
        def cache_file_name(self) -> str:
            return 'test.json'

    config = MainConfig(CONFIG)
    config.cache = False
    config.report = False
    config.dataset = 'test_data'

    with pytest.raises(click.UsageError):
        RequireStage.process(config)
