"""Tests for CLI utilities."""
from typing import Callable, Optional, Type

import pathlib

import click
import click.testing
import pytest

import pipeline.base
from pipeline.base import ResultMap
import util.cli as cli
from util.config import Option
from config import DiscoverConfig, MainConfig


def config_main(config: MainConfig) -> None:
    ...


def config_disc(config: DiscoverConfig) -> None:
    ...


def config_no_anno(config):  # type: ignore
    ...


def config_no_param() -> None:
    ...


def config_wrong_type(config: str) -> None:
    ...


class DummyResult:
    id: str

    def __init__(self, id_: str) -> None:
        self.id = id_


@pytest.mark.parametrize('config_fun, config_type', [
    (config_main, MainConfig),
    (config_disc, DiscoverConfig)])
def test_get_config_type(
        config_fun: Callable[[MainConfig], None],
        config_type: Type[MainConfig]
) -> None:
    assert cli._get_configuration_type(config_fun) is config_type


@pytest.mark.parametrize('config_fun', [
        config_no_anno, config_no_param, config_wrong_type])
def test_get_config_type_error(
        config_fun: Callable[[MainConfig], None]
) -> None:
    with pytest.raises(TypeError):
        print(cli._get_configuration_type(config_fun))


opt1_: Option[bool] = Option('help value')
opt2_: Option[str] = Option('help value 2')


class MyConfig(MainConfig):
    opt1: Option[bool] = opt1_
    opt2: Option[str] = opt2_


def test_get_config_options_main() -> None:
    opts = cli._get_configuration_options(MainConfig)
    assert (sorted([
                'progress', 'report', 'cache', 'dataset', 'output', 'force'])
            == sorted(opts.keys()))
    assert (sorted([
                'progress', 'report', 'cache', 'dataset', 'output', 'force'])
            == sorted(opt.name for opt in opts.values()))
    assert not ({bool, str} - {opt.type_ for opt in opts.values()})
    # click.Path parameter type in MainConfig
    assert {opt.type_ for opt in opts.values()
            if isinstance(opt.type_, click.Path)}


def test_get_config_options_sub() -> None:
    # No dataset in the comparison, since dataset is final and is filtered out
    opts = cli._get_configuration_options(MyConfig)
    assert (sorted(['opt1', 'opt2', 'progress', 'report', 'cache', 'force'])
            == sorted(opts.keys()))
    assert (sorted(['opt1', 'opt2', 'progress', 'report', 'cache', 'force'])
            == sorted(opt.name for opt in opts.values()))
    assert ({bool, str} == {opt.type_ for opt in opts.values()})


def test_args_to_config_normal() -> None:
    # Always recreate context since it is modified destructively and the tests
    # will be flaky
    ctx = click.Context(click.Command('test'), obj=None)
    config_options = cli._get_configuration_options(MyConfig)
    cfg = cli._args_to_config(
            ctx, MyConfig, config_options, opt1=True, opt2='hello')

    assert cfg.opt1
    assert cfg.opt2 == 'hello'


def test_args_to_config_arg_not_given() -> None:
    ctx = click.Context(click.Command('test'), obj=None)
    config_options = cli._get_configuration_options(MyConfig)
    cfg = cli._args_to_config(
            ctx, MyConfig, config_options, opt1=None, opt2='hello')

    assert cfg.opt2 == 'hello'
    with pytest.raises(click.BadParameter):
        assert cfg.opt1


def test_args_to_config_sub_config() -> None:
    main = MainConfig()
    ctx = click.Context(click.Command('test'), obj=main)
    config_options = cli._get_configuration_options(MyConfig)
    cfg = cli._args_to_config(
            ctx, MyConfig, config_options, opt1=False, opt2='hello',
            cache=False)

    assert not cfg.opt1
    assert cfg.opt2 == 'hello'
    # Defaults set by main config
    assert not cfg.report
    assert not cfg.progress
    # Option overridden
    assert not cfg.cache
    assert main.cache


def test_args_to_config_converter() -> None:
    ctx = click.Context(click.Command('test'), obj=None)
    config_options = cli._get_configuration_options(MainConfig)
    cfg = cli._args_to_config(
            ctx, MainConfig, config_options, progress=True, output='.')

    # Defaults set by main config
    assert not cfg.report
    assert cfg.cache
    # Option overridden
    assert cfg.progress
    assert isinstance(cfg.output, pathlib.Path)
    assert cfg.output == pathlib.Path('.')


class DummyCommandResult:
    cmd: click.Group
    config: Optional[MainConfig] = None


@pytest.fixture()
def dummy_command() -> DummyCommandResult:
    res = DummyCommandResult()

    @cli.register_command
    def tester(cfg: MainConfig) -> None:
        nonlocal res
        res.config = cfg

    res.cmd = tester
    return res


