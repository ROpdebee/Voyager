"""Tests for util."""

import pytest

from util import (
        ValueMap, capitalized_to_dashed, capitalized_to_underscored,
        underscored_to_dashed)


class ValueMapTest(ValueMap):
    test1 = 'Test 1'
    test3 = 'Another test string'


def test_valuemap_get_values() -> None:
    assert ValueMapTest.test1 == 'Test 1'
    assert ValueMapTest.test3 == 'Another test string'
    with pytest.raises(AttributeError):
        ValueMapTest.test2  # type: ignore


def test_valuemap_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        ValueMapTest('test')


def test_valuemap_is_immutable() -> None:
    with pytest.raises(TypeError):
        ValueMapTest.test1 = 'Changed test'

    assert ValueMapTest.test1 != 'Changed test'


def test_valuemap_is_immutable_add_attr() -> None:
    with pytest.raises(TypeError):
        ValueMapTest.test2 = 'Added test 2'

    assert not hasattr(ValueMapTest, 'test2')


@pytest.mark.parametrize('inp, expected', [
    ('', ''),
    ('Test', 'test'),
    ('test', 'test'),
    ('Test123', 'test123'),
    ('TestAgain', 'test_again'),
    ('Test,Test', 'test,_test'),
    ('TestTestTest', 'test_test_test'),
    ('DiscoverStage', 'discover_stage'),
    ('ABTest', 'ab_test'),
    ('AB', 'ab'),
    ('TestABC', 'test_abc')])
def test_capitalize_to_underscores(inp: str, expected: str) -> None:
    assert capitalized_to_underscored(inp) == expected


@pytest.mark.parametrize('inp, expected', [
    ('', ''),
    ('Test', 'test'),
    ('test', 'test'),
    ('Test123', 'test123'),
    ('TestAgain', 'test-again'),
    ('Test,Test', 'test,-test'),
    ('TestTestTest', 'test-test-test'),
    ('DiscoverStage', 'discover-stage'),
    ('ABTest', 'ab-test'),
    ('AB', 'ab'),
    ('TestABC', 'test-abc')])
def test_capitalize_to_dashed(inp: str, expected: str) -> None:
    assert capitalized_to_dashed(inp) == expected


@pytest.mark.parametrize('underscores, dashed', [
    ('test_option', 'test-option'),
    ('test', 'test'),
    ('_test', 'test'),
    ('_test_test', 'test-test'),
    ('test__test', 'test-test'),
    ('__magic__', 'magic'),
    ('type_', 'type'),
    ('type__', 'type'),
    ('very_long_test', 'very-long-test')])
def test_underscored_to_dashed(underscores: str, dashed: str) -> None:
    assert underscored_to_dashed(underscores) == dashed
