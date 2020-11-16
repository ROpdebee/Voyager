"""Serialization utilities."""
from typing import cast

import operator

from pathlib import Path, PurePosixPath

import cattr
import pendulum

CONVERTER = cattr.Converter()

# Customize converter for paths
CONVERTER.register_structure_hook(Path, lambda p, _: Path(p))
CONVERTER.register_unstructure_hook(Path, operator.methodcaller('as_posix'))

CONVERTER.register_structure_hook(PurePosixPath, lambda p, _: PurePosixPath(p))
CONVERTER.register_unstructure_hook(
        PurePosixPath, operator.methodcaller('as_posix'))


# Customize converter for timestamps
CONVERTER.register_structure_hook(
        pendulum.DateTime,
        lambda ts, _: cast(pendulum.DateTime, pendulum.parse(ts)))
CONVERTER.register_unstructure_hook(
        pendulum.DateTime, operator.methodcaller('to_rfc3339_string'))
