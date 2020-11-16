"""Miscellaneous utilities."""
from typing import (
        Any, ContextManager, Dict, Iterator, List, Optional, Sequence, Tuple,
        Union, TYPE_CHECKING, overload)

import csv
from contextlib import contextmanager
from pathlib import Path

import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from numpy import ndarray
else:
    from typing import List as ndarray


class _ValueMapMeta(type):
    def __setattr__(self, attr_name: str, attr_value: object) -> None:
        raise TypeError('ValueMap and derivatives are immutable.')


class ValueMap(metaclass=_ValueMapMeta):
    """An ABC for classes that contain values. They cannot be instantiated.

    Allows for sort of a static, immutable dict, but with attribute access.
    Also kind of like an Enum, but with direct access to the value.
    """

    def __new__(cls, *args: object, **kwargs: object) -> 'ValueMap':
        """Disallow instantiation."""
        raise TypeError('ValueMap or derivatives cannot be instantiated.')


def underscored_to_dashed(s: str) -> str:
    """Convert underscore attribute name to dashed option name."""
    tokens = s.split('_')
    tokens_no_empty = [token for token in tokens if token]
    return '-'.join(tokens_no_empty)


def capitalized_to_dashed(name: str) -> str:
    """Convert a capitalized name to dashed."""
    return capitalized_to_sep(name, '-').lower()


def capitalized_to_underscored(name: str) -> str:
    """Convert a capitalized name to dashed."""
    return capitalized_to_sep(name, '_').lower()


def capitalized_to_sep(name: str, sep: str) -> str:
    return sep.join(capitalized_to_tokenized(name))


def capitalized_to_tokenized(name: str) -> List[str]:
    """Convert a capitalized name to underscores."""
    if not name:
        return ['']

    tokens = []
    current_token = name[0]

    for char in name[1:]:
        if char.isupper():
            tokens.append(current_token)
            current_token = ''
        current_token += char
    tokens.append(current_token)

    tokens_merged = []
    current_token = tokens[0]
    for token in tokens[1:]:
        if current_token.isupper() and token.isupper():
            current_token += token
        else:
            tokens_merged.append(current_token)
            current_token = token
    tokens_merged.append(current_token)

    return tokens_merged


# The Axes type is missing a lot of stuff we're using here, so set it to Any
# for now.
# TODO(ROpdebee): Fix the type annotations for Axes and specify the correct
# type here. Depends on upstream data-science-types.
_FigAx = Tuple[plt.Figure, Any]
_FigAx1D = Tuple[plt.Figure, ndarray[Any]]
_FigAx2D = Tuple[plt.Figure, ndarray[Any]]


@overload
def plot(
        name: Path, gridspec_kw: Optional[Dict[str, object]] = None,
        **kwargs: object
) -> ContextManager[_FigAx]:
    ...


@overload
def plot(
        name: Path, nrows: int,
        gridspec_kw: Optional[Dict[str, object]] = None, **kwargs: object
) -> ContextManager[_FigAx1D]:
    ...


@overload
def plot(  # type: ignore[misc]
        name: Path, *, ncols: int,
        gridspec_kw: Optional[Dict[str, object]] = None, **kwargs: object
) -> ContextManager[_FigAx1D]:
    ...


@overload
def plot(
        name: Path, nrows: int, ncols: int,
        gridspec_kw: Optional[Dict[str, object]] = None, **kwargs: object
) -> ContextManager[_FigAx2D]:
    ...


@contextmanager  # type: ignore[misc]
def plot(
    path: Path, nrows: int = 1, ncols: int = 1,
    gridspec_kw: Optional[Dict[str, object]] = None,
    **kwargs: object
) -> Union[Iterator[_FigAx], Iterator[_FigAx1D], Iterator[_FigAx2D]]:
    f, axs = plt.subplots(  # type: ignore
        nrows=nrows, ncols=ncols, gridspec_kw=gridspec_kw,
        constrained_layout=True, **kwargs)
    try:
        yield f, axs
    finally:
        path.parent.mkdir(exist_ok=True, parents=True)
        f.savefig(path, dpi=300)


def write_csv(
        out_path: Path, header: Sequence[Any], rows: Sequence[Any]
) -> None:
    with out_path.open('w') as f_csv:
        w = csv.writer(f_csv)
        w.writerow(header)
        w.writerows(rows)
