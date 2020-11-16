"""Tests for configurations."""
from typing import Any, List

from pathlib import Path

import click
import pytest

from util.config import Config, Option

HELP_TEXT_BOOL = 'Help text for test option'
HELP_TEXT_LIST = 'Help text for list test option'
HELP_TEXT_SUB = 'Help text for subconfig'


class ConfigTest(Config):
    """Test configuration."""
    test_option: Option[bool] = Option(
            HELP_TEXT_BOOL, default=False, final=True)
    test_list_option: Option[List[int]] = Option(
            HELP_TEXT_LIST, default_factory=list)
    test_no_default: Option[int] = Option('For a test')


class SubConfigTest(ConfigTest):
    """Test subconfiguration."""
    test_new_option: Option[str] = Option(HELP_TEXT_SUB, default='test')


def test_option_default() -> None:
    c = ConfigTest()

    assert not c.test_option


def test_option_default_factory() -> None:
    c = ConfigTest()

    assert isinstance(c.test_list_option, list)
    assert not c.test_list_option

    c.test_list_option.append(1)

    assert c.test_list_option[0] == 1


def test_option_nonexistent_attr() -> None:
    c = ConfigTest()

    with pytest.raises(AttributeError):
        _ = c.doesnt_exist  # type: ignore


def test_option_undef_attr_set() -> None:
    c = ConfigTest()
    c.test_no_default = 0

    assert c.test_no_default == 0


def test_option_undef_attr() -> None:
    c = ConfigTest()

    with pytest.raises(click.BadParameter):
        _ = c.test_no_default


def test_set_option() -> None:
    c = ConfigTest()
    c.test_option = True
    c.test_list_option = [1, 2, 3]

    assert c.test_option
    assert c.test_list_option == [1, 2, 3]


def test_subconfig_inherits_parent_options() -> None:
    c = ConfigTest()
    c.test_list_option = [1, 2, 3]
    s = SubConfigTest(c)

    # New option
    assert s.test_new_option == 'test'
    # Inherited option with default
    assert not s.test_option
    # Inherited option that has been set
    assert s.test_list_option == [1, 2, 3]


def test_config_override() -> None:
    c1 = ConfigTest()
    c1.test_list_option = [1, 2, 3]
    c1.test_option = False
    c1.test_no_default = 10
    c2 = ConfigTest(c1)
    c2.test_option = True

    assert c1.test_list_option == [1, 2, 3]
    assert not c1.test_option
    assert c1.test_no_default == 10
    # Overridden options
    assert c2.test_option
    # Inherited options
    assert c2.test_list_option == [1, 2, 3]
    assert c2.test_no_default == 10


def test_option_nonfinal_option() -> None:
    s = SubConfigTest()
    s.test_list_option = [1, 2, 3]

    assert s.test_list_option == [1, 2, 3]


def test_option_nonfinal_option_extend() -> None:
    c = ConfigTest()
    s = SubConfigTest(c)
    old_list = c.test_list_option
    s.test_list_option = [1, 2, 3]

    assert s.test_list_option == [1, 2, 3]
    assert c.test_list_option is old_list


def test_option_final_option() -> None:
    s = SubConfigTest()

    with pytest.raises(AttributeError):
        s.test_option = True


def test_option_help() -> None:
    assert ConfigTest.test_option.help_text == HELP_TEXT_BOOL
    assert ConfigTest.test_list_option.help_text == HELP_TEXT_LIST


def test_subconfig_option_help() -> None:
    assert (SubConfigTest.test_option.help_text
            == ConfigTest.test_option.help_text)


def test_converter() -> None:
    with pytest.raises(TypeError):
        class Wrong(Config):
            conv: Option[str] = Option('bla', converter=str)

    with pytest.raises(TypeError):
        class WrongAgain(Config):
            conv: Option[Path] = Option('bla', click_type=str)

    class Correct(Config):
        conv: Option[Path] = Option('bla', click_type=str, converter=Path)


def test_multi_default() -> None:
    with pytest.raises(TypeError):
        def partial_option(**kwargs: Any) -> Option[str]:
            return Option('bla', default='test', **kwargs)

        class Wrong(Config):
            conv = partial_option(default='again')

    with pytest.raises(TypeError):
        def partial_option(**kwargs: Any) -> Option[str]:
            return Option('bla', default_factory=str, **kwargs)

        class WrongAgain(Config):
            conv = partial_option(
                    default_factory=lambda: 'test')  # pragma: no cover

    with pytest.raises(TypeError):
        class WrongAgainAgain(Config):
            conv: Option[Path] = Option(
                    'bla', default=Path('test'), default_factory=Path)


def test_has_default() -> None:
    assert ConfigTest.test_option.has_default
    assert ConfigTest.test_list_option.has_default
    assert not ConfigTest.test_no_default.has_default


def test_get_names() -> None:
    assert (list(sorted(ConfigTest.get_all_option_names()))
            == ['test_list_option', 'test_no_default', 'test_option'])


def test_get_attr_name() -> None:
    c = ConfigTest()

    assert ConfigTest.test_option._get_attr_name(c) == 'test_option'


def test_get_attr_name_nonexistent() -> None:
    c = ConfigTest()
    o: Option[bool] = Option('test option')

    with pytest.raises(TypeError):
        o._get_attr_name(c)
