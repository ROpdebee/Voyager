"""Tests for ResultMap."""
from typing import List

import attr
import pytest

from pipeline.base import ResultMap


@attr.s(auto_attribs=True)
class Data:
    id: str
    val: int


DATA = [Data('test', 1), Data('tset', -1)]


def test_init() -> None:
    my_dict = {d.id: d for d in DATA}

    rm1: ResultMap[Data] = ResultMap(my_dict)
    rm2: ResultMap[Data] = ResultMap(DATA)

    assert rm1 == rm2


@pytest.mark.parametrize('data', [DATA, []])
def test_len(data: List[Data]) -> None:
    rm: ResultMap[Data] = ResultMap(data)

    assert len(rm) == len(data)


@pytest.mark.parametrize('data', [DATA, []])
def test_iter(data: List[Data]) -> None:
    rm: ResultMap[Data] = ResultMap(data)

    keys = set()
    for k in rm:
        keys.add(k)

    assert keys == {d.id for d in data}


def test_get_item() -> None:
    rm: ResultMap[Data] = ResultMap(DATA)

    assert rm['test'] == DATA[0]
    assert rm['tset'] == DATA[1]


def test_get_empty() -> None:
    rm: ResultMap[Data] = ResultMap([])

    with pytest.raises(KeyError):
        rm['test']


def test_get_nonexistant() -> None:
    rm: ResultMap[Data] = ResultMap(DATA)

    with pytest.raises(KeyError):
        rm['doesnt_exist']


def test_unstructure() -> None:
    rm = ResultMap(DATA)

    d = rm.unstructure()

    assert d == {
        'test': {'id': 'test', 'val': 1},
        'tset': {'id': 'tset', 'val': -1}}


def test_structure() -> None:
    d = {
        'test': {'id': 'test', 'val': 1},
        'tset': {'id': 'tset', 'val': -1}}

    rm: ResultMap[Data] = ResultMap.structure(d, ResultMap[Data])

    assert rm == ResultMap(DATA)