def test_create_command_no_args(dummy_command: DummyCommandResult) -> None:
    runner = click.testing.CliRunner()
    result = runner.invoke(dummy_command.cmd)

    print(result.output)
    print(result.exception)
    print(result.exc_info)
    assert not result.exit_code
    assert 'tester' in result.output
    assert '--progress' in result.output


def test_create_command_help(dummy_command: DummyCommandResult) -> None:
    runner = click.testing.CliRunner()
    result = runner.invoke(dummy_command.cmd, '--help')

    print(result.output)
    print(result.exception)
    print(result.exc_info)
    assert not result.exit_code
    assert 'tester' in result.output
    assert '--progress' in result.output


def test_create_command_args(dummy_command: DummyCommandResult) -> None:
    was_run = False

    @dummy_command.cmd.command()
    def dummy() -> None:
        nonlocal was_run
        was_run = True
        print('Test success 123')

    runner = click.testing.CliRunner()
    result = runner.invoke(
            dummy_command.cmd,
            [
                '--dataset=testset', '--progress', '--report', '--no-cache',
                'dummy'])

    print(result.output)
    print(result.exception)
    print(result.exc_info)
    assert not result.exit_code
    assert was_run
    assert 'Test success 123' in result.output
    assert dummy_command.config is not None
    assert dummy_command.config.progress
    assert dummy_command.config.report
    assert not dummy_command.config.cache
    assert dummy_command.config.dataset == 'testset'
    assert dummy_command.config.output == pathlib.Path('data')
    assert (dummy_command.config.output_directory
            == pathlib.Path('data', 'testset'))


class DummyStage(pipeline.base.Stage[DummyResult, MyConfig]):
    """A dummy stage."""
    was_run: bool = False
    save_config: Optional[MyConfig] = None

    def __init__(self, cfg: MyConfig) -> None:
        self.__class__.save_config = cfg

    def run(self) -> ResultMap[DummyResult]:
        self.__class__.was_run = True
        return ResultMap([DummyResult('test')])

    def report_results(self, results: ResultMap[DummyResult]) -> None:
        ...

    @property
    def cache_file_name(self) -> str:
        ...


@pytest.fixture()
def dummy_sub(dummy_command: DummyCommandResult) -> None:
    DummyStage.was_run = False
    DummyStage.save_config = None
    cli.register_subcommand(dummy_command.cmd, MyConfig, DummyStage)


def test_create_subcommand(
        dummy_command: DummyCommandResult, dummy_sub: None
) -> None:
    runner = click.testing.CliRunner()
    result = runner.invoke(dummy_command.cmd)

    print(result.output)
    print(result.exception)
    print(result.exc_info)
    assert not result.exit_code
    assert 'dummy-stage' in result.output
    assert 'A dummy stage' in result.output


def test_create_subcommand_help(
        dummy_command: DummyCommandResult, dummy_sub: None
) -> None:
    runner = click.testing.CliRunner()
    result = runner.invoke(
            dummy_command.cmd,
            ['--dataset=testset', 'dummy-stage', '--help'])

    print(result.output)
    print(result.exception)
    print(result.exc_info)
    assert not result.exit_code
    assert 'dummy-stage' in result.output
    assert 'A dummy stage' in result.output
    assert '--opt1' in result.output


def test_create_subcommand_args(
        dummy_command: DummyCommandResult, dummy_sub: None
) -> None:
    runner = click.testing.CliRunner()
    result = runner.invoke(
            dummy_command.cmd,
            [
                '--dataset=testset', '--no-cache',
                'dummy-stage', '--no-opt1', '--opt2=xargs'])

    print(result.output)
    print(result.exception)
    print(result.exc_info)
    assert not result.exit_code
    assert DummyStage.was_run
    assert DummyStage.save_config is not None
    assert not DummyStage.save_config.opt1
    assert DummyStage.save_config.opt2 == 'xargs'


def test_create_subcommand_override(
        dummy_command: DummyCommandResult, dummy_sub: None
) -> None:
    runner = click.testing.CliRunner()
    result = runner.invoke(
            dummy_command.cmd,
            [
                '--dataset=testset', '--no-cache', '--no-progress',
                'dummy-stage', '--no-opt1', '--opt2=xargs', '--progress'])

    print(result.output)
    print(result.exception)
    print(result.exc_info)
    assert not result.exit_code
    assert DummyStage.was_run
    assert DummyStage.save_config is not None
    assert not DummyStage.save_config.opt1
    assert DummyStage.save_config.opt2 == 'xargs'
    assert DummyStage.save_config.progress
