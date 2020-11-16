"""Smoke tests."""
from typing import Any, Callable

import functools

from pathlib import Path
from subprocess import run, CompletedProcess

import pytest
pytestmark = pytest.mark.smoke


def twice(f: Callable[..., None]) -> Callable[..., None]:
    """Decorator to run a test twice with the same arguments.

    Can be used to test caching works correctly. Note that the wrapped function
    cannot return anything.
    """
    @functools.wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        f(*args, **kwargs)
        f(*args, **kwargs)

    return wrapper


def run_py(path: Path, *args: str) -> 'CompletedProcess[bytes]':
    return run(
            ['python', 'main.py', f'--output={path}', *args],
            capture_output=True)


def test_help(tmp_path: Path) -> None:
    proc = run_py(tmp_path, '--help')

    assert not proc.returncode
    assert b'Usage:' in proc.stdout


def test_no_command(tmp_path: Path) -> None:
    proc = run_py(tmp_path, '--dataset=smoke_test')

    assert proc.returncode
    assert b'Error: Missing command' in proc.stderr


def test_discover_help(tmp_path: Path) -> None:
    proc = run_py(tmp_path, 'discover', '--help')

    assert not proc.returncode
    assert b'Usage: ' in proc.stdout


@twice
def test_discover(tmp_path: Path) -> None:  # type: ignore[misc]
    proc = run_py(tmp_path, '--dataset=smoke_tests', 'discover', '--count=20')

    assert not proc.returncode


@twice
def test_clone(tmp_path: Path) -> None:  # type: ignore[misc]
    proc = run_py(
            tmp_path, '--dataset=smoke_tests', '--progress', 'discover',
            '--count=2', 'clone')

    assert not proc.returncode
