"""Tests for base models."""
from typing import List

import attr

from models.base import Model


@attr.s(auto_attribs=True)
class DummyModel(Model):
    a: str
    b: int
    c: List[bool]

    @property
    def id(self) -> str:
        ...


@attr.s(auto_attribs=True)
class DummySuperModel(Model):
    dummy: DummyModel
    dummySet: List[DummyModel]
    x: float

    @property
    def id(self) -> str:
        ...


def test_nonnested_model_inst() -> None:
    d = DummyModel('Hello world', 10, [True, False, True])

    assert d.a == 'Hello world'
    assert d.b == 10
    assert d.c == [True, False, True]

    d.a = 'Changed'
    assert d.a == 'Changed'


def test_nonnested_model_serialize_obj() -> None:
    d = DummyModel('Hello world', 10, [True, False, True])

    assert DummyModel.from_json_obj(d.to_json_obj()) == d


def test_nonnested_model_serialize_str() -> None:
    d = DummyModel('Hello world', 10, [True, False, True])

    assert DummyModel.from_json_str(d.to_json_str()) == d


def test_nested_model_inst() -> None:
    d = DummyModel('Hello world', 10, [True, False, True])
    d2 = DummyModel('xyz', 2, [])
    d3 = DummyModel('abc', 1234, [False])
    n = DummySuperModel(d, [d2, d3], 3.1415)

    assert n.dummy == d
    assert n.dummy.a == 'Hello world'
    assert len(n.dummySet) == 2
    assert d2 in n.dummySet
    assert d3 in n.dummySet
    assert n.x == 3.1415

    n.dummy.a = 'Changed'
    assert n.dummy.a == 'Changed'
    assert d.a == 'Changed'


def test_nested_model_serialize_obj() -> None:
    d = DummyModel('Hello world', 10, [True, False, True])
    d2 = DummyModel('xyz', 2, [])
    d3 = DummyModel('abc', 1234, [False])
    n = DummySuperModel(d, [d2, d3], 3.1415)

    assert DummySuperModel.from_json_obj(n.to_json_obj()) == n


def test_nested_model_serialize_str() -> None:
    d = DummyModel('Hello world', 10, [True, False, True])
    d2 = DummyModel('xyz', 2, [])
    d3 = DummyModel('abc', 1234, [False])
    n = DummySuperModel(d, [d2, d3], 3.1415)

    assert DummySuperModel.from_json_str(n.to_json_str()) == n
